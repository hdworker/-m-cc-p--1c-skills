#!/usr/bin/env python3
"""Probe or start a local OpenCode Serve instance without exposing it to a network."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request


def probe(url: str, timeout: float = 2.0) -> dict | None:
    request = urllib.request.Request(url.rstrip("/") + "/config/providers", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hostname", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4096)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--no-start", action="store_true", help="Only probe; never start OpenCode.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    url = f"http://{args.hostname}:{args.port}"
    payload = probe(url)
    started = False
    if not payload and not args.no_start:
        executable = shutil.which("opencode")
        if not executable:
            message = {"status": "offline", "url": url, "error": "opencode executable not found on PATH"}
            print(json.dumps(message) if args.json else message["error"], file=sys.stderr)
            return 2
        options = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            options["start_new_session"] = True
        subprocess.Popen([executable, "serve", "--hostname", args.hostname, "--port", str(args.port)], **options)
        started = True
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            time.sleep(0.4)
            payload = probe(url)
            if payload:
                break
    if not payload:
        message = {"status": "offline", "url": url, "error": "OpenCode Serve did not become ready"}
        print(json.dumps(message) if args.json else message["error"], file=sys.stderr)
        return 1
    providers = payload.get("providers", []) if isinstance(payload, dict) else []
    message = {"status": "online", "url": url, "started": started, "providers": len(providers)}
    print(json.dumps(message) if args.json else f"OpenCode Serve online at {url} ({len(providers)} providers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
