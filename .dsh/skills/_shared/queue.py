#!/usr/bin/env python3
"""queue.py — очередь операций 1С по базам (cc_queue).

Запрос = каталог %LOCALAPPDATA%\\cc_queue\\<id>:
  request.json  — что запускать (script/args/cwd/base/expect/priority/deadline)
  state.json    — состояние: pending|waiting-lock|running|done|failed|blocked-version|expired|cancelled
  out.log/err.log, exit.code — результат запуска

Воркер (один на машину, lock-файл):
  • проверяет профиль базы (_store\\bases\\<ref>.json): ожидаемая конфигурация/версия;
  • ждёт освобождения базы (активные cc_async-запуски, Конфигуратор, блокировки в логах);
  • исполняет скрипт с CC_SYNC=1, при блокировке — retry с backoff;
  • при превышении attempts/deadline — failed/expired.

CLI:
  python queue.py add -Script db-update.py -Args="-InfoBaseRef test6 -Extension Корада" -Base test6 [-Priority 5]
  python queue.py worker        # цикл (Ctrl+C — стоп)
  python queue.py once          # один проход
  python queue.py status <id> | list [-n 20] | cancel <id>
  python queue.py profile -Ref test6 -Config "<Имя>" -Version 2.5.17.219 [-Extensions "Корада=1.0.3"]
"""

import argparse
import ctypes
import datetime
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid

QUEUE = os.path.join(os.environ.get("LOCALAPPDATA", ""), "cc_queue")
ASYNC = os.path.join(os.environ.get("LOCALAPPDATA", ""), "cc_async")
SKILLS = r"C:\Users\Grishin1c\.config\opencode\skills"
STORE = r"E:\Grishin\Code\_store"
BASES = os.path.join(STORE, "bases")

LOCK_PATTERNS = ("исключительной блокировки", "блокировки информационной базы",
                 "фоновое задание", "ошибка блокировки")

DEFAULT_MAX_ATTEMPTS = 8
BACKOFF_MIN = (1, 2, 5, 10, 15, 30, 30, 30)


def now_ts():
    return time.time()


def fmt(ts):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def req_dir(qid):
    return os.path.join(QUEUE, qid)


def load_req(qid):
    d = req_dir(qid)
    req = read_json(os.path.join(d, "request.json"), None)
    st = read_json(os.path.join(d, "state.json"), {})
    return req, st


def save_state(qid, **kw):
    d = req_dir(qid)
    st = read_json(os.path.join(d, "state.json"), {})
    st.update(kw)
    st["updated"] = fmt(now_ts())
    write_json(os.path.join(d, "state.json"), st)
    return st


def pid_alive(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    h = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)
    if h:
        ctypes.windll.kernel32.CloseHandle(h)
        return True
    return False


def base_sig_from_args(args):
    server = ref = ""
    for i, token in enumerate(args):
        low = token.lower()
        nxt = args[i + 1] if i + 1 < len(args) else ""
        if low == "-infobaseserver":
            server = nxt
        elif low == "-infobaseref":
            ref = nxt
    return "server:%s/%s" % (server.lower(), ref.lower()) if server and ref else ""


def active_async_for(base_ref):
    if not base_ref or not os.path.isdir(ASYNC):
        return []
    hits = []
    for d in os.listdir(ASYNC):
        p = os.path.join(ASYNC, d)
        if not os.path.isdir(p) or os.path.isfile(os.path.join(p, "exit.code")):
            continue
        pid = ""
        try:
            pid = open(os.path.join(p, "pid")).read().strip()
        except OSError:
            continue
        if not pid_alive(pid):
            continue
        meta = read_json(os.path.join(p, "meta.json"), {})
        sig = meta.get("base", "")
        if sig.endswith("/" + base_ref.lower()):
            hits.append(d)
    return hits


