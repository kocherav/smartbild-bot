# SmartBild bot monorepo

Private source snapshot of the SmartBild automation stack.

## Projects

- `telegram-bridge` — Telegram UI, workflow state, QA orchestration and tests.
- `megaplan-crm` — Megaplan CRM, finance, procurement, contracts and documents.
- `hogart-scraper` — Hogart integration, reports, dashboard and finance tools.
- `daichi-scraper` — Daichi catalogue integration.

Production state is deliberately excluded: credentials, tokens, SQLite databases,
customer documents, generated reports, caches, financial registries, inboxes,
archives and evidence containing real business data are not part of this repository.

Repository-level operating rules live in each project's `AGENTS.md`. The complete
offline acceptance command is documented in `telegram-bridge/AGENTS.md` and
`telegram-bridge/docs/architecture/TEST_MATRIX.md`.

## Local configuration

Create local `.env` files outside version control. Never commit credentials or
production exports. Runtime directories and generated evidence must remain local.

