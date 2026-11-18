#!/usr/bin/env python3
"""1c-init.py — инициализация нового проекта разработки 1С.

Выбирает свободную тестовую базу из _store, создаёт .v8-project.json,
заготовку расширения (эталон из _store или cfe-init) и рабочие каталоги.
"""

import argparse
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import time

SKILLS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CFE_INIT = os.path.join(SKILLS, "cfe-init", "scripts", "cfe-init.py")
DEFAULT_STORE = r"E:\Grishin\Code\_store"


def die(msg, code=1):
    print("ОШИБКА: " + msg)
    sys.exit(code)


def ci_parse_args(parser, argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    names = {s.lower(): s for a in parser._actions for s in a.option_strings}
    for i, tok in enumerate(argv):
        if tok.startswith("-") and tok.lower() in names:
            argv[i] = names[tok.lower()]
    return parser.parse_args(argv)


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default


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


def busy_by_async():
    busy = set()
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "cc_async")
    if not os.path.isdir(base):
        return busy
    for rid in os.listdir(base):
        d = os.path.join(base, rid)
        if not os.path.isdir(d) or os.path.isfile(os.path.join(d, "exit.code")):
            continue
        pid = ""
        try:
            pid = open(os.path.join(d, "pid")).read().strip()
        except OSError:
            continue
        if not alive(pid):
            continue
        meta = read_json(os.path.join(d, "meta.json"), {}) or {}
        if meta.get("base"):
            busy.add(meta["base"])
    return busy


def designers():
    ps = ("$p = Get-CimInstance Win32_Process -Filter \"Name='1cv8.exe'\" -ErrorAction SilentlyContinue; "
          "$p | Where-Object { $_.CommandLine -match 'DESIGNER' } | ForEach-Object { $_.CommandLine }")
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=90,
                           encoding="cp866", errors="replace")
        return r.stdout or ""
    except Exception:
        return ""


def sig(db):
    return "server:%s/%s" % (str(db.get("server", "")).lower(), str(db.get("ref", "")).lower())