def designers_cache():
    ps = ("$p = Get-CimInstance Win32_Process -Filter \"Name='1cv8.exe'\" -ErrorAction SilentlyContinue; "
          "$p | Where-Object { $_.CommandLine -match 'DESIGNER' } | ForEach-Object { $_.CommandLine }")
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=90,
                           encoding="cp866", errors="replace")
        return (r.stdout or "").lower()
    except Exception:
        return ""


def base_profile(ref):
    return read_json(os.path.join(BASES, ref + ".json"), {})


def profile_path(ref):
    return os.path.join(BASES, ref + ".json")


def base_busy_reason(ref, design_lines):
    runs = active_async_for(ref)
    if runs:
        return "активные async-запуски: " + ", ".join(runs[:3])
    if ref.lower() in design_lines:
        return "запущен Конфигуратор"
    return ""


def resolve_script(script):
    if os.path.isabs(script):
        return script
    cand = os.path.join(SKILLS, script)
    if os.path.isfile(cand):
        return cand
    for dp, _dn, fn in os.walk(SKILLS):
        if script in fn:
            return os.path.join(dp, script)
    return cand


def log_has_lock(path):
    try:
        data = io.open(path, encoding="utf-8", errors="replace").read().lower()
    except OSError:
        return False
    return any(pat in data for pat in LOCK_PATTERNS)


