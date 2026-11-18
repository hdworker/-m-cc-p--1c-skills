---
name: epf-dump
description: Разобрать EPF-файл обработки 1С (EPF/ERF) в XML-исходники. Используй когда пользователь просит разобрать, декомпилировать обработку, получить исходники из EPF/ERF файла
---

# epf-dump — Разборка обработки

## Usage

```
python "$env:USERPROFILE\.dsh\skills\epf-dump\scripts\epf-dump.py" <EpfFile> [OutDir]
```

| Параметр | Обязательный | По умолчанию | Описание                            |
|----------|:------------:|--------------|-------------------------------------|
| EpfFile  | да           | —            | Путь к EPF-файлу                    |
| OutDir   | нет          | `src`        | Каталог для выгрузки исходников     |

## Параметры подключения (обязательно)

Для разборки EPF/ERF требуется информационная база с конфигурацией. Без базы ссылочные типы безвозвратно теряются.

1. Прочитай `.v8-project.json` из корня проекта и разреши базу:
2. Если пользователь указал параметры подключения (путь, сервер) — используй напрямую
3. Если указал базу по имени — ищи по id / alias / name в `.v8-project.json`
4. Если не указал — сопоставь текущую ветку Git с `databases[].branches`
5. Если ветка не совпала — используй `default`
6. Если `.v8-project.json` нет или база не найдена — **сообщи пользователю об ошибке**. Для dump база обязательна: в пустой базе ссылочные типы (CatalogRef, DocumentRef и т.д.) безвозвратно сбрасываются в строки. Предложи указать базу или зарегистрировать через `db-list add`.

Платформа — `v8path` найденной записи базы, иначе корневой `v8path`. Не задан ни там, ни там — `-V8Path` не передавай.
Если использованная база не зарегистрирована — после выполнения предложи добавить через `db-list add`.

## Команда

```powershell
python "$env:USERPROFILE\.dsh\skills\epf-dump/scripts/epf-dump.py" <параметры>
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
| `-InputFile <путь>` | да | Путь к EPF/ERF-файлу |
| `-OutputDir <путь>` | да | Каталог для выгрузки исходников |
| `-Format <формат>` | нет | `Hierarchical` (по умолч.) / `Plain` |
| `-AdditionalV8Arguments <список>` | нет | Доп. аргументы запуска `1cv8.exe` через запятую, напр. `/UseHwLicenses+` |
| `-AdditionalIbcmdArguments <список>` | нет | Доп. аргументы `ibcmd` через запятую, в форме `--ключ=значение` |

> `*` — обязательно хотя бы одно подключение. Без базы скрипт завершится с ошибкой (dump в пустой базе безвозвратно теряет ссылочные типы)

## Примеры

```powershell
# Разборка обработки (файловая база)
python "$env:USERPROFILE\.dsh\skills\epf-dump/scripts/epf-dump.py" -InfoBasePath "C:\Bases\MyDB" -InputFile "build/МояОбработка.epf" -OutputDir "src"

# Серверная база
python "$env:USERPROFILE\.dsh\skills\epf-dump/scripts/epf-dump.py" -InfoBaseServer "srv01" -InfoBaseRef "MyDB" -UserName "Admin" -Password "secret" -InputFile "build/МояОбработка.epf" -OutputDir "src"
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
