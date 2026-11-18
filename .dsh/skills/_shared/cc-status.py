#!/usr/bin/env python3
"""cc-status.py v2 — современный монитор операций 1С из %LOCALAPPDATA%\\cc_async.

Возможности:
  • alt-screen, без мерцания, скрытый курсор;
  • карточки операций: ● работает (спиннер + прогресс по медиане), ✓ готов, ✗ ошибка, ⚠ убит;
  • панель лога выбранной операции с автопрокруткой (f/Enter);
  • фильтры: Tab — Active/Today/All, / — живой поиск;
  • действия: k — убить процесс, L — полный лог (pager), c — очистить события;
  • маскирование паролей; темы dark/light/mono; --notify (звонок при финале).

Режимы:
  python cc-status.py                 — интерактивный дашборд (q — выход)
  python cc-status.py --once          — один снимок (текст)
  python cc-status.py --once --json   — машиночитаемо
  python cc-status.py --tail RUN_ID   — follow конкретного запуска
  python cc-status.py --prune         — удалить завершённые старше 7 дней
"""

import argparse
import ctypes
import io
import json
import os
import re
import shutil
import statistics
import sys
import time

BASE_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "cc_async")
QUEUE_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "cc_queue")

THEMES = {
    "dark": {"bg": "", "dim": "\033[2m", "reset": "\033[0m", "run": "\033[33m",
             "done": "\033[32m", "fail": "\033[31m", "stale": "\033[38;5;244m",
             "accent": "\033[36m", "sel": "\033[7m", "hl": "\033[1m"},
    "light": {"bg": "", "dim": "\033[2m", "reset": "\033[0m", "run": "\033[35m",
              "done": "\033[32m", "fail": "\033[31m", "stale": "\033[90m",
              "accent": "\033[34m", "sel": "\033[7m", "hl": "\033[1m"},
    "mono": {"bg": "", "dim": "", "reset": "", "run": "", "done": "", "fail": "",
             "stale": "", "accent": "", "sel": "", "hl": ""},
}
SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def enable_vt():
    os.system("")
    try:
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass


def pid_alive(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    h = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)
    if h:
        ctypes.windll.kernel32.CloseHandle(h)
        return True
    return False


def kill_pid(pid):
    try:
        h = ctypes.windll.kernel32.OpenProcess(0x0001, False, int(pid))  # PROCESS_TERMINATE
        if not h:
            return False
        ok = ctypes.windll.kernel32.TerminateProcess(h, 1)
        ctypes.windll.kernel32.CloseHandle(h)
        return bool(ok)
    except Exception:
        return False


def read_text(path, limit=None):
    try:
        with open(path, "rb") as f:
            if limit:
                f.seek(max(0, os.path.getsize(path) - limit))
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def read_tail(path, max_bytes=65536):
    text = read_text(path, max_bytes)
    return [ln.rstrip() for ln in text.splitlines()]


def mask(cmd):
    cmd = re.sub(r"(-Password\s+)\S+", r"\1***", cmd, flags=re.IGNORECASE)
    cmd = re.sub(r"(--password[= ])\S+", r"\1***", cmd, flags=re.IGNORECASE)
    return cmd


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def vlen(s):
    return len(ANSI_RE.sub("", s))


def clip(s, w):
    """Обрезка по ВИДИМОЙ ширине (ANSI-коды не считаются)."""
    if w <= 0:
        return ""
    if vlen(s) <= w:
        return s
    out, vis, i = [], 0, 0
    while i < len(s):
        m = ANSI_RE.match(s, i)
        if m:
            out.append(m.group(0))
            i = m.end()
            continue
        if vis >= w - 1:
            out.append("…")
            break
        out.append(s[i])
        vis += 1
        i += 1
    out.append("\x1b[0m")
    return "".join(out)


def skill_of(raw):
    for tok in raw.split():
        if tok.lower().endswith(".py"):
            return os.path.basename(tok)
    return "(cmd)"


