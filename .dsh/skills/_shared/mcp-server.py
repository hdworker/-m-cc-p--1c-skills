#!/usr/bin/env python3
"""cc-mcp — MCP-сервер (stdio) для запуска скилл-команд без ожидания оболочки.

Инструменты:
  run_start(script, args?, cwd?)  — detached-запуск .py из skills, сразу run_id
  run_status(run_id)              — состояние/exit/длительность/последняя строка
  run_tail(run_id, offset?)       — новые байты out.log с указанного offset
  run_wait(run_id, timeout_sec?)  — подождать завершения (ограниченно)
  run_kill(run_id)                — TerminateProcess по pid
  run_list(limit?)                — последние запуски

Транспорт: newline-delimited JSON-RPC 2.0 по stdin/stdout (MCP stdio).
Данные — %LOCALAPPDATA%\\cc_async (совместимо с async_run.py и cc-status.py).
Лог сервера — %LOCALAPPDATA%\\cc_async\\mcp-server.log (stdout не засоряется).
"""

import ctypes
import io
import json
import os
import re
import sys
import time
import uuid

BASE = os.path.join(os.environ.get("LOCALAPPDATA", ""), "cc_async")
SKILLS = r"C:\Users\Grishin1c\.config\opencode\skills"
PROTO = "2024-11-05"
ALLOW_ANY = os.environ.get("CC_MCP_ALLOW_ANY") == "1"
ALLOW_TEMP = os.environ.get("CC_MCP_ALLOW_TEMP", "1") == "1"
TEMP_ROOT = os.path.realpath(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Temp")).lower()

RUN_PY = """import os, subprocess, sys
d = os.path.dirname(os.path.abspath(__file__))
out = open(os.path.join(d, 'out.log'), 'wb')
err = open(os.path.join(d, 'err.log'), 'wb')
rc = subprocess.call(sys.argv[1:], stdout=out, stderr=err, stdin=subprocess.DEVNULL)
out.close(); err.close()
with open(os.path.join(d, 'exit.code'), 'w') as f:
    f.write(str(rc))
"""


def log(msg):
    try:
        os.makedirs(BASE, exist_ok=True)
        with open(os.path.join(BASE, "mcp-server.log"), "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    except OSError:
        pass


def flags():
    if os.name != "nt":
        return 0
    return 0x00000008 | 0x00000200 | 0x08000000 | 0x01000000


def alive(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    h = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)
    if h:
        ctypes.windll.kernel32.CloseHandle(h)
        return True
    return False


def kill(pid):
    try:
        h = ctypes.windll.kernel32.OpenProcess(0x0001, False, int(pid))
        if not h:
            return False
        ok = ctypes.windll.kernel32.TerminateProcess(h, 1)
        ctypes.windll.kernel32.CloseHandle(h)
        return bool(ok)
    except Exception:
        return False


def read(path, limit=None):
    try:
        with open(path, "rb") as f:
            if limit:
                f.seek(max(0, os.path.getsize(path) - limit))
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def mask(cmd):
    cmd = re.sub(r"(-Password\s+)\S+", r"\1***", cmd, flags=re.IGNORECASE)
    cmd = re.sub(r"(--password[= ])\S+", r"\1***", cmd, flags=re.IGNORECASE)
    return cmd


def base_signature(args):
    server = ref = path = ""
    for i, token in enumerate(args):
        low = token.lower()
        nxt = args[i + 1] if i + 1 < len(args) else ""
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


def run_dir(run_id):
    return os.path.join(BASE, run_id)


def run_state(run_id):
    d = run_dir(run_id)
    if not os.path.isdir(d):
        return None
    ec = os.path.join(d, "exit.code")
    pid = read(os.path.join(d, "pid")).strip()
    start = os.path.getmtime(d)
    meta = {}
    try:
        meta = json.loads(read(os.path.join(d, "meta.json")) or "{}")
    except Exception:
        pass
    try:
        start = time.mktime(time.strptime(meta.get("started", ""), "%Y-%m-%d %H:%M:%S"))
    except (ValueError, TypeError):
        pass
    if os.path.isfile(ec):
        code = read(ec).strip()
        end = os.path.getmtime(ec)
        out = read(os.path.join(d, "out.log"), 8192)
        err = read(os.path.join(d, "err.log"), 8192)
        lines = [ln.strip() for ln in (out + err).splitlines() if ln.strip()]
        return {"run_id": run_id, "state": "done" if code == "0" else "fail",
                "exit": code, "elapsed_sec": round(end - start, 1),
                "pid": pid, "dir": d, "base": meta.get("base", ""),
                "cwd": meta.get("cwd", ""), "cmd": mask(meta.get("cmd", "")),
                "last": lines[-1] if lines else "", "out": os.path.join(d, "out.log")}
    return {"run_id": run_id, "state": "run" if alive(pid) else "stale",
            "exit": None, "elapsed_sec": round(time.time() - start, 1),
            "pid": pid, "dir": d, "base": meta.get("base", ""),
            "cwd": meta.get("cwd", ""), "cmd": mask(meta.get("cmd", "")),
            "last": "", "out": os.path.join(d, "out.log")}


TOOLS = [
    {"name": "run_start",
     "description": "Запустить скилл-скрипт detached; сразу вернуть run_id (без ожидания процесса).",
     "inputSchema": {"type": "object", "properties": {
         "script": {"type": "string", "description": "имя/путь .py из skills (например db-update.py или полный путь)"},
         "args": {"type": "array", "items": {"type": "string"}, "description": "аргументы скрипта"},
         "cwd": {"type": "string", "description": "рабочий каталог (по умолчанию текущий проекта)"}},
         "required": ["script"]}},
    {"name": "run_status",
     "description": "Состояние запуска: state/exit/длительность/последняя строка лога.",
     "inputSchema": {"type": "object", "properties": {"run_id": {"type": "string"}},
                     "required": ["run_id"]}},
    {"name": "run_tail",
     "description": "Новые байты out.log начиная с offset (хвост буфера).",
     "inputSchema": {"type": "object", "properties": {
         "run_id": {"type": "string"}, "offset": {"type": "integer"}}, "required": ["run_id"]}},
    {"name": "run_wait",
     "description": "Дождаться завершения запуска (ограниченный таймаут).",
     "inputSchema": {"type": "object", "properties": {
         "run_id": {"type": "string"}, "timeout_sec": {"type": "integer"}}, "required": ["run_id"]}},
    {"name": "run_kill",
     "description": "Прервать запуск (TerminateProcess).",
     "inputSchema": {"type": "object", "properties": {"run_id": {"type": "string"}},
                     "required": ["run_id"]}},
    {"name": "run_list",
     "description": "Последние запуски (id/state/base/cwd/skill).",
     "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer"}}}},
    {"name": "queue_submit",
     "description": "Положить операцию в очередь по базе (выполнится, когда база освободится; версия базы проверяется).",
     "inputSchema": {"type": "object", "properties": {
         "script": {"type": "string"}, "args": {"type": "array", "items": {"type": "string"}},
         "cwd": {"type": "string"}, "base": {"type": "string"},
         "priority": {"type": "integer"},
         "expect_config": {"type": "string"},
         "expect_extensions": {"type": "object"},
         "deadline_min": {"type": "integer"},
         "max_attempts": {"type": "integer"}},
         "required": ["script"]}},
    {"name": "queue_status",
     "description": "Состояние запроса очереди (pending/waiting-lock/running/done/failed/blocked-version).",
     "inputSchema": {"type": "object", "properties": {"queue_id": {"type": "string"}},
                     "required": ["queue_id"]}},
    {"name": "queue_list",
     "description": "Список запросов очереди.",
     "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer"}}}},
    {"name": "queue_cancel",
     "description": "Отменить запрос очереди.",
     "inputSchema": {"type": "object", "properties": {"queue_id": {"type": "string"}},
                     "required": ["queue_id"]}},
]


