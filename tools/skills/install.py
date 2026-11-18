#!/usr/bin/env python3
"""Установка набора скиллов из репозитория в каталог агента.

    python install.py --target dsh [--src <каталог ветки>] [--dest <каталог>]

По умолчанию:
  * source — `.dsh/skills` (dsh) или `.opencode/skills` (opencode) рядом с репозиторием;
  * dest   — `%USERPROFILE%\\.dsh\\skills` (dsh) или `%USERPROFILE%\\.config\\opencode\\skills`.

Текущий каталог не удаляется: переименовывается в `<dest>.bak-<метка времени>`.
После копирования сверяет число файлов и печатает манифест платформы.
"""

import argparse
import json
import os
import shutil
import sys
import time


def default_paths(target):
    home = os.path.expanduser("~")
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if target == "dsh":
        return os.path.join(repo, ".dsh", "skills"), os.path.join(home, ".dsh", "skills")
    if target == "opencode":
        return (os.path.join(repo, ".opencode", "skills"),
                os.path.join(home, ".config", "opencode", "skills"))
    raise SystemExit("неизвестный target: " + target)


def count_files(root):
    total = 0
    for _dp, _dn, files in os.walk(root):
        total += len(files)
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, choices=["dsh", "opencode"])
    ap.add_argument("--src")
    ap.add_argument("--dest")
    ap.add_argument("--force", action="store_true", help="не спрашивать подтверждение")
    a = ap.parse_args()

    src, dest = default_paths(a.target)
    src = os.path.abspath(a.src or src)
    dest = os.path.abspath(a.dest or dest)
    if not os.path.isdir(src):
        raise SystemExit("нет источника: " + src)
    if not a.force and os.path.isdir(dest):
        sys.stderr.write("Будет заменено: %s\nПродолжить? [y/N] " % dest)
        if input().strip().lower() not in ("y", "yes", "д", "да"):
            raise SystemExit("отменено")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    if os.path.isdir(dest):
        backup = "%s.bak-%s" % (dest, stamp)
        os.rename(dest, backup)
        print("старый каталог: " + backup)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    src_n, dst_n = count_files(src), count_files(dest)
    print("файлов: источник %d, установлено %d" % (src_n, dst_n))
    if src_n != dst_n:
        raise SystemExit("РАСХОЖДЕНИЕ: установлено %d из %d" % (dst_n, src_n))
    manifest = os.path.join(dest, ".cc-1c-skills.json")
    if os.path.isfile(manifest):
        with open(manifest, encoding="utf-8") as f:
            m = json.load(f)
        print("манифест: platform=%s runtime=%s mode=%s skills=%d"
              % (m.get("platform"), m.get("runtime"), m.get("mode"), len(m.get("skills", []))))
    print("готово: " + dest)


if __name__ == "__main__":
    main()
