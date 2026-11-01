status: done
commits: 2d2ddb44efce297375c85f888d5aa2c32cf80096

В ветке `handoff/IDEA-08EFF217` к каждой сделке в результатах поиска добавлена
кнопка «🧾 Запросить общий счёт №…». Она за одно действие открывает существующий
предпросмотр полного счёта с явной привязкой к ID сделки. Создание счёта по-прежнему
выполняется только отдельной кнопкой подтверждения; предпросмотр записей CRM не делает.

Проверки:

- воспроизведение до исправления: новый HumanJourneyCase не находил прямую кнопку;
- `python3 -m unittest test_human_quick_actions` — 15/15, успешно;
- `QuickActionJourneys.test_search_result_opens_full_invoice_preview_in_one_action`:
  поиск + одно нажатие до предпросмотра, 0 CRM-записей, 0 вызовов модели;
- `SMARTBILD_HOME=/var/lib/smartbild-projects/handoff-work/IDEA-08EFF217
  /home/kocher.av/.report-venv/bin/python
  telegram-bridge/docs/architecture/quality_gate.py --run` — `ok: true`, 1285 тестов,
  2026-11-01T17:54:26.675116+00:00;
- `git diff --check` и `py_compile` изменённых Python-файлов — успешно.

Документация обновлена в `CHANGELOG.md` и `QA_IDEAS.md`.

Стадии:

- реализовано: да, коммит опубликован в handoff-ветке;
- проверено изолированно: да, СИНТЕТИЧЕСКИЙ HumanJourneyCase и полный offline gate;
- выпущено: нет — задание `kind: code`, выпуск должен быть отдельным заданием;
- подтверждено в работающей системе: нет — ветка не слита, служба не перезапускалась.

Не сделано: merge в `main`, safe reload и живое создание счёта. Это запрещено областью
текущего задания; хозяйственные записи ради проверки не выполнялись.
