#!/usr/bin/env python3
"""bench.py — measure async vs sync vs raw-platform execution.

Modes:
  async  — запуск навыка через async_run (мгновенный возврат), затем ожидание фонового процесса
  sync   — тот же вызов навыка с CC_SYNC=1 (ожидание целиком)
  raw    — прямой вызов платформы (без навыка), если передан --raw "<команда>"

Usage:
  python bench.py [--raw "<1cv8 command>"] [--label NAME] -- <skill cmd...>

Metrics:
  response_s — время до возврата управления (то, что «висит» у агента)
  total_s    — полное время выполнения операции
"""

import argparse
import os
import re
import shlex
import subprocess
import sys
import time

ASYNC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "async_run.py")
TEMP = os.environ.get("TEMP") or os.environ.get("TMP") or "."


def split_win(cmd):
    try:
        return shlex.split(cmd, posix=False) if False else _split(cmd)
    except Exception:
        return _split(cmd)


def _split(text):
    out, cur, q = [], "", None
    for ch in text:
        if q:
            if ch == q:
                q = None
            else:
                cur += ch
        elif ch in "\"'":
            q = ch
        elif ch.isspace():
            if cur:
                out.append(cur)
                cur = ""
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out


def run_async(cmd):
    t0 = time.time()
    env = dict(os.environ)
    env["CC_SYNC"] = "1"
    r = subprocess.run([sys.executable, ASYNC, "start", "--"] + cmd,
                       capture_output=True, text=True, timeout=60,
                       encoding="utf-8", errors="replace", env=env)
    t_resp = time.time() - t0
    m = re.search(r"RUN_ID:\s*(\S+)", r.stdout or "")
    d = re.search(r"DIR:\s*(.+?)\s*$", r.stdout or "", re.MULTILINE)
    if not m or not d:
        return None
    run_dir = d.group(1).strip()
    exit_file = os.path.join(run_dir, "exit.code")
    while not os.path.isfile(exit_file):
        time.sleep(0.5)
    code = ""
    try:
        code = open(exit_file).read().strip()
    except OSError:
        pass
    return t_resp, time.time() - t0, code, run_dir


def run_sync(cmd):
    t0 = time.time()
    env = dict(os.environ)
    env["CC_SYNC"] = "1"
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    return time.time() - t0, r.returncode, (r.stdout or "") + (r.stderr or "")


def run_raw(cmd):
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return time.time() - t0, r.returncode, (r.stdout or "") + (r.stderr or "")


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="async vs sync vs raw benchmark")
    ap.add_argument("-Label", default="operation")
    ap.add_argument("-Raw", default="")
    ap.add_argument("rest", nargs=argparse.REMAINDER)
    args = ap.parse_args()

    cmd = list(args.rest)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("ОШИБКА: не передана команда навыка")
        return 1

    rows = []

    res = run_async(cmd)
    if res is None:
        print("ОШИБКА: async_run не вернул RUN_ID")
        return 1
    rows.append(("async", res[0], res[1], res[2]))

    t_sync, rc_sync, out_sync = run_sync(cmd)
    rows.append(("sync", t_sync, t_sync, str(rc_sync)))
    try:
        with open(os.path.join(TEMP, "bench_sync.log"), "w", encoding="utf-8") as f:
            f.write(out_sync)
    except OSError:
        pass

    if args.Raw:
        raw_cmd = split_win(args.Raw)
        t_raw, rc_raw, out_raw = run_raw(raw_cmd)
        rows.append(("raw", t_raw, t_raw, str(rc_raw)))
        try:
            with open(os.path.join(TEMP, "bench_raw.log"), "w", encoding="utf-8") as f:
                f.write(out_raw)
        except OSError:
            pass
    else:
        raw_cmd = None

    print()
    print("=== Замер: %s ===" % args.Label)
    print("mode     response_s   total_s   exit")
    for name, resp, total, code in rows:
        print("%-8s %10.2f  %8.2f   %s" % (name, resp, total, code))

    sync_total = rows[1][2]
    async_resp = rows[0][1]
    if raw_cmd:
        raw_total = rows[2][2]
        print("Навык добавляет к платформе: %.2f с" % (sync_total - raw_total))
    if async_resp > 0:
        print("Выигрыш async по отзывчивости: %.1fx (%.2f с вместо %.2f с)" %
              (sync_total / async_resp, async_resp, sync_total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
