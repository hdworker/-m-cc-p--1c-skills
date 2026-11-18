#!/usr/bin/env python3
"""Submit single prompts or resumable JSONL batches through local OpenCode Serve."""
from __future__ import annotations

import argparse
import base64
import concurrent.futures
import json
import os
from pathlib import Path
import threading
import urllib.error
import urllib.parse
import urllib.request


def auth_header() -> dict[str, str]:
    username = os.getenv("OPENCODE_SERVER_USERNAME", "")
    password = os.getenv("OPENCODE_SERVER_PASSWORD", "")
    if not password:
        return {}
    value = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {value}"}


def request_json(url: str, method: str, body: dict | None, timeout: float) -> dict:
    headers = {"Accept": "application/json", "Content-Type": "application/json", **auth_header()}
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("data", payload) if isinstance(payload, dict) else payload


def models(url: str, timeout: float) -> list[dict]:
    payload = request_json(url + "/config/providers", "GET", None, timeout)
    result = []
    for provider in payload.get("providers", []) if isinstance(payload, dict) else []:
        for model_id, model in (provider.get("models") or {}).items():
            if not isinstance(model, dict):
                continue
            result.append({
                "key": f"{provider.get('id')}/{model_id}",
                "name": model.get("name") or model_id,
                "limit": model.get("limit") or {},
                "capabilities": model.get("capabilities") or {},
                "cost": model.get("cost") or {},
                "status": model.get("status", "active"),
            })
    return [model for model in result if model["status"] == "active"]


def choose_model(url: str, task: str, timeout: float) -> str:
    catalog = models(url, timeout)
    if not catalog:
        raise RuntimeError("OpenCode returned no active models")
    presets = {
        "fast-extraction": {"context": 128000, "reasoning": False, "attachment": False, "cost": True},
        "bulk-classification": {"context": 200000, "reasoning": False, "attachment": False, "cost": True},
        "long-document-classification": {"context": 256000, "reasoning": False, "attachment": False, "cost": True},
        "deep-analysis": {"context": 200000, "reasoning": True, "attachment": False, "cost": False},
        "synthesis": {"context": 500000, "reasoning": True, "attachment": False, "cost": False},
        "million-synthesis": {"context": 900000, "reasoning": True, "attachment": False, "cost": False},
        "multimodal": {"context": 128000, "reasoning": False, "attachment": True, "cost": True},
    }
    if task not in presets:
        raise ValueError("Unknown --task; use --list-presets")
    preset = presets[task]
    preferred = {
        "fast-extraction": ["opencode/big-pickle", "opencode-go/deepseek-v4-flash", "opencode-go/qwen3.8-flash"],
        "bulk-classification": ["opencode/big-pickle", "opencode-go/deepseek-v4-flash", "opencode-go/qwen3.8-flash", "opencode-go/qwen3.7-plus"],
        "long-document-classification": ["opencode-go/qwen3.7-plus", "opencode-go/qwen3.6-plus", "opencode-go/mimo-v2.5"],
        "deep-analysis": ["opencode-go/mimo-v2.5", "opencode-go/qwen3.7-plus", "opencode-go/qwen3.8-flash", "opencode-go/minimax-m3"],
        "synthesis": ["opencode-go/mimo-v2.5", "opencode-go/qwen3.7-plus", "opencode-go/qwen3.8-flash", "opencode-go/minimax-m3"],
        "million-synthesis": ["opencode-go/mimo-v2.5", "opencode-go/qwen3.7-plus", "opencode-go/qwen3.6-plus", "opencode-go/minimax-m3"],
        "multimodal": ["opencode-go/mimo-v2.5", "opencode-go/qwen3.8-flash", "opencode/mimo-v2.5-free"],
    }
    eligible = []
    for model in catalog:
        limit = model["limit"]
        capabilities = model["capabilities"]
        context = int(limit.get("context") or 0)
        if context < preset["context"]:
            continue
        if preset["reasoning"] and not capabilities.get("reasoning"):
            continue
        if preset["attachment"] and not (capabilities.get("attachment") or capabilities.get("input", {}).get("image")):
            continue
        input_cost = float((model["cost"] or {}).get("input") or 0)
        output_cost = float((model["cost"] or {}).get("output") or 0)
        preference = preferred[task].index(model["key"]) if model["key"] in preferred[task] else 99
        eligible.append((preference, input_cost + output_cost, -context, model["key"]))
    if not eligible:
        raise RuntimeError(f"No active model satisfies preset {task}")
    eligible.sort(key=lambda item: (item[0], item[1] if preset["cost"] else 0, item[2]))
    return eligible[0][3]


