#!/usr/bin/env python3
"""Сборка целевого набора скиллов из opencode-версии.

    python build_target.py --from <opencode-skills-dir> --target dsh --out <dir>

Что делает для target=dsh:
  * frontmatter: оставляет name/description, убирает argument-hint/allowed-tools;
  * заголовок "# /skill — ..." -> "# skill — ...";
  * пути `.opencode/skills/...` -> `$env:USERPROFILE\\.dsh\\skills\\...`;
  * строки использования "/skill args" -> вызов python-скрипта скилла;
  * ссылки `/<skill>` -> `<skill>`;
  * раздел "Запуск через MCP (cc)" -> раздел про нативные фоновые задания DSH;
  * копирует scripts/ и reference/ как есть (без __pycache__/*.pyc);
  * пишет манифест .cc-1c-skills.json с platform=dsh.

Скрипт идемпотентен: выходной каталог очищается.
"""

import argparse
import json
import os
import re
import shutil

SKIP_DIRS = {"__pycache__"}
SKIP_EXT = {".pyc"}

DSH_ASYNC_SECTION = """## Запуск в DSH — без ожидания оболочки

Долгий вызов запускай через `pwsh` с `run_in_background: true` и `CC_SYNC=1`:

```powershell
$env:CC_SYNC='1'; python "$env:USERPROFILE\\.dsh\\skills\\<скилл>\\scripts\\<скилл>.py" <аргументы>
```

DSH сразу вернёт job id (аналог `RUN_ID`), по завершении пришлёт уведомление.
`job_output` — хвост лога и результат, `job_list` — статус, `job_kill` — остановка.
Ждать синхронно не нужно.

Команда без `CC_SYNC=1` сама уходит в фон через `async_run.py` и печатает `RUN_ID` —
этот путь оставлен для совместимости с opencode и общим монитором:
`python "$env:USERPROFILE\\.dsh\\skills\\_shared\\async_run.py" status <RUN_ID>` (также `start`, `tail`, `list`, `wait`).
Данные — `%LOCALAPPDATA%\\cc_async`, тот же формат, что у opencode.
Монитор для человека: `python "$env:USERPROFILE\\.dsh\\skills\\_shared\\cc-status.py"`.
Полный протокол — `E:\\Grishin\\Code\\_store\\PROCESS.md`.
"""


def split_frontmatter(text):
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return None, text
    return text[4:end], text[end + 5:]


def convert_frontmatter(fm):
    keep, out, skipping = ("name", "description"), [], False
    for line in fm.splitlines():
        m = re.match(r"^([A-Za-z0-9_-]+):(.*)$", line)
        if m:
            key = m.group(1)
            skipping = key not in keep
            if not skipping:
                out.append(line)
            continue
        if skipping:
            # продолжение удаляемого поля (например, список allowed-tools)
            if line.startswith(" ") or line.startswith("-") or not line.strip():
                continue
            skipping = False
        out.append(line)
    return "\n".join(out)


def convert_body(skill, body):
    body = re.sub(r"^#\s+/([a-z0-9][a-z0-9-]*)", r"# \1", body, flags=re.M)

    # пути установки opencode -> DSH
    body = body.replace(".opencode/skills/", "$env:USERPROFILE\\.dsh\\skills\\")
    body = body.replace(".config/opencode/skills/", "$env:USERPROFILE\\.dsh\\skills\\")

    # строки использования: "/skill ..." в начале строки
    def usage_line(m):
        name = m.group(1)
        if name != skill:
            return m.group(0)
        script = '$env:USERPROFILE\\.dsh\\skills\\%s\\scripts\\%s.py' % (name, name)
        return 'python "%s" %s' % (script, m.group(2).strip())

    body = re.sub(r"^/([a-z0-9][a-z0-9-]*)\s*(.*)$", usage_line, body, flags=re.M)

    # ссылки в тексте `\/skill` -> `skill`
    body = re.sub(r"`/([a-z0-9][a-z0-9-]*)`", r"`\1`", body)
    body = re.sub(r"`/([a-z0-9][a-z0-9-]*)\b", r"`\1", body)

    # раздел про MCP cc заменяем на нативный запуск DSH
    idx = body.find("## Запуск через MCP")
    if idx >= 0:
        body = body[:idx] + DSH_ASYNC_SECTION

    return body


def build(from_dir, out_dir, target):
    if target != "dsh":
        raise SystemExit("пока поддерживается только --target dsh")
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)

    skills = sorted(
        d for d in os.listdir(from_dir)
        if os.path.isdir(os.path.join(from_dir, d)) and not d.startswith(".")
    )
    converted = 0
    for skill in skills:
        src = os.path.join(from_dir, skill)
        dst = os.path.join(out_dir, skill)
        skill_md = os.path.join(src, "SKILL.md")
        if not os.path.isfile(skill_md):
            # _shared и подобные каталоги переносим как есть
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*SKIP_DIRS, "*.pyc"))
            continue
        os.makedirs(dst, exist_ok=True)
        with open(skill_md, encoding="utf-8") as f:
            text = f.read()
        fm, body = split_frontmatter(text)
        if fm is None:
            raise SystemExit("%s: нет frontmatter" % skill_md)
        body = convert_body(skill, body)
        with open(os.path.join(dst, "SKILL.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("---\n%s\n---\n%s" % (convert_frontmatter(fm), body))
        for name in os.listdir(src):
            path = os.path.join(src, name)
            if name == "SKILL.md" or name in SKIP_DIRS or name.endswith(".pyc"):
                continue
            target_path = os.path.join(dst, name)
            if os.path.isdir(path):
                shutil.copytree(path, target_path,
                                ignore=shutil.ignore_patterns(*SKIP_DIRS, "*.pyc"))
            else:
                shutil.copy2(path, target_path)
        converted += 1

    manifest = {
        "source": "https://github.com/Nikolay-Shirokov/cc-1c-skills",
        "commit": os.environ.get("CC_SOURCE_COMMIT", "4fc37e1f992057847228a69837337bd3c141c059"),
        "platform": "dsh",
        "runtime": "python",
        "mode": "generated",
        "skills": skills,
    }
    with open(os.path.join(out_dir, ".cc-1c-skills.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print("dsh: %d навыков -> %s" % (converted, out_dir))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", required=True)
    ap.add_argument("--out", dest="out", required=True)
    ap.add_argument("--target", default="dsh", choices=["dsh"])
    a = ap.parse_args()
    build(os.path.abspath(a.src), os.path.abspath(a.out), a.target)


if __name__ == "__main__":
    main()
