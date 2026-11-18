#!/usr/bin/env python3
# check-task.py v2.0 — preflight audit + launch 1C:Enterprise for manual check.
# Uses db-run.py (launch) and db-cfe-admin.py (deep checks) from the same skills set.

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime

SKILLS_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_RUN = os.path.join(SKILLS_DIR, "db-run", "scripts", "db-run.py")
CFE_ADMIN = os.path.join(SKILLS_DIR, "db-cfe-admin", "scripts", "db-cfe-admin.py")

URL_FOLDERS = {
    "Обработка": "DataProcessors",
    "Справочник": "Catalogs",
    "Документ": "Documents",
    "Отчет": "Reports",
    "РегистрСведений": "InformationRegisters",
    "РегистрНакопления": "AccumulationRegisters",
    "ПланВидовХарактеристик": "ChartsOfCharacteristicTypes",
    "ОбщийМодуль": "CommonModules",
}

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def ci_parse_args(parser, argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    names = {s.lower(): s for a in parser._actions for s in a.option_strings}
    for i, tok in enumerate(argv):
        if tok.startswith("-") and tok.lower() in names:
            argv[i] = names[tok.lower()]
    return parser.parse_args(argv)


def find_project_file(start):
    d = os.path.abspath(start) if start else os.getcwd()
    for _ in range(20):
        candidate = os.path.join(d, ".v8-project.json")
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


def read_version(config_xml):
    if not os.path.isfile(config_xml):
        return "", ""
    with open(config_xml, encoding="utf-8-sig", errors="replace") as f:
        text = f.read()
    version = re.search(r"<Version>([^<]*)</Version>", text)
    name = re.search(r"<Name>([^<]*)</Name>", text)
    return (version.group(1).strip() if version else "",
            name.group(1).strip() if name else "")


def newest_file(path):
    newest = None
    for root, dirs, files in os.walk(path):
        for f in files:
            p = os.path.join(root, f)
            try:
                mt = os.path.getmtime(p)
            except OSError:
                continue
            if newest is None or mt > newest[0]:
                newest = (mt, p)
    return newest


def temp_roots():
    roots = []
    for var in ("TEMP", "TMP"):
        v = os.environ.get(var)
        if v and os.path.isdir(v):
            roots.append(v)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        v = os.path.join(local, "Temp")
        if os.path.isdir(v):
            roots.append(v)
    return list(dict.fromkeys(roots))


def latest_log_dir(pattern):
    found = []
    for root in temp_roots():
        for dirpath, dirs, _files in os.walk(root):
            depth = dirpath[len(root):].count(os.sep)
            if depth > 3:
                dirs[:] = []
                continue
            for d in list(dirs):
                if re.fullmatch(pattern, d):
                    p = os.path.join(dirpath, d)
                    try:
                        found.append((os.path.getmtime(p), p))
                    except OSError:
                        pass
    if not found:
        return None, None
    found.sort()
    return found[-1][0], found[-1][1]


def read_text(path):
    if not path or not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def fmt_time(ts):
    return datetime.fromtimestamp(ts).strftime("%d.%m %H:%M")


def add(check_list, name, status, text):
    check_list.append({"name": name, "status": status, "text": text})


def designer_running(db_ref):
    ps = ("$p = Get-CimInstance Win32_Process -Filter \"Name='1cv8.exe'\" -ErrorAction Stop; "
          "($p | Where-Object { $_.CommandLine -and $_.CommandLine -match 'DESIGNER' -and "
          "$_.CommandLine -match '" + db_ref.replace("'", "''") + "' } | Measure-Object).Count")
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=60, encoding="cp866", errors="replace")
        if r.returncode != 0:
            return None
        return int((r.stdout or "0").strip() or 0) > 0
    except Exception:
        return None


def run_admin(args, timeout=180):
    """Run db-cfe-admin.py; return (rc, output)."""
    cmd = [sys.executable, "-u", CFE_ADMIN] + args
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return -1, "timeout"


