---
name: cfe-validate
description: Валидация расширения конфигурации 1С (CFE). Используй после создания или модификации расширения для проверки корректности
argument-hint: <ExtensionPath> [-ConfigPath <ConfigDir>] [-Detailed] [-MaxErrors 30]
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /cfe-validate — валидация расширения конфигурации (CFE)

Проверяет структурную корректность расширения: XML-формат, свойства, состав, заимствованные объекты, права ролей. Аналог `/cf-validate`, но для расширений.

Проверяются исходники. Применимость — уже после загрузки в базу: `/db-cfe-admin check`.

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
python ".opencode/skills/cfe-validate/scripts/cfe-validate.py" -ExtensionPath "src\cfe\extname"
python ".opencode/skills/cfe-validate/scripts/cfe-validate.py" -ExtensionPath "src\cfe\extname\Configuration.xml"
python ".opencode/skills/cfe-validate/scripts/cfe-validate.py" -ExtensionPath "src\cfe\extname" -ConfigPath "src\cf"
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
