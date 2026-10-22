# Запуск и эксплуатация

## Что требуется вне Git

- Python-окружение с фактическими зависимостями;
- Node.js и `npm ci` для Playwright-утилит;
- защищённый `.env`;
- доступ к Telegram, Мегаплану, поставщикам, почте и архиву;
- рабочие SQLite/JSON-реестры либо согласованные пустые хранилища;
- LibreOffice и шрифты для документов; Caddy/systemd для пульта.

В снимке пока нет единого Python lock-файла. Развёртывание с нуля **не
воспроизводимо одной командой**: зависимости рабочего окружения нужно выделить и
зафиксировать отдельным изменением.

## Конфигурация

| Группа | Примеры | Назначение |
|---|---|---|
| Telegram | `BOT_TOKEN`, `TELEGRAM_BOT_TOKEN`, chat/user IDs | polling и доставка |
| Мегаплан | параметры `megaplan_api.load_env()` | REST API CRM |
| Каталоги | `DAICHI_ACCESS_TOKEN`, `DAICHI_API_VERSION` | Daichi API |
| Почта | `IMAP_HOST`, `IMAP_PORT`, `IMAP_USERNAME`, `IMAP_PASSWORD` | read-only intake |
| Пульт | `DASHBOARD_DB`, `DASHBOARD_ORIGIN`, `DASHBOARD_PORT` | SQLite и HTTP |
| Исполнители | `INSTALLER_TELEGRAM_CHAT_ID`, `INSTALLER_TELEGRAM_USERNAMES` | права монтажников |
| Служебные | `BRIDGE_CODEX_BIN`, `QA_SERVICE_USER`, `MEGAPLAN_PRIORITY` | модель/QA/транспорт |

Полный `.env` нельзя восстанавливать догадками. Секреты не добавляются в Git.

## Основные процессы

| Процесс | Команда/файл | Роль |
|---|---|---|
| Telegram bot | `python telegram-bridge/bridge.py` | polling и workers |
| Dashboard | `python hogart-scraper/dashboard/server.py` | приватный API/UI |
| Dashboard sync | `python hogart-scraper/dashboard/sync.py` | read-only снимок CRM |
| Finance intake | `python hogart-scraper/finance/daily.py` | почта → журнал |
| Megaplan webhook | `python megaplan-crm/megaplan_webhook.py` | webhook-сценарий |

Systemd units находятся в `deploy/`. Перед применением проверить пути, пользователя,
EnvironmentFile и права: они относятся к production-размещению вне Git.

## Безопасное знакомство и запуск

1. Запустить изолированные тесты без `.env` и production-хранилищ.
2. Использовать временные каталоги и БД.
3. Убедиться, что сеть замокана/запрещена тестовой обвязкой.
4. Затем подключать только read-only доступ к API.
5. До записи составить карточку: объект, изменение, read-back и восстановление.
6. Не запускать `finance/tools`, миграции и `post_confirmed.py` «для проверки».

## Перезапуск

Telegram-процесс перезапускается через `safe_reload.py`: после workers и между
polling batches. Перед ним проверяются очереди, SHA, quality gate и возможность
отката кода. После — версия процесса, журналы, права на хранилища и read-only smoke.
Откат кода не отменяет уже выполненную хозяйственную операцию.

## Диагностика

| Симптом | Проверить |
|---|---|
| Кнопка открывает другую сделку | callback payload, `ui_context`, snapshot, stale-worker guard |
| Повторный вопрос | pending state, `human_intents`, continuation и контекст worker |
| Повтор подтверждения | operation id, receipt, `effect_runner`, внешний read-back |
| 429/задержка | `megaplan_transport`, очереди и сетевые вызовы до первого ответа |
| ИИ не ответил | `model_recovery`, сохранённый request и ручной путь продолжения |
| Файл есть, результата нет | отдельные receipt CRM/архива/Telegram/email |
| Пустой каталог | пагинация, ошибка API, возраст кэша |
| Дубли денег | idempotency key, read-back и подтверждённая разбивка |

## Резервирование

Git хранит код, но не состояние. SQLite/JSON, оригиналы и квитанции резервируются
отдельно. Перед восстановлением старого реестра внешние операции после его даты
сверяются в CRM, банке и архиве.
