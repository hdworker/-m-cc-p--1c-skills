#!/usr/bin/env python3
"""Журнал выгрузок и сборок проекта (EXPORTS.md).

Зачем: после перерыва (неделя/месяц) видно, что уже выгружено, куда и когда —
и не нужно выгружать заново, работа продолжается с места остановки.

Использование:
  python export_log.py add --kind Обработка --name diadoc_4_62_0.epf \\
      --target "src\\diadoc" --operation epf-dump [--source "vendor\\diadoc_4_62_0.epf"] \\
      [--project <каталог проекта>]
  python export_log.py show [--project <каталог проекта>] [--limit 30]

Файл: <проект>\\EXPORTS.md. Проект — каталог с `.v8-project.json` (или `.git`);
если не найден — текущий каталог (или --project).
"""

import argparse
import os
import sys
import time

HEADER = """# Журнал выгрузок и сборок

Файл ведут навыки выгрузки и сборки (`epf-dump`, `epf-build`, `db-dump-cf`,
`db-dump-xml`). Назначение: после перерыва продолжить работу с места остановки,
а не выгружать заново.

| Дата | Тип | Имя | Куда | Операция | Источник |
|---|---|---|---|---|---|
"""


def find_project(start):
    cur = os.path.abspath(start)
    for _ in range(8):
        if os.path.isfile(os.path.join(cur, ".v8-project.json")) or os.path.isdir(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return os.path.abspath(start)


def display_path(project, path):
    if not path:
        return ""
    if not os.path.isabs(path):
        path = os.path.join(project, path)
    full = os.path.abspath(path)
    try:
        rel = os.path.relpath(full, project)
        if not rel.startswith(".."):
            return rel
    except ValueError:
        pass
    return full


def cell(text):
    return str(text or "").replace("|", "\\|").replace("\n", " ").strip()


def ensure_file(path):
    if os.path.isfile(path):
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(HEADER)


def add(args):
    project = find_project(args.project or os.getcwd())
    path = os.path.join(project, "EXPORTS.md")
    ensure_file(path)
    row = "| %s | %s | %s | %s | %s | %s |\n" % (
        time.strftime("%Y-%m-%d %H:%M"),
        cell(args.kind), cell(args.name), cell(display_path(project, args.target)),
        cell(args.operation), cell(display_path(project, args.source) if args.source else ""),
    )
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(row)
    print("Журнал: " + path)
    print(row.rstrip())
    return 0


def show(args):
    project = find_project(args.project or os.getcwd())
    path = os.path.join(project, "EXPORTS.md")
    if not os.path.isfile(path):
        print("Журнала нет: " + path)
        return 0
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    limit = max(1, args.limit or 30)
    print("\n".join(lines[:6]))
    print("\n".join(lines[6:][-limit:]))
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--kind", required=True, help="Обработка/Отчёт/CF/CFE/XML/DT")
    a.add_argument("--name", required=True)
    a.add_argument("--target", required=True, help="Каталог или файл результата")
    a.add_argument("--operation", required=True)
    a.add_argument("--source", default="")
    a.add_argument("--project", default="")
    a.set_defaults(func=add)
    s = sub.add_parser("show")
    s.add_argument("--project", default="")
    s.add_argument("--limit", type=int, default=30)
    s.set_defaults(func=show)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
