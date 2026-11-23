---
name: db-update
description: Обновление конфигурации базы данных 1С. Используй когда нужно обновить БД, применить конфигурацию, UpdateDBCfg
---

# db-update — Обновление конфигурации БД

Применяет изменения основной конфигурации к конфигурации базы данных (`/UpdateDBCfg`) —
отдельным шагом после загрузки. У `db-load-xml` и `db-load-git` то же самое делает
ключ `-UpdateDB`.

## Usage

```
python "$env:USERPROFILE\.dsh\skills\db-update\scripts\db-update.py" [database]
python "$env:USERPROFILE\.dsh\skills\db-update\scripts\db-update.py" dev
python "$env:USERPROFILE\.dsh\skills\db-update\scripts\db-update.py" dev -Dynamic on
```

## Параметры подключения

Прочитай `.v8-project.json` из корня проекта и разреши базу:
1. Если пользователь указал параметры подключения (путь, сервер) — используй напрямую
2. Если указал базу по имени — ищи по id / alias / name в `.v8-project.json`
3. Если не указал — сопоставь текущую ветку Git с `databases[].branches`
4. Если ветка не совпала — используй `default`
Платформа — `v8path` найденной записи базы, иначе корневой `v8path`. Не задан ни там, ни там — `-V8Path` не передавай.
Если файла нет — предложи `db-list add`.
Если использованная база не зарегистрирована — после выполнения предложи добавить через `db-list add`.

## Авторизация информационной базы

До вызова установи переменные окружения `ONEC_USER` и `ONEC_PWD`. Авторизация ИБ берётся только из этих переменных; CLI-параметры, `.v8-project.json` и хранилище учётных данных как запасной источник не используются.

## Команда

```powershell
python "$env:USERPROFILE\.dsh\skills\db-update/scripts/db-update.py" <параметры>
```

### Параметры скрипта

| Параметр | Обязательный | Описание |
|----------|:------------:|----------|
| `-V8Path <путь>` | нет | Каталог bin платформы, или полный путь к `1cv8.exe` / `ibcmd.exe` |
| `-InfoBasePath <путь>` | * | Файловая база |
| `-InfoBaseServer <сервер>` | * | Сервер 1С (для серверной базы) |
| `-InfoBaseRef <имя>` | * | Имя базы на сервере |
| `-Extension <имя>` | нет | Обновить расширение |
| `-AllExtensions` | нет | Обновить все расширения |
| `-NoApplyCheck` | нет | Не проверять применимость расширения после обновления |
| `-Dynamic <on/off>` | нет | `on` — динамическое обновление, без монопольного доступа к базе; `off` — отключить |
| `-Server` | нет | Обновление на стороне сервера |
| `-WarningsAsErrors` | нет | Предупреждения считать ошибками |
| `-AdditionalV8Arguments <список>` | нет | Доп. аргументы запуска `1cv8.exe` через запятую, напр. `/UseHwLicenses+` |
| `-AdditionalIbcmdArguments <список>` | нет | Доп. аргументы `ibcmd` через запятую, в форме `--ключ=значение` |

> `*` — нужен либо `-InfoBasePath`, либо пара `-InfoBaseServer` + `-InfoBaseRef`

### Фоновое обновление (серверная база)

| Параметр | Описание |
|----------|----------|
| `-BackgroundStart` | Начать фоновое обновление |
| `-BackgroundFinish` | Дождаться окончания |
| `-BackgroundCancel` | Отменить |
| `-BackgroundSuspend` | Приостановить |
| `-BackgroundResume` | Возобновить |

## Примеры

```powershell
# Обычное обновление (файловая база)
python "$env:USERPROFILE\.dsh\skills\db-update/scripts/db-update.py" -InfoBasePath "C:\Bases\MyDB"

# Динамическое обновление
python "$env:USERPROFILE\.dsh\skills\db-update/scripts/db-update.py" -InfoBaseServer "srv01" -InfoBaseRef "MyDB" -Dynamic on

# Обновление расширения
python "$env:USERPROFILE\.dsh\skills\db-update/scripts/db-update.py" -InfoBasePath "C:\Bases\MyDB" -Extension "МоёРасширение"
```

## Запуск в DSH — без ожидания оболочки

Долгий вызов запускай через `pwsh` с `run_in_background: true` и `CC_SYNC=1`:

```powershell
$env:CC_SYNC='1'; python "$env:USERPROFILE\.dsh\skills\<скилл>\scripts\<скилл>.py" <аргументы>
```

DSH сразу вернёт job id (аналог `RUN_ID`), по завершении пришлёт уведомление.
`job_output` — хвост лога и результат, `job_list` — статус, `job_kill` — остановка.
Ждать синхронно не нужно.

Команда без `CC_SYNC=1` сама уходит в фон через `async_run.py` и печатает `RUN_ID` —
этот путь оставлен для совместимости с opencode и общим монитором:
`python "$env:USERPROFILE\.dsh\skills\_shared\async_run.py" status <RUN_ID>` (также `start`, `tail`, `list`, `wait`).
Данные — `%LOCALAPPDATA%\cc_async`, тот же формат, что у opencode.
Монитор для человека: `python "$env:USERPROFILE\.dsh\skills\_shared\cc-status.py"`.
Полный протокол — `E:\Grishin\Code\_store\PROCESS.md`.
