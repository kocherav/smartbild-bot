# Статическая карта текущего bridge.py

Сгенерировано inventory.py без импорта бота и без обращения к внешним системам.
Это индекс для ручной трассировки, не доказательство полноты достижимых маршрутов.
Динамические клавиатуры, условия в вызываемых модулях и семантика ИИ требуют отдельной проверки.

SHA-256 исходника: `5cfd0dcd875204edcacb4cf9448f670c5c10298cb250dc6cd20ea948e6b7cf87`

## Меню

### MAIN_KEYBOARD — строка 242

- 📊 Пульт сделок
- 🤝 Работа со сделками
- 🏦 Банк и платежи
- 📦 Нераспределённые закупки
- 🧰 Отчёт монтажника
- 📄 Создать КП
- 📥 Монтажные отчёты
- 🛠 Задача разработчику
- ❓ Помощь

### PAYER_UPLOAD_KEYBOARD — строка 255

- ❌ Отмена
- ⬅️ Главное меню

### PAYER_TARGET_CONFIRM_KEYBOARD — строка 259

- ✅ Создать и привязать плательщика
- ❌ Отмена

### BANK_MENU_KEYBOARD — строка 263

- 📤 Загрузить выписку
- 📩 Банковские уведомления
- 🔗 Найти соответствия
- 🔍 Неразнесённые операции
- 📚 Все операции
- ⬅️ Главное меню

### BANK_CANCEL_KEYBOARD — строка 273

- ❌ Отмена
- ⬅️ Главное меню

### BANK_CONFIRM_KEYBOARD — строка 277

- ✅ Привязать к сделке
- ❌ Отмена

### BANK_INSTALLER_PAYMENT_KEYBOARD — строка 281

- ✅ Учесть как выплату монтажнику
- ❌ Не учитывать как выплату

### BANK_AUTO_CONFIRM_KEYBOARD — строка 285

- ✅ Привязать все найденные
- ❌ Отмена

### EMAIL_PAYMENT_CONFIRM_KEYBOARD — строка 289

- ✅ Создать расходные операции
- ⏭ Отложить платёж

### EMAIL_PAYMENT_UNMATCHED_KEYBOARD — строка 293

- 📋 Как привязать платёж
- ⏭ Отложить платёж
- ⬅️ Банк и платежи

### DEVELOPER_TASK_KEYBOARD — строка 298

- ❌ Отменить задачу
- ⬅️ Главное меню

### PAYER_DEAL_KEYBOARD — строка 302

- Без привязки к сделке
- ❌ Отменить

### INSTALLER_USER_KEYBOARD — строка 306

- 🛠 Мои монтажи
- 📤 Сборный отчёт
- 📜 История монтажей
- 📚 Утверждённые отчёты
- 📊 Мои взаиморасчёты
- ❓ Помощь

### DEALS_KEYBOARD — строка 456

- 📊 Пульт сделок
- 🕘 Последние 5
- 🕘 Последние 10
- 🕘 Последние 15
- 🔎 Найти по клиенту
- 📍 Найти по адресу
- 🔢 Найти по номеру
- ➕ Создать сделку
- ⬅️ Главное меню

### DEAL_ACTIONS_KEYBOARD — строка 466

- 🔄 Изменить статус
- 💰 Экономика
- 📄 КП по сделке
- 🧾 Работа со счетами
- 🧾 Учесть счёт
- 📋 Монтажная ведомость
- 👷 Монтаж по сделке
- 📐 Приложить проект
- 👤 Контакт по монтажу
- 💵 Выплата монтажнику
- 📦 Закупка по сделке
- 📄 Позиции сделки
- 📑 Работа с договором
- ⬅️ К списку сделок
- ⬅️ Главное меню

### PROCUREMENT_KEYBOARD — строка 481

- 📋 Скачать перечень закупки
- 📎 Загрузить счёт поставщика
- 📚 Реестр для бухгалтерии
- 🔎 Подобрать из остатков
- 🔄 Повторить последний счёт
- 📊 Статус закупок
- 🏦 Сверить оплаты поставщикам
- 🏢 Организация продажи
- 🏢 Межфирменные взаиморасчёты
- 📥 Отметить поступление
- 📎 Загрузить УПД/акт поставщика
- ✅ Проверить готовность закупки
- ⬅️ Назад к сделке
- ⬅️ Главное меню

### PROCUREMENT_COMPANY_KEYBOARD — строка 497

- ООО «КЛИВЭЛ»
- ООО «Инсис»
- ИП Кочержинский А.В.
- ❌ Отмена

### SUPPLIER_INVOICE_CONFIRM_KEYBOARD — строка 502

- ✅ Применить счёт поставщика
- ❌ Отмена

### SUPPLIER_DISTRIBUTION_KEYBOARD — строка 506

- 🔗 Сопоставить с позицией сделки
- 🧾 В прочую себестоимость сделки
- ✅ Подтвердить всё распределение
- ✅ Только в текущую сделку
- 📦 Весь остаток в нераспределённые
- ✏️ Изменить распределение
- 🔍 Показать другие сделки
- 🚫 Не учитывать остаток
- ❌ Отмена

### SUPPLIER_MISC_CONFIRM_KEYBOARD — строка 517

- ✅ Подтвердить прочую себестоимость
- ❌ Отмена

### UNALLOCATED_STOCK_KEYBOARD — строка 521

- 📋 Показать остатки
- 📥 Скачать реестр остатков
- 🔎 Найти в остатках
- ⬅️ Главное меню

### PROCUREMENT_STOCK_CONFIRM_KEYBOARD — строка 528

- ✅ Использовать найденные остатки
- ⏭ Не использовать остатки
- ❌ Отмена

### PROCUREMENT_RECEIPT_QTY_KEYBOARD — строка 535

- ✅ Получено полностью
- ❌ Отмена

### PROCUREMENT_CLOSE_KEYBOARD — строка 539

- ✅ Закрыть закупку
- ❌ Отмена

### INVOICE_MENU_KEYBOARD — строка 543

- 📋 Общий счёт по спецификации
- 6.4.1
- 6.4.2
- 6.4.3
- 📚 Скачать счёт
- ⬅️ Назад к сделке
- ⬅️ Главное меню

### TRANSITION_INVOICE_TYPE_KEYBOARD — строка 552

- 1. Полностью согласно спецификации
- 2. Упрощённый согласно п.6.4
- 3. Оба варианта
- ❌ Отмена

### INVOICE_FULL_CONFIRM_KEYBOARD — строка 561

- ✅ Выставить общий счёт
- ❌ Отмена

### CONTRACT_KEYBOARD — строка 565

- 📝 Подготовить договор
- 👁 Проверить данные договора
- 🏢 Добавить плательщика
- 📎 Получить договор из Мегаплана
- 🧾 Выставить счёт по договору
- 🏢 Смена нашей фирмы
- ⬅️ Назад к сделке
- ⬅️ Главное меню

### CONTRACT_INVOICE_CLAUSE_KEYBOARD — строка 576

- 6.4.1
- 6.4.2
- 6.4.3
- ❌ Отмена

### CONTRACT_INVOICE_CONFIRM_KEYBOARD — строка 581

- ✅ Выставить счёт
- ❌ Отмена

### CONTRACT_UPLOAD_KEYBOARD — строка 585

- ✅ Загрузить договоры в сделку
- ❌ Не загружать
- ⬅️ Назад к сделке

### TAX_KEYBOARD — строка 593

- Без НДС
- НДС 22%
- НДС 5%

### DEAL_CREATE_CONFIRM_KEYBOARD — строка 598

- ✅ Создать подтверждённую сделку
- ✏️ Заменить спецификацию
- ❌ Отмена

### INSTALLER_REPORT_OBJECTS_KEYBOARD — строка 603

- ✅ Объекты верны
- ✏️ Исправить объект
- ❌ Отменить отчёт

### INSTALLER_REPORT_REVIEW_KEYBOARD — строка 611

- ▶️ Разобрать исключения
- ✅ Утвердить черновик
- ❌ Отменить отчёт

### INSTALLER_REPORT_SUBMIT_KEYBOARD — строка 619

- ▶️ Разобрать исключения
- 📤 Передать руководителю
- ❌ Отменить отчёт

### INSTALLER_MANAGER_OPEN_KEYBOARD — строка 627

- 🧰 Открыть отчёт монтажника
- ⬅️ Главное меню

### INSTALLER_REPORT_UPLOAD_KEYBOARD — строка 635

- 📤 Загрузить выполнение в сделки
- ❌ Не загружать выполнение
- ⬅️ Главное меню

### INSTALLER_REPORT_FILES_KEYBOARD — строка 643

- ✅ Все файлы загружены
- ❌ Отменить отчёт

### INSTALLER_MENU_KEYBOARD — строка 650

- 📄 Загрузить отчёт
- 💳 Учесть выплату
- 📊 Взаиморасчёты
- ⬅️ Главное меню

### INSTALLER_PAYMENT_KEYBOARD — строка 658

- 🏦 Безналичная — зачесть 94%
- 💵 Наличная — зачесть 100%
- ❌ Отменить выплату

### INSTALLATION_DRAFT_KEYBOARD — строка 667

- ✅ Утвердить монтажную ведомость
- 📋 Скачать монтажную ведомость
- 📤 Загрузить исправленную ведомость
- 👤 Выбрать контакт по монтажу
- ✍️ Ввести контакт вручную
- 📎 Привязать проект
- 🚫 Работать БЕЗ ПРОЕКТА
- ⏸ Подготовить позже

