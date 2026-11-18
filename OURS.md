# Ветки и выкладка наших скиллов

Форк `Nikolay-Shirokov/cc-1c-skills`. Ветки `ours/*` — наша версия набора, переработанная
под процесс разработки 1С (python вместо PowerShell, асинхронный запуск, реестр `.v8-project.json`).

## Ветки

| Ветка | Каталог в репозитории | Формат | Куда ставится |
|---|---|---|---|
| `ours/opencode` | `.opencode/skills` | opencode/Claude: `allowed-tools`, слэш-команды, MCP `cc` | `%USERPROFILE%\.config\opencode\skills` |
| `ours/dsh` | `.dsh/skills` | DSH: `name`/`description`, вызов python, нативные фоновые задания и `job_output` | `%USERPROFILE%\.dsh\skills` |

Общая часть (`scripts/*.py`, `reference/`, `_shared/`) одинакова; `SKILL.md` в `ours/dsh`
генерируется из `ours/opencode` скриптом `tools/skills/build_target.py`.

## Синхронизация с мейнстримом

1. `git fetch upstream` — изменения `Nikolay-Shirokov/cc-1c-skills`.
2. В `ours/opencode` влить соответствующую ветку `upstream/port-opencode-py`
   (`main` не трогаем: это зеркало апстрима).
3. `ours/dsh` пересобрать: `python tools/skills/build_target.py --from <opencode-skills> --out .dsh/skills`.
4. Проверить: число навыков/файлов и загрузку каталога в целевом агенте.

## Выкладка на машину

```powershell
# DSH
python tools/skills/install.py --target dsh
# opencode
python tools/skills/install.py --target opencode
```

`install.py` переименовывает текущий каталог в `<dest>.bak-<время>` и копирует ветку,
затем сверяет число файлов и печатает манифест `.cc-1c-skills.json` (platform/runtime/mode).

## Правила

- Источник правды — ветка `ours/*`, а не установленный каталог машины.
- Не перезаписывать ветку файлами из установленного каталога.
- В `ours/dsh` нет MCP-сервера `cc` в основном пути: долгие операции — нативные фоновые
  задания DSH (`run_in_background` → `job_output`/`job_kill`); `_shared/async_run.py` и
  `cc-status.py` остаются для совместимости и монитора.
- Крупные артефакты 1С — в `_store`; здесь только скиллы.