def main():
    parser = argparse.ArgumentParser(description="Preflight audit and launch 1C:Enterprise for manual checks")
    parser.add_argument("-Database", default="")
    parser.add_argument("-Url", default="")
    parser.add_argument("-CParam", default="")
    parser.add_argument("-Checklist", default="")
    parser.add_argument("-ProjectDir", default="")
    parser.add_argument("-PrintOnly", action="store_true")
    parser.add_argument("-PreflightOnly", action="store_true")
    parser.add_argument("-SkipPreflight", action="store_true")
    parser.add_argument("-Force", action="store_true")
    parser.add_argument("-Deep", action="store_true",
                        help="Check applied extensions in the infobase (db-cfe-admin check apply + version)")
    parser.add_argument("-Json", action="store_true", help="Print result as JSON")
    args = ci_parse_args(parser)

    project_file = find_project_file(args.ProjectDir)
    if not project_file:
        print("ОШИБКА: не найден .v8-project.json (поиск вверх от текущего каталога). Укажите -ProjectDir.")
        return 1

    project_root = os.path.dirname(project_file)
    with open(project_file, encoding="utf-8-sig", errors="replace") as f:
        project = json.load(f)

    databases = project.get("databases") or []
    db = None
    if args.Database:
        want = args.Database.lower()
        for d in databases:
            keys = [str(d.get("id", "")), str(d.get("ref", "")), str(d.get("name", ""))]
            keys += [str(a) for a in (d.get("aliases") or [])]
            if any(k.lower() == want for k in keys if k):
                db = d
                break
    if not db:
        check_db = str((project.get("check") or {}).get("database", "")).lower()
        if check_db:
            for d in databases:
                keys = [str(d.get("id", "")), str(d.get("ref", "")), str(d.get("name", ""))]
                keys += [str(a) for a in (d.get("aliases") or [])]
                if any(k.lower() == check_db for k in keys if k):
                    db = d
                    break
    if not db and project.get("default"):
        for d in databases:
            if str(d.get("id", "")).lower() == str(project.get("default", "")).lower():
                db = d
                break
    if not db and databases:
        db = databases[0]
    if not db:
        print("ОШИБКА: в .v8-project.json нет ни одной базы.")
        return 1

    check_config = project.get("check") or {}
    build = check_config.get("build") or {}

    src_dir = ""
    if build.get("srcDir"):
        src_dir = os.path.join(project_root, build["srcDir"])
    elif db.get("extensions"):
        first = db["extensions"][0] or {}
        if first.get("src"):
            src_dir = os.path.join(project_root, first["src"])

    config_xml = ""
    if build.get("configXml"):
        config_xml = os.path.join(project_root, build["configXml"])
    elif src_dir:
        config_xml = os.path.join(src_dir, "Configuration.xml")

    cfe_pattern = build.get("cfePattern") or "*.cfe"
    checklist_path = args.Checklist or ""
    if not checklist_path and check_config.get("checklist"):
        checklist_path = os.path.join(project_root, check_config["checklist"])
    if not checklist_path:
        fallback = os.path.join(project_root, "checks", "current.md")
        if os.path.isfile(fallback):
            checklist_path = fallback

    url = args.Url or check_config.get("url") or ""

    checks = []
    source_version, ext_name = read_version(config_xml)
    newest_source = newest_file(src_dir) if src_dir and os.path.isdir(src_dir) else None

    if not args.SkipPreflight:
        if not src_dir or not os.path.isdir(src_dir):
            add(checks, "Исходники", "FAIL", "каталог не найден: " + src_dir)
        else:
            when = fmt_time(newest_source[0]) if newest_source else "пусто"
            add(checks, "Исходники", "OK", "%s (изменён %s)" % (src_dir, when))

        load_ts, load_dir = latest_log_dir(r"db_load_xml_\d+")
        if not load_dir:
            add(checks, "Загрузка", "WARN", "лог загрузки не найден — подтвердите загрузку вручную")
        else:
            load_text = read_text(os.path.join(load_dir, "load_log.txt"))
            fresh = newest_source is None or load_ts >= newest_source[0]
            low = load_text.lower()
            if "load completed successfully" in low and fresh:
                add(checks, "Загрузка", "OK", "успешно, " + fmt_time(load_ts))
            elif fresh and ("error" in low or "ошибка" in low):
                add(checks, "Загрузка", "FAIL", "последняя загрузка с ошибкой (%s)" % fmt_time(load_ts))
            elif fresh:
                add(checks, "Загрузка", "WARN", "результат последней загрузки не подтверждён (%s)" % fmt_time(load_ts))
            else:
                add(checks, "Загрузка", "WARN", "нет подтверждения загрузки новее исходников (%s)" % fmt_time(load_ts))

        update_ts, update_dir = latest_log_dir(r"db_update_\d+")
        if not update_dir:
            add(checks, "Обновление БД", "WARN", "лог обновления не найден")
        else:
            update_text = read_text(os.path.join(update_dir, "update_log.txt"))
            fresh = newest_source is None or update_ts >= newest_source[0]
            low = update_text.lower()
            locked = ("блокировки" in low or "фоновое задание" in low)
            failed = ("error" in low or "ошибка" in low)
            if "updated successfully" in low and fresh:
                add(checks, "Обновление БД", "OK", "успешно, " + fmt_time(update_ts))
            elif fresh and locked:
                add(checks, "Обновление БД", "FAIL",
                    "база была заблокирована (конфигуратор/фоновое задание) — освободите и повторите UpdateDBCfg")
            elif fresh and failed:
                add(checks, "Обновление БД", "FAIL", "последнее обновление с ошибкой (%s)" % fmt_time(update_ts))
            elif fresh:
                add(checks, "Обновление БД", "WARN", "результат последнего обновления не подтверждён (%s)" % fmt_time(update_ts))
            else:
                add(checks, "Обновление БД", "WARN", "нет подтверждения обновления новее исходников (%s)" % fmt_time(update_ts))

        if newest_source and load_dir:
            if load_ts < newest_source[0]:
                add(checks, "Свежесть загрузки", "FAIL", "исходники новее последней загрузки — нужна повторная загрузка")
            else:
                add(checks, "Свежесть загрузки", "OK", "исходники не новее загрузки")

        if load_dir and update_dir:
            if update_ts < load_ts:
                add(checks, "Свежесть обновления", "FAIL", "загружено, но БД не обновлена после загрузки")
            else:
                add(checks, "Свежесть обновления", "OK", "обновление после загрузки")

        import fnmatch
        mask = os.path.basename(cfe_pattern)
        if not build.get("cfePattern") and ext_name:
            mask = ext_name + "_*.cfe"
        pattern = cfe_pattern if os.path.isabs(cfe_pattern) else os.path.join(project_root, cfe_pattern)
        cfe_files = []
        directory = os.path.dirname(pattern) or "."
        search_dirs = [directory]
        if not (build.get("cfePattern")):
            search_dirs.append(os.path.join(project_root, "build"))
        for d in search_dirs:
            if not os.path.isdir(d):
                continue
            for f in os.listdir(d):
                if fnmatch.fnmatch(f.lower(), mask.lower()):
                    cfe_files.append(os.path.join(d, f))
        cfe_files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        cfe = cfe_files[0] if cfe_files else None
        if not cfe:
            add(checks, "CFE", "WARN", "не найден по маске " + cfe_pattern)
        else:
            if newest_source and os.path.getmtime(cfe) < newest_source[0]:
                add(checks, "CFE", "FAIL", "сборка старше исходников: " + os.path.basename(cfe))
            else:
                add(checks, "CFE", "OK", os.path.basename(cfe))
            m = re.search(r"_(\d+\.\d+\.\d+)\.cfe$", os.path.basename(cfe), re.IGNORECASE)
            if m and source_version:
                if m.group(1) != source_version:
                    add(checks, "Версия CFE", "FAIL", "CFE %s <> Configuration.xml %s" % (m.group(1), source_version))
                else:
                    add(checks, "Версия CFE", "OK", "совпадает: " + source_version)

        if checklist_path and os.path.isfile(checklist_path):
            checklist_text = read_text(checklist_path)
            if source_version and source_version not in checklist_text:
                add(checks, "Чек-лист", "WARN", "не упоминает версию " + source_version)
            else:
                add(checks, "Чек-лист", "OK", checklist_path)
        else:
            add(checks, "Чек-лист", "WARN", "не найден — шаги проверки не заданы")

        if url:
            m = re.search(r"e1cib/(?:app|data)/([^./]+)\.([^/?]+)", url)
            if m:
                kind, obj_name = m.group(1), m.group(2)
                folder = URL_FOLDERS.get(kind)
                if folder and src_dir:
                    obj_file = os.path.join(src_dir, folder, obj_name + ".xml")
                    if os.path.isfile(obj_file):
                        add(checks, "Цель URL", "OK", kind + "." + obj_name)
                    else:
                        add(checks, "Цель URL", "FAIL", "%s.%s не найдена в исходниках" % (kind, obj_name))

        locked = designer_running(str(db.get("ref", "")))
        if locked is None:
            add(checks, "Блокировка", "WARN", "не удалось проверить процессы")
        elif locked:
            add(checks, "Блокировка", "WARN", "конфигуратор этой базы запущен — обновление БД будет невозможно")
        else:
            add(checks, "Блокировка", "OK", "конфигуратор базы не запущен")

        if args.Deep and ext_name:
            base_args = ["-InfoBaseServer", str(db.get("server", "")),
                         "-InfoBaseRef", str(db.get("ref", "")),
                         "-UserName", str(db.get("user", "")),
                         "-Password", str(db.get("password", ""))]
            rc, out = run_admin(base_args + ["-Command", "check", "-Checks", "apply"])
            low = out.lower()
            if rc == 0 and "ошиб" not in low and "error" not in low and "fail" not in low:
                add(checks, "Применимость", "OK", "расширения применимы к конфигурации")
            elif rc == -1:
                add(checks, "Применимость", "WARN", "проверка не выполнена (таймаут)")
            else:
                add(checks, "Применимость", "FAIL", "проверка применимости не пройдена — смотрите лог")

            rc, out = run_admin(base_args + ["-Command", "list"])
            found = re.search(re.escape(ext_name) + r"[^\n]*?(\d+\.\d+\.\d+)", out)
            if rc == 0 and found:
                db_version = found.group(1)
                if source_version and db_version != source_version:
                    add(checks, "Версия в базе", "FAIL",
                        "в базе %s, в исходниках %s — примените CFE" % (db_version, source_version))
                else:
                    add(checks, "Версия в базе", "OK", "совпадает: " + db_version)
            else:
                add(checks, "Версия в базе", "WARN", "не удалось определить версию расширения " + ext_name)

    fail_count = sum(1 for c in checks if c["status"] == "FAIL")
    warn_count = sum(1 for c in checks if c["status"] == "WARN")

    summary = {
        "project": project.get("name", ""),
        "database": db.get("name", ""),
        "ref": db.get("ref", ""),
        "url": url,
        "checks": checks,
        "fail": fail_count,
        "warn": warn_count,
        "launched": False,
        "pid": None,
        "checklist": checklist_path if checklist_path and os.path.isfile(checklist_path) else "",
    }

    if not args.SkipPreflight and not args.Json:
        title = "=== Предварительная проверка: %s / %s ===" % (project.get("name") or db.get("name", ""), db.get("name", ""))
        print(title)
        for c in checks:
            print("[%-4s] %s: %s" % (c["status"], c["name"], c["text"]))
        if fail_count:
            print("ИТОГ: есть блокирующие проблемы (%d) — запуск отменён." % fail_count)
        elif warn_count:
            print("ИТОГ: можно запускать, предупреждений: %d." % warn_count)
        else:
            print("ИТОГ: все проверки пройдены.")

    run_args = [sys.executable, "-u", DB_RUN,
                "-InfoBaseServer", str(db.get("server", "")),
                "-InfoBaseRef", str(db.get("ref", ""))]
    if db.get("user"):
        run_args += ["-UserName", str(db["user"])]
    if db.get("password"):
        run_args += ["-Password", str(db["password"])]
    if url:
        run_args += ["-URL", url]
    if args.CParam:
        run_args += ["-CParam", args.CParam]

    if args.PreflightOnly or args.PrintOnly:
        if args.Json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        shown = list(run_args[2:])
        for i, token in enumerate(shown):
            if i > 0 and shown[i - 1] == "-Password":
                shown[i] = "***"
        print("CMD: " + " ".join(shown))
        return 0 if fail_count == 0 else 2

    if fail_count and not args.Force:
        if args.Json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        print("Запуск отменён: сначала устраните блокирующие проблемы (или -Force).")
        return 2

    try:
        r = subprocess.run(run_args, capture_output=True, text=True, timeout=180,
                           encoding="utf-8", errors="replace")
        out = (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        out = ""
        print("ПРЕДУПРЕЖДЕНИЕ: db-run не ответил за 180 с (клиент мог стартовать)")

    pid_match = re.search(r"PID:\s*(\d+)", out)
    summary["launched"] = True
    summary["pid"] = int(pid_match.group(1)) if pid_match else None

    if args.Json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        line = "Запущено: %s" % db.get("name", "")
        if summary["pid"]:
            line += " (PID %d)" % summary["pid"]
        if url:
            line += "; URL: " + url
        print(line)
        if summary["checklist"]:
            try:
                os.startfile(summary["checklist"])
            except Exception:
                pass
            print("Чек-лист: " + summary["checklist"])

    return 0


if __name__ == "__main__":
    sys.exit(main())
