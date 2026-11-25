---
name: form-edit
description: Роутер для форм 1С: выбери создание новой формы или доработку типовой формы.
disable-model-invocation: true
---

# /form-edit — выбор маршрута

Определи, что меняется, и сообщи пользователю точный следующий навык; роутер не выполняет дочерний workflow.

- **Создать новую собственную форму** — вызови `form-edit-create-own-form` (логическое имя `form-edit:create-own-form`): новая общая/объектная форма, форма обработки или отчёта, в конфигурации, CFE, EPF/ERF.
- **Изменить типовую форму** — вызови `form-edit-extend-typical-form` (логическое имя `form-edit:extend-typical-form`): форма поставщика, в том числе добавление/изменение реквизитов.
- **Точечно изменить уже существующую нетиповую форму** — используй `/form-info`, затем справочник `references/form-edit-operations.md` и валидатор формы.

## Имена навыков

В DSH skill ID допускает только kebab-case; двоеточие не является допустимым символом. Поэтому `form-edit:create-own-form` и `form-edit:extend-typical-form` — логические имена ветвей, а реальные ID — `form-edit-create-own-form` и `form-edit-extend-typical-form`. Эти дочерние навыки можно вызвать напрямую.