def resolve_script(script):
    if os.path.isabs(script):
        p = script
    else:
        cand = os.path.join(SKILLS, script)
        if os.path.isfile(cand):
            p = cand
        else:
            hits = []
            for dp, _dn, fn in os.walk(SKILLS):
                if script in fn:
                    hits.append(os.path.join(dp, script))
            p = hits[0] if hits else cand
    p = os.path.abspath(p)
    if not os.path.isfile(p) or not p.lower().endswith(".py"):
        raise RuntimeError("скрипт не найден или не .py: " + script)
    low = os.path.realpath(p).lower()
    skills_root = os.path.realpath(SKILLS).lower()
    allowed = low.startswith(skills_root)
    if not allowed and ALLOW_TEMP:
        allowed = low.startswith(TEMP_ROOT) and (os.sep + "opencode" + os.sep) in low
    if not (ALLOW_ANY or allowed):
        raise RuntimeError("разрешены скрипты из skills и temp-opencode (или CC_MCP_ALLOW_ANY=1)")
    return p


def tool_run_start(a):
    script = resolve_script(str(a.get("script", "")))
    args = [str(x) for x in (a.get("args") or [])]
    cwd = a.get("cwd") or os.getcwd()
    os.makedirs(BASE, exist_ok=True)
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    d = run_dir(run_id)
    os.makedirs(d, exist_ok=True)
    runner = os.path.join(d, "_run.py")
    with open(runner, "w", encoding="utf-8") as f:
        f.write(RUN_PY)
    cmd = [sys.executable, "-u", runner, sys.executable, "-u", script] + args
    env = dict(os.environ)
    env["CC_SYNC"] = "1"
    p = None
    try:
        import subprocess
        p = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=flags(), close_fds=True, env=env)
    except OSError as e:
        raise RuntimeError("не удалось запустить: %s" % e)
    with open(os.path.join(d, "pid"), "w") as f:
        f.write(str(p.pid))
    meta = {"run_id": run_id, "pid": p.pid,
            "started": time.strftime("%Y-%m-%d %H:%M:%S"),
            "base": base_signature(args), "cwd": cwd,
            "cmd": mask(" ".join([script] + args))}
    with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    log("start %s %s" % (run_id, meta["cmd"][:200]))
    return {"run_id": run_id, "pid": p.pid, "dir": d,
            "out": os.path.join(d, "out.log"), "state": "run"}


