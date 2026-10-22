# Архитектура SmartBild

## Назначение и схема

SmartBild принимает запросы владельца и монтажников через Telegram, читает файлы и
текст, получает каталог и цены поставщиков, обслуживает сделки в Мегаплане,
формирует документы, ведёт закупки, монтажные отчёты и финансовую сверку.

```text
Пользователь / монтажник
          │ Telegram update, текст, кнопка, файл
          ▼
telegram-bridge/bridge.py
  ├─ маршрутизация и контекст диалога
  ├─ извлечение данных / обращение к модели
  ├─ durable operation + preview + подтверждение
  └──────────┬─────────────────┬──────────────────┐
             ▼                 ▼                  ▼
      megaplan-crm       Hogart / Daichi     dashboard
      сделки/документы   каталоги и цены     локальный HTTP API
             │                                     │
             ▼                                     ▼
      Megaplan API                         браузер владельца
             │
      локальные реестры ── OneDrive/email/Telegram
```

Это не монолит с единой БД. Состояние распределено между SQLite, JSON-реестрами и
внешними системами. Поэтому операциям нужны устойчивые идентификаторы, а каждому
внешнему эффекту — отдельная квитанция и обратная проверка.

## Telegram-контур

`telegram-bridge/bridge.py` — композиционный корень: окружение, Telegram polling,
клавиатуры, сценарии диалога и вызовы специализированных модулей. Новую бизнес-
логику следует выносить из него в отдельные модули.

- Маршрутизация: `human_intents`, `incoming_dispatch`, `catalog_conversation`.
- Контекст: `ui_context`, `creation_attachment`, `invoice_continuation`, `order_continuation`.
- Надёжность: `workflow_runtime`, `effect_runner`, `durable_json`, `model_recovery`, `safe_reload`.
- Документы: `invoice_tasks`, `kp_jobs`, `delivery_steps`.
- Монтаж: `installer_*`, `installation_handoff`, `legacy_report_ui`.
- Закупка: `procurement_intake_runtime`, `product_matching_runtime`, `allocation_runtime`, `partial_shipments`.
- QA: `qa_autopilot`, `qa_handoff`, инструменты `docs/architecture`.

## CRM и документы

`megaplan-crm/megaplan_api.py` — низкоуровневый REST-клиент. Выше него работают:

- `deal_browser` — чтение, поиск и переходы сделки;
- `deal_proposal` — КП из фактических строк CRM;
- `generate_contract`, `contract_invoice`, `document_order` — договор и счета;
- `payer_manager`, `payer_signatory_store`, `own_companies`, `seller_documents` — стороны и подписанты;
- `procurement_workflow`, `procurement_projection`, `hogart_procurement` — закупка;
- `installation_workflow`, `installation_materials`, `shipment_finance` — монтаж и отгрузка;
- `bank_statement`, `bank_matcher`, `megaplan_finance` — платежи;
- `financial_archive`, `archive_outbox`, `report_media_store` — файлы и отложенная доставка.

`megaplan_transport.py` задаёт общий бюджет обращений и circuit breaker. После
неизвестного результата записи выполняется read-back, а не слепой повтор.

## Каталоги и расчёты

`hogart_api.py` и `daichi_api.py` — клиенты поставщиков. Кэши и поиск отделены от
API, чтобы недоступность поставщика не выглядела как пустой каталог.
`generate_kp.py`, `price_spec_items.py`, `price_install_addons.py` и `xlsx_report.py`
считают и визуализируют КП. Файлы `.mjs` — операторские сценарии Playwright, а не
основной серверный маршрут бота.

## Веб-пульт

`hogart-scraper/dashboard/server.py` обслуживает приватный API и статическое
приложение за Caddy, проверяет Telegram WebApp init data и работает с SQLite.

- `model.py` — проекции данных;
- `workspace.py` — планы и рабочее пространство объекта;
- `shipment_workspace.py` — отгрузки;
- `matching_store.py` — очередь сопоставлений;
- `supplier_documents.py` — документы поставщика;
- `sync.py` — полный read-only снимок Мегаплана;
- `static/*.js` — клиентские экраны.

## Финансовый контур

`hogart-scraper/finance` ведёт проверяемый импорт банковских и закупочных документов:

```text
почта/ZIP/документ → безопасное чтение → ledger → review_registry
→ подтверждённое сопоставление → post_confirmed → read-back и отчёт
```

Источник фактов — журнал/реестр, XLSX является проекцией. `finance/tools` содержит
исторические одноразовые утилиты конкретных сверок. Новую общую логику туда
добавлять нельзя.

## Механизмы сохранности

- `workflow_runtime` — операция, статус, квитанции и вопросы владельцу;
- `effect_runner` — локальная защита exactly-once и неизвестный внешний результат;
- `registry_transaction`/`durable_json` — блокировка и атомарная запись;
- `ui_context` — кнопка и worker привязаны к исходному сообщению;
- `delivery_steps` — независимые квитанции каналов доставки;
- `safe_reload` — перезагрузка между polling-пакетами после завершения workers.

## Основные маршруты

**Создание сделки:** ввод/файл → намерение → поиск клиента → строки → preview →
подтверждение → запись CRM → обратное чтение ID, строк и сумм → ответ пользователю.

**Документы:** сделка → продавец/плательщик/налог → preview → генерация → проверка
PDF → CRM/архив → доставка → отдельные квитанции.

**Закупка:** оригинал счёта → разбор → сопоставление → подтверждение распределения
→ реестр → финансовая проекция → архив.

**Монтаж:** назначение → ведомость → отчёт → preview/сопоставление → приёмка →
накопительный план/факт → начисление → публикация. Повтор не повторяет начисление.

**Платёж:** выписка → неизменяемый импорт → кандидаты → подтверждение →
идемпотентная запись → обратная сверка.

## Исторические материалы

`telegram-bridge/docs/architecture/*/before` — снимки до исправлений, не актуальная
реализация. Действующие правила: `TEST_MATRIX.md`, `SCENARIOS.md`, `DECISIONS.md` и
`VERIFIABLE_REALITY_PROTOCOL.md`.