def merged_project(existing, registry, databases, db_ref, project_dir, name, src_dir, build_dir):
    """Дополнить существующий .v8-project.json, не меняя заданные значения."""
    project = dict(existing)
    if not project.get("v8path"):
        project["v8path"] = registry.get("v8path", "")
    have = {str(d.get("ref", "")).lower() for d in (project.get("databases") or [])}
    merged = list(project.get("databases") or [])
    for db in databases:
        if str(db.get("ref", "")).lower() not in have:
            merged.append(db)
    project["databases"] = merged
    if not project.get("default"):
        project["default"] = db_ref
    check = project.get("check") or {}
    check.setdefault("database", db_ref)
    check.setdefault("checklist", "checks/current.md")
    if name:
        build = check.get("build") or {}
        build.setdefault("srcDir", os.path.relpath(src_dir, project_dir))
        build.setdefault("configXml", os.path.relpath(os.path.join(src_dir, "Configuration.xml"), project_dir))
        build.setdefault("cfePattern", os.path.relpath(os.path.join(build_dir, name + "_*.cfe"), project_dir))
        check["build"] = build
    project["check"] = check
    return project


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        description="Init 1C project: project-only setup or extension scaffold on a free base")
    ap.add_argument("-ProjectDir", required=True)
    ap.add_argument("-Name", default="")
    ap.add_argument("-Adopt", action="store_true")
    ap.add_argument("-ProjectOnly", action="store_true",
                    help="инициализировать проект без создания расширения")
    ap.add_argument("-Synonym", default="")
    ap.add_argument("-NamePrefix", default="")
    ap.add_argument("-Version", default="1.0.0")
    ap.add_argument("-Database", default="")
    ap.add_argument("-StoreDir", default=DEFAULT_STORE)
    ap.add_argument("-NoScaffold", action="store_true")
    ap.add_argument("-DryRun", action="store_true")
    ap.add_argument("-Force", action="store_true")
    args = ci_parse_args(ap)

    store = os.path.abspath(args.StoreDir)
    registry = read_json(os.path.join(store, ".v8-project.json"))
    if not registry:
        die("не найден реестр " + os.path.join(store, ".v8-project.json"))
    databases = registry.get("databases") or []
    if not databases:
        die("в реестре стора нет баз")

    project_dir = os.path.abspath(args.ProjectDir)
    project_file = os.path.join(project_dir, ".v8-project.json")
    existing_project = None
    if os.path.isfile(project_file):
        existing_project = read_json(project_file, {}) or {}
        if not args.Force and not args.Adopt and not args.ProjectOnly:
            die("проект уже инициализирован: " + project_file +
                "\n  Для существующего проекта используйте -Adopt (подключить к стору) или -Force (дополнить).")

    busy_async = busy_by_async()
    design_lines = designers()

    if args.ProjectOnly:
        if args.Name:
            die("-ProjectOnly используется без -Name; для создания расширения уберите -ProjectOnly")
        if args.Adopt:
            die("-ProjectOnly и -Adopt несовместимы")
        if existing_project:
            die("проект уже инициализирован; используйте -Adopt для подключения к стору")

        def project_base_busy(db):
            if sig(db) in busy_async:
                return "активное async-задание"
            ref = str(db.get("ref", ""))
            if ref and ref.lower() in design_lines.lower():
                return "запущен конфигуратор"
            return ""

        chosen = None
        if args.Database:
            want = args.Database.lower()
            for db in databases:
                if (str(db.get("ref", "")).lower() == want
                        or str(db.get("id", "")).lower() == want):
                    chosen = db
                    break
            if not chosen:
                die("база не найдена в реестре: " + args.Database)
            reason = project_base_busy(chosen)
            if reason and not args.Force:
                die("база %s занята (%s); укажите другую или -Force" % (chosen.get("ref"), reason))
        else:
            default = str(registry.get("default", ""))
            ordered = sorted(databases, key=lambda d: (
                0 if str(d.get("ref")) == default else 1, str(d.get("ref"))))
            for db in ordered:
                if not project_base_busy(db):
                    chosen = db
                    break
            if not chosen:
                if args.Force:
                    chosen = ordered[0]
                else:
                    die("нет свободных баз: все заняты (укажите -Database или -Force)")

        db_ref = str(chosen.get("ref", ""))
        build_dir = os.path.join(project_dir, "build")
        checks_dir = os.path.join(project_dir, "checks")
        checklist = os.path.join(checks_dir, "current.md")
        plan = {
            "project": project_dir,
            "mode": "project-only",
            "database": db_ref,
            "project_config": project_file,
            "build": build_dir,
            "checklist": checklist,
            "extension_scaffold": False,
        }
        if args.DryRun:
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 0

        os.makedirs(project_dir, exist_ok=True)
        os.makedirs(build_dir, exist_ok=True)
        os.makedirs(checks_dir, exist_ok=True)
        project = {
            "v8path": registry.get("v8path", ""),
            "databases": databases,
            "default": db_ref,
            "check": {
                "database": db_ref,
                "url": "",
                "checklist": "checks/current.md",
            },
        }
        try:
            with open(project_file, "x", encoding="utf-8") as f:
                json.dump(project, f, ensure_ascii=False, indent=2)
        except FileExistsError:
            die("файл проекта появился во время инициализации; существующие настройки не изменены: "
                + project_file)

        if not os.path.isfile(checklist):
            with open(checklist, "x", encoding="utf-8") as f:
                f.write("# Чек-лист проекта\n\n"
                        "Добавьте пункты проверки после определения доработки.\n")

        print("Проектная среда подготовлена без создания расширения:")
        print("  Папка:        " + project_dir)
        print("  База:         " + db_ref)
        print("  Реестр:       " + project_file)
        print("  Сборки:       " + build_dir)
        print("  Чек-лист:     " + checklist)
        print("  Расширение:   не создавалось; добавьте его позже через 1c-init -Name <имя> -Force")
        print("  URL проверки: не задан; укажите его в секции check после определения задачи")
        return 0

    if not args.Name and not args.Adopt:
        die("укажите -Name <имя расширения>, -ProjectOnly (проект без расширения) "
            "или -Adopt (подключить существующий проект к стору)")

    if args.Adopt:
        if not existing_project:
            die("проект не инициализирован (нет .v8-project.json); для создания укажите -Name")
        db = None
        pref = str(existing_project.get("default", ""))
        for item in (existing_project.get("databases") or []):
            if str(item.get("ref", "")) == pref:
                db = item
                break
        if db is None and (existing_project.get("databases") or []):
            db = existing_project["databases"][0]
        db_ref = str((db or {}).get("ref", ""))
        project = merged_project(existing_project, registry, databases, db_ref, project_dir, "", "", "")
        backup = project_file + ".bak-" + time.strftime("%Y%m%d-%H%M%S")
        shutil.copy2(project_file, backup)
        with open(project_file, "w", encoding="utf-8") as f:
            json.dump(project, f, ensure_ascii=False, indent=2)

        def base_busy_adopt(d):
            if not d:
                return ""
            if sig(d) in busy_async:
                return "активное async-задание"
            ref = str(d.get("ref", ""))
            if ref and ref.lower() in design_lines.lower():
                return "запущен конфигуратор"
            return ""

        reason = base_busy_adopt(db)
        print("Проект подключён к стору: " + project_dir)
        print("  База:          " + (db_ref or "-") + ((" (внимание: %s)" % reason) if reason else ""))
        print("  Базы стора:    " + ", ".join(str(x.get("ref")) for x in databases))
        print("  Резервная копия: " + backup)
        print("Ничего не создано и не удалено.")
        return 0

    def base_busy(db):
        if sig(db) in busy_async:
            return "активное async-задание"
        ref = str(db.get("ref", ""))
        if ref and ref.lower() in design_lines.lower():
            return "запущен конфигуратор"
        return ""

    chosen = None
    if existing_project and not args.Database:
        pref = str(existing_project.get("default", ""))
        for db in (existing_project.get("databases") or []):
            if str(db.get("ref", "")) == pref:
                chosen = db
                break
        if chosen is None and (existing_project.get("databases") or []):
            chosen = existing_project["databases"][0]
        if chosen:
            db_ref = str(chosen.get("ref", ""))
            reason = base_busy(chosen)
            print("Существующий проект: база не меняется — " + db_ref +
                  ((" (внимание: занята — %s)" % reason) if reason else ""))
    if chosen is None and args.Database:
        want = args.Database.lower()
        for db in databases:
            if str(db.get("ref", "")).lower() == want or str(db.get("id", "")).lower() == want:
                chosen = db
                break
        if not chosen:
            die("база не найдена в реестре: " + args.Database)
        reason = base_busy(chosen)
        if reason and not args.Force:
            die("база %s занята (%s); укажите другую или -Force" % (chosen.get("ref"), reason))
    elif chosen is None:
        default = str(registry.get("default", ""))
        ordered = sorted(databases, key=lambda d: (0 if str(d.get("ref")) == default else 1,
                                                  str(d.get("ref"))))
        for db in ordered:
            if not base_busy(db):
                chosen = db
                break
        if not chosen:
            if args.Force:
                chosen = ordered[0]
            else:
                die("нет свободных баз: все заняты (укажите -Database или -Force)")

    db_ref = str(chosen.get("ref", ""))
    src_dir = os.path.join(project_dir, "src", "cfe", args.Name)
    build_dir = os.path.join(project_dir, "build")
    checks_dir = os.path.join(project_dir, "checks")

    plan = {
        "project": project_dir,
        "database": db_ref,
        "extension": args.Name,
        "src": src_dir,
        "build": build_dir,
        "checklist": os.path.join(checks_dir, "current.md"),
        "scaffold": not args.NoScaffold,
    }
    if args.DryRun:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    os.makedirs(project_dir, exist_ok=True)
    os.makedirs(build_dir, exist_ok=True)
    os.makedirs(checks_dir, exist_ok=True)

    prefix = args.NamePrefix
    if not prefix:
        prefix = "бкк_"

    if existing_project:
        # Настройки существующего проекта не перезаписываются: только дополнение.
        project = merged_project(existing_project, registry, databases, db_ref, project_dir,
                                 args.Name, src_dir, build_dir)
        backup = project_file + ".bak-" + time.strftime("%Y%m%d-%H%M%S")
        shutil.copy2(project_file, backup)
        print("Резервная копия: " + backup)
    else:
        project = {
            "v8path": registry.get("v8path", ""),
            "databases": databases,
            "default": db_ref,
            "check": {
                "database": db_ref,
                "url": "",
                "checklist": "checks/current.md",
                "build": {
                    "srcDir": os.path.relpath(src_dir, project_dir),
                    "configXml": os.path.relpath(os.path.join(src_dir, "Configuration.xml"), project_dir),
                    "cfePattern": os.path.relpath(os.path.join(build_dir, args.Name + "_*.cfe"), project_dir),
                },
            },
        }
    with open(project_file, "w", encoding="utf-8") as f:
        json.dump(project, f, ensure_ascii=False, indent=2)

    checklist = os.path.join(checks_dir, "current.md")
    if not os.path.isfile(checklist):
        with open(checklist, "w", encoding="utf-8") as f:
            f.write("# Чек-лист проверки: %s v%s (база %s)\n\n"
                    "- [ ] Форма/обработка открывается без ошибок\n"
                    "- [ ] Проверяемый сценарий работает\n"
                    "- [ ] В журнале регистрации нет ошибок\n" % (args.Name, args.Version, db_ref))

    scaffold_from = ""
    other_layout = os.path.join(project_dir, "src", args.Name)
    sources_exist = os.path.isdir(src_dir) or os.path.isdir(other_layout)
    if sources_exist:
        if not args.NoScaffold:
            print("Исходники уже есть — заготовка НЕ создаётся и НЕ удаляется:")
            print("  " + (src_dir if os.path.isdir(src_dir) else other_layout))
    elif not args.NoScaffold:
        ref_root = os.path.join(store, "reference", "extensions", args.Name)
        if os.path.isdir(ref_root):
            versions = sorted(os.listdir(ref_root))
            if versions:
                scaffold_from = os.path.join(ref_root, versions[-1])
                shutil.copytree(scaffold_from, src_dir)
                print("Заготовка скопирована из эталона: " + scaffold_from)

    if not args.NoScaffold and not scaffold_from and not sources_exist:
        if not os.path.isfile(CFE_INIT):
            die("не найден cfe-init: " + CFE_INIT)
        os.makedirs(os.path.dirname(src_dir), exist_ok=True)
        cmd = [sys.executable, CFE_INIT, "-Name", args.Name, "-OutputDir", src_dir,
               "-Purpose", "AddOn", "-Version", args.Version, "-NamePrefix", prefix]
        if args.Synonym:
            cmd += ["-Synonym", args.Synonym]
        cfg_roots = os.path.join(store, "reference", "config")
        if os.path.isdir(cfg_roots):
            for d in sorted(os.listdir(cfg_roots)):
                cfg_xml = os.path.join(cfg_roots, d, "Configuration.xml")
                if os.path.isfile(cfg_xml):
                    cmd += ["-ConfigPath", cfg_xml]
                    break
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180,
                           encoding="utf-8", errors="replace")
        print(r.stdout or "", end="")
        if r.returncode != 0:
            print(r.stderr or "", end="")
            die("cfe-init завершился с кодом %d" % r.returncode)

    print()
    print("Проект инициализирован:")
    print("  Папка:        " + project_dir)
    print("  База:         " + db_ref + (" (из эталона)" if scaffold_from else ""))
    print("  Расширение:   " + args.Name + "  (префикс " + prefix + ")")
    print("  Исходники:    " + src_dir)
    print("  Сборки:       " + build_dir)
    print("  Чек-лист:     " + checklist)
    print()
    print("Далее: правка XML -> сборка CFE -> 1c-check-task (-ProjectDir \"" + project_dir + "\")")
    return 0


if __name__ == "__main__":
    sys.exit(main())
