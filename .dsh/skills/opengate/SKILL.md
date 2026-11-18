---
name: opengate
description: Use a local OpenCode Serve instance as an AI gateway for one-off or large-volume processing when OpenAI providers are unsuitable. Starts and probes the gateway on the agent's current Windows or Linux machine; does not silently fall back to OpenAI.
---

# OpenGate

Use this skill when a task should call the local OpenCode gateway instead of a hosted OpenAI provider, especially for large-volume extraction, classification, transformation, or summarisation.

The gateway is always local to the current agent environment:

~~~
opencode serve --hostname 127.0.0.1 --port 4096
~~~

## Workflow

1. Run scripts/ensure_opencode_server.py --json. It probes GET /config/providers, or starts the local server only if it is absent.
2. Do not expose the server beyond 127.0.0.1, and do not change it to a public address.
3. For a normal request, use scripts/opengate_request.py --prompt.
4. For large input, use JSONL with --input, --output, and a small --workers value. The output file is a checkpoint: existing record indexes are skipped, so a stopped run can resume safely.
5. Choose a model explicitly with --model provider/model, or use --task for a dynamic preset. The preset reads the live catalog's context limits and capabilities; it does not assume that a model name or a 1M context window remains available forever.

## Task/model matrix

The preferred order is intentional: try the first available model that satisfies the context and capability threshold, then continue to the next one.

| Task | Model priority | Minimum context |
| --- | --- | --- |
| Fast extraction | Big Pickle -> DeepSeek Flash -> Qwen Flash | 128k |
| Large-batch classification | Big Pickle -> DeepSeek Flash -> Qwen 3.6/3.7 Plus | 200k |
| Long-document classification | Qwen 3.6/3.7 Plus -> MiMo V2.5 | 256k |
| Multi-document synthesis | MiMo V2.5 -> Qwen 3.7 Plus -> MiniMax-3 | 500k |
| Million-token synthesis | MiMo V2.5 -> Qwen with 1M window -> MiniMax-3 | 500k-1M |
| Images | MiMo or Qwen with `attachment/image=true` | 128k+ |

`million-synthesis` requires a live model with approximately a 1M-token context window; it will not silently downgrade to a 200k model.
6. Report an unavailable gateway clearly. Do not substitute OpenAI, another remote provider, or a fake result unless the user explicitly asks.

## Safety and data handling

- Treat the gateway as a local tool, but do not assume an OpenCode subscription permits every external model or provider it exposes.
- Do not put credentials in prompts, files, Git, or logs. If the local gateway requires Basic Auth, obtain it from OPENCODE_SERVER_USERNAME and OPENCODE_SERVER_PASSWORD environment variables.
- Batch outputs contain input excerpts by design. Put them in a project-local, user-approved location and avoid committing sensitive results.
- Default to two workers; increase only after observing the gateway can sustain the load.

## Useful commands

~~~
# Windows or Linux, from the project that needs processing
python <skill-path>/scripts/ensure_opencode_server.py --json
python <skill-path>/scripts/opengate_request.py --prompt "Extract three facts from: ..." --model opencode-go/deepseek-v4-flash
python <skill-path>/scripts/opengate_request.py --input data.jsonl --field text --template "Classify this text:\n{text}" --output result.jsonl --workers 2 --task bulk-classification
~~~

For batch details, recovery semantics, and JSONL formats, read [references/bulk-processing.md](references/bulk-processing.md).