def tool_run_tail(a):
    run_id = str(a.get("run_id", ""))
    offset = int(a.get("offset") or 0)
    d = run_dir(run_id)
    p = os.path.join(d, "out.log")
    if not os.path.isdir(d):
        raise RuntimeError("нет такого запуска: " + run_id)
    size = os.path.getsize(p) if os.path.isfile(p) else 0
    if offset > size:
        offset = 0
    data = ""
    if size > offset:
        with open(p, "rb") as f:
            f.seek(offset)
            data = f.read(262144).decode("utf-8", errors="replace")
    ec = os.path.join(d, "exit.code")
    return {"run_id": run_id, "offset": offset + len(data.encode("utf-8")),
            "data": data, "eof": os.path.isfile(ec)}


def tool_run_wait(a):
    run_id = str(a.get("run_id", ""))
    timeout = min(int(a.get("timeout_sec") or 60), 600)
    end = time.time() + timeout
    while time.time() < end:
        st = run_state(run_id)
        if st is None:
            raise RuntimeError("нет такого запуска: " + run_id)
        if st["state"] != "run":
            return st
        time.sleep(0.5)
    st = run_state(run_id)
    st["note"] = "таймаут ожидания; продолжайте run_status/run_tail"
    return st


def tool_run_list(a):
    limit = int(a.get("limit") or 15)
    if not os.path.isdir(BASE):
        return {"runs": []}
    ids = sorted((d for d in os.listdir(BASE) if os.path.isdir(run_dir(d))), reverse=True)[:limit]
    out = []
    for rid in ids:
        st = run_state(rid)
        if st:
            out.append({k: st[k] for k in ("run_id", "state", "exit", "base", "cwd", "last", "elapsed_sec")})
    return {"runs": out}


