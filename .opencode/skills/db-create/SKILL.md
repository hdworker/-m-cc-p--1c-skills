---
name: db-create
description: Создание информационной базы 1С. Используй когда нужно создать базу, новую ИБ, пустую базу
argument-hint: <path|name>
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
  - AskUserQuestion
---

# /db-create — Создание информационной базы

Создаёт новую информационную базу 1С (файловую или серверную) и предлагает зарегистрировать в `.v8-project.json`.

## Usage

```
/db-create <path>                   — файловая база по указанному пути
/db-create <server>/<name>          — серверная база
/db-create                          — интерактивно
```

## Параметры подключения

Прочитай `.v8-project.json` из корня проекта. Платформа — `v8path` записи создаваемой базы,
если она уже в реестре, иначе корневой `v8path`. Не задан ни там, ни там — `-V8Path` не передавай.
После создания базы предложи зарегистрировать через `/db-list add`.

## Команда

```powershell
python ".opencode/skills/db-create/scripts/db-create.py" <параметры>
```

### Параметры скрипта

| Параметр | Обязательный | Описание |
|----------|:------------:|----------|
| `-V8Path <путь>` | нет | Каталог bin платформы, или полный путь к `1cv8.exe` / `ibcmd.exe` |
| `-InfoBasePath <путь>` | * | Путь к файловой базе |
| `-InfoBaseServer <сервер>` | * | Сервер 1С (для серверной базы) |
| `-InfoBaseRef <имя>` | * | Имя базы на сервере |
| `-UseTemplate <файл>` | нет | Создать из шаблона (.cf или .dt) |
| `-AddToList` | нет | Добавить в список баз 1С |
| `-ListName <имя>` | нет | Имя базы в списке |
| `-AdditionalV8Arguments <список>` | нет | Доп. аргументы запуска `1cv8.exe` через запятую, напр. `/UseHwLicenses+` |
| `-AdditionalIbcmdArguments <список>` | нет | Доп. аргументы `ibcmd` через запятую, в форме `--ключ=значение` |

> `*` — нужен либо `-InfoBasePath`, либо пара `-InfoBaseServer` + `-InfoBaseRef`

## После создания

Предложи зарегистрировать базу в `.v8-project.json` (через `/db-list add`)
3. Если указан шаблон `/UseTemplate` — предупреди что конфигурация будет загружена из шаблона

## Примеры

```powershell
# Создать файловую базу
python ".opencode/skills/db-create/scripts/db-create.py" -InfoBasePath "C:\Bases\NewDB"

# Создать серверную базу
python ".opencode/skills/db-create/scripts/db-create.py" -InfoBaseServer "srv01" -InfoBaseRef "MyApp_Test"

# Создать из шаблона CF
python ".opencode/skills/db-create/scripts/db-create.py" -InfoBasePath "C:\Bases\NewDB" -UseTemplate "C:\Templates\config.cf"

# Создать и добавить в список баз
python ".opencode/skills/db-create/scripts/db-create.py" -InfoBasePath "C:\Bases\NewDB" -AddToList -ListName "Новая база"
```

## Запуск через MCP (`cc`) — без ожидания оболочки

Долгий вызов этого скилла запускать инструментом MCP-сервера `cc`:
`run_start(script="<имя>.py", args=[...])` → `run_id`; затем жди через
`run_wait(run_id, timeout_sec=60)` (для долгих операций — до 600 секунд). Если ожидание
истекло, а задача ещё выполняется, повтори `run_wait`. `run_tail` читай после завершения
или для диагностики; `run_status` используй только для разовой проверки состояния.

Fallback без MCP: `python "C:\Users\Grishin1c\.config\opencode\skills\_shared\async_run.py" start -- python "<этот-скрипт>" <аргументы>`.
Мониторинг: `python "C:\Users\Grishin1c\.config\opencode\skills\_shared\cc-status.py"`.
Полный протокол — `E:\Grishin\Code\_store\PROCESS.md`.
