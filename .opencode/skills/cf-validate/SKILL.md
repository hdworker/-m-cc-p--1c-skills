---
name: cf-validate
description: Валидация конфигурации 1С. Используй после создания или модификации конфигурации для проверки корректности
argument-hint: <ConfigPath> [-Detailed] [-MaxErrors 30]
allowed-tools:
  - Bash
  - Read
  - Glob
---

# /cf-validate — валидация конфигурации 1С

Проверяет Configuration.xml на структурные ошибки: XML well-formedness, InternalInfo, свойства, enum-значения, ChildObjects, DefaultLanguage, файлы языков, каталоги объектов.

## Параметры

| Параметр   | Обяз. | Умолч. | Описание                                      |
|------------|:-----:|---------|-------------------------------------------------|
| ConfigPath | да    | —       | Путь к Configuration.xml или каталогу выгрузки  |
| Detailed   | нет   | —       | Подробный вывод (все проверки, включая успешные) |
| MaxErrors  | нет   | 30      | Остановиться после N ошибок                     |
| OutFile    | нет   | —       | Записать результат в файл (UTF-8 BOM)           |

## Команда

```powershell
python ".opencode/skills/cf-validate/scripts/cf-validate.py" -ConfigPath "upload/cfempty"
python ".opencode/skills/cf-validate/scripts/cf-validate.py" -ConfigPath "upload/cfempty/Configuration.xml"
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
