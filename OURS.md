# Ветки и распространение скиллов (наш форк)

Этот репозиторий — форк `https://github.com/Nikolay-Shirokov/cc-1c-skills.git`.
Ветки `ours/*` содержат нашу версию скиллов, переработанную под процесс разработки 1С.

## Ветки

| Ветка | Формат | Ставится в | Источник |
|---|---|---|---|
| `ours/opencode` | opencode / Claude-стиль (`allowed-tools`, `/команды`) | `%USERPROFILE%\.config\opencode\skills` | `origin/port-opencode-py` |
| `ours/dsh` | DSH (`name`, `description`; вызов `python`, имена инструментов DSH) | `%USERPROFILE%\.dsh\skills` | `origin/main` + адаптация |
| `ours/codex` (при необходимости) | Codex/AGENTS-формат | каталог скиллов Codex | `origin/port-codex-py` |

Общая часть (скрипты `scripts/*.py`, каталог `_shared/`, реестр `.v8-project.json`)
одинакова во всех ветках; различаются только `SKILL.md` и адаптеры.

## Синхронизация с мейнстримом

1. `git fetch upstream` — подтянуть изменения `Nikolay-Shirokov/cc-1c-skills`.
2. Перенести новые коммиты в `ours/<target>` (merge/rebase от соответствующей `port-*-py` ветки).
3. Конфликты решаются в пользу наших доработок там, где они осознанные
   (async/монитор, реестр настроек, Python-вызовы), остальное — как в upstream.
4. Прогнать проверку: число навыков и файлов, загрузка каталога в целевом агенте.

## Распространение на машины

- Сборка: `python tools/skills/pack.py --target dsh|opencode|codex` → архив `dist/skills-<target>-<version>.zip`.
- Установка: `python tools/skills/install.py --target dsh|opencode|codex [--dest <каталог>]`
  (robocopy/копия + проверка файлов и каталога навыков).
- Версия — тег `v<YYYY.MM.DD>-<target>`; в `_store` хранится только указатель
  (`_store\tools\skills.json`: репозиторий, ветка, коммит, target, дата выкладки).

## Правила

- Источник правды по коду — ветка `ours/*`, а не установленный каталог машины.
- Не перезаписывать ветку скиллами из установленного каталога: только коммит из репозитория.
- Крупные референсы и артефакты 1С остаются в `_store`; здесь только скиллы.
