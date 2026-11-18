---
name: db-run
description: Запуск 1С:Предприятие. Используй когда нужно запустить 1С, открыть базу, запустить предприятие
---

# db-run — Запуск 1С:Предприятие

Запускает информационную базу в режиме 1С:Предприятие (пользовательский режим).

## Usage

```
python "$env:USERPROFILE\.dsh\skills\db-run\scripts\db-run.py" [database]
python "$env:USERPROFILE\.dsh\skills\db-run\scripts\db-run.py" dev
python "$env:USERPROFILE\.dsh\skills\db-run\scripts\db-run.py" dev /Execute process.epf
python "$env:USERPROFILE\.dsh\skills\db-run\scripts\db-run.py" dev /C "параметр запуска"
```

## Параметры подключения

Прочитай `.v8-project.json` из корня проекта и разреши базу:
1. Если пользователь указал параметры подключения (путь, сервер) — используй напрямую
2. Если указал базу по имени — ищи по id / alias / name в `.v8-project.json`
3. Если не указал — сопоставь текущую ветку Git с `databases[].branches`
4. Если ветка не совпала — используй `default`
Платформа — `v8path` найденной записи базы, иначе корневой `v8path`. Не задан ни там, ни там — `-V8Path` не передавай.
Если файла нет — предложи `/db-list add`.
Если использованная база не зарегистрирована — после выполнения предложи добавить через `/db-list add`.

## Команда

```powershell
python "$env:USERPROFILE\.dsh\skills\db-run/scripts/db-run.py" <параметры>
```

### Параметры скрипта

| Параметр | Обязательный | Описание |
|----------|:------------:|----------|
| `-V8Path <путь>` | нет | Каталог bin платформы (или полный путь к 1cv8.exe) |
| `-InfoBasePath <путь>` | * | Файловая база |
| `-InfoBaseServer <сервер>` | * | Сервер 1С (для серверной базы) |
| `-InfoBaseRef <имя>` | * | Имя базы на сервере |
| `-UserName <имя>` | нет | Имя пользователя |
| `-Password <пароль>` | нет | Пароль |
| `-Execute <файл.epf>` | нет | Запуск внешней обработки сразу после старта |
| `-CParam <строка>` | нет | Параметр запуска (/C) |
| `-URL <ссылка>` | нет | Навигационная ссылка (формат `e1cib/...`) |
| `-AdditionalV8Arguments <список>` | нет | Доп. аргументы запуска `1cv8.exe` через запятую, напр. `/UseHwLicenses+` |

> `*` — нужен либо `-InfoBasePath`, либо пара `-InfoBaseServer` + `-InfoBaseRef`

## Важно

Скрипт запускает 1С в фоне (`Start-Process` без `-Wait`) — управление возвращается сразу.

## Примеры

```powershell
# Простой запуск
python "$env:USERPROFILE\.dsh\skills\db-run/scripts/db-run.py" -InfoBasePath "C:\Bases\MyDB" -UserName "Admin"

# Запуск с обработкой
python "$env:USERPROFILE\.dsh\skills\db-run/scripts/db-run.py" -InfoBasePath "C:\Bases\MyDB" -UserName "Admin" -Execute "C:\epf\МояОбработка.epf"

# Открыть по навигационной ссылке
python "$env:USERPROFILE\.dsh\skills\db-run/scripts/db-run.py" -InfoBasePath "C:\Bases\MyDB" -UserName "Admin" -URL "e1cib/data/Справочник.Номенклатура"

# Серверная база с параметром запуска
python "$env:USERPROFILE\.dsh\skills\db-run/scripts/db-run.py" -InfoBaseServer "srv01" -InfoBaseRef "MyDB" -UserName "Admin" -Password "secret" -CParam "ЗапуститьОбновление"
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
