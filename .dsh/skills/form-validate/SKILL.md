---
name: form-validate
description: Валидация управляемой формы 1С. Используй после создания или модификации формы для проверки корректности
---

# form-validate — валидация управляемой формы 1С

## Параметры

| Параметр  | Обяз. | Умолч. | Описание                                |
|-----------|:-----:|---------|-----------------------------------------|
| FormPath  | да    | —       | Путь к файлу Form.xml                   |
| Detailed  | нет   | —       | Подробный вывод (все проверки, включая успешные) |
| MaxErrors | нет   | 30      | Остановиться после N ошибок              |

## Команда

```powershell
python "$env:USERPROFILE\.dsh\skills\form-validate/scripts/form-validate.py" -FormPath "Catalogs/Номенклатура/Forms/ФормаЭлемента"
python "$env:USERPROFILE\.dsh\skills\form-validate/scripts/form-validate.py" -FormPath "src/МояОбработка/Forms/Форма/Ext/Form.xml"
```

