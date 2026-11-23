---
name: db-dump-dt
description: Выгрузка информационной базы 1С в DT-файл (вся база — конфигурация + данные). Используй когда нужно выгрузить информационную базу, выгрузить архив базы, сделать бэкап, выгрузить dt
---

# db-dump-dt — Выгрузка информационной базы в DT-файл

Выгружает информационную базу целиком (конфигурация **+ данные**) в DT-файл — полный снимок ИБ.

> В отличие от `db-dump-cf` (только конфигурация), `.dt` содержит **всю базу**: данные,
> настройки, пользователей. Это бэкап/точка отката, а не выгрузка метаданных.

## Usage

```
python "$env:USERPROFILE\.dsh\skills\db-dump-dt\scripts\db-dump-dt.py" [database] [output.dt]
python "$env:USERPROFILE\.dsh\skills\db-dump-dt\scripts\db-dump-dt.py" dev backup.dt
python "$env:USERPROFILE\.dsh\skills\db-dump-dt\scripts\db-dump-dt.py" — база по умолчанию, имя файла по базе и дате
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
python "$env:USERPROFILE\.dsh\skills\db-dump-dt/scripts/db-dump-dt.py" <параметры>
```

### Параметры скрипта

| Параметр | Обязательный | Описание |
|----------|:------------:|----------|
| `-V8Path <путь>` | нет | Каталог bin платформы, или полный путь к `1cv8.exe` / `ibcmd.exe` |
| `-InfoBasePath <путь>` | * | Файловая база |
| `-InfoBaseServer <сервер>` | * | Сервер 1С (для серверной базы) |
| `-InfoBaseRef <имя>` | * | Имя базы на сервере |
| `-OutputFile <путь>` | да | Путь к выходному DT-файлу |
| `-AdditionalV8Arguments <список>` | нет | Доп. аргументы запуска `1cv8.exe` через запятую, напр. `/UseHwLicenses+` |
| `-AdditionalIbcmdArguments <список>` | нет | Доп. аргументы `ibcmd` через запятую, в форме `--ключ=значение` |

> `*` — нужен либо `-InfoBasePath`, либо пара `-InfoBaseServer` + `-InfoBaseRef`

## Примеры

```powershell
# Выгрузка ИБ (файловая база)
python "$env:USERPROFILE\.dsh\skills\db-dump-dt/scripts/db-dump-dt.py" -InfoBasePath "C:\Bases\MyDB" -OutputFile "C:\backup\base.dt"

# Серверная база
python "$env:USERPROFILE\.dsh\skills\db-dump-dt/scripts/db-dump-dt.py" -InfoBaseServer "srv01" -InfoBaseRef "MyApp_Dev" -OutputFile "base.dt"
```

## Связанные навыки

- `db-load-dt` — загрузка ИБ из DT (обратная операция)
- `db-dump-cf` — выгрузка только конфигурации (без данных)
- `db-create` — создать новую базу (в т.ч. из DT-шаблона)

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