### INSTALLATION_TRANSFER_KEYBOARD — строка 676

- ✅ Передать объект монтажнику
- ⬅️ Назад к сделке

### INSTALLATION_STATUS_KEYBOARD — строка 680

- ✅ Перевести сделку в Монтаж
- 📋 Скачать монтажную ведомость
- ⬅️ Назад к сделке

### INSTALLER_INSTALLATION_KEYBOARD — строка 686

- 📋 Монтажная ведомость
- 📐 Проектная документация
- 📦 Материалы по счетам
- 🧰 Новый отчёт
- ⬅️ Мои монтажи

### INSTALLATION_REPORT_COLLECT_KEYBOARD — строка 692

- ✅ Все материалы отправлены
- ❌ Отменить отчёт

### INSTALLATION_REPORT_REVIEW_KEYBOARD — строка 696

- ✅ Принять монтажный отчёт
- ✏️ Скорректировать объёмы
- ↩️ Вернуть монтажнику

### INSTALLATION_CASH_CONFIRM_KEYBOARD — строка 701

- ✅ Записать выплату из кассы
- ❌ Отмена

## Изменения состояния диалога

- Строка 1430, `retry_supplier_invoice_document`: `current_deal_id=deal_id; supplier_invoice_deal_id=deal_id; active_document_job_id=job['id']; pending='invoice_file'`
- Строка 1483, `retry_supplier_invoice_document`: `active_document_job_id=None; pending='supplier_invoice_confirm'`
- Строка 1454, `retry_supplier_invoice_document`: `active_document_job_id=None`
- Строка 1472, `retry_supplier_invoice_document`: `active_document_job_id=None`
- Строка 1463, `retry_supplier_invoice_document`: `active_document_job_id=None`
- Строка 1813, `show_email_payment_candidate`: `pending='email_payment_confirm'; email_payment_candidate_id=candidate['id']`
- Строка 1821, `show_email_payment_candidate`: `pending='email_payment_unmatched'; email_payment_candidate_id=candidate['id']`
- Строка 1873, `send_bank_transactions`: `pending='bank_operation_list'; bank_operation_choices=choices`
- Строка 1891, `handle_bank_ui`: `pending=None; bank_operation_choices=None; bank_transaction_id=None; bank_pending_deal=None; bank_auto_matches=None`
- Строка 1908, `handle_bank_ui`: `pending='email_payment_list'; email_payment_choices=choices; email_payment_offset=offset`
- Строка 1919, `handle_bank_ui`: `pending=None; email_payment_candidate_id=None`
- Строка 1935, `handle_bank_ui`: `pending=None; email_payment_candidate_id=None`
- Строка 1950, `handle_bank_ui`: `pending=None; email_payment_candidate_id=None`
- Строка 1956, `handle_bank_ui`: `pending=None; bank_operation_choices=None; bank_transaction_id=None; bank_pending_deal=None; bank_auto_matches=None`
- Строка 1964, `handle_bank_ui`: `pending=None; bank_operation_choices=None; bank_transaction_id=None; bank_pending_deal=None; bank_auto_matches=None`
- Строка 1970, `handle_bank_ui`: `pending='bank_statement_file'`
- Строка 2008, `handle_bank_ui`: `pending='bank_auto_confirm'; bank_auto_matches=matches`
- Строка 2033, `handle_bank_ui`: `pending=None; bank_auto_matches=None`
- Строка 2065, `handle_bank_ui`: `pending='bank_assign_confirm'; bank_pending_deal=deal['deal']`
- Строка 2115, `handle_bank_ui`: `pending=None; bank_installer_transaction=None; bank_installer_deal_id=None`
- Строка 2121, `handle_bank_ui`: `pending=None; bank_installer_transaction=None; bank_installer_deal_id=None`
- Строка 2047, `handle_bank_ui`: `pending='bank_deal_id'; bank_transaction_id=transaction_id`
- Строка 2090, `handle_bank_ui`: `pending='bank_installer_payment_confirm'; bank_installer_transaction=item; bank_installer_deal_id=str(deal['id']); bank_transaction_id=None; bank_pending_deal=None`
- Строка 2097, `handle_bank_ui`: `pending=None; bank_transaction_id=None; bank_pending_deal=None`
- Строка 2236, `prepare_installation_after_transition`: `pending='installation_draft_review'; installation_deal_id=str(deal_id); installation_pending_transition={'deal_id': str(deal_id), 'state_id': '136', 'name': 'Монтаж'}`
- Строка 2426, `handle_current_execution_ui`: `pending='current_execution_select'; current_execution_candidates=candidates[:10]`
- Строка 2376, `handle_current_execution_ui`: `pending=None; current_execution_candidates=None`
- Строка 2390, `handle_current_execution_ui`: `pending='current_execution_select'; current_execution_candidates=candidates[:10]`
- Строка 2417, `handle_current_execution_ui`: `pending='current_execution_query'`
- Строка 2386, `handle_current_execution_ui`: `pending=None`
- Строка 2474, `request_exception_amount`: `pending='installer_report_exception_amount'; installer_report=installer`
- Строка 2568, `send_installer_exception`: `installer_report=session; pending='installer_report_exception'`
- Строка 2654, `process_installer_report`: `pending='installer_report_objects'; installer_report=session`
- Строка 2614, `process_installer_report`: `pending='installer_report_file'; installer_report=None`
- Строка 2633, `process_installer_report`: `pending='installer_excel_report_deal'; installer_report=session`
- Строка 2642, `process_installer_report`: `pending='installer_report_tables'; installer_report=session`
- Строка 2630, `process_installer_report`: `pending='installer_excel_report_date'; installer_report=session`
- Строка 2671, `finish_installer_report_files`: `pending='installer_report_objects'; installer_report=completed`
- Строка 3059, `select_deal`: `None=values`
- Строка 3283, `prepare_contract_preview`: `pending='contract_generate_confirm'; contract_deal_id=str(deal_id); contract_data_fingerprint=preview.get('fingerprint')`
- Строка 3250, `prepare_contract_preview`: `contract_signatory=None; contract_signatory_payer_id=payer_id`
- Строка 3254, `prepare_contract_preview`: `contract_signatory=resolved_signer; contract_signatory_payer_id=payer_id`
- Строка 3259, `prepare_contract_preview`: `pending='contract_date'; contract_deal_id=str(deal_id)`
- Строка 3263, `prepare_contract_preview`: `pending='contract_address'; contract_deal_id=str(deal_id)`
- Строка 3267, `prepare_contract_preview`: `pending='contract_signatory_name'; contract_deal_id=str(deal_id)`
- Строка 3271, `prepare_contract_preview`: `pending='contract_signatory_position'; contract_deal_id=str(deal_id)`
- Строка 3275, `prepare_contract_preview`: `pending='contract_signatory_authority'; contract_deal_id=str(deal_id)`
- Строка 3338, `handle_global_navigation`: `pending=None; transitions=None; pending_transition=None; bank_transaction_id=None; bank_pending_deal=None; deal_creation_active=False`
- Строка 3346, `handle_global_navigation`: `pending=None; transitions=None; pending_transition=None; bank_transaction_id=None; bank_pending_deal=None; deal_creation_active=False`
- Строка 3427, `handle_deal_ui`: `pending='installation_report_review'; installation_report_id=report_id; installation_partial=None`
- Строка 3440, `handle_deal_ui`: `pending='proposal_recipient'; proposal_deal_id=str(target)`
- Строка 3461, `handle_deal_ui`: `pending=None; proposal_deal_id=None`
- Строка 3463, `handle_deal_ui`: `pending='deal_create_title'; deal_creation_active=True; deal_create_spec={}; deal_creation_items=None; deal_creation_economics_path=None; current_deal_id=None; contract_deal_id=None`
- Строка 3510, `handle_deal_ui`: `deal_create_spec=draft; pending='deal_create_items'; deal_create_clients=None`
- Строка 3521, `handle_deal_ui`: `pending='deal_create_items'; deal_create_spec=draft; deal_creation_items=None`
- Строка 3593, `handle_deal_ui`: `pending=legacy_report_ui.PENDING_EDIT`
- Строка 3601, `handle_deal_ui`: `pending=legacy_report_ui.PENDING_MAP; installer_bundle_preview=preview`
- Строка 3629, `handle_deal_ui`: `pending='installation_contact_select'; installation_deal_id=installation_deal_id; installation_contact_choices=choices; installation_contact_return=back`
- Строка 3660, `handle_deal_ui`: `pending='installation_contact_create_phone'; installation_contact_new_name=value`
- Строка 3688, `handle_deal_ui`: `pending='installation_draft_review' if back == 'draft' else None; installation_contact_new_name=None; installation_contact_choices=None; installation_contact_return=None`
- Строка 3703, `handle_deal_ui`: `pending='installation_project_select'; installation_deal_id=installation_deal_id; installation_project_choices=choices; installation_project_selected=[]; installation_project_return='draft' if value == '📎 Привязать проект' else 'deal'`
- Строка 3753, `handle_deal_ui`: `pending='installation_workbook_file'; installation_deal_id=installation_deal_id`
- Строка 3757, `handle_deal_ui`: `pending='installation_contact_name'; installation_deal_id=installation_deal_id`
- Строка 3762, `handle_deal_ui`: `pending='installation_contact_phone'; installation_contact_name=value`
- Строка 3772, `handle_deal_ui`: `pending='installation_draft_review'; installation_contact_name=None`
- Строка 3795, `handle_deal_ui`: `pending='installation_status_ready'; installation_pending_transition=transition`
- Строка 3828, `handle_deal_ui`: `pending=None; installation_pending_transition=None`
- Строка 3838, `handle_deal_ui`: `pending=None; installation_deal_id=None`
- Строка 3848, `handle_deal_ui`: `pending=None; installation_report_id=None; installation_partial=None`
- Строка 3856, `handle_deal_ui`: `pending='installation_report_return_comment'`
- Строка 3862, `handle_deal_ui`: `pending=None; installation_report_id=None`
- Строка 3870, `handle_deal_ui`: `pending='installation_report_correction'`
- Строка 3879, `handle_deal_ui`: `pending='installation_report_review'; installation_partial=partial`
- Строка 3887, `handle_deal_ui`: `pending='installation_cash_amount'; installation_deal_id=str(deal_id)`
- Строка 3896, `handle_deal_ui`: `pending='installation_cash_confirm'; installation_cash_amount=amount; installation_cash_date=datetime.now().strftime('%d.%m.%Y')`
- Строка 3906, `handle_deal_ui`: `pending=None; installation_cash_amount=None`
- Строка 3963, `handle_deal_ui`: `pending='developer_task_input'`
- Строка 3972, `handle_deal_ui`: `pending=None`
- Строка 3979, `handle_deal_ui`: `pending='developer_task_running'; developer_task_text=value; developer_task_started_at=datetime.now(timezone.utc).isoformat()`
- Строка 3994, `handle_deal_ui`: `pending='unallocated_stock_menu'`
- Строка 4027, `handle_deal_ui`: `pending='unallocated_stock_search'`
- Строка 4032, `handle_deal_ui`: `pending='unallocated_stock_menu'`
- Строка 4081, `handle_deal_ui`: `pending=None; transitions=None; pending_transition=None`
- Строка 4085, `handle_deal_ui`: `pending=None; transitions=None; pending_transition=None`
- Строка 4089, `handle_deal_ui`: `pending=None; transitions=None; pending_transition=None`
- Строка 4105, `handle_deal_ui`: `pending=pending`
- Строка 4120, `handle_deal_ui`: `pending='installer_excel_report_deal'; installer_report=installer`
- Строка 4144, `handle_deal_ui`: `pending='installer_report_review'; installer_report=installer`
- Строка 4154, `handle_deal_ui`: `pending='installer_report_review'; installer_report=incoming; incoming_installer_report=None`
- Строка 4174, `handle_deal_ui`: `incoming_installer_report=submitted`
- Строка 4175, `handle_deal_ui`: `pending='installer_report_submitted'; installer_report=installer`
- Строка 4190, `handle_deal_ui`: `pending=None`
- Строка 4194, `handle_deal_ui`: `pending='installer_report_file'; installer_report=None`
- Строка 4199, `handle_deal_ui`: `pending='installer_payment_file'; installer_payment=None`
- Строка 4211, `handle_deal_ui`: `pending=None; installer_payment=None`
- Строка 4219, `handle_deal_ui`: `pending='installer_payment_confirm'; installer_payment=payment`
- Строка 4239, `handle_deal_ui`: `pending=None; installer_payment=None`
- Строка 4254, `handle_deal_ui`: `pending=None; installer_report=None`
- Строка 4262, `handle_deal_ui`: `pending='installer_report_review'; installer_report=installer`
- Строка 4268, `handle_deal_ui`: `pending='installer_report_fix_object'; installer_report=installer`
- Строка 4274, `handle_deal_ui`: `pending='installer_report_fix_deal'; installer_report=installer`
- Строка 4292, `handle_deal_ui`: `pending='installer_report_objects'; installer_report=installer`
- Строка 4454, `handle_deal_ui`: `pending='installer_report_upload'; installer_report=installer`
- Строка 4483, `handle_deal_ui`: `pending=None; installer_report=installer`
- Строка 4488, `handle_deal_ui`: `pending=None; installer_report=installer`
- Строка 4493, `handle_deal_ui`: `pending='invoice_menu' if from_invoice_menu else None; contract_invoice_preview=None; invoice_origin=None`
- Строка 4498, `handle_deal_ui`: `pending=None; invoice_downloads=None`
- Строка 4506, `handle_deal_ui`: `pending='contract_invoice_confirm'; contract_invoice_preview=result; invoice_origin='menu'`
- Строка 4510, `handle_deal_ui`: `pending='invoice_menu'`
- Строка 4519, `handle_deal_ui`: `pending='invoice_menu'; invoice_downloads=None`
- Строка 4531, `handle_deal_ui`: `pending='contract_invoice_confirm'; contract_invoice_preview=result; invoice_origin=None`
- Строка 4545, `handle_deal_ui`: `pending='invoice_menu' if state.get('invoice_origin') == 'menu' else None; contract_invoice_preview=None; invoice_origin=None`
- Строка 4565, `handle_deal_ui`: `pending='contract_signatory_position'; contract_signatory=signer; contract_signatory_payer_id=state.get('contract_signatory_payer_id')`
- Строка 4575, `handle_deal_ui`: `pending='contract_signatory_authority'; contract_signatory=signer`
- Строка 4582, `handle_deal_ui`: `pending=None; contract_signatory=signer`
- Строка 4605, `handle_deal_ui`: `pending=None`
- Строка 4616, `handle_deal_ui`: `pending=None`
- Строка 4620, `handle_deal_ui`: `pending=None`
- Строка 4644, `handle_deal_ui`: `pending='procurement_stock_confirm'; procurement_stock_suggestions=selected_suggestions`
- Строка 4682, `handle_deal_ui`: `pending=None; procurement_stock_deal_id=None; procurement_stock_suggestions=None`
- Строка 4707, `handle_deal_ui`: `transitions=transitions`
- Строка 4730, `handle_deal_ui`: `pending_transition=pending_transition`
- Строка 4745, `handle_deal_ui`: `pending=None; pending_transition=transition`
- Строка 4755, `handle_deal_ui`: `pending=None; pending_transition=transition`
- Строка 4764, `handle_deal_ui`: `pending_transition=None; transitions=None`
- Строка 4832, `handle_deal_ui`: `pending=None; pending_transition=None; transitions=None`
- Строка 4847, `handle_deal_ui`: `installation_deal_id=str(deal_id)`
- Строка 4858, `handle_deal_ui`: `pending='invoice_menu'; invoice_downloads=None`
- Строка 4865, `handle_deal_ui`: `pending='invoice_full_confirm'; invoice_full_preview=preview`
- Строка 4884, `handle_deal_ui`: `pending='invoice_download'; invoice_downloads=downloads`
- Строка 4889, `handle_deal_ui`: `pending='procurement_menu'`
- Строка 4913, `handle_deal_ui`: `pending='procurement_stock_select'; procurement_stock_deal_id=str(deal_id); procurement_stock_suggestions=suggestions`
- Строка 4958, `handle_deal_ui`: `pending='supplier_closing_invoice'; supplier_closing_choices=choices`
- Строка 4963, `handle_deal_ui`: `pending='supplier_closing_upload'; supplier_closing_invoice=invoice`
- Строка 4968, `handle_deal_ui`: `pending='procurement_selling_company'`
- Строка 4982, `handle_deal_ui`: `pending='procurement_menu'`
- Строка 5013, `handle_deal_ui`: `pending='procurement_settlement_select'; procurement_settlement_choices=choices`
- Строка 5020, `handle_deal_ui`: `pending='procurement_settlement_confirm'; procurement_settlement_candidate=candidate`
- Строка 5040, `handle_deal_ui`: `pending='procurement_menu'; procurement_settlement_choices=None; procurement_settlement_candidate=None`
- Строка 5078, `handle_deal_ui`: `pending='procurement_receipt_item'; procurement_receipt_choices=choices`
- Строка 5083, `handle_deal_ui`: `pending='procurement_receipt_qty'; procurement_receipt_item=item`
- Строка 5105, `handle_deal_ui`: `pending='procurement_menu'; procurement_receipt_item=None; procurement_receipt_choices=None`
- Строка 5130, `handle_deal_ui`: `pending='procurement_close_confirm'`
- Строка 5144, `handle_deal_ui`: `pending='procurement_menu'`
- Строка 5149, `handle_deal_ui`: `pending='invoice_file'; supplier_invoice_deal_id=str(deal_id); supplier_invoice_queue=None; supplier_invoice_preview=None`
- Строка 5177, `handle_deal_ui`: `pending='supplier_manual_mapping'; supplier_mapping_sources=sources; supplier_mapping_targets=targets`
- Строка 5210, `handle_deal_ui`: `pending='supplier_invoice_confirm'; supplier_invoice_queue=new_queue; supplier_invoice_preview=base_spec; supplier_mapping_sources=None; supplier_mapping_targets=None`
- Строка 5242, `handle_deal_ui`: `pending='supplier_misc_confirm'; supplier_invoice_queue=new_queue; supplier_invoice_preview=base_spec`
- Строка 5317, `handle_deal_ui`: `pending='supplier_invoice_confirm'; supplier_invoice_queue=new_queue; supplier_invoice_preview=base_spec`
- Строка 5536, `handle_deal_ui`: `pending='payer_card_file'; payer_card=None; payer_result=None; payer_target_deal_id=str(deal_id); deal_creation_active=False`
- Строка 5551, `handle_deal_ui`: `pending='contract_selling_company'`
- Строка 5567, `handle_deal_ui`: `pending=None; generated_contract=None; contract_invoice_preview=None`
- Строка 5573, `handle_deal_ui`: `contract_deal_id=str(deal_id); deal_creation_active=False`
- Строка 5577, `handle_deal_ui`: `pending='contract_invoice_clause'; contract_invoice_preview=None`
- Строка 5582, `handle_deal_ui`: `generated_contract=None`
- Строка 5596, `handle_deal_ui`: `pending='contract_upload'; generated_contract={'deal_id': str(deal_id), 'docx_path': result['docx_path'], 'pdf_path': result['pdf_path']}`
- Строка 5630, `handle_deal_ui`: `pending=None; generated_contract=None`
- Строка 5638, `handle_deal_ui`: `pending=None; generated_contract=None`
- Строка 3368, `handle_deal_ui`: `pending=None; deal_sync_spec=None`
- Строка 3382, `handle_deal_ui`: `pending=None; work_price_preview=None`
- Строка 3396, `handle_deal_ui`: `pending=None; price_catalog_spec=None`
- Строка 3453, `handle_deal_ui`: `pending=None; proposal_deal_id=None`
- Строка 3475, `handle_deal_ui`: `deal_create_spec=draft; pending='deal_create_client'`
- Строка 3488, `handle_deal_ui`: `deal_create_spec=draft; pending='deal_create_client_select'; deal_create_clients=clients`
- Строка 3499, `handle_deal_ui`: `pending='deal_create_client'`
- Строка 3569, `handle_deal_ui`: `pending=pending_now; supplier_invoice_preview=queue[0]`
- Строка 3640, `handle_deal_ui`: `pending='installation_draft_review' if back == 'draft' else None; installation_contact_choices=None; installation_contact_return=None`
- Строка 3647, `handle_deal_ui`: `pending='installation_contact_create_name'`
- Строка 3655, `handle_deal_ui`: `pending='installation_contact_create_name'; installation_contact_new_name=None`
- Строка 3667, `handle_deal_ui`: `pending='installation_contact_create_name'; installation_contact_new_name=None`
- Строка 3714, `handle_deal_ui`: `installation_project_selected=sorted(selected)`
- Строка 3717, `handle_deal_ui`: `pending='installation_project_upload'`
- Строка 3727, `handle_deal_ui`: `pending='installation_draft_review' if back == 'draft' else None; installation_project_choices=None; installation_project_selected=None; installation_project_return=None`
- Строка 3925, `handle_deal_ui`: `pending=None; deal_create_spec=None`
- Строка 3932, `handle_deal_ui`: `pending=next_step; deal_create_spec=spec`
- Строка 3942, `handle_deal_ui`: `pending=None; deal_create_spec=None; deal_creation_active=False; deal_creation_items=None; deal_creation_economics_path=None; current_deal_id=str(result.get('id') or '')`
- Строка 4359, `handle_deal_ui`: `pending='installer_report_review'; installer_report=installer`
- Строка 4434, `handle_deal_ui`: `pending='installer_report_review'; installer_report=installer`
- Строка 4634, `handle_deal_ui`: `pending='procurement_menu'; procurement_stock_deal_id=None; procurement_stock_suggestions=None`
- Строка 4719, `handle_deal_ui`: `transitions=None; pending_transition=None; installation_pending_transition=pending_transition; installation_deal_id=str(deal_id)`
- Строка 4727, `handle_deal_ui`: `pending='transition_invoice_type'; pending_transition=pending_transition`
- Строка 4742, `handle_deal_ui`: `pending='transition_invoice_clause'; pending_transition=transition`
- Строка 4849, `handle_deal_ui`: `pending='installation_draft_review'`
- Строка 5373, `handle_deal_ui`: `pending='supplier_distribution_edit'`
- Строка 5382, `handle_deal_ui`: `pending='supplier_distribution_exclusion_reason'`
- Строка 3514, `handle_deal_ui`: `pending='deal_create_tax'`
- Строка 3681, `handle_deal_ui`: `pending='installation_contact_create_name'; installation_contact_new_name=None`
- Строка 4339, `handle_deal_ui`: `pending='installer_report_review'; installer_report=installer`
- Строка 4344, `handle_deal_ui`: `pending='installer_report_exception_deal'; installer_report=installer`
- Строка 4852, `handle_deal_ui`: `pending='installation_ready_to_transfer'`
- Строка 5363, `handle_deal_ui`: `supplier_invoice_queue=remaining_queue; supplier_invoice_preview=base_spec`
- Строка 4778, `handle_deal_ui`: `pending='procurement_stock_confirm'; procurement_stock_deal_id=str(transition['deal_id']); procurement_stock_suggestions=suggestions`
- Строка 5771, `handle_invoice_cancellation`: `None=updates`
- Строка 6417, `begin_payer_card_flow`: `pending='payer_client'; payer_card=card; payer_target_deal_id=None`
- Строка 6406, `begin_payer_card_flow`: `pending='payer_target_confirm'; payer_card=card; payer_target_deal_id=target_deal_id; payer_target_client_name=client_name`
- Строка 6509, `handle_payer_flow_text`: `pending=None; payer_card=None; payer_result=None; payer_target_deal_id=None`
- Строка 6436, `handle_payer_flow_text`: `pending=None; payer_card=None; payer_result=None; payer_target_deal_id=None; payer_target_client_name=None`
- Строка 6458, `handle_payer_flow_text`: `pending=None; payer_card=None; payer_result=None; payer_target_deal_id=None; payer_target_client_name=None`
- Строка 6487, `handle_payer_flow_text`: `pending='payer_deal'; payer_result=result; payer_card=state.get('payer_card')`
- Строка 6496, `handle_payer_flow_text`: `pending=None; payer_card=None; payer_result=None; payer_target_deal_id=None`
- Строка 6483, `handle_payer_flow_text`: `pending=None; payer_card=None; payer_result=None; payer_target_deal_id=None`
- Строка 6635, `prepare_economics_deal_request`: `deal_creation_active=True; deal_create_spec=spec; deal_creation_items=economics['items']; deal_creation_economics_path=path; current_deal_id=None; contract_deal_id=None; deal_create_clients=None; pending='deal_create_client'`
- Строка 6657, `prepare_economics_deal_request`: `pending='deal_create_client_select'; deal_create_clients=clients`
- Строка 6652, `prepare_economics_deal_request`: `deal_create_spec=spec; pending='deal_create_tax'`
- Строка 6679, `prepare_deal_creation_review`: `deal_create_spec=spec; pending='deal_create_confirm'; deal_creation_active=True`
- Строка 6670, `prepare_deal_creation_review`: `deal_create_spec=spec; pending='deal_create_client'`
- Строка 6676, `prepare_deal_creation_review`: `deal_create_spec=spec; pending='deal_create_items'`
- Строка 7549, `create_and_send_full_invoice`: `invoice_full_preview=None`
- Строка 8027, `process_developer_task`: `pending=None; developer_task_text=None; developer_task_started_at=None`
- Строка 8043, `handle_installer_ui`: `pending=None; installation_report_id=None`
- Строка 8052, `handle_installer_ui`: `pending='installer_report_file'; installer_report=None; installation_report_id=None`
- Строка 8076, `handle_installer_ui`: `pending='installation_mine_select'; installation_choices=choices`
- Строка 8085, `handle_installer_ui`: `pending='installation_history_select'; installation_history_choices=choices`
- Строка 8090, `handle_installer_ui`: `pending='installation_object'; installation_deal_id=did; installation_choices=None`
- Строка 8095, `handle_installer_ui`: `pending='installation_history_object'; installation_deal_id=did; installation_history_choices=None`
- Строка 8151, `handle_installer_ui`: `pending='installation_report_collect'; installation_report_id=report['id']`
- Строка 8157, `handle_installer_ui`: `pending=None; installation_report_id=None`
- Строка 8164, `handle_installer_ui`: `pending=None; installation_report_id=None`
- Строка 8184, `handle_installer_ui`: `pending='installer_approved_report_list'`
- Строка 8204, `handle_installer_ui`: `pending=None`
- Строка 8207, `handle_installer_ui`: `pending=None`
- Строка 8830, `main`: `conversation_invoice=task_doc`
- Строка 9550, `main`: `active_document_job_id=None`
- Строка 9201, `main`: `pending='deal_create_tax'; deal_create_spec=deal_spec; current_deal_id=None; deal_creation_active=True`
- Строка 8336, `main`: `active_document_job_id=document_job['id']`
- Строка 8357, `main`: `pending='installation_draft_review' if back == 'draft' else None; installation_project_choices=None; installation_project_selected=None; installation_project_return=None`
- Строка 8379, `main`: `pending='installation_draft_review'`
- Строка 8417, `main`: `pending='procurement_menu'; supplier_closing_invoice=None; supplier_closing_choices=None`
- Строка 8457, `main`: `pending=None`
- Строка 8511, `main`: `pending='installer_report_tables'; installer_report=session`
- Строка 8536, `main`: `pending='installer_payment_confirm'; installer_payment=payment`
- Строка 8560, `main`: `conversation_invoice=None`
- Строка 8645, `main`: `deal_creation_active=True; contract_deal_id=None; deal_creation_items=None; deal_creation_economics_path=None`
- Строка 9144, `main`: `pending=next_step; deal_create_spec=saved`
- Строка 9208, `main`: `deal_create_spec=deal_spec; deal_creation_items=deal_spec.get('items'); deal_creation_active=True`
- Строка 9229, `main`: `pending='deal_sync_confirm'; deal_sync_spec=prepared`
- Строка 9491, `main`: `pending='work_price_confirm'; work_price_preview=prepared`
- Строка 9510, `main`: `pending='price_catalog_confirm'; price_catalog_spec=safe_spec`
- Строка 8390, `main`: `pending='procurement_menu'; supplier_closing_invoice=None; supplier_closing_choices=None`
- Строка 8430, `main`: `deal_creation_items=economics['items']; deal_creation_economics_path=original_path`
- Строка 8531, `main`: `pending=None; installer_payment=None`
- Строка 8564, `main`: `conversation_invoice=invoice_continuation.remember(source_document_path, extracted, chat_id)`
- Строка 8627, `main`: `pending=None`
- Строка 8650, `main`: `deal_creation_active=False`
- Строка 8573, `main`: `conversation_invoice=current_doc`
- Строка 9180, `main`: `pending='deal_create_items'; deal_create_spec=incomplete_spec; deal_creation_active=True`