def answer(base_url: str, prompt: str, system: str, model: str, directory: str, timeout: float) -> str:
    suffix = "?directory=" + urllib.parse.quote(directory) if directory else ""
    session = request_json(base_url + "/session" + suffix, "POST", {"title": "OpenGate request"}, timeout)
    session_id = str(session.get("id", ""))
    if not session_id:
        raise RuntimeError("OpenCode did not return a session id")
    try:
        body: dict = {"parts": [{"type": "text", "text": prompt}]}
        if system:
            body["system"] = system
        if model and model != "opencode/default":
            provider, separator, model_id = model.partition("/")
            if not separator:
                raise ValueError("--model must have the form provider/model")
            body["model"] = {"providerID": provider, "modelID": model_id}
        response = request_json(base_url + f"/session/{session_id}/message" + suffix, "POST", body, timeout)
        parts = response.get("parts", []) if isinstance(response, dict) else []
        text = "\n\n".join(
            str(part.get("text", "")).strip()
            for part in parts
            if isinstance(part, dict) and part.get("type") == "text" and part.get("text")
        )
        if not text:
            raise RuntimeError("OpenCode returned no text")
        return text
    finally:
        try:
            request_json(base_url + f"/session/{session_id}" + suffix, "DELETE", None, timeout)
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError):
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:4096")
    parser.add_argument("--prompt")
    parser.add_argument("--system", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--task", choices=["fast-extraction", "bulk-classification", "long-document-classification", "deep-analysis", "synthesis", "million-synthesis", "multimodal"])
    parser.add_argument("--list-presets", action="store_true")
    parser.add_argument("--directory", default="")
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--field", default="text")
    parser.add_argument("--template", default="{text}")
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    if args.list_presets:
        print(json.dumps({
            "fast-extraction": "text extraction; >=128k context; lowest listed input/output cost",
            "bulk-classification": "large text batches; >=200k context; Big Pickle -> DeepSeek Flash -> Qwen",
            "long-document-classification": "long document classification; >=256k context; Qwen Plus first",
            "deep-analysis": "reasoning analysis; >=200k context",
            "synthesis": "long-context reasoning synthesis; >=500k context",
            "million-synthesis": "million-token synthesis; prefer models with >=1M context",
            "multimodal": "image-aware processing; >=128k context; lowest listed input/output cost",
        }, ensure_ascii=False, indent=2))
        return 0
    if bool(args.prompt) == bool(args.input):
        parser.error("Specify exactly one of --prompt or --input.")
    base_url = args.url.rstrip("/")
    if args.task and not args.model:
        try:
            args.model = choose_model(base_url, args.task, min(args.timeout, 10))
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError, RuntimeError) as exc:
            parser.exit(1, f"OpenGate model selection failed: {exc}\n")
    if args.prompt:
        try:
            print(answer(base_url, args.prompt, args.system, args.model, args.directory, args.timeout))
            return 0
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError, RuntimeError) as exc:
            parser.exit(1, f"OpenGate request failed: {exc}\n")
    if not args.output:
        parser.error("--output is required with --input.")
    items = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
    completed: set[int] = set()
    if args.output.exists():
        for line in args.output.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                if "index" in row and "output" in row:
                    completed.add(int(row["index"]))
            except (ValueError, TypeError):
                continue
    pending = [(index, item) for index, item in enumerate(items) if index not in completed]
    write_lock = threading.Lock()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def process(entry: tuple[int, dict]) -> None:
        index, item = entry
        try:
            value = item.get(args.field, "") if isinstance(item, dict) else str(item)
            prompt = args.template.format(text=value, item=json.dumps(item, ensure_ascii=False))
            record = {
                "index": index,
                "item": item,
                "output": answer(base_url, prompt, args.system, args.model, args.directory, args.timeout),
            }
        except Exception as exc:
            record = {"index": index, "item": item, "error": str(exc)}
        with write_lock:
            with args.output.open("a", encoding="utf-8") as output:
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
                output.flush()

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        list(pool.map(process, pending))
    print(json.dumps({
        "input": len(items),
        "already_completed": len(completed),
        "processed": len(pending),
        "output": str(args.output),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
