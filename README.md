# SmartBild bot

Единый приватный репозиторий автоматизации SmartBild. Здесь находятся Telegram-бот,
интеграция с Мегапланом, каталоги Hogart и Daichi, пульт сделок, документы,
закупки, монтаж и финансовая сверка.

## С чего начать

1. [Архитектура и маршруты данных](docs/ARCHITECTURE.md) — что за что отвечает и как проекты связаны.
2. [Запуск и эксплуатация](docs/OPERATIONS.md) — окружение, процессы, хранилища и диагностика.
3. [Разработка и тестирование](docs/DEVELOPMENT.md) — порядок исправления, тесты и выпуск.
4. [Полный индекс модулей](docs/MODULE_INDEX.md) — каждый Python/JavaScript-модуль и его интерфейс.
5. [Глоссарий](docs/GLOSSARY.md) — термины предметной области.

## Состав репозитория

| Каталог | Назначение | Основная точка входа |
|---|---|---|
| `telegram-bridge` | Telegram-интерфейс, диалоги, фоновые операции, устойчивое состояние и оркестрация | `bridge.py` |
| `megaplan-crm` | API Мегаплана, сделки, договоры, счета, КП, закупки, монтаж и архив | `megaplan_api.py` и специализированные модули |
| `hogart-scraper` | Каталог Hogart, расчёты КП, веб-пульт и финансовый контур | `hogart_api.py`, `dashboard/server.py` |
| `daichi-scraper` | API, кэш и поиск каталога Daichi | `daichi_api.py`, `daichi_search.py` |
| `kids-internet` | Детский интернет по расписанию: KidsBot на VPS и скрипты MikroTik | `vps/app.py`, `mikrotik/sbkb-scripts.rsc.in` |

## Важные границы

- Это снимок **исходного кода**, а не резервная копия рабочей системы.
- В Git намеренно не входят токены, `.env`, базы SQLite, реестры операций, клиентские документы, почтовые выгрузки, кэши и созданные отчёты.
- Без локальных секретов и рабочих хранилищ внешние интеграции не запускаются.
- Зелёный unit-тест не подтверждает запись в CRM, отправку Telegram/email либо сохранение в архив.
- Скрипты `finance/tools` и исторические миграции могут менять реальные данные. Их нельзя запускать для знакомства с проектом.

## Быстрая навигация по задаче

| Нужно изменить | Начать с |
|---|---|
| Меню, кнопки, текстовый диалог | `telegram-bridge/bridge.py`, `human_intents.py`, `ui_context.py` |
| Создание и поиск сделки | `telegram-bridge/deal_creation.py`, `megaplan-crm/deal_browser.py`, `megaplan_api.py` |
| Договор, счёт, КП | `megaplan-crm/generate_contract.py`, `contract_invoice.py`, `deal_proposal.py` |
| Закупка и счёт поставщика | `megaplan-crm/procurement_workflow.py`, `hogart-scraper/finance/procurement_*` |
| Монтаж и отчёт монтажника | `telegram-bridge/installer_*`, `megaplan-crm/installation_workflow.py` |
| Банк и платежи | `megaplan-crm/bank_*`, `hogart-scraper/finance` |
| Веб-пульт | `hogart-scraper/dashboard/server.py`, `dashboard/static` |
| Каталожный поиск/цены | `hogart-scraper/hogart_api.py`, `daichi-scraper/daichi_*` |
| Падение ИИ или повтор операции | `model_recovery.py`, `effect_runner.py`, `workflow_runtime.py` |

Документация построена по исходникам опубликованного снимка. Внешние API и
работающая production-среда при документировании не изменялись и не проверялись.
