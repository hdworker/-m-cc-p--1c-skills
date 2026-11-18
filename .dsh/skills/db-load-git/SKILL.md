---
name: db-load-git
description: Загрузка изменений из Git в базу 1С. Используй когда нужно загрузить изменения из гита, обновить базу из репозитория, partial load из коммита
---

# db-load-git — Загрузка изменений из Git

Определяет изменённые файлы конфигурации по данным Git и выполняет частичную загрузку в информационную базу.

> Если в изменениях есть `Configuration.xml`, платформа выполнит **полную загрузку конфигурации**, а не только изменённых объектов.

> Удалённый объект уйдёт из базы, только если удалён и из состава владельца (`ChildObjects` объекта или `Configuration.xml`). Удалённый файл-часть объекта (модуль, файлы `Ext/`) загрузкой частями не удаляется: скрипт перечислит такие удаления в `[ВНИМАНИЕ]`, а если кроме них загружать нечего, завершится ошибкой. Применить их можно только полной загрузкой (`db-load-xml -Mode Full`); чтобы убрать код модуля, достаточно оставить файл пустым.

## Usage

```
python "$env:USERPROFILE\.dsh\skills\db-load-git\scripts\db-load-git.py" [database]
python "$env:USERPROFILE\.dsh\skills\db-load-git\scripts\db-load-git.py" dev                              — все незафиксированные изменения
python "$env:USERPROFILE\.dsh\skills\db-load-git\scripts\db-load-git.py" dev -Source Staged               — только staged
python "$env:USERPROFILE\.dsh\skills\db-load-git\scripts\db-load-git.py" dev -Source Commit -CommitRange "HEAD~3..HEAD"
python "$env:USERPROFILE\.dsh\skills\db-load-git\scripts\db-load-git.py" dev -DryRun                      — только показать что будет загружено
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
Если в записи базы указан `configSrc` — используй как каталог конфигурации.

## Команда

```powershell
python "$env:USERPROFILE\.dsh\skills\db-load-git/scripts/db-load-git.py" <параметры>
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
| `-ConfigDir <путь>` | да | Каталог XML-выгрузки (git-репозиторий) |
| `-Source <источник>` | нет | `All` (по умолч.) / `Staged` / `Unstaged` / `Commit` |
| `-CommitRange <range>` | для Commit | Диапазон коммитов (напр. `HEAD~3..HEAD`) |
| `-Extension <имя>` | нет | Загрузить в расширение |
| `-NoApplyCheck` | нет | Не проверять применимость расширения после загрузки |
| `-Format <формат>` | нет | `Hierarchical` (по умолч.) / `Plain` |
| `-DryRun` | нет | Только показать что будет загружено (без загрузки) |
| `-UpdateDB` | нет | После загрузки сразу обновить конфигурацию БД (`/UpdateDBCfg`) |
| `-AdditionalV8Arguments <список>` | нет | Доп. аргументы запуска `1cv8.exe` через запятую, напр. `/UseHwLicenses+` |
| `-AdditionalIbcmdArguments <список>` | нет | Доп. аргументы `ibcmd` через запятую, в форме `--ключ=значение` |

> `*` — нужен либо `-InfoBasePath`, либо пара `-InfoBaseServer` + `-InfoBaseRef`

## После выполнения

Если `-UpdateDB` не был указан — **предложить `db-update`** для применения изменений к БД

## Примеры

```powershell
# Все незафиксированные изменения
python "$env:USERPROFILE\.dsh\skills\db-load-git/scripts/db-load-git.py" -V8Path "C:\Program Files\1cv8\8.3.25.1257\bin" -InfoBasePath "C:\Bases\MyDB" -ConfigDir "C:\WS\cfsrc" -Source All -UpdateDB

# Из диапазона коммитов
python "$env:USERPROFILE\.dsh\skills\db-load-git/scripts/db-load-git.py" -InfoBasePath "C:\Bases\MyDB" -ConfigDir "C:\WS\cfsrc" -Source Commit -CommitRange "HEAD~3..HEAD"
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
