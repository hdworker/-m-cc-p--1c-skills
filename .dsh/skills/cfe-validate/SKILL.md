---
name: cfe-validate
description: Валидация расширения конфигурации 1С (CFE). Используй после создания или модификации расширения для проверки корректности
---

# cfe-validate — валидация расширения конфигурации (CFE)

Проверяет структурную корректность расширения: XML-формат, свойства, состав, заимствованные объекты, права ролей. Аналог `cf-validate`, но для расширений.

Проверяются исходники. Применимость — уже после загрузки в базу: `db-cfe-admin check`.

## Параметры

| Параметр      | Обяз. | Умолч. | Описание                                        |
|---------------|:-----:|---------|-------------------------------------------------|
| ExtensionPath | да    | —       | Путь к каталогу или Configuration.xml расширения |
| ConfigPath    | нет   | —       | Каталог конфигурации, из которой заимствованы объекты |
| Detailed      | нет   | —       | Подробный вывод (все проверки, включая успешные)  |
| MaxErrors     | нет   | 30      | Остановиться после N ошибок                      |
| OutFile       | нет   | —       | Записать результат в файл                        |

### ConfigPath

Указывай всегда, когда конфигурация-источник доступна: по ней сверяется связь заимствованных объектов с объектами конфигурации и основной язык. Без неё такие расхождения не ловятся, и расширение может пройти валидацию, а потом быть отвергнутым платформой.

Если пользователь не указал путь — определи сам:
1. Прочитай `.v8-project.json` из корня проекта
2. Разреши целевую базу (по имени, ветке или `default`)
3. Возьми её поле `configSrc`

## Команда

```powershell
python "$env:USERPROFILE\.dsh\skills\cfe-validate/scripts/cfe-validate.py" -ExtensionPath "src\cfe\extname"
python "$env:USERPROFILE\.dsh\skills\cfe-validate/scripts/cfe-validate.py" -ExtensionPath "src\cfe\extname\Configuration.xml"
python "$env:USERPROFILE\.dsh\skills\cfe-validate/scripts/cfe-validate.py" -ExtensionPath "src\cfe\extname" -ConfigPath "src\cf"
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
