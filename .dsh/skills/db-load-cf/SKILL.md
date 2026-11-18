---
name: db-load-cf
description: Загрузка конфигурации 1С из CF-файла. Используй когда нужно загрузить конфигурацию из CF, восстановить из бэкапа CF
---

# db-load-cf — Загрузка конфигурации из CF-файла

Загружает конфигурацию из бинарного CF-файла в информационную базу.

## Usage

```
python "$env:USERPROFILE\.dsh\skills\db-load-cf\scripts\db-load-cf.py" <input.cf> [database]
python "$env:USERPROFILE\.dsh\skills\db-load-cf\scripts\db-load-cf.py" config.cf dev
```

> **Внимание**: загрузка CF **полностью заменяет** конфигурацию в базе. Перед выполнением запроси подтверждение у пользователя.

## Параметры подключения

Прочитай `.v8-project.json` из корня проекта и разреши базу:
1. Если пользователь указал параметры подключения (путь, сервер) — используй напрямую
2. Если указал базу по имени — ищи по id / alias / name в `.v8-project.json`
3. Если не указал — сопоставь текущую ветку Git с `databases[].branches`
4. Если ветка не совпала — используй `default`
Платформа — `v8path` найденной записи базы, иначе корневой `v8path`. Не задан ни там, ни там — `-V8Path` не передавай.
Если файла нет — предложи `db-list add`.
Если использованная база не зарегистрирована — после выполнения предложи добавить через `db-list add`.

## Команда

```powershell
python "$env:USERPROFILE\.dsh\skills\db-load-cf/scripts/db-load-cf.py" <параметры>
```

### Параметры скрипта

| Параметр | Обязательный | Описание |
|----------|:------------:|----------|
| `-V8Path <путь>` | нет | Каталог bin платформы, или полный путь к `1cv8.exe` / `ibcmd.exe` |
| `-InfoBasePath <путь>` | * | Файловая база |
| `-InfoBaseServer <сервер>` | * | Сервер 1С (для серверной базы) |
| `-InfoBaseRef <имя>` | * | Имя базы на сервере |
| `-UserName <имя>` | нет | Имя пользователя |
| `-Password <пароль>` | нет | Пароль |
| `-InputFile <путь>` | да | Путь к CF-файлу |
| `-Extension <имя>` | нет | Загрузить как расширение |
| `-NoApplyCheck` | нет | Не проверять применимость расширения после загрузки |
| `-AllExtensions` | нет | Загрузить все расширения из архива |
| `-AdditionalV8Arguments <список>` | нет | Доп. аргументы запуска `1cv8.exe` через запятую, напр. `/UseHwLicenses+` |
| `-AdditionalIbcmdArguments <список>` | нет | Доп. аргументы `ibcmd` через запятую, в форме `--ключ=значение` |

> `*` — нужен либо `-InfoBasePath`, либо пара `-InfoBaseServer` + `-InfoBaseRef`

## После выполнения

**Предложи выполнить `db-update`** — загрузка CF обновляет только «основную» конфигурацию конфигуратора, для применения к БД нужен `/UpdateDBCfg`

## Примеры

```powershell
# Файловая база
python "$env:USERPROFILE\.dsh\skills\db-load-cf/scripts/db-load-cf.py" -InfoBasePath "C:\Bases\MyDB" -UserName "Admin" -InputFile "C:\backup\config.cf"

# Серверная база
python "$env:USERPROFILE\.dsh\skills\db-load-cf/scripts/db-load-cf.py" -InfoBaseServer "srv01" -InfoBaseRef "MyApp_Test" -UserName "Admin" -Password "secret" -InputFile "config.cf"

# Загрузка расширения
python "$env:USERPROFILE\.dsh\skills\db-load-cf/scripts/db-load-cf.py" -InfoBasePath "C:\Bases\MyDB" -UserName "Admin" -InputFile "ext.cfe" -Extension "МоёРасширение"
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
