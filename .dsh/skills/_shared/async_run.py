#!/usr/bin/env python3
"""async_run.py — detached runner with buffered output for long skill calls (1C etc.).

Usage:
  python async_run.py start [--cwd DIR] -- <command> [args...]
  python async_run.py status <run_id>
  python async_run.py tail <run_id> [-n 40]
  python async_run.py list [-n 10]
  python async_run.py wait <run_id> [--timeout 300]

Each run gets a directory under %TEMP%\\cc_async\\<run_id> with:
  cmd.txt      — exact command line
  pid          — child PID
  out.log      — buffered stdout (grows while running)
  err.log      — buffered stderr
  exit.code    — written when the command finishes

The launcher returns immediately; poll with status/tail.
"""

import argparse
import ctypes
import os
import subprocess
import sys
import time
import uuid

BASE = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or os.environ.get("TMP") or ".",
    "cc_async",
)

RUN_PY = """import os, subprocess, sys
d = os.path.dirname(os.path.abspath(__file__))
out = open(os.path.join(d, 'out.log'), 'wb')
err = open(os.path.join(d, 'err.log'), 'wb')
rc = subprocess.call(sys.argv[1:], stdout=out, stderr=err, stdin=subprocess.DEVNULL)
out.close(); err.close()
with open(os.path.join(d, 'exit.code'), 'w') as f:
    f.write(str(rc))
"""


def _flags():
    if os.name != "nt":
        return 0
    return 0x00000008 | 0x00000200 | 0x08000000 | 0x01000000  # DETACHED | NEW_GROUP | NO_WINDOW | BREAKAWAY_FROM_JOB


def _alive(pid):
    if not pid:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    h = ctypes.windll.kernel32.OpenProcess(0x00100000, False, int(pid))  # SYNCHRONIZE
    if h:
        ctypes.windll.kernel32.CloseHandle(h)
        return True
    return False


def _base_signature(argv):
    """Extract infobase signature from skill arguments: server/ref or path."""
    server = ref = path = ""
    for i, token in enumerate(argv):
        low = token.lower()
        nxt = argv[i + 1] if i + 1 < len(argv) else ""
        if low == "-infobaseserver":
            server = nxt
        elif low == "-infobaseref":
            ref = nxt
        elif low == "-infobasepath":
            path = nxt
    if server and ref:
        return "server:" + server.lower() + "/" + ref.lower()
    if path:
        return "path:" + path.lower()
    return ""


def _active_runs():
    result = []
    if not os.path.isdir(BASE):
        return result
    for run_id in os.listdir(BASE):
        run_dir = os.path.join(BASE, run_id)
        if not os.path.isdir(run_dir):
            continue
        if os.path.isfile(os.path.join(run_dir, "exit.code")):
            continue
        pid = _read(os.path.join(run_dir, "pid")).strip()
        if not pid or not _alive(pid):
            continue
        meta = _read(os.path.join(run_dir, "meta.json"))
        base_sig = ""
        try:
            import json as _json
            base_sig = (_json.loads(meta) or {}).get("base", "")
        except Exception:
            pass
        result.append((run_id, pid, base_sig, run_dir))
    return result