## Условия ветвления (синтаксический индекс)

- Строка 1547, `send_message`: `not persistent and (UI_CONTEXT is None or UI_CONTEXT.actor != str(chat_id)) and (ui_state_store().current(chat_id).get('pending') or ui_state_store().current(chat_id).get('deal_creation_active'))`
- Строка 1656, `update_deal_ui_state`: `value is None`
- Строка 1807, `show_email_payment_candidate`: `candidate.get('status') not in ('pending', 'postponed')`
- Строка 1887, `handle_bank_ui`: `(value in bank_values or pending.startswith(('bank_', 'email_payment_'))) and (not _background)`
- Строка 1890, `handle_bank_ui`: `value == '🏦 Банк и платежи'`
- Строка 1895, `handle_bank_ui`: `value == '📩 Банковские уведомления' or (pending == 'email_payment_list' and value in ('➡️ Ещё уведомления', '⬅️ Предыдущие уведомления'))`
- Строка 1911, `handle_bank_ui`: `pending == 'email_payment_list' and value in (state.get('email_payment_choices') or {})`
- Строка 1916, `handle_bank_ui`: `pending == 'email_payment_confirm' and value == '⏭ Отложить платёж'`
- Строка 1922, `handle_bank_ui`: `pending == 'email_payment_unmatched' and value == '📋 Как привязать платёж'`
- Строка 1932, `handle_bank_ui`: `pending == 'email_payment_unmatched' and value == '⏭ Отложить платёж'`
- Строка 1938, `handle_bank_ui`: `pending == 'email_payment_confirm' and value == '✅ Создать расходные операции'`
- Строка 1955, `handle_bank_ui`: `value == '⬅️ Банк и платежи'`
- Строка 1963, `handle_bank_ui`: `pending.startswith('bank_') and value in ('❌ Отмена', '⬅️ Главное меню')`
- Строка 1969, `handle_bank_ui`: `value == '📤 Загрузить выписку'`
- Строка 1973, `handle_bank_ui`: `value == '🔍 Неразнесённые операции'`
- Строка 1976, `handle_bank_ui`: `value == '📚 Все операции'`
- Строка 1979, `handle_bank_ui`: `value == '🔗 Найти соответствия'`
- Строка 2015, `handle_bank_ui`: `pending == 'bank_auto_confirm' and value == '✅ Привязать все найденные'`
- Строка 2037, `handle_bank_ui`: `pending == 'bank_operation_list' and value in (state.get('bank_operation_choices') or {})`
- Строка 2052, `handle_bank_ui`: `pending == 'bank_deal_id'`
- Строка 2071, `handle_bank_ui`: `pending == 'bank_assign_confirm' and value == '✅ Привязать к сделке'`
- Строка 2100, `handle_bank_ui`: `pending == 'bank_installer_payment_confirm' and value == '✅ Учесть как выплату монтажнику'`
- Строка 2120, `handle_bank_ui`: `pending == 'bank_installer_payment_confirm' and value == '❌ Не учитывать как выплату'`
- Строка 1943, `handle_bank_ui`: `loaded['candidate'].get('status') not in ('pending', 'postponed')`
- Строка 2300, `archive_deal_labels`: `value not in bucket`
- Строка 2313, `execution_token_matches`: `token in text`
- Строка 2316, `execution_token_matches`: `stem_len >= 4 and token[:stem_len] in text`
- Строка 2369, `handle_current_execution_ui`: `state.get('pending') == 'current_execution_select' and re.match('^№\\d+\\b', value)`
- Строка 2379, `handle_current_execution_ui`: `state.get('pending') == 'current_execution_query'`
- Строка 2450, `money`: `value is None`
- Строка 2927, `check_external_procurement_transitions`: `marker in ('монтаж', 'закупка') and previous != marker and (live_ui.get('pending') or live_ui.get('deal_creation_active'))`
- Строка 3289, `handle_status_query`: `value not in ('/status', 'статус обработки', 'что сейчас делает бот')`
- Строка 3332, `handle_global_navigation`: `value in ('📊 Пульт сделок', 'Пульт сделок', '/dashboard')`
- Строка 3337, `handle_global_navigation`: `value in ('🤝 Работа со сделками', '/deals')`
- Строка 3345, `handle_global_navigation`: `value in ('⬅️ Главное меню', '/menu', '/start', '❌ Отмена')`
- Строка 3358, `handle_deal_ui`: `value == '✅ Заменить позиции подтверждённым КП'`
- Строка 3373, `handle_deal_ui`: `value == '✅ Записать стоимость монтажных работ'`
- Строка 3388, `handle_deal_ui`: `value == '✅ Обновить подтверждённый прайс'`
- Строка 3400, `handle_deal_ui`: `value == '📥 Монтажные отчёты'`
- Строка 3433, `handle_deal_ui`: `value == '📄 КП по сделке' or re.fullmatch('📄 КП для сделки №\\d+', value) or proposal_request`
- Строка 3444, `handle_deal_ui`: `proposal_state.get('pending') == 'proposal_recipient'`
- Строка 3462, `handle_deal_ui`: `value == '➕ Создать сделку'`
- Строка 3471, `handle_deal_ui`: `creation_pending in ('deal_create_title', 'deal_create_client') and value not in ('❌ Отмена', '⬅️ Главное меню')`
- Строка 3496, `handle_deal_ui`: `creation_pending == 'deal_create_client_select' and value not in ('❌ Отмена', '⬅️ Главное меню')`
- Строка 3519, `handle_deal_ui`: `creation_pending == 'deal_create_confirm' and value == '✏️ Заменить спецификацию'`
- Строка 3535, `handle_deal_ui`: `value == '🔄 Повторить последний счёт'`
- Строка 3564, `handle_deal_ui`: `value in supplier_control_values and (not pending_now.startswith('supplier_'))`
- Строка 3576, `handle_deal_ui`: `pending_now.startswith('contract_') and state.get('contract_deal_id')`
- Строка 3587, `handle_deal_ui`: `(value in installation_values or pending_now.startswith(('installation_', 'installer_report', 'installer_excel_report'))) and (not _background)`
- Строка 3591, `handle_deal_ui`: `pending_now == legacy_report_ui.PENDING_CONFIRM and value == legacy_report_ui.EDIT`
- Строка 3596, `handle_deal_ui`: `pending_now == legacy_report_ui.PENDING_EDIT`
- Строка 3605, `handle_deal_ui`: `pending_now == legacy_report_ui.PENDING_COST`
- Строка 3612, `handle_deal_ui`: `pending_now == legacy_report_ui.PENDING_MAP`
- Строка 3620, `handle_deal_ui`: `value in ('👤 Выбрать контакт по монтажу', '👤 Контакт по монтажу') and installation_deal_id`
- Строка 3632, `handle_deal_ui`: `pending_now == 'installation_contact_select'`
- Строка 3649, `handle_deal_ui`: `pending_now == 'installation_contact_create_name'`
- Строка 3662, `handle_deal_ui`: `pending_now == 'installation_contact_create_phone'`
- Строка 3694, `handle_deal_ui`: `value in ('📐 Приложить проект', '📎 Привязать проект') and installation_deal_id`
- Строка 3709, `handle_deal_ui`: `pending_now == 'installation_project_select'`
- Строка 3733, `handle_deal_ui`: `value == '🚫 Работать БЕЗ ПРОЕКТА' and installation_deal_id`
- Строка 3739, `handle_deal_ui`: `value == '📋 Скачать монтажную ведомость' and installation_deal_id`
- Строка 3752, `handle_deal_ui`: `value == '📤 Загрузить исправленную ведомость' and installation_deal_id`
- Строка 3756, `handle_deal_ui`: `value in ('👤 Указать контакт объекта', '✍️ Ввести контакт вручную') and installation_deal_id`
- Строка 3761, `handle_deal_ui`: `pending_now == 'installation_contact_name'`
- Строка 3765, `handle_deal_ui`: `pending_now == 'installation_contact_phone'`
- Строка 3775, `handle_deal_ui`: `value == '✅ Утвердить монтажную ведомость' and installation_deal_id`
- Строка 3803, `handle_deal_ui`: `value == '✅ Перевести сделку в Монтаж' and installation_deal_id`
- Строка 3833, `handle_deal_ui`: `value == '✅ Передать объект монтажнику' and installation_deal_id`
- Строка 3841, `handle_deal_ui`: `value == '✅ Принять монтажный отчёт' and state.get('installation_report_id')`
- Строка 3855, `handle_deal_ui`: `value == '↩️ Вернуть монтажнику' and state.get('installation_report_id')`
- Строка 3859, `handle_deal_ui`: `pending_now == 'installation_report_return_comment' and state.get('installation_report_id')`
- Строка 3866, `handle_deal_ui`: `value == '✏️ Скорректировать объёмы' and state.get('installation_report_id')`
- Строка 3873, `handle_deal_ui`: `pending_now == 'installation_report_correction' and state.get('installation_report_id')`
- Строка 3883, `handle_deal_ui`: `value == '💵 Выплата монтажнику' and deal_id`
- Строка 3890, `handle_deal_ui`: `pending_now == 'installation_cash_amount'`
- Строка 3900, `handle_deal_ui`: `value == '✅ Записать выплату из кассы' and pending_now == 'installation_cash_confirm'`
- Строка 3914, `handle_deal_ui`: `pending_now == 'deal_create_tax' and chosen_tax`
- Строка 3919, `handle_deal_ui`: `pending_now == 'deal_create_confirm' and value == '✅ Создать подтверждённую сделку'`
- Строка 3959, `handle_deal_ui`: `value == '🛠 Задача разработчику'`
- Строка 3971, `handle_deal_ui`: `pending_now == 'developer_task_input' and value in ('❌ Отменить задачу', '⬅️ Главное меню')`
- Строка 3975, `handle_deal_ui`: `pending_now == 'developer_task_input'`
- Строка 3984, `handle_deal_ui`: `pending_now == 'developer_task_running' and value in ('/dev_status', '🛠 Задача разработчику')`
- Строка 3990, `handle_deal_ui`: `value in stock_actions and (not _background)`
- Строка 3993, `handle_deal_ui`: `value == '📦 Нераспределённые закупки'`
- Строка 3998, `handle_deal_ui`: `value == '📋 Показать остатки'`
- Строка 4015, `handle_deal_ui`: `value == '📥 Скачать реестр остатков'`
- Строка 4026, `handle_deal_ui`: `value == '🔎 Найти в остатках'`
- Строка 4030, `handle_deal_ui`: `pending_now == 'unallocated_stock_search' and value not in stock_actions`
- Строка 4047, `handle_deal_ui`: `value in contract_actions and (not deal_id)`
- Строка 4080, `handle_deal_ui`: `value in ('🤝 Работа со сделками', '/deals')`
- Строка 4084, `handle_deal_ui`: `value == '⬅️ Главное меню'`
- Строка 4088, `handle_deal_ui`: `value == '⬅️ К списку сделок'`
- Строка 4103, `handle_deal_ui`: `value in search_prompts`
- Строка 4110, `handle_deal_ui`: `pending == 'installer_excel_report_date'`
- Строка 4125, `handle_deal_ui`: `pending == 'installer_excel_report_deal'`
- Строка 4147, `handle_deal_ui`: `value == '🧰 Открыть отчёт монтажника' and state.get('incoming_installer_report')`
- Строка 4162, `handle_deal_ui`: `value == '📤 Передать руководителю' and str(chat_id) in INSTALLER_CHAT_IDS and (pending or '').startswith('installer_report')`
- Строка 4189, `handle_deal_ui`: `value == '🧰 Отчёт монтажника'`
- Строка 4193, `handle_deal_ui`: `value == '📄 Загрузить отчёт'`
- Строка 4198, `handle_deal_ui`: `value == '💳 Учесть выплату'`
- Строка 4202, `handle_deal_ui`: `value == '📊 Взаиморасчёты'`
- Строка 4210, `handle_deal_ui`: `value == '❌ Отменить выплату' and (pending or '').startswith('installer_payment')`
- Строка 4214, `handle_deal_ui`: `pending == 'installer_payment_file'`
- Строка 4230, `handle_deal_ui`: `pending == 'installer_payment_confirm' and value in ('🏦 Безналичная — зачесть 94%', '💵 Наличная — зачесть 100%')`
- Строка 4253, `handle_deal_ui`: `value == '❌ Отменить отчёт' and (pending or '').startswith(('installer_report', 'installer_excel_report'))`
- Строка 4257, `handle_deal_ui`: `pending == 'installer_report_tables' and value == '✅ Все файлы загружены'`
- Строка 4260, `handle_deal_ui`: `pending == 'installer_report_objects' and value == '✅ Объекты верны'`
- Строка 4265, `handle_deal_ui`: `pending == 'installer_report_objects' and value == '✏️ Исправить объект'`
- Строка 4271, `handle_deal_ui`: `pending == 'installer_report_fix_object' and value.startswith('Объект: ')`
- Строка 4277, `handle_deal_ui`: `pending == 'installer_report_fix_deal'`
- Строка 4295, `handle_deal_ui`: `pending == 'installer_report_review' and value == '▶️ Разобрать исключения'`
- Строка 4299, `handle_deal_ui`: `pending == 'installer_report_exception'`
- Строка 4355, `handle_deal_ui`: `pending == 'installer_report_exception_amount'`
- Строка 4386, `handle_deal_ui`: `pending == 'installer_report_exception_deal'`
- Строка 4413, `handle_deal_ui`: `value == '✅ Утвердить черновик' and pending in ('installer_report_review', 'installer_report_exception') or (value == legacy_report_ui.CONFIRM and pending == legacy_report_ui.PENDING_CONFIRM)`
- Строка 4471, `handle_deal_ui`: `pending == 'installer_report_upload' and value == '📤 Загрузить выполнение в сделки'`
- Строка 4487, `handle_deal_ui`: `pending == 'installer_report_upload' and value == '❌ Не загружать выполнение'`
- Строка 4491, `handle_deal_ui`: `value == '❌ Отмена' and pending and pending.startswith('contract_')`
- Строка 4497, `handle_deal_ui`: `value == '❌ Отмена' and pending and pending.startswith('invoice_')`
- Строка 4501, `handle_deal_ui`: `pending == 'invoice_menu' and re.fullmatch('6\\.4\\.\\d+', value)`
- Строка 4509, `handle_deal_ui`: `pending == 'invoice_full_confirm' and value == '✅ Выставить общий счёт'`
- Строка 4513, `handle_deal_ui`: `pending == 'invoice_download'`
- Строка 4522, `handle_deal_ui`: `pending == 'contract_invoice_clause'`
- Строка 4538, `handle_deal_ui`: `pending == 'contract_invoice_confirm' and value == '✅ Выставить счёт'`
- Строка 4559, `handle_deal_ui`: `pending == 'contract_signatory_name'`
- Строка 4569, `handle_deal_ui`: `pending == 'contract_signatory_position'`
- Строка 4579, `handle_deal_ui`: `pending == 'contract_signatory_authority'`
- Строка 4592, `handle_deal_ui`: `pending == 'contract_date'`
- Строка 4608, `handle_deal_ui`: `pending == 'contract_address'`
- Строка 4619, `handle_deal_ui`: `pending in ('search_client', 'search_address', 'get_number')`
- Строка 4631, `handle_deal_ui`: `pending == 'procurement_stock_select'`
- Строка 4652, `handle_deal_ui`: `pending == 'procurement_stock_confirm' and value in ('✅ Использовать найденные остатки', '⏭ Не использовать остатки')`
- Строка 4692, `handle_deal_ui`: `value == '🔄 Изменить статус'`
- Строка 4714, `handle_deal_ui`: `value in transitions`
- Строка 4735, `handle_deal_ui`: `pending == 'transition_invoice_type' and value in ('1. Полностью согласно спецификации', '2. Упрощённый согласно п.6.4', '3. Оба варианта')`
- Строка 4749, `handle_deal_ui`: `pending == 'transition_invoice_clause'`
- Строка 4761, `handle_deal_ui`: `value == '✅ Подтвердить' and state.get('pending_transition')`
- Строка 4831, `handle_deal_ui`: `value == '❌ Отмена'`
- Строка 4836, `handle_deal_ui`: `value == '💰 Экономика' and deal_id`
- Строка 4839, `handle_deal_ui`: `value == '👷 Монтаж по сделке' and deal_id`
- Строка 4857, `handle_deal_ui`: `value == '🧾 Работа со счетами' and deal_id`
- Строка 4861, `handle_deal_ui`: `value == '📋 Общий счёт по спецификации' and deal_id and (pending == 'invoice_menu')`
- Строка 4868, `handle_deal_ui`: `value == '📚 Скачать счёт' and deal_id and (pending == 'invoice_menu')`
- Строка 4887, `handle_deal_ui`: `value == '📦 Закупка по сделке' and deal_id`
- Строка 4892, `handle_deal_ui`: `value in ('🔎 Подобрать из остатков', 'найди в нераспределенных закупках товары похожие на неприобретенные в данной сделке') and deal_id`
- Строка 4919, `handle_deal_ui`: `value in ('📋 Скачать перечень закупки', '📚 Реестр для бухгалтерии') and deal_id`
- Строка 4924, `handle_deal_ui`: `value == '📊 Статус закупок' and deal_id`
- Строка 4944, `handle_deal_ui`: `value == '📎 Загрузить УПД/акт поставщика' and deal_id`
- Строка 4961, `handle_deal_ui`: `pending == 'supplier_closing_invoice' and value in (state.get('supplier_closing_choices') or {})`
- Строка 4967, `handle_deal_ui`: `value == '🏢 Организация продажи' and deal_id`
- Строка 4971, `handle_deal_ui`: `pending == 'procurement_selling_company' and deal_id`
- Строка 4986, `handle_deal_ui`: `value == '🏢 Межфирменные взаиморасчёты' and deal_id`
- Строка 5018, `handle_deal_ui`: `pending == 'procurement_settlement_select' and value in (state.get('procurement_settlement_choices') or {})`
- Строка 5028, `handle_deal_ui`: `pending == 'procurement_settlement_confirm' and value == '✅ Подтвердить компенсацию'`
- Строка 5048, `handle_deal_ui`: `value == '🏦 Сверить оплаты поставщикам' and deal_id`
- Строка 5060, `handle_deal_ui`: `value == '📥 Отметить поступление' and deal_id`
- Строка 5081, `handle_deal_ui`: `pending == 'procurement_receipt_item' and value in (state.get('procurement_receipt_choices') or {})`
- Строка 5088, `handle_deal_ui`: `pending == 'procurement_receipt_qty'`
- Строка 5112, `handle_deal_ui`: `value == '✅ Проверить готовность закупки' and deal_id`
- Строка 5135, `handle_deal_ui`: `pending == 'procurement_close_confirm' and value == '✅ Закрыть закупку'`
- Строка 5148, `handle_deal_ui`: `value in ('🧾 Учесть счёт', '📎 Загрузить счёт поставщика') and deal_id`
- Строка 5155, `handle_deal_ui`: `pending == 'supplier_invoice_confirm' and value == '🔗 Сопоставить с позицией сделки'`
- Строка 5187, `handle_deal_ui`: `pending == 'supplier_manual_mapping'`
- Строка 5217, `handle_deal_ui`: `pending == 'supplier_invoice_confirm' and value == '🧾 В прочую себестоимость сделки'`
- Строка 5250, `handle_deal_ui`: `pending == 'supplier_misc_confirm' and value == '✅ Подтвердить прочую себестоимость'`
- Строка 5264, `handle_deal_ui`: `pending == 'supplier_distribution_edit'`
- Строка 5324, `handle_deal_ui`: `pending == 'supplier_distribution_exclusion_reason'`
- Строка 5349, `handle_deal_ui`: `pending == 'supplier_invoice_confirm' and value in distribution_actions`
- Строка 5431, `handle_deal_ui`: `pending == 'supplier_invoice_confirm' and value == '✅ Применить счёт поставщика'`
- Строка 5532, `handle_deal_ui`: `value == '📑 Работа с договором' and deal_id`
- Строка 5535, `handle_deal_ui`: `value == '🏢 Добавить плательщика' and deal_id`
- Строка 5547, `handle_deal_ui`: `value == '⬅️ Назад к сделке' and deal_id`
- Строка 5550, `handle_deal_ui`: `value == '🏢 Смена нашей фирмы' and deal_id`
- Строка 5556, `handle_deal_ui`: `pending == 'contract_selling_company' and deal_id`
- Строка 5572, `handle_deal_ui`: `value in ('📝 Подготовить договор', '👁 Проверить данные договора') and deal_id`
- Строка 5576, `handle_deal_ui`: `value == '🧾 Выставить счёт по договору' and deal_id`
- Строка 5580, `handle_deal_ui`: `value == '✅ Сформировать договор' and deal_id`
- Строка 5607, `handle_deal_ui`: `value == '✅ Загрузить договоры в сделку' and deal_id`
- Строка 5636, `handle_deal_ui`: `value == '❌ Не загружать' and deal_id`
- Строка 5641, `handle_deal_ui`: `value in ('📑 Получить договор', '📎 Получить договор из Мегаплана') and deal_id`
- Строка 5652, `handle_deal_ui`: `value in ('🛠 Ведомость работ', '📋 Монтажная ведомость', '📄 Позиции сделки') and deal_id`
- Строка 3360, `handle_deal_ui`: `state.get('pending') != 'deal_sync_confirm' or not state.get('deal_sync_spec')`
- Строка 3376, `handle_deal_ui`: `state.get('pending') != 'work_price_confirm' or not prepared`
- Строка 3390, `handle_deal_ui`: `state.get('pending') != 'price_catalog_confirm' or not state.get('price_catalog_spec')`
- Строка 3447, `handle_deal_ui`: `value not in navigation and (not value.startswith('/'))`
- Строка 3473, `handle_deal_ui`: `creation_pending == 'deal_create_title'`
- Строка 3498, `handle_deal_ui`: `value == '🔍 Другой клиент'`
- Строка 3598, `handle_deal_ui`: `not value.isdigit() or not 1 <= int(value) <= len(rows)`
- Строка 3634, `handle_deal_ui`: `value in choices`
- Строка 3646, `handle_deal_ui`: `value == '➕ Создать контакт по монтажу'`
- Строка 3650, `handle_deal_ui`: `len(value.split()) < 2`
- Строка 3672, `handle_deal_ui`: `len(re.sub('\\D', '', value)) < 7`
- Строка 3716, `handle_deal_ui`: `value == '📤 Загрузить новый файл'`
- Строка 3719, `handle_deal_ui`: `value == '✅ Привязать выбранные файлы'`
- Строка 3877, `handle_deal_ui`: `not all((math.isfinite(x) and x >= 0 for x in partial.values()))`
- Строка 3960, `handle_deal_ui`: `pending_now == 'developer_task_running'`
- Строка 3976, `handle_deal_ui`: `not value or value.startswith(('🤝 ', '🧰 ', '📄 ', '❓ '))`
- Строка 4126, `handle_deal_ui`: `value != '📦 Всякая всячина' and (not re.fullmatch('\\d+', value))`
- Строка 4129, `handle_deal_ui`: `value == '📦 Всякая всячина'`
- Строка 4425, `handle_deal_ui`: `value != legacy_report_ui.CONFIRM`
- Строка 4449, `handle_deal_ui`: `not accrual.get('ok') or (accrual.get('result') or {}).get('pending_errors')`
- Строка 4560, `handle_deal_ui`: `value.startswith(('📝 ', '📑 ', '👁 ', '✅ ', '⬅️ ', '🤝 '))`
- Строка 4570, `handle_deal_ui`: `value.startswith(('📝 ', '📑 ', '👁 ', '✅ ', '⬅️ ', '🤝 '))`
- Строка 4593, `handle_deal_ui`: `not re.fullmatch('\\d{2}\\.\\d{2}\\.\\d{4}', value)`
- Строка 4609, `handle_deal_ui`: `len(value) < 5`
- Строка 4621, `handle_deal_ui`: `pending == 'get_number'`
- Строка 4633, `handle_deal_ui`: `value == '❌ Отмена'`
- Строка 4656, `handle_deal_ui`: `value == '✅ Использовать найденные остатки'`
- Строка 4750, `handle_deal_ui`: `not re.fullmatch('6\\.4\\.\\d+', value)`
- Строка 4974, `handle_deal_ui`: `value not in company_ids`
- Строка 5090, `handle_deal_ui`: `value == '✅ Получено полностью'`
- Строка 5327, `handle_deal_ui`: `len(value.strip()) < 3`
- Строка 5355, `handle_deal_ui`: `value == '🔍 Показать другие сделки'`
- Строка 5372, `handle_deal_ui`: `value == '✏️ Изменить распределение'`
- Строка 5381, `handle_deal_ui`: `value == '🚫 Не учитывать остаток'`
- Строка 5558, `handle_deal_ui`: `value not in choices`
- Строка 5657, `handle_deal_ui`: `value in ('🛠 Ведомость работ', '📋 Монтажная ведомость')`
- Строка 3506, `handle_deal_ui`: `not creation.get('deal_create_clients') and value in ('Новый клиент — организация', 'Новый клиент — физическое лицо')`
- Строка 4313, `handle_deal_ui`: `value == '📦 Всякая всячина' and item.get('type') == 'deal'`
- Строка 4323, `handle_deal_ui`: `value == '✅ Принять построчный итог' and item.get('type') == 'discrepancy'`
- Строка 4330, `handle_deal_ui`: `value == '➕ Добавить корректировку' and item.get('type') == 'discrepancy'`
- Строка 4337, `handle_deal_ui`: `value == '✏️ Исправить строки' and item.get('type') == 'discrepancy'`
- Строка 4342, `handle_deal_ui`: `value == '🔢 Указать номер сделки'`
- Строка 4347, `handle_deal_ui`: `value in resolutions`
- Строка 4348, `handle_deal_ui`: `item.get('amount') is None and value != '⏭ Оставить вопросом'`
- Строка 5908, `download_telegram_document`: `(document.get('file_size') or 0) > MAX_INCOMING_DOC_BYTES`
- Строка 5936, `download_telegram_document`: `text_path`
- Строка 6178, `retry_failed_kp`: `not re.fullmatch('(?i)\\s*(?:повтори|повторить|пересобери)\\s+кп[.!]?\\s*', text or '')`
- Строка 6285, `normalize_create_deal_spec`: `normalized_tax not in ('none', '22', '5', 'pending')`
- Строка 6432, `handle_payer_flow_text`: `pending not in ('payer_card_file', 'payer_target_confirm', 'payer_client', 'payer_deal')`
- Строка 6435, `handle_payer_flow_text`: `value.casefold() in ('❌ отменить', 'отмена', 'отменить')`
- Строка 6441, `handle_payer_flow_text`: `pending == 'payer_card_file'`
- Строка 6445, `handle_payer_flow_text`: `pending == 'payer_target_confirm'`
- Строка 6466, `handle_payer_flow_text`: `pending == 'payer_client'`
- Строка 6495, `handle_payer_flow_text`: `value.casefold() in ('без привязки к сделке', 'без привязки', 'не привязывать')`
- Строка 6446, `handle_payer_flow_text`: `value != '✅ Создать и привязать плательщика'`
- Строка 6529, `tax_mode_from_text`: `value in ('1', 'без ндс', 'ндс не облагается', 'none')`
- Строка 6531, `tax_mode_from_text`: `value in ('ндс 22%', '22%', '22') or value.startswith('ндс 22% ')`
- Строка 6533, `tax_mode_from_text`: `value in ('ндс 5%', '5%', '5') or value.startswith('ндс 5% ')`
- Строка 8026, `process_developer_task`: `current.get('pending') == 'developer_task_running'`
- Строка 8035, `installer_media_allowed`: `pending == 'installation_report_collect'`
- Строка 8042, `handle_installer_ui`: `value in ('⬅️ Главное меню', '/menu', '/start', '❌ Отмена')`
- Строка 8048, `handle_installer_ui`: `value in ('📤 Сборный отчёт', '📄 Отправить отчёт')`
- Строка 8055, `handle_installer_ui`: `pending.startswith(('installer_report', 'installer_excel')) and value not in ('🛠 Мои монтажи', '⬅️ Мои монтажи', '📜 История монтажей', '📚 Утверждённые отчёты', '📊 Мои взаиморасчёты', '❓ Помощь')`
- Строка 8065, `handle_installer_ui`: `value in ('/start', '/help', '/помощь', '/menu', '❓ Помощь')`
- Строка 8069, `handle_installer_ui`: `value in ('🛠 Мои монтажи', '⬅️ Мои монтажи')`
- Строка 8078, `handle_installer_ui`: `value in ('📜 История монтажей', '⬅️ История монтажей')`
- Строка 8087, `handle_installer_ui`: `pending == 'installation_mine_select' and value in (state.get('installation_choices') or {})`
- Строка 8092, `handle_installer_ui`: `pending == 'installation_history_select' and value in (state.get('installation_history_choices') or {})`
- Строка 8098, `handle_installer_ui`: `pending in ('installation_object', 'installation_history_object') and value == '📋 Монтажная ведомость'`
- Строка 8105, `handle_installer_ui`: `pending == 'installation_object' and value == '📦 Материалы по счетам'`
- Строка 8139, `handle_installer_ui`: `pending == 'installation_object' and value == '📐 Проектная документация'`
- Строка 8148, `handle_installer_ui`: `pending == 'installation_object' and value == '🧰 Новый отчёт'`
- Строка 8153, `handle_installer_ui`: `pending == 'installation_report_collect' and value == '✅ Все материалы отправлены'`
- Строка 8163, `handle_installer_ui`: `pending == 'installation_report_collect' and value == '❌ Отменить отчёт'`
- Строка 8166, `handle_installer_ui`: `pending == 'installation_report_collect'`
- Строка 8169, `handle_installer_ui`: `value == '📊 Мои взаиморасчёты'`
- Строка 8177, `handle_installer_ui`: `value == '📚 Утверждённые отчёты'`
- Строка 8188, `handle_installer_ui`: `pending == 'installer_approved_report_list' and value.startswith('📄 Отчёт ')`
- Строка 8206, `handle_installer_ui`: `value == '⬅️ Главное меню'`
- Строка 8049, `handle_installer_ui`: `pending.startswith(('installer_report', 'installer_excel')) and state.get('installer_report') and (pending != 'installer_report_submitted')`
- Строка 8057, `handle_installer_ui`: `pending == 'installer_report_exception'`
- Строка 8059, `handle_installer_ui`: `pending == 'installer_excel_report_deal'`
- Строка 8061, `handle_installer_ui`: `value in allowed or free_input`
- Строка 8251, `main`: `owner_state.get('pending') == 'developer_task_running' and owner_state.get('developer_task_text')`
- Строка 8722, `main`: `document_job`
- Строка 8725, `main`: `not request_is_current() and (not (document_job and supplier_invoice_deal_id))`
- Строка 8813, `main`: `is_owner and 'text' in msg and (not supplier_invoice_mode) and (not creation_document_mode) and (not catalog_task_mode) and (not routing_state.get('paused')) and (msg.get('text', '').strip().casefold() not in ('/повторить', 'повтори необработанный запрос'))`
- Строка 8849, `main`: `creation_document_mode`
- Строка 8999, `main`: `creation_document_mode and (not CREATE_MEGAPLAN_DEAL_RE.search(reply))`
- Строка 9520, `main`: `clean_text`
- Строка 9541, `main`: `document_job`
- Строка 9561, `main`: `kp_document_path`
- Строка 8263, `main`: `video_state.get('pending') != 'installation_report_collect'`
- Строка 8281, `main`: `photo_state.get('pending') == 'installation_report_collect'`
- Строка 8289, `main`: `is_installer and (not is_owner)`
- Строка 8297, `main`: `'document' in msg`
- Строка 8727, `main`: `document_job`
- Строка 8749, `main`: `document_job`
- Строка 8783, `main`: `extracted_document_text`
- Строка 8855, `main`: `document_job`
- Строка 8866, `main`: `document_job`
- Строка 8974, `main`: `(catalog_task_mode or needs_fresh_hogart_search(msg.get('text') or msg.get('caption') or '')) and (not catalog_fired_this_message) and (not forced_hogart_refresh)`
- Строка 9697, `main`: `not msg or ('text' not in msg and 'document' not in msg and ('photo' not in msg) and ('video' not in msg))`
- Строка 9709, `main`: `not is_owner and (not is_installer) and (not is_edo_recipient)`
- Строка 9712, `main`: `is_edo_recipient and (not is_owner) and (not is_installer)`
- Строка 9730, `main`: `is_installer and (not is_owner)`
- Строка 9735, `main`: `is_owner and handle_status_query(token, chat_id, msg.get('text'))`
- Строка 9740, `main`: `is_owner and ('reply_to_message' in msg or decision_channel.CODE.match(str(msg.get('text') or '')))`
- Строка 9753, `main`: `not msg.get('_workflow_callback') and str(msg.get('text') or '').startswith('✅ ')`
- Строка 9757, `main`: `is_installer and (not is_owner) and any((k in msg for k in ('document', 'photo', 'video')))`
- Строка 9762, `main`: `is_owner and handle_invoice_cancellation(token, chat_id, msg)`
- Строка 9769, `main`: `msg.get('_workflow_callback') or any((key in msg for key in ('document', 'photo', 'video'))) or direct_slow_command or str(current_deal_ui_state(chat_id).get('pending') or '').startswith('payer_')`
- Строка 8317, `main`: `is_owner and original_ext == '.xlsx' and is_explicit_new_deal_request(caption) and prepare_economics_deal_request(token, chat_id, caption, source_document_path)`
- Строка 8337, `main`: `report_pending == 'installation_report_collect'`
- Строка 8348, `main`: `report_pending == 'installation_project_upload'`
- Строка 8366, `main`: `report_pending in ('installation_workbook_file', 'installation_draft_review') and original_ext == '.xlsx' and report_state.get('installation_deal_id')`
- Строка 8383, `main`: `report_pending == 'supplier_closing_upload'`
- Строка 8441, `main`: `report_pending == 'bank_statement_file'`
- Строка 8472, `main`: `is_installer and (not is_owner) and (not report_pending)`
- Строка 8480, `main`: `report_pending == 'installer_report_file'`
- Строка 8488, `main`: `report_pending == 'installer_report_tables'`
- Строка 8519, `main`: `report_pending == 'installer_payment_file'`
- Строка 8549, `main`: `report_pending == 'payer_card_file'`
- Строка 8559, `main`: `is_owner`
- Строка 8561, `main`: `is_owner and invoice_tasks.accepts_upload(report_state)`
- Строка 8604, `main`: `is_owner and retry_failed_kp(token, chat_id, text)`
- Строка 8608, `main`: `is_owner and handle_global_navigation(token, chat_id, text)`
- Строка 8615, `main`: `is_owner and installer_payment_intent(text)`
- Строка 8618, `main`: `is_owner and handle_payer_flow_text(token, chat_id, text)`
- Строка 8620, `main`: `handle_current_execution_ui(token, chat_id, text)`
- Строка 8622, `main`: `is_installer and (not is_owner)`
- Строка 8625, `main`: `text.strip() in ('/start', '/help', '/помощь', '/menu', '❓ Помощь')`
- Строка 8631, `main`: `handle_bank_ui(token, chat_id, text)`
- Строка 8633, `main`: `handle_deal_ui(token, chat_id, text)`
- Строка 8636, `main`: `is_owner and text.strip().casefold() in ('/повторить', 'повтори необработанный запрос')`
- Строка 8644, `main`: `raw_user_text == '➕ Создать сделку' or is_explicit_new_deal_request(raw_user_text)`
- Строка 8658, `main`: `text.strip() == '💰 Экономика сделки'`
- Строка 8661, `main`: `text.strip() in button_prompts`
- Строка 8835, `main`: `prompt != text`
- Строка 9115, `main`: `_pending_kp_deal is None`
- Строка 9758, `main`: `not installer_media_allowed(msg, current_deal_ui_state(chat_id).get('pending'))`
- Строка 8324, `main`: `document_job.get('deduplicated')`
- Строка 8349, `main`: `os.path.getsize(source_document_path) > 20 * 1024 * 1024`
- Строка 8442, `main`: `os.path.splitext(original_name)[1].casefold() not in ('.xlsx', '.txt')`
- Строка 8626, `main`: `text.strip() in ('/start', '/menu')`
- Строка 8649, `main`: `is_explicit_contract_request(raw_user_text)`
- Строка 8880, `main`: `document_job`
- Строка 9506, `main`: `isinstance(value, dict)`
- Строка 9092, `main`: `RUNTIME_ACTIVE or not should_auto_create_kp_deal(text)`