def run_request(qid, req):
    d = req_dir(qid)
    out = open(os.path.join(d, "out.log"), "wb")
    err = open(os.path.join(d, "err.log"), "wb")
    env = dict(os.environ)
    env["CC_SYNC"] = "1"
    script = resolve_script(req["script"])
    cmd = [sys.executable, "-u", script] + [str(a) for a in (req.get("args") or [])]
    timeout = int(req.get("deadline_min", 60)) * 60
    t0 = now_ts()
    try:
        rc = subprocess.call(cmd, cwd=req.get("cwd") or os.getcwd(),
                             stdout=out, stderr=err, stdin=subprocess.DEVNULL,
                             env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        rc = -1
    finally:
        out.close()
        err.close()
    with open(os.path.join(d, "exit.code"), "w") as f:
        f.write(str(rc))
    return rc, now_ts() - t0


def version_mismatch(req):
    ref = str(req.get("base") or "")
    expect = (req.get("expect") or {})
    if not ref or not expect:
        return ""
    prof = base_profile(ref)
    if not prof.get("version") and not prof.get("extensions"):
        return ""  # профиль не ведётся — проверку пропускаем
    want = str(expect.get("config") or "")
    have = str(prof.get("version") or "")
    if want and have and want != have:
        return "конфигурация базы %s: %s, ожидалась %s" % (ref, have, want)
    for ext, ver in (expect.get("extensions") or {}).items():
        have_ext = (prof.get("extensions") or {}).get(ext, "")
        if have_ext and str(ver) != str(have_ext):
            return "расширение %s в базе %s: %s, ожидалось %s" % (ext, ref, have_ext, ver)
    return ""


def process_one(qid, design_lines_fn):
    req, st = load_req(qid)
    if not req:
        save_state(qid, state="failed", last_error="request.json не найден")
        return False
    if st.get("state") in ("done", "failed", "cancelled", "blocked-version", "expired"):
        return False
    if st.get("next_try") and float(st["next_try"]) > now_ts():
        return False

    mismatch = version_mismatch(req)
    if mismatch:
        save_state(qid, state="blocked-version", last_error=mismatch)
        return True

    ref = str(req.get("base") or "")
    reason = base_busy_reason(ref, design_lines_fn()) if ref else ""
    if reason:
        attempts = int(st.get("attempts") or 0)
        wait = BACKOFF_MIN[min(attempts, len(BACKOFF_MIN) - 1)] * 60
        save_state(qid, state="waiting-lock", last_error=reason, next_try=now_ts() + wait)
        return True

    save_state(qid, state="running", started=fmt(now_ts()), next_try=None)
    rc, dur = run_request(qid, req)
    if rc == 0:
        save_state(qid, state="done", exit=rc, elapsed_sec=round(dur, 1), last_error="")
        return True

    locked = log_has_lock(os.path.join(req_dir(qid), "out.log")) or \
        log_has_lock(os.path.join(req_dir(qid), "err.log"))
    attempts = int(st.get("attempts") or 0) + 1
    max_attempts = int(req.get("max_attempts") or DEFAULT_MAX_ATTEMPTS)
    if locked and attempts < max_attempts:
        wait = BACKOFF_MIN[min(attempts, len(BACKOFF_MIN) - 1)] * 60
        save_state(qid, state="waiting-lock", attempts=attempts, exit=rc,
                   last_error="блокировка базы", next_try=now_ts() + wait)
        return True
    if locked:
        save_state(qid, state="failed", attempts=attempts, exit=rc,
                   last_error="база оставалась занятой, попытки исчерпаны", elapsed_sec=round(dur, 1))
        return True
    save_state(qid, state="failed", attempts=attempts, exit=rc,
               last_error="код возврата %d" % rc, elapsed_sec=round(dur, 1))
    return True


def queue_ids():
    if not os.path.isdir(QUEUE):
        return []
    return [d for d in os.listdir(QUEUE) if os.path.isfile(os.path.join(QUEUE, d, "request.json"))]


def sorted_pending():
    items = []
    for qid in queue_ids():
        req, st = load_req(qid)
        if not req:
            continue
        if st.get("state") in ("pending", "waiting-lock"):
            items.append((int(req.get("priority") or 5), req.get("created") or "", qid))
    items.sort()
    return [qid for _p, _c, qid in items]


def worker_loop(interval=5):
    lock = os.path.join(QUEUE, "worker.lock")
    os.makedirs(QUEUE, exist_ok=True)
    if os.path.isfile(lock):
        try:
            pid = int(open(lock).read().strip() or 0)
        except (OSError, ValueError):
            pid = 0
        if pid and pid_alive(pid):
            print("Воркер уже запущен (pid %d)" % pid)
            return 1
    with open(lock, "w") as f:
        f.write(str(os.getpid()))

    cache = {"t": 0.0, "lines": ""}

    def design_lines():
        if now_ts() - cache["t"] > 30:
            cache["lines"] = designers_cache()
            cache["t"] = now_ts()
        return cache["lines"]

    print("queue worker started, pid=%d, dir=%s" % (os.getpid(), QUEUE))
    try:
        while True:
            progressed = False
            for qid in sorted_pending():
                if process_one(qid, design_lines):
                    progressed = True
                    print("%s  %s -> %s" % (fmt(now_ts()), qid,
                          read_json(os.path.join(req_dir(qid), "state.json"), {}).get("state")))
            if not progressed:
                time.sleep(interval)
    except KeyboardInterrupt:
        print("worker stopped")
        return 0
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass


def cmd_add(args):
    os.makedirs(QUEUE, exist_ok=True)
    qid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    d = req_dir(qid)
    os.makedirs(d, exist_ok=True)
    req = {
        "id": qid,
        "created": fmt(now_ts()),
        "script": args.Script,
        "args": args.Args.split() if isinstance(args.Args, str) else (args.Args or []),
        "cwd": args.Cwd or os.getcwd(),
        "base": args.Base or "",
        "priority": int(args.Priority or 5),
        "deadline_min": int(args.Deadline or 60),
        "max_attempts": int(args.MaxAttempts or DEFAULT_MAX_ATTEMPTS),
        "expect": {},
    }
    if args.ExpectConfig or args.ExpectExtensions:
        req["expect"] = {"config": args.ExpectConfig or "",
                         "extensions": dict(pair.split("=", 1) for pair in (args.ExpectExtensions or "").split(",") if "=" in pair)}
    write_json(os.path.join(d, "request.json"), req)
    save_state(qid, state="pending", attempts=0, last_error="", next_try=None)
    print("QUEUE_ID: %s" % qid)
    if not args.NoWorker:
        ensure_worker()
    return 0


def ensure_worker():
    lock = os.path.join(QUEUE, "worker.lock")
    if os.path.isfile(lock):
        try:
            pid = int(open(lock).read().strip() or 0)
        except (OSError, ValueError):
            pid = 0
        if pid and pid_alive(pid):
            return
    flags = 0x00000008 | 0x00000200 | 0x08000000 | 0x01000000
    subprocess.Popen([sys.executable, "-u", os.path.abspath(__file__), "worker"],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, creationflags=flags, close_fds=True)


def cmd_status(args):
    qid = args.id
    req, st = load_req(qid)
    if not req:
        print("не найден запрос: " + qid)
        return 1
    print(json.dumps({"request": req, "state": st}, ensure_ascii=False, indent=2))
    return 0


def cmd_list(args):
    rows = []
    for qid in queue_ids():
        req, st = load_req(qid)
        if req:
            rows.append((req.get("created") or "", qid, st.get("state", "?"),
                         req.get("base", ""), (req.get("script") or "").split("\\")[-1].split("/")[-1],
                         st.get("last_error", "")))
    rows.sort(reverse=True)
    for r in rows[: int(args.n or 20)]:
        print("%s  %-20s %-14s %-8s %-22s %s" % (r[0], r[1], r[2], r[3], r[4], (r[5] or "")[:60]))
    return 0


def cmd_cancel(args):
    req, st = load_req(args.id)
    if not req:
        print("не найден: " + args.id)
        return 1
    if st.get("state") in ("done", "failed", "cancelled"):
        print("уже завершён: " + st.get("state"))
        return 0
    save_state(args.id, state="cancelled", last_error="отменён пользователем")
    print("cancelled: " + args.id)
    return 0


def cmd_profile(args):
    os.makedirs(BASES, exist_ok=True)
    p = profile_path(args.Ref)
    prof = read_json(p, {})
    prof["ref"] = args.Ref
    if args.Config is not None:
        prof["config"] = args.Config
    if args.Version is not None:
        prof["version"] = args.Version
    if args.Extensions is not None:
        prof["extensions"] = dict(pair.split("=", 1) for pair in args.Extensions.split(",") if "=" in pair)
    prof["updated"] = fmt(now_ts())
    write_json(p, prof)
    print("profile: " + p)
    return 0


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="cc_queue — очередь операций по базам")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add")
    p_add.add_argument("-Script", required=True)
    p_add.add_argument("-Args", default="")
    p_add.add_argument("-Cwd", default="")
    p_add.add_argument("-Base", default="")
    p_add.add_argument("-Priority", default="5")
    p_add.add_argument("-Deadline", default="60")
    p_add.add_argument("-MaxAttempts", default=str(DEFAULT_MAX_ATTEMPTS))
    p_add.add_argument("-ExpectConfig", default="")
    p_add.add_argument("-ExpectExtensions", default="")
    p_add.add_argument("-NoWorker", action="store_true")

    sub.add_parser("worker")
    sub.add_parser("once")

    p_st = sub.add_parser("status")
    p_st.add_argument("id")
    p_ls = sub.add_parser("list")
    p_ls.add_argument("-n", default="20")
    p_cn = sub.add_parser("cancel")
    p_cn.add_argument("id")

    p_pr = sub.add_parser("profile")
    p_pr.add_argument("-Ref", required=True)
    p_pr.add_argument("-Config", default=None)
    p_pr.add_argument("-Version", default=None)
    p_pr.add_argument("-Extensions", default=None)

    args = ap.parse_args()
    if args.cmd == "add":
        return cmd_add(args)
    if args.cmd == "worker":
        return worker_loop()
    if args.cmd == "once":
        os.makedirs(QUEUE, exist_ok=True)
        design_lines = designers_cache()
        for qid in sorted_pending():
            process_one(qid, lambda: design_lines)
        return 0
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "list":
        return cmd_list(args)
    if args.cmd == "cancel":
        return cmd_cancel(args)
    if args.cmd == "profile":
        return cmd_profile(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