def cmd_start(argv):
    if not argv:
        print("ОШИБКА: пустая команда")
        return 1
    import shutil
    exe = argv[0]
    if exe.lower() in ("python", "python3", "py"):
        exe = sys.executable
    else:
        exe = shutil.which(exe) or exe
    argv = [exe] + list(argv[1:])

    base_sig = _base_signature(argv[1:])
    duplicates = [r for r in _active_runs() if base_sig and r[2] == base_sig]
    if duplicates:
        for run_id, pid, _sig, run_dir in duplicates:
            print("ВНИМАНИЕ: по этой базе уже выполняется RUN_ID %s (pid %s, %s)" % (run_id, pid, run_dir))
        if os.environ.get("CC_ASYNC_NO_DUP") == "1":
            print("Запуск отменён (CC_ASYNC_NO_DUP=1).")
            return 3
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    run_dir = os.path.join(BASE, run_id)
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, "cmd.txt"), "w", encoding="utf-8") as f:
        f.write(" ".join(argv))
    runner = os.path.join(run_dir, "_run.py")
    with open(runner, "w", encoding="utf-8") as f:
        f.write(RUN_PY)
    proc = None
    try:
        proc = subprocess.Popen(
            [sys.executable, "-u", runner] + argv,
            cwd=os.getcwd(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_flags(),
            close_fds=True,
        )
    except OSError:
        proc = subprocess.Popen(
            [sys.executable, "-u", runner] + argv,
            cwd=os.getcwd(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=0x00000008 | 0x00000200 | 0x08000000,
            close_fds=True,
        )
    with open(os.path.join(run_dir, "pid"), "w") as f:
        f.write(str(proc.pid))
    try:
        import json as _json
        with open(os.path.join(run_dir, "meta.json"), "w", encoding="utf-8") as f:
            _json.dump({
                "run_id": run_id,
                "pid": proc.pid,
                "started": time.strftime("%Y-%m-%d %H:%M:%S"),
                "base": base_sig,
                "cwd": os.getcwd(),
                "cmd": " ".join(argv),
            }, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    print("RUN_ID: " + run_id)
    print("DIR: " + run_dir)
    print("OUT: " + os.path.join(run_dir, "out.log"))
    return 0


def _read(path, default=""):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return default


def _state(run_id):
    run_dir = os.path.join(BASE, run_id)
    if not os.path.isdir(run_dir):
        return None
    code = _read(os.path.join(run_dir, "exit.code")).strip()
    pid = _read(os.path.join(run_dir, "pid")).strip()
    if code:
        return {"state": "done", "exit": code, "pid": pid, "dir": run_dir}
    if pid and _alive(pid):
        return {"state": "running", "exit": None, "pid": pid, "dir": run_dir}
    return {"state": "dead", "exit": None, "pid": pid, "dir": run_dir}


def cmd_status(run_id, tail_lines):
    st = _state(run_id)
    if not st:
        print("ОШИБКА: run не найден: " + run_id)
        return 1
    print("RUN_ID: %s\nSTATE: %s\nPID: %s\nDIR: %s" % (run_id, st["state"], st["pid"], st["dir"]))
    if st["exit"] is not None:
        print("EXIT: " + st["exit"])
    out = _read(os.path.join(st["dir"], "out.log"))
    err = _read(os.path.join(st["dir"], "err.log"))
    if out.strip():
        lines = out.rstrip().splitlines()
        print("--- out.log (last %d) ---" % tail_lines)
        print("\n".join(lines[-tail_lines:]))
    if err.strip():
        lines = err.rstrip().splitlines()
        print("--- err.log (last %d) ---" % tail_lines)
        print("\n".join(lines[-tail_lines:]))
    return 0


def cmd_list(count):
    if not os.path.isdir(BASE):
        print("(пусто)")
        return 0
    ids = sorted(os.listdir(BASE), reverse=True)[:count]
    for rid in ids:
        st = _state(rid)
        if st:
            print("%s  %-8s exit=%s" % (rid, st["state"], st["exit"] or "-"))
    return 0


def cmd_wait(run_id, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = _state(run_id)
        if not st:
            print("ОШИБКА: run не найден: " + run_id)
            return 1
        if st["state"] in ("done", "dead"):
            return cmd_status(run_id, 40)
        time.sleep(2)
    print("ТАЙМАУТ ожидания")
    return cmd_status(run_id, 40)


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(description="Detached runner with buffered output")
    parser.add_argument("action", choices=["start", "status", "tail", "list", "wait"])
    parser.add_argument("run_id", nargs="?")
    parser.add_argument("-n", type=int, default=20)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--cwd", default=None)
    parser.add_argument("rest", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    if args.action == "start":
        raw = list(sys.argv[2:])
        if raw and raw[0] == "--":
            raw = raw[1:]
        if args.cwd:
            os.chdir(args.cwd)
        return cmd_start(raw)
    rid = sys.argv[2] if len(sys.argv) > 2 else ""
    if args.action in ("status", "tail"):
        if not rid:
            print("ОШИБКА: не указан run_id")
            return 1
        return cmd_status(rid, args.n)
    if args.action == "wait":
        if not rid:
            print("ОШИБКА: не указан run_id")
            return 1
        return cmd_wait(rid, args.timeout)
    return cmd_list(args.n)


if __name__ == "__main__":
    sys.exit(main())