def key_params(raw):
    parts = []
    for flag in ("-Extension", "-Command", "-InfoBaseRef", "-Mode"):
        m = re.search(re.escape(flag) + r"\s+(\S+)", raw)
        if m:
            parts.append(m.group(1))
    return " ".join(parts)


class Run:
    def __init__(self, run_id):
        self.id = run_id
        self.dir = os.path.join(BASE_DIR, run_id)
        meta_p = os.path.join(self.dir, "meta.json")
        self.meta = {}
        if os.path.isfile(meta_p):
            try:
                self.meta = json.loads(read_text(meta_p) or "{}")
            except Exception:
                pass
        raw = self.meta.get("cmd") or read_text(os.path.join(self.dir, "cmd.txt"))
        self.raw = mask(raw)
        self.skill = skill_of(raw)
        self.params = key_params(self.raw)
        base = self.meta.get("base", "")
        self.base = base.split("/")[-1] if base else "-"
        cwd = self.meta.get("cwd", "")
        self.project = os.path.basename(cwd.rstrip("\\/")) if cwd else "-"
        self.pid = read_text(os.path.join(self.dir, "pid")).strip()
        self.start_ts = os.path.getmtime(self.dir)
        try:
            self.start_ts = time.mktime(time.strptime(self.meta.get("started", ""), "%Y-%m-%d %H:%M:%S"))
        except (ValueError, TypeError):
            pass
        ec = os.path.join(self.dir, "exit.code")
        if os.path.isfile(ec):
            self.exit = read_text(ec).strip() or "?"
            self.state = "done" if self.exit == "0" else "fail"
            self.end_ts = os.path.getmtime(ec)
        else:
            self.state = "run" if pid_alive(self.pid) else "stale"
            self.exit = None
            self.end_ts = None

    @property
    def elapsed(self):
        return (self.end_ts or time.time()) - self.start_ts

    def dur_text(self):
        s = int(self.elapsed)
        if s < 60:
            return "%2ds" % s
        if s < 3600:
            return "%dm%02ds" % (s // 60, s % 60)
        return "%dh%02dm" % (s // 3600, (s % 3600) // 60)

    def last_line(self):
        out = read_tail(os.path.join(self.dir, "out.log"), 8192)
        if self.state == "fail":
            err = read_tail(os.path.join(self.dir, "err.log"), 8192)
            out = out + err
        lines = [ln.strip() for ln in out if ln.strip()]
        return lines[-1] if lines else ""

    def log_lines(self, limit_bytes=262144):
        return read_tail(os.path.join(self.dir, "out.log"), limit_bytes)


def history_medians():
    med = {}
    by_skill = {}
    if not os.path.isdir(BASE_DIR):
        return med
    for d in os.listdir(BASE_DIR):
        p = os.path.join(BASE_DIR, d)
        ec = os.path.join(p, "exit.code")
        if not (os.path.isdir(p) and os.path.isfile(ec)):
            continue
        try:
            r = Run(d)
        except OSError:
            continue
        if r.end_ts and r.elapsed > 0:
            by_skill.setdefault(r.skill, []).append(r.elapsed)
    for k, vals in by_skill.items():
        if len(vals) >= 1:
            med[k] = statistics.median(vals)
    return med


def scan(needle=""):
    runs = []
    if not os.path.isdir(BASE_DIR):
        return runs
    for d in os.listdir(BASE_DIR):
        p = os.path.join(BASE_DIR, d)
        if not os.path.isdir(p):
            continue
        try:
            r = Run(d)
        except OSError:
            continue
        if needle and needle.lower() not in (r.base + " " + r.project + " " + r.skill + " " + r.params).lower():
            continue
        runs.append(r)
    runs.sort(key=lambda x: (x.state != "run", -(x.end_ts or x.start_ts)))
    return runs


QUEUE_LABEL = {
    "pending": "ожидает",
    "waiting-lock": "ждёт базу",
    "running": "выполняется",
    "done": "готов",
    "failed": "ошибка",
    "blocked-version": "версия!",
    "expired": "просрочен",
    "cancelled": "отменён",
}

HUMAN = {
    "db-load-xml.py": "загрузка XML в базу",
    "db-update.py": "применение конфигурации",
    "db-dump-cf.py": "сборка CFE",
    "db-dump-xml.py": "выгрузка XML",
    "db-dump-dt.py": "выгрузка базы (DT)",
    "db-load-cf.py": "загрузка CF",
    "db-load-dt.py": "загрузка базы (DT)",
    "db-create.py": "создание базы",
    "db-run.py": "запуск 1С",
    "db-load-git.py": "загрузка из git",
    "db-repo.py": "операции хранилища",
    "db-cfe-admin.py": "расширения в базе",
    "cf-info.py": "анализ конфигурации",
    "cf-edit.py": "правка конфигурации",
    "cf-init.py": "новая конфигурация",
    "cf-validate.py": "валидация конфигурации",
    "cfe-init.py": "новое расширение",
    "cfe-validate.py": "валидация расширения",
    "cfe-borrow.py": "заимствование объектов",
    "cfe-diff.py": "анализ расширения",
    "cfe-patch-method.py": "перехват метода",
    "epf-build.py": "сборка обработки",
    "epf-dump.py": "разбор обработки",
    "epf-init.py": "новая обработка",
    "epf-validate.py": "валидация обработки",
    "erf-build.py": "сборка отчёта",
    "erf-dump.py": "разбор отчёта",
    "erf-init.py": "новый отчёт",
    "erf-validate.py": "валидация отчёта",
    "form-add.py": "добавление формы",
    "form-compile.py": "сборка формы",
    "form-decompile.py": "разбор формы",
    "form-edit.py": "правка формы",
    "form-info.py": "анализ формы",
    "form-remove.py": "удаление формы",
    "form-validate.py": "валидация формы",
    "meta-compile.py": "создание метаданных",
    "meta-decompile.py": "разбор метаданных",
    "meta-edit.py": "правка метаданных",
    "meta-info.py": "анализ метаданных",
    "meta-remove.py": "удаление метаданных",
    "meta-validate.py": "валидация метаданных",
    "skd-compile.py": "сборка СКД",
    "skd-decompile.py": "разбор СКД",
    "skd-edit.py": "правка СКД",
    "skd-info.py": "анализ СКД",
    "skd-validate.py": "валидация СКД",
    "mxl-compile.py": "сборка макета",
    "mxl-decompile.py": "разбор макета",
    "mxl-info.py": "анализ макета",
    "mxl-validate.py": "валидация макета",
    "role-compile.py": "создание роли",
    "role-edit.py": "правка роли",
    "role-info.py": "анализ роли",
    "role-validate.py": "валидация роли",
    "subsystem-compile.py": "создание подсистемы",
    "subsystem-edit.py": "правка подсистемы",
    "subsystem-info.py": "анализ подсистемы",
    "subsystem-validate.py": "валидация подсистемы",
    "xdto-compile.py": "создание XDTO",
    "xdto-decompile.py": "разбор XDTO",
    "xdto-edit.py": "правка XDTO",
    "xdto-info.py": "анализ XDTO",
    "xdto-validate.py": "валидация XDTO",
    "template-add.py": "добавление макета",
    "template-remove.py": "удаление макета",
    "help-add.py": "добавление справки",
    "interface-edit.py": "правка интерфейса",
    "interface-validate.py": "валидация интерфейса",
    "support-edit.py": "поддержка конфигурации",
    "web-publish.py": "веб-публикация",
    "web-unpublish.py": "снятие публикации",
    "web-info.py": "статус веб-сервера",
    "web-stop.py": "остановка веб-сервера",
    "web-test.py": "тест веб-клиента",
    "1c-init": "инициализация проекта",
    "check-task.py": "проверка задачи",
}

CFE_CMD = {
    "check": "проверка расширений",
    "list": "список расширений",
    "set-properties": "свойства расширения",
    "delete": "удаление расширения",
}


def human_of(skill, raw=""):
    if skill == "db-cfe-admin.py":
        m = re.search(r"-Command\s+(\S+)", raw or "", re.IGNORECASE)
        if m:
            return CFE_CMD.get(m.group(1).lower(), "расширения: " + m.group(1))
    return HUMAN.get(skill, "")


def scan_queue(needle=""):
    items = []
    if not os.path.isdir(QUEUE_DIR):
        return items
    for d in os.listdir(QUEUE_DIR):
        p = os.path.join(QUEUE_DIR, d)
        if not os.path.isdir(p):
            continue
        req = read_json_file(os.path.join(p, "request.json"))
        if not req:
            continue
        st = read_json_file(os.path.join(p, "state.json"))
        item = {
            "id": d,
            "state": st.get("state", "pending"),
            "base": req.get("base", ""),
            "project": os.path.basename((req.get("cwd") or "").rstrip("\\/")) or "-",
            "skill": os.path.basename((req.get("script") or "").replace("/", "\\")) or "?",
            "created_ts": 0.0,
            "error": st.get("last_error", ""),
            "next_try": st.get("next_try") or 0,
        }
        try:
            item["created_ts"] = time.mktime(time.strptime(req.get("created", ""), "%Y-%m-%d %H:%M:%S"))
        except (ValueError, TypeError):
            pass
        if needle and needle.lower() not in (item["base"] + " " + item["project"] + " " + item["skill"]).lower():
            continue
        items.append(item)
    items.sort(key=lambda x: (x["state"] in ("done", "failed", "cancelled", "expired"), -x["created_ts"]))
    return items


def read_json_file(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {}


def progress_bar(r, med):
    if r.state != "run":
        return ""
    base = med.get(r.skill)
    if not base or base <= 0:
        return ""
    pct = min(r.elapsed / base, 0.99)
    filled = int(pct * 10)
    return "▓" * filled + "░" * (10 - filled) + " %3d%%" % int(pct * 100)


class App:
    def __init__(self, theme, notify):
        self.c = THEMES.get(theme, THEMES["dark"])
        self.notify = notify
        self.scope = "active"          # active | today | all
        self.filter = ""
        self.sel = 0
        self.follow = True
        self.scroll = 0                # 0 = хвост
        self.events = []               # (ts, text, kind)
        self.prev = {}
        self.pending_kill = None
        self.mode = "list"             # list | fullog | filter
        self.msg = ""
        self.med = history_medians()
        self.last_history = time.time()
        self.run_map = {}
        self.queue = []
        self.human = False

    # ---------- data ----------
    def filtered(self):
        runs = scan(self.filter)
        if self.scope == "active":
            runs = [r for r in runs if r.state in ("run", "stale")]
        elif self.scope == "today":
            today = time.strftime("%Y-%m-%d")
            runs = [r for r in runs if time.strftime("%Y-%m-%d", time.localtime(r.start_ts)) == today]
        else:
            runs = runs[:100]
        return runs

    def current(self, runs):
        if not runs:
            return None
        self.sel = max(0, min(self.sel, len(runs) - 1))
        return runs[self.sel]

    def detect_events(self, runs):
        c = self.c
        now = time.strftime("%H:%M:%S")
        for r in runs:
            old = self.prev.get(r.id)
            if old is None and r.state == "run":
                self.events.append((time.time(), "%s ● старт %s · %s/%s · %s" % (now, r.id, r.project, r.base, r.skill), c["run"]))
            elif old != r.state:
                if r.state == "done":
                    self.events.append((time.time(), "%s ✓ готов %s · %s (%.0fs)" % (now, r.id, r.skill, r.elapsed), c["done"]))
                    if self.notify:
                        sys.stdout.write("\a")
                elif r.state == "fail":
                    self.events.append((time.time(), "%s ✗ ошибка %s · %s exit=%s" % (now, r.id, r.skill, r.exit), c["fail"]))
                    if self.notify:
                        sys.stdout.write("\a")
                elif r.state == "stale":
                    self.events.append((time.time(), "%s ⚠ пропал %s · %s" % (now, r.id, r.skill), c["stale"]))
            self.prev[r.id] = r.state
        self.events = self.events[-20:]

    # ---------- render ----------
    def status_glyph(self, r):
        c = self.c
        if r.state == "run":
            spin = SPIN[int(time.time() * 8) % len(SPIN)]
            return c["run"] + spin
        if r.state == "done":
            return c["done"] + "✓"
        if r.state == "fail":
            return c["fail"] + "✗"
        return c["stale"] + "⚠"

    def render(self, runs):
        c = self.c
        w, h = shutil.get_terminal_size((120, 32))
        w = max(w, 60)
        h = max(h, 16)

        active = [r for r in runs if r.state == "run"]
        finished = [r for r in runs if r.state != "run"]
        today = sum(1 for r in runs if time.strftime("%Y-%m-%d", time.localtime(r.start_ts)) == time.strftime("%Y-%m-%d"))
        fails = sum(1 for r in finished if r.state == "fail")

        self.sel = max(0, min(self.sel, max(0, len(runs) - 1)))
        self.current_rows = runs
        cur = runs[self.sel] if runs else None

        lines = []
        lines.append(clip("%scc_async%s %s  %s● %d в работе%s  %s⏳ %d в очереди%s  ✓ %d сегодня  ✗ %d  · %s%s" % (
            c["hl"], c["reset"], time.strftime("%H:%M:%S"),
            c["run"], len(active), c["reset"],
            c["accent"], len(getattr(self, "queue", [])), c["reset"],
            today, fails,
            {"active": "Active", "today": "Today", "all": "All"}[self.scope],
            ("  /" + self.filter) if self.filter else ""), w))
        lines.append(c["dim"] + "─" * w + c["reset"])

        queue_items = getattr(self, "queue", []) or []
        if self.scope == "active":
            queue_items = [q for q in queue_items
                           if q["state"] not in ("done", "failed", "cancelled", "expired")]
        if queue_items:
            lines.append(c["accent"] + "⏳ ОЧЕРЕДЬ (%d)" % len(queue_items) + c["reset"])
            for q in queue_items[:4]:
                label = QUEUE_LABEL.get(q["state"], q["state"])
                when = ""
                if q["state"] == "waiting-lock" and q["next_try"]:
                    when = "повтор ~" + time.strftime("%H:%M", time.localtime(q["next_try"]))
                exit_txt = ""
                qname = q["skill"]
                if self.human:
                    qname = human_of(q["skill"], "") or q["skill"]
                line = "⏳ %-11s %-8s %-12s %-18s %s %s" % (
                    label, q["base"][:8], q["project"][:12], qname[:18],
                    when, (q["error"] or "")[:60])
                lines.append(clip((c["accent"] if q["state"] in ("pending", "waiting-lock") else c["dim"]) + line + c["reset"], w))
            if len(queue_items) > 4:
                lines.append(c["dim"] + "  … ещё %d" % (len(queue_items) - 4) + c["reset"])
            lines.append("")

        list_h = max(4, h // 2 + 2)
        if self.scope == "active":
            entries = active[: max(0, list_h - 2)]
        else:
            entries = (active + finished)[: max(4, list_h - 4)]
        self.sel = max(0, min(self.sel, max(0, len(entries) - 1)))
        self.current_rows = entries
        cur = entries[self.sel] if entries else None

        if not entries:
            lines.append(c["dim"] + "● активных операций нет   (Tab → Today/All)" + c["reset"])
            lines.append(c["dim"] + "  жду запусков…" + c["reset"])
        else:
            shown_active = False
            shown_finished = False
            for r in entries:
                if r.state == "run":
                    if not shown_active:
                        lines.append(c["run"] + "● В ПРОЦЕССЕ" + c["reset"])
                        shown_active = True
                    lines.append(self.row(r, c["hl"] + c["run"], w))
                else:
                    if not shown_finished:
                        lines.append("")
                        lines.append(c["dim"] + "ЗАВЕРШЁННЫЕ" + c["reset"])
                        shown_finished = True
                    lines.append(self.row(r, c["dim"], w))
            if self.scope == "active" and finished:
                lines.append(c["dim"] + "  скрыто завершённых: %d (Tab — показать)" % len(finished) + c["reset"])
            elif self.scope != "active" and len(active) + len(finished) > len(entries):
                lines.append(c["dim"] + "  … скрыто %d (Tab — охват)" % (len(active) + len(finished) - len(entries)) + c["reset"])

        lines.append(c["dim"] + "─" * w + c["reset"])
        log_h = max(3, h - len(lines) - 5)
        if cur:
            state_txt = {"run": "работает", "done": "готов", "fail": "ошибка", "stale": "убит/пропал"}[cur.state]
            cur_name = (human_of(cur.skill, cur.raw) or cur.skill) if self.human else cur.skill
            head = "log: %s · %s (%s) %s" % (cur.id, cur_name, state_txt, cur.params)
            lines.append(clip(c["accent"] + head + c["reset"], w))
            logs = cur.log_lines()
            for ln in logs[-log_h:]:
                lines.append(clip(ln, w))
            while len(lines) < h - 4:
                lines.append("")
        else:
            lines.append(c["dim"] + "выберите операцию (↑↓)" + c["reset"])

        lines.append(c["dim"] + "─" * w + c["reset"])
        toast = ""
        if self.events:
            ts, txt, col = self.events[-1]
            if time.time() - ts < 8:
                toast = col + txt + c["reset"]
        lines.append(clip(toast, w))
        if self.pending_kill:
            lines.append(c["fail"] + "Убить %s? (y/n)" % self.pending_kill + c["reset"])
        elif self.mode == "filter":
            lines.append(c["accent"] + "поиск: " + self.filter + "▌  (Enter — применить, Esc — отмена)" + c["reset"])
        else:
            lines.append(c["dim"] + "↑↓ выбор · f/Enter следить · / поиск · Tab охват · h подписи · K убить · L лог · c очистить · q выход" + c["reset"])
        return "\n".join(lines[:h])

    def row(self, r, prefix_color, w):
        c = self.c
        selected = (self.sel < len(getattr(self, "current_rows", [])) and
                    r is self.current_rows[self.sel])
        mark = "▸" if selected else " "
        glyph = self.status_glyph(r)
        if r.state == "run":
            when = "старт " + time.strftime("%H:%M", time.localtime(r.start_ts))
        elif r.state == "stale":
            when = "нет процесса"
        else:
            when = "финиш " + time.strftime("%H:%M", time.localtime(r.end_ts))
        bar = progress_bar(r, self.med)
        exit_txt = ("exit=%s" % r.exit) if (r.state == "fail" and r.exit) else ""
        name = r.skill
        if self.human:
            name = human_of(r.skill, r.raw) or r.skill
        line = "%s %s %-8s %-12s %-22s %6s %s %s %s" % (
            mark, glyph, r.base[:8], r.project[:12], name[:22], r.dur_text(),
            when, exit_txt, (bar + " " if bar else "") + r.params)
        if selected:
            return clip(c["sel"] + line + c["reset"], w)
        return clip(prefix_color + line + c["reset"], w)

    def draw(self, runs):
        frame = self.render(runs)
        out = ["\x1b[H"]
        for line in frame.splitlines():
            out.append(line + "\x1b[K\r\n")
        out.append("\x1b[J")
        sys.stdout.write("".join(out))

    def pager(self, cur):
        """Полноэкранный просмотр лога (L). q/L — назад."""
        c = self.c
        logs = cur.log_lines(2 * 1024 * 1024)
        pos = max(0, len(logs) - 30)
        while True:
            w, h = shutil.get_terminal_size((120, 32))
            view = logs[pos:pos + h - 2]
            frame = [c["accent"] + "log %s · %s  (PgUp/PgDn/↑↓, q — назад)" % (cur.id, cur.skill) + c["reset"]]
            frame += [ln[:w] for ln in view]
            out = ["\x1b[H"]
            for ln in frame:
                out.append(clip(ln, w) + "\x1b[K\r\n")
            out.append("\x1b[J")
            sys.stdout.write("".join(out))
            key = self.read_key(0.5)
            if key in ("q", "Q", "L", "\x1b"):
                return
            if key in ("PAGEUP",):
                pos = max(0, pos - (h - 4))
            elif key in ("PAGEDOWN",):
                pos = min(max(0, len(logs) - (h - 2)), pos + (h - 4))
            elif key in ("UP",):
                pos = max(0, pos - 1)
            elif key in ("DOWN",):
                pos = min(max(0, len(logs) - (h - 2)), pos + 1)

    # ---------- keys ----------
    def read_key(self, timeout):
        import msvcrt
        end = time.time() + timeout
        while time.time() < end:
            if msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch in ("\x00", "\xe0"):
                    ch2 = msvcrt.getwch()
                    return {"H": "UP", "P": "DOWN", "I": "PAGEUP", "Q": "PAGEDOWN",
                            "G": "HOME", "O": "END", "K": "LEFT", "M": "RIGHT"}.get(ch2, "")
                return ch
            time.sleep(0.03)
        return ""

    def run(self):
        enable_vt()
        sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[2J")
        sys.stdout.flush()
        try:
            while True:
                if time.time() - self.last_history > 60:
                    self.med = history_medians()
                    self.last_history = time.time()
                runs = self.filtered()
                self.queue = scan_queue(self.filter)
                self.detect_events(runs)
                self.draw(runs)
                sys.stdout.flush()
                key = self.read_key(0.25)
                if not key:
                    continue
                cur = self.current(runs)
                if self.pending_kill:
                    if key.lower() == "y" and cur:
                        ok = kill_pid(cur.pid) if cur.pid else False
                        self.msg = "убит" if ok else "не удалось"
                    self.pending_kill = None
                    continue
                if self.mode == "filter":
                    if key == "\r":
                        self.mode = "list"
                    elif key == "\x1b":
                        self.filter = ""
                        self.mode = "list"
                    elif key in ("\x08", "\x7f"):
                        self.filter = self.filter[:-1]
                        self.sel = 0
                    elif key.isprintable() and key != "\r":
                        self.filter += key
                        self.sel = 0
                    continue
                if key in ("q", "Q", "\x03"):
                    return 0
                if key in ("DOWN", "j"):
                    self.sel += 1
                elif key in ("UP", "k"):
                    self.sel -= 1
                elif key in ("f", "F", "\r"):
                    self.follow = not self.follow
                elif key == "/":
                    self.mode = "filter"
                elif key == "\t":
                    self.scope = {"active": "today", "today": "all", "all": "active"}[self.scope]
                    self.sel = 0
                elif key == "K":
                    if cur and cur.state == "run":
                        self.pending_kill = cur.id
                elif key in ("L",):
                    if cur:
                        sys.stdout.write("\x1b[?25h\x1b[2J")
                        self.pager(cur)
                        sys.stdout.write("\x1b[?25l")
                elif key == "c":
                    self.events = []
                elif key in ("h", "H"):
                    self.human = not self.human
        finally:
            sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
            sys.stdout.flush()


def tail_run(run_id):
    enable_vt()
    d = os.path.join(BASE_DIR, run_id)
    if not os.path.isdir(d):
        print("не найден запуск: " + run_id)
        return 1
    pos = 0
    print("— follow %s (Ctrl+C выход) —" % run_id)
    try:
        while True:
            p = os.path.join(d, "out.log")
            if os.path.isfile(p):
                size = os.path.getsize(p)
                if size >= pos:
                    with open(p, "rb") as f:
                        f.seek(pos)
                        data = f.read()
                        pos = f.tell()
                    if data:
                        sys.stdout.write(data.decode("utf-8", errors="replace"))
                        sys.stdout.flush()
            ec = os.path.join(d, "exit.code")
            if os.path.isfile(ec):
                sys.stdout.write("\n[завершён, exit=%s]\n" % read_text(ec).strip())
                return 0
            time.sleep(0.7)
    except KeyboardInterrupt:
        return 0


def prune():
    cutoff = time.time() - 7 * 86400
    doomed = []
    for d in os.listdir(BASE_DIR):
        p = os.path.join(BASE_DIR, d)
        ec = os.path.join(p, "exit.code")
        if os.path.isdir(p) and os.path.isfile(ec) and os.path.getmtime(ec) < cutoff:
            doomed.append(p)
    if not doomed:
        print("нечего удалять (старше 7 дней нет)")
        return 0
    for p in doomed:
        shutil.rmtree(p, ignore_errors=True)
    print("удалено запусков: %d" % len(doomed))
    return 0


def once(json_out):
    runs = scan("")
    med = history_medians()
    if json_out:
        data = [{"id": r.id, "state": r.state, "exit": r.exit, "base": r.base,
                 "project": r.project, "skill": r.skill, "dur": r.dur_text(),
                 "cmd": r.raw, "last": r.last_line()} for r in runs]
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    c = THEMES["mono"]
    qitems = scan_queue("")
    if qitems:
        print("ОЧЕРЕДЬ: %d" % len(qitems))
        for q in qitems:
            print("  %-12s %-8s %-12s %-18s %s" % (
                QUEUE_LABEL.get(q["state"], q["state"]), q["base"][:8],
                q["project"][:12], q["skill"][:18], (q["error"] or "")[:60]))
    print("cc_async  %s" % BASE_DIR)
    print("%-21s %-4s %-9s %-10s %-18s %-24s %6s %-4s %s" % (
        "RUN_ID", "ST", "БАЗА", "ПРОЕКТ", "СКИЛЛ", "ОПЕРАЦИЯ", "ВРЕМЯ", "EXIT", "ПАРАМЕТРЫ"))
    for r in runs:
        st = {"run": "●", "done": "✓", "fail": "✗", "stale": "⚠"}[r.state]
        print("%-21s %-4s %-9s %-10s %-18s %-24s %6s %-4s %s" % (
            r.id, st, r.base[:9], r.project[:10], r.skill[:18],
            (human_of(r.skill, r.raw) or "")[:24], r.dur_text(),
            r.exit if r.exit else "-", r.params))
    return 0


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="cc_async live monitor v2")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--text", action="store_true", help="принудительно текстовый снимок")
    ap.add_argument("--base", default="", help="фильтр по базе/проекту/скиллу")
    ap.add_argument("--tail", metavar="RUN_ID")
    ap.add_argument("--prune", action="store_true")
    ap.add_argument("--theme", default="dark", choices=list(THEMES))
    ap.add_argument("--notify", action="store_true")
    args = ap.parse_args()

    if args.prune:
        return prune()
    if args.tail:
        return tail_run(args.tail)
    if args.once or args.json:
        return once(args.json or (not args.text and not sys.stdout.isatty()))

    app = App(args.theme, args.notify)
    app.filter = args.base
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
