# Batch processing

Use a JSONL input: one JSON object per line. --field selects the text field, defaulting to text.

~~~
{"id":"a-01","text":"First document"}
{"id":"a-02","text":"Second document"}
~~~

Run:

~~~
python scripts/opengate_request.py --input source.jsonl --field text --template "Extract companies and dates from:\n{text}" --output extracted.jsonl --workers 2
~~~

Each output line contains index, the source item, and either output or error. The tool reads the existing output first and skips completed indexes. Delete only the specific incomplete/error rows if they should be retried; do not delete a whole checkpoint without confirming the intended scope.

Use --workers 1 for expensive models or a fragile server. Presets are selected from the live OpenCode catalog:

- fast-extraction: Big Pickle first, then DeepSeek Flash and Qwen Flash, at least 128k context;
- bulk-classification: Big Pickle first, then DeepSeek Flash or Qwen 3.6/3.7 Plus, at least 200k context;
- long-document-classification: Qwen 3.6/3.7 Plus first, then MiMo, at least 256k context;
- deep-analysis: MiMo first, then Qwen Plus, with MiniMax-3 as a reserve, at least 200k context;
- synthesis: MiMo first, then Qwen Plus, with MiniMax-3 as a reserve, at least 500k context;
- million-synthesis: MiMo V2.5 first, then Qwen with a 1M window, with MiniMax-3 as a reserve, requiring approximately 1M context;
- multimodal: MiMo or Qwen with image support, at least 128k context.

Pass --model to override a preset. Keep source input immutable while a checkpoint exists; line indexes are the resume key.