def _queue_mod():
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "queue.py")
    spec = importlib.util.spec_from_file_location("cc_queue_mod", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def tool_queue_submit(a):
    q = _queue_mod()
    os.makedirs(q.QUEUE, exist_ok=True)
    qid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    d = q.req_dir(qid)
    os.makedirs(d, exist_ok=True)
    req = {
        "id": qid,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "script": str(a.get("script", "")),
        "args": [str(x) for x in (a.get("args") or [])],
        "cwd": a.get("cwd") or os.getcwd(),
        "base": str(a.get("base") or ""),
        "priority": int(a.get("priority") or 5),
        "deadline_min": int(a.get("deadline_min") or 60),
        "max_attempts": int(a.get("max_attempts") or 6),
        "expect": {
            "config": str(a.get("expect_config") or ""),
            "extensions": a.get("expect_extensions") or {},
        },
    }
    q.write_json(os.path.join(d, "request.json"), req)
    q.save_state(qid, state="pending", attempts=0, last_error="", next_try=None)
    q.ensure_worker()
    log("queue_submit %s %s" % (qid, req["script"]))
    return {"queue_id": qid, "state": "pending", "base": req["base"]}


def tool_queue_status(a):
    q = _queue_mod()
    qid = str(a.get("queue_id", ""))
    req, st = q.load_req(qid)
    if not req:
        raise RuntimeError("нет такого запроса: " + qid)
    return {"queue_id": qid, "request": req, "state": st}


def tool_queue_list(a):
    q = _queue_mod()
    limit = int(a.get("limit") or 20)
    rows = []
    for qid in q.queue_ids():
        req, st = q.load_req(qid)
        if req:
            rows.append({"queue_id": qid, "state": st.get("state", "?"),
                         "base": req.get("base", ""), "script": req.get("script", ""),
                         "created": req.get("created", ""), "error": st.get("last_error", "")})
    rows.sort(key=lambda x: x["created"], reverse=True)
    return {"queue": rows[:limit]}


def tool_queue_cancel(a):
    q = _queue_mod()
    qid = str(a.get("queue_id", ""))
    req, st = q.load_req(qid)
    if not req:
        raise RuntimeError("нет такого запроса: " + qid)
    if st.get("state") in ("done", "failed", "cancelled"):
        return {"queue_id": qid, "state": st.get("state"), "cancelled": False}
    q.save_state(qid, state="cancelled", last_error="отменён через MCP")
    return {"queue_id": qid, "state": "cancelled", "cancelled": True}


def call_tool(name, a):
    if name == "run_start":
        return tool_run_start(a)
    if name == "run_status":
        st = run_state(str(a.get("run_id", "")))
        if st is None:
            raise RuntimeError("нет такого запуска")
        return st
    if name == "run_tail":
        return tool_run_tail(a)
    if name == "run_wait":
        return tool_run_wait(a)
    if name == "run_kill":
        st = run_state(str(a.get("run_id", "")))
        if st is None:
            raise RuntimeError("нет такого запуска")
        ok = kill(st.get("pid")) if st.get("state") == "run" else False
        return {"run_id": st["run_id"], "killed": ok}
    if name == "run_list":
        return tool_run_list(a)
    if name == "queue_submit":
        return tool_queue_submit(a)
    if name == "queue_status":
        return tool_queue_status(a)
    if name == "queue_list":
        return tool_queue_list(a)
    if name == "queue_cancel":
        return tool_queue_cancel(a)
    raise RuntimeError("неизвестный инструмент: " + name)


def respond(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle(req):
    method = req.get("method")
    rid = req.get("id")
    if method == "initialize":
        params = req.get("params") or {}
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": params.get("protocolVersion") or PROTO,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "cc-mcp", "version": "1.0.0"}}}
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            result = call_tool(name, args)
            text = json.dumps(result, ensure_ascii=False, indent=2)
            log("call %s ok" % name)
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": text}], "isError": False}}
        except Exception as e:
            log("call %s error: %s" % (name, e))
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": "ОШИБКА: %s" % e}], "isError": True}}
    if rid is None:
        return None
    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": "method not found: %s" % method}}


def main():
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    log("server start, pid=%d" % os.getpid())
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            log("bad json: %s" % line[:200])
            continue
        batch = payload if isinstance(payload, list) else [payload]
        for req in batch:
            resp = handle(req)
            if resp is not None:
                respond(resp)
    log("server exit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
