---
name: db-create
description: Создание информационной базы 1С. Используй когда нужно создать базу, новую ИБ, пустую базу
---

# db-create — Создание информационной базы

Создаёт новую информационную базу 1С (файловую или серверную) и предлагает зарегистрировать в `.v8-project.json`.

## Usage

```
python "$env:USERPROFILE\.dsh\skills\db-create\scripts\db-create.py" <path>                   — файловая база по указанному пути
python "$env:USERPROFILE\.dsh\skills\db-create\scripts\db-create.py" <server>/<name>          — серверная база
python "$env:USERPROFILE\.dsh\skills\db-create\scripts\db-create.py" — интерактивно
```

## Параметры подключения

Прочитай `.v8-project.json` из корня проекта. Платформа — `v8path` записи создаваемой базы,
если она уже в реестре, иначе корневой `v8path`. Не задан ни там, ни там — `-V8Path` не передавай.
После создания базы предложи зарегистрировать через `db-list add`.

## Команда

```powershell
python "$env:USERPROFILE\.dsh\skills\db-create/scripts/db-create.py" <параметры>
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

Предложи зарегистрировать базу в `.v8-project.json` (через `db-list add`)
3. Если указан шаблон `/UseTemplate` — предупреди что конфигурация будет загружена из шаблона

## Примеры

```powershell
# Создать файловую базу
python "$env:USERPROFILE\.dsh\skills\db-create/scripts/db-create.py" -InfoBasePath "C:\Bases\NewDB"

# Создать серверную базу
python "$env:USERPROFILE\.dsh\skills\db-create/scripts/db-create.py" -InfoBaseServer "srv01" -InfoBaseRef "MyApp_Test"

# Создать из шаблона CF
python "$env:USERPROFILE\.dsh\skills\db-create/scripts/db-create.py" -InfoBasePath "C:\Bases\NewDB" -UseTemplate "C:\Templates\config.cf"

# Создать и добавить в список баз
python "$env:USERPROFILE\.dsh\skills\db-create/scripts/db-create.py" -InfoBasePath "C:\Bases\NewDB" -AddToList -ListName "Новая база"
```

## Запуск в DSH — без ожидания оболочки

Долгий вызов запускай через `pwsh` в фоне: `run_in_background: true` — сразу вернётся job id.
Дальше: `job_output` — хвост лога и результат, `job_list` — статус, `job_kill` — остановка.
DSH сам пришлёт уведомление о завершении; ждать синхронно не нужно.

Совместимость с общим монитором: `python "$env:USERPROFILE\.dsh\skills\_shared\async_run.py" status <RUN_ID>`
(также `start`, `tail`, `list`, `wait`). Данные — `%LOCALAPPDATA%\cc_async`, тот же формат, что у opencode.
Монитор для человека: `python "$env:USERPROFILE\.dsh\skills\_shared\cc-status.py"`.
Очередь по базе: `python "$env:USERPROFILE\.dsh\skills\_shared\queue.py" add|status|list|cancel`.
Полный протокол — `E:\Grishin\Code\_store\PROCESS.md`.
