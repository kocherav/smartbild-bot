status: done
commits: a8223e9

Ветка: `handoff/IDEA-D49F8B64` (опубликована в `origin`).

Что сделано:
- сохранено намерение выставить общий счёт в составном маршруте «найти сделку → выбрать»;
- после выбора сразу показывается предпросмотр с датой, плательщиком, позициями и суммой;
- до единственной кнопки подтверждения хозяйственных записей нет;
- добавлен `HumanJourneyCase`: 5 действий до изменения, 3 после;
- обновлены `CHANGELOG.md` и `QA_IDEAS.md`.

Проверки:
- воспроизводящая регрессия до исправления: FAIL — после выбора показывалась только карточка сделки;
- `python3 -m unittest -v test_human_quick_actions test_human_voice test_human_intents`: 32/32 OK;
- `python3 -m py_compile bridge.py test_human_quick_actions.py`: OK;
- `git diff --check`: OK;
- `/home/kocher.av/.report-venv/bin/python telegram-bridge/docs/architecture/quality_gate.py --run`: `ok: true`, 1301 тест, 0 ошибок;
- дополнительный запуск `test_contract_invoice` системным Python не стартовал: в системном окружении нет `python-docx`; штатный полный gate в `.report-venv` этот контур прошёл.

Статусы проверяемой реальности:
- реализовано: да, коммит `a8223e9`;
- проверено изолированно: да, human-регрессия и полный offline quality gate;
- выпущено: нет, выпуск является отдельным заданием;
- подтверждено в работающей системе: нет, живой Telegram/CRM-маршрут не выполнялся.

Не сделано: merge в `main`, safe reload и хозяйственные записи — не разрешены для `kind: code` и отложены до отдельного release-задания.
