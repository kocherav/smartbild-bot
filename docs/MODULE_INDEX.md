# Полный индекс модулей

Создан `tools/generate_module_index.py` статическим разбором исходников.
Модули не импортируются, конфигурация и сеть не читаются.

## `telegram-bridge`

| Файл | Тип | Назначение | Публичный интерфейс |
|---|---|---|---|
| `telegram-bridge/allocation_runtime.py` | Рабочий модуль | Resumable application of dashboard-confirmed supplier cost allocations. | `money`, `sync_deal`, `process`, `poll`, `poll_in_environment` |
| `telegram-bridge/bridge.py` | Рабочий модуль | Главный Telegram polling-процесс, меню, обработчики сообщений и композиция бизнес-сценариев. | `notify_installers`, `deliver_installation_handoffs`, `notify_megaplan_protection`, `complete_installation_handoff`, `home_keyboard`, `installer_review_keyboard`, `load_approved_installer_reports`, `save_approved_installer_report`, `approved_report_text`, `load_env`, `create_document_job`, `finish_document_job` (+208) |
| `telegram-bridge/build_cumulative_deal_execution.py` | Рабочий модуль | Build a cumulative plan/fact workbook for one deal from a multi-period table. | `normalized`, `approved_table_totals`, `build` |
| `telegram-bridge/build_current_execution.py` | Рабочий модуль | Build the best available cumulative execution workbook for a deal. | `safe`, `build_generic`, `build` |
| `telegram-bridge/build_installer_report_mockups.py` | Рабочий модуль | Создание демонстрационных XLSX-макетов отчёта монтажника и сверки владельца. | `setup`, `style_body`, `reconciliation_sheet`, `owner_book`, `installer_book` |
| `telegram-bridge/build_installer_report_result.py` | Рабочий модуль | Create the final approved installer-report workbook from a review session. | `header`, `widths`, `style`, `safe_sheet`, `deal_sheet_name`, `add_deal_sheet`, `add_execution_sheet`, `build` |
| `telegram-bridge/catalog_conversation.py` | Рабочий модуль | A catalog conversation owns its followups; pending documents cannot capture them. | `proposal_requested`, `explicit`, `is_turn`, `begin`, `finish`, `prompt`, `search_failure`, `guard` |
| `telegram-bridge/closing_runtime.py` | Рабочий модуль | Closing delivery integration. Test runs never create invoices or change CRM states. | `env`, `recipient`, `now`, `registry`, `api`, `effect`, `tg`, `send_file`, `sources`, `deadline`, `onedrive_url`, `procurement_links` (+17) |
| `telegram-bridge/closing_scheme.py` | Рабочий модуль | Prepare an auditable minimal transition change for the installation scheme. | `plan` |
| `telegram-bridge/closing_workflow.py` | Рабочий модуль | Closing workflow decisions and durable state. No remote effects in this module. | `cents`, `next_business_day`, `final_clause`, `settled_amount`, `bank_closure_allowed`, `Registry` |
| `telegram-bridge/company_cards.py` | Рабочий модуль | Serve approved own-company cards without model generation or CRM writes. | `normalize`, `handle_request` |
| `telegram-bridge/convert_document.py` | Рабочий модуль | Converts a Word/Excel document (supplier invoices/КП often arrive as one of these, not | `convert` |
| `telegram-bridge/creation_attachment.py` | Рабочий модуль | Explicit creation instructions survive separate attachment/model turns. | `explicit`, `initial_state`, `awaiting_file`, `is_current`, `prompt` |
| `telegram-bridge/deal_creation.py` | Рабочий модуль | Deterministic final review; extraction must never itself authorize a CRM write. | `number`, `rub`, `qty_text`, `review` |
| `telegram-bridge/decision_channel.py` | Рабочий модуль | Owner decisions via the existing bot polling process, never a second poller. | `consume`, `ask`, `main` |
| `telegram-bridge/delivery_steps.py` | Рабочий модуль | Per-channel durable receipts; retry must not resend already delivered files. | `deliver` |
| `telegram-bridge/docs/architecture/861-signed-cash/attach_contract.py` | Архитектурный инструмент или исторический снимок | Узкоспециализированная утилита «attach contract»; интерфейс перечислен справа. | `save` |
| `telegram-bridge/docs/architecture/861-signed-cash/record_cash.py` | Архитектурный инструмент или исторический снимок | Узкоспециализированная утилита «record cash»; интерфейс перечислен справа. | `save` |
| `telegram-bridge/docs/architecture/act861-correction-20261014/deliver.py` | Архитектурный инструмент или исторический снимок | Узкоспециализированная утилита «deliver»; интерфейс перечислен справа. | `save`, `step` |
| `telegram-bridge/docs/architecture/act861-correction-20261014/prepare.py` | Архитектурный инструмент или исторический снимок | Узкоспециализированная утилита «prepare»; интерфейс перечислен справа. | — |
| `telegram-bridge/docs/architecture/act861-date-20260930/deliver.py` | Архитектурный инструмент или исторический снимок | Узкоспециализированная утилита «deliver»; интерфейс перечислен справа. | `save`, `step` |
| `telegram-bridge/docs/architecture/attachments-20261012/before/closing_runtime.py` | Архитектурный инструмент или исторический снимок | Closing delivery integration. Test runs never create invoices or change CRM states. | `env`, `recipient`, `now`, `registry`, `api`, `effect`, `tg`, `send_file`, `sources`, `deadline`, `onedrive_url`, `procurement_links` (+11) |
| `telegram-bridge/docs/architecture/audit-20261012-installer/before/bridge.py` | Архитектурный инструмент или исторический снимок | Узкоспециализированная утилита «bridge»; интерфейс перечислен справа. | `notify_installers`, `deliver_installation_handoffs`, `notify_megaplan_protection`, `complete_installation_handoff`, `home_keyboard`, `installer_review_keyboard`, `load_approved_installer_reports`, `save_approved_installer_report`, `approved_report_text`, `load_env`, `create_document_job`, `finish_document_job` (+184) |
| `telegram-bridge/docs/architecture/audit-20261012-installer/before/installer_report_intake.py` | Архитектурный инструмент или исторический снимок | Build a compact, read-only review session for an installer PDF report. | `pdf_text`, `identify_report`, `mapped_object`, `number`, `table_profile`, `table_score`, `attach_tables`, `date_from_filename`, `build_excel_session`, `build_session`, `main` |
| `telegram-bridge/docs/architecture/closing-20261012/before/bridge.py` | Архитектурный инструмент или исторический снимок | Узкоспециализированная утилита «bridge»; интерфейс перечислен справа. | `notify_installers`, `deliver_installation_handoffs`, `notify_megaplan_protection`, `complete_installation_handoff`, `home_keyboard`, `installer_review_keyboard`, `load_approved_installer_reports`, `save_approved_installer_report`, `approved_report_text`, `load_env`, `create_document_job`, `finish_document_job` (+184) |
| `telegram-bridge/docs/architecture/closing-live-20261013/before/bridge.py` | Архитектурный инструмент или исторический снимок | Узкоспециализированная утилита «bridge»; интерфейс перечислен справа. | `notify_installers`, `deliver_installation_handoffs`, `notify_megaplan_protection`, `complete_installation_handoff`, `home_keyboard`, `installer_review_keyboard`, `load_approved_installer_reports`, `save_approved_installer_report`, `approved_report_text`, `load_env`, `create_document_job`, `finish_document_job` (+184) |
| `telegram-bridge/docs/architecture/closing-live-20261013/before/closing_runtime.py` | Архитектурный инструмент или исторический снимок | Closing delivery integration. Test runs never create invoices or change CRM states. | `env`, `recipient`, `now`, `registry`, `api`, `effect`, `tg`, `send_file`, `sources`, `deadline`, `onedrive_url`, `procurement_links` (+12) |
| `telegram-bridge/docs/architecture/export_document.py` | Архитектурный инструмент или исторический снимок | Build a readable, self-contained DOCX from the architecture source documents. | `plain` |
| `telegram-bridge/docs/architecture/extract_message_handler.py` | Архитектурный инструмент или исторический снимок | Print an AST-checked mechanical patch; never edit source directly. | `point`, `walk` |
| `telegram-bridge/docs/architecture/historical-shipment-861/read_only_trial.py` | Архитектурный инструмент или исторический снимок | Узкоспециализированная утилита «read only trial»; интерфейс перечислен справа. | `read_call` |
| `telegram-bridge/docs/architecture/inventory.py` | Архитектурный инструмент или исторический снимок | Static inventory. Never imports the bot, reads configuration or calls APIs. | `literals`, `scan`, `render` |
| `telegram-bridge/docs/architecture/live_smoke.py` | Архитектурный инструмент или исторический снимок | Explicit read-only connector smoke check. No sends, orders or CRM writes. | `main` |
| `telegram-bridge/docs/architecture/offline_tests.py` | Архитектурный инструмент или исторический снимок | Run existing tests in source-only temporary copies with side effects blocked. | `main` |
| `telegram-bridge/docs/architecture/position-types-20261014/before/generate_contract.py` | Архитектурный инструмент или исторический снимок | Build a Cliwell deal contract from live Megaplan data. | `money_value`, `rubles`, `rubles_words`, `classify`, `classify_position`, `lower_first`, `subject_for_title`, `subject_for_body`, `is_full_person_name`, `contract_data`, `all_paragraphs`, `table_paragraphs` (+17) |
| `telegram-bridge/docs/architecture/position-types-20261014/before/megaplan_api.py` | Архитектурный инструмент или исторический снимок | Thin client for Megaplan CRM's official REST API v3 (cclimat.megaplan.ru). | `comparable_contractor_name`, `comparable_contractor_tokens`, `upsert_deal_browser_cache`, `load_env`, `MegaplanAPIError`, `MegaplanAPI` |
| `telegram-bridge/docs/architecture/position-types-20261014/check_act.py` | Архитектурный инструмент или исторический снимок | Узкоспециализированная утилита «check act»; интерфейс перечислен справа. | — |
| `telegram-bridge/docs/architecture/position-types-20261014/refresh_books.py` | Архитектурный инструмент или исторический снимок | Узкоспециализированная утилита «refresh books»; интерфейс перечислен справа. | — |
| `telegram-bridge/docs/architecture/position-types-20261014/verify_live.py` | Архитектурный инструмент или исторический снимок | Узкоспециализированная утилита «verify live»; интерфейс перечислен справа. | — |
| `telegram-bridge/docs/architecture/prepare_act861_date.py` | Архитектурный инструмент или исторический снимок | Узкоспециализированная утилита «prepare act861 date»; интерфейс перечислен справа. | — |
| `telegram-bridge/docs/architecture/qa_agent.py` | Архитектурный инструмент или исторический снимок | SmartBild QA orchestrator: evidence in, deduplicated developer tasks out. | `utc_now`, `load_json`, `atomic_save`, `report_failures`, `human_coverage_failures`, `is_external`, `task_kind`, `shared_provenance`, `severity`, `fingerprint`, `developer_prompt`, `Registry` (+6) |
| `telegram-bridge/docs/architecture/quality_gate.py` | Архитектурный инструмент или исторический снимок | Release receipt: fail on tests, isolation escapes, skips or changed source. | `verify` |
| `telegram-bridge/docs/architecture/scenario_contracts.py` | Архитектурный инструмент или исторический снимок | Versioned scenario ownership for the current bridge and its successor. | `owner`, `values`, `inventory` |
| `telegram-bridge/docs/architecture/shipment-861-fix/before/closing_documents.py` | Архитектурный инструмент или исторический снимок | Узкоспециализированная утилита «closing documents»; интерфейс перечислен справа. | `font`, `p`, `heading`, `table`, `base`, `signs`, `floating_picture`, `special_notes`, `money`, `sign_block`, `validate_contract_rows`, `act_number` (+4) |
| `telegram-bridge/docs/architecture/shipment-861-fix/before/contract_invoice.py` | Архитектурный инструмент или исторический снимок | Create a one-line Megaplan invoice from a payment clause in the latest deal contract. | `money`, `megaplan_date`, `contract_basis`, `basis_from_deal`, `document_text`, `parse_contract`, `latest_contract`, `preview_fingerprint`, `validate_contract_context`, `preview`, `payment_offer`, `v1_call` (+10) |
| `telegram-bridge/docs/architecture/shipment-861-fix/before/partial_shipments.py` | Архитектурный инструмент или исторический снимок | Bridge worker for owner-confirmed dashboard shipments. | `snapshot`, `validate`, `import_full_jobs`, `poll`, `apply`, `all_edo`, `invoice`, `to_ship`, `queue_remainders` |
| `telegram-bridge/docs/architecture/shipment-861-fix/before/shipment_workspace.py` | Архитектурный инструмент или исторический снимок | One shipment ledger shared by the dashboard and the document worker. | `decimal`, `digest`, `connection`, `book`, `request`, `save_book`, `pending_books`, `shipments`, `patch`, `used`, `projection`, `select` (+3) |
| `telegram-bridge/docs/architecture/shipments-20261013/before/closing_documents.py` | Архитектурный инструмент или исторический снимок | Узкоспециализированная утилита «closing documents»; интерфейс перечислен справа. | `font`, `p`, `heading`, `table`, `base`, `signs`, `floating_picture`, `special_notes`, `money`, `sign_block`, `validate_contract_rows`, `act_number` (+4) |
| `telegram-bridge/docs/architecture/shipments-20261013/before/closing_runtime.py` | Архитектурный инструмент или исторический снимок | Closing delivery integration. Test runs never create invoices or change CRM states. | `env`, `recipient`, `now`, `registry`, `api`, `effect`, `tg`, `send_file`, `sources`, `deadline`, `onedrive_url`, `procurement_links` (+15) |
| `telegram-bridge/docs/architecture/shipments-20261013/before/closing_workflow.py` | Архитектурный инструмент или исторический снимок | Closing workflow decisions and durable state. No remote effects in this module. | `cents`, `next_business_day`, `final_clause`, `settled_amount`, `bank_closure_allowed`, `Registry` |
| `telegram-bridge/docs/architecture/shipments-20261013/before/server.py` | Архитектурный инструмент или исторический снимок | Private dashboard API and static app, bound to loopback behind Caddy. | `read_env`, `credentials`, `verify_telegram`, `ClosingConnection`, `connect`, `initialize`, `digest`, `new_session`, `session_user`, `snapshot`, `task_rows`, `save_task` (+4) |
| `telegram-bridge/docs/architecture/snapshot_runtime.py` | Архитектурный инструмент или исторический снимок | Protected local rollback evidence; never restores business registries automatically. | `main` |
| `telegram-bridge/docs/architecture/test_inventory.py` | Архитектурный инструмент или исторический снимок | Узкоспециализированная утилита «test inventory»; интерфейс перечислен справа. | `InventoryTest` |
| `telegram-bridge/docs/architecture/test_qa_agent.py` | Архитектурный инструмент или исторический снимок | Узкоспециализированная утилита «test qa agent»; интерфейс перечислен справа. | `QaAgentTests`, `HumanProfileTests` |
| `telegram-bridge/docs/architecture/test_quality_gate.py` | Архитектурный инструмент или исторический снимок | Узкоспециализированная утилита «test quality gate»; интерфейс перечислен справа. | `QualityGateTests` |
| `telegram-bridge/docs/architecture/vat5-20261013/before/bridge.py` | Архитектурный инструмент или исторический снимок | Узкоспециализированная утилита «bridge»; интерфейс перечислен справа. | `notify_installers`, `deliver_installation_handoffs`, `notify_megaplan_protection`, `complete_installation_handoff`, `home_keyboard`, `installer_review_keyboard`, `load_approved_installer_reports`, `save_approved_installer_report`, `approved_report_text`, `load_env`, `create_document_job`, `finish_document_job` (+184) |
| `telegram-bridge/docs/architecture/vat5-20261013/before/closing_documents.py` | Архитектурный инструмент или исторический снимок | Узкоспециализированная утилита «closing documents»; интерфейс перечислен справа. | `font`, `p`, `heading`, `table`, `base`, `signs`, `floating_picture`, `special_notes`, `money`, `sign_block`, `validate_contract_rows`, `generate_act` (+1) |
| `telegram-bridge/docs/architecture/vat5-20261013/before/closing_runtime.py` | Архитектурный инструмент или исторический снимок | Closing delivery integration. Test runs never create invoices or change CRM states. | `env`, `recipient`, `now`, `registry`, `api`, `effect`, `tg`, `send_file`, `sources`, `deadline`, `onedrive_url`, `procurement_links` (+13) |
| `telegram-bridge/docs/architecture/vat5-20261013/before/contract_invoice.py` | Архитектурный инструмент или исторический снимок | Create a one-line Megaplan invoice from a payment clause in the latest deal contract. | `money`, `megaplan_date`, `contract_basis`, `basis_from_deal`, `document_text`, `parse_contract`, `latest_contract`, `preview_fingerprint`, `validate_contract_context`, `preview`, `payment_offer`, `v1_call` (+10) |
| `telegram-bridge/docs/architecture/vat5-20261013/before/deal_creation.py` | Архитектурный инструмент или исторический снимок | Deterministic final review; extraction must never itself authorize a CRM write. | `number`, `review` |
| `telegram-bridge/docs/architecture/vat5-20261013/before/document_tax_policy.py` | Архитектурный инструмент или исторический снимок | Guard the existing no-VAT contract template; never silently relabel tax. | `require_no_vat` |
| `telegram-bridge/docs/architecture/vat5-20261013/before/generate_contract.py` | Архитектурный инструмент или исторический снимок | Build a Cliwell deal contract from live Megaplan data. | `money_value`, `rubles`, `rubles_words`, `classify`, `classify_position`, `lower_first`, `subject_for_title`, `subject_for_body`, `is_full_person_name`, `contract_data`, `all_paragraphs`, `table_paragraphs` (+17) |
| `telegram-bridge/docs/architecture/vat5-20261013/before/megaplan_api.py` | Архитектурный инструмент или исторический снимок | Thin client for Megaplan CRM's official REST API v3 (cclimat.megaplan.ru). | `comparable_contractor_name`, `comparable_contractor_tokens`, `upsert_deal_browser_cache`, `load_env`, `MegaplanAPIError`, `MegaplanAPI` |
| `telegram-bridge/docs/architecture/vat5-20261013/before/replace_deal_from_kp.py` | Архитектурный инструмент или исторический снимок | Atomically replace an existing deal's rows with a confirmed KP specification. | `normalize_spec`, `backup_deal`, `deal_fingerprint`, `validate_rows`, `run` |
| `telegram-bridge/durable_json.py` | Рабочий модуль | Small fail-closed storage for legacy ledgers while their readers coexist. | `locked`, `transaction`, `read`, `save` |
| `telegram-bridge/effect_runner.py` | Рабочий модуль | Exactly-once local dispatch with honest handling of uncertain remote effects. | `execute` |
| `telegram-bridge/extract_document_text.py` | Рабочий модуль | Read Office invoice cells without empty merged-cell noise; no external writes. | `extract` |
| `telegram-bridge/handoff_watcher.py` | Рабочий модуль | Task exchange between the AI tester and the developer agent through Git. | `utc_now`, `parse`, `needs_owner`, `developer_prompt`, `repository`, `discover`, `read_state`, `save_state`, `plan`, `decide`, `start`, `finish` (+5) |
| `telegram-bridge/hogart_closing.py` | Рабочий модуль | Fetch verified Trio Climate closing originals before composing accountant hints. | `money`, `DocumentList`, `documents`, `candidates`, `validate_text`, `fetch`, `sync` |
| `telegram-bridge/human_fixtures.py` | Рабочий модуль | Read-only CRM snapshots for human journeys. | `crm_cli`, `capture`, `provenance_path`, `register`, `current_provenance`, `verified_snapshot`, `load` |
| `telegram-bridge/human_intents.py` | Рабочий модуль | Conservative routing of ordinary Russian business requests. | `Intent`, `name_stems`, `classify` |
| `telegram-bridge/human_live_journeys.py` | Рабочий модуль | Human journeys on a read-only snapshot of the real CRM. | `money`, `LiveSnapshotJourneys` |
| `telegram-bridge/human_qa_explorer.py` | Рабочий модуль | AI exploratory tester: a language model plays the manager on the QA stand. | `CodexBrain`, `CommandBrain`, `parse_json`, `load_missions`, `choose`, `screen_for_actor`, `explore`, `judge`, `case_from`, `fixture_from`, `live_model_stand`, `main` |
| `telegram-bridge/human_qa_harness.py` | Рабочий модуль | Human QA stand: the real bridge.main() talks to a virtual operator. | `run_script_in_process`, `JourneyStop`, `SimulatedCrash`, `ForkedChildDone`, `FakeTelegram`, `FakeMegaplan`, `ScriptedModel`, `codex_jsonl`, `Action`, `say`, `press`, `press_old` (+7) |
| `telegram-bridge/incoming_dispatch.py` | Рабочий модуль | Track routing separately from completion of background business operations. | `tracked` |
| `telegram-bridge/installation_handoff.py` | Рабочий модуль | Durable handoff delivery, independent of dialog state and financial writes. | `deliver` |
| `telegram-bridge/installer_material_delivery.py` | Рабочий модуль | Price-free material files, authorized against current installer assignment. | `authorize`, `build` |
| `telegram-bridge/installer_onboarding.py` | Рабочий модуль | Owner-approved additional Telegram accounts for the existing installer. | `connect`, `members`, `invitation`, `request`, `decide`, `handle` |
| `telegram-bridge/installer_report_intake.py` | Рабочий модуль | Build a review draft from actual PDF/Word/Excel contents; never post finances. | `ExtractedText`, `pdf_text`, `mapped_object`, `number`, `table_profile`, `table_score`, `attach_tables`, `date_from_filename`, `build_excel_session`, `build_session`, `main` |
| `telegram-bridge/installer_report_text.py` | Рабочий модуль | Conservative extraction of actual installer report text; no pilot data lookup. | `money`, `amount_of`, `logical_lines`, `parse_rows`, `docx_text`, `ocr_page`, `extract_pdf` |
| `telegram-bridge/installer_settlements.py` | Рабочий модуль | Persistent installer accrual/payment ledger and cumulative Excel export. | `load`, `save`, `digest_file`, `operation_id`, `record_accrual`, `allocate_available_advances`, `pdf_text`, `parse_amount`, `parse_payment`, `balances`, `date_key`, `reconcile_all` (+5) |
| `telegram-bridge/installer_workbook_intake.py` | Рабочий модуль | Read our quantity-based workbook as a draft, with canonical accepted quantities. | `canonical`, `read` |
| `telegram-bridge/invoice_continuation.py` | Рабочий модуль | Bind a conversational invoice draft to a real, recent attachment. | `remember`, `bind`, `context` |
| `telegram-bridge/invoice_tasks.py` | Рабочий модуль | Durable document queue and deterministic cancellation, independent of model history. | `normal`, `same_number`, `read`, `change`, `active`, `register`, `cancellation_number`, `cancel`, `cancelled`, `history`, `pause`, `complete` (+4) |
| `telegram-bridge/kp_jobs.py` | Рабочий модуль | Retain deterministic proposal jobs, including failures and their original specification. | `run`, `latest_failed` |
| `telegram-bridge/legacy_report_ui.py` | Рабочий модуль | Manager preview/mapping for the transition from collected legacy reports. | `stage`, `apply_material_decision`, `apply_mapping`, `source_target`, `edit_rows` |
| `telegram-bridge/migration_transition_guard.py` | Рабочий модуль | Suppress procurement side effects during an explicitly recorded migration. | `blocked` |
| `telegram-bridge/model_recovery.py` | Рабочий модуль | Durable, user-visible model failures; no credentials or automatic side-effect replay. | `compact`, `ModelUnavailable`, `failure_kind`, `key`, `save_failure`, `begin_request`, `mark_answered`, `latest`, `failure_message` |
| `telegram-bridge/order_continuation.py` | Рабочий модуль | Keep the requested documents attached to the deal creation intent. | `requested`, `parse`, `question`, `recovery_hint` |
| `telegram-bridge/partial_shipments.py` | Рабочий модуль | Bridge worker for owner-confirmed dashboard shipments. | `round_document_rows`, `document_payer`, `snapshot`, `validate`, `import_full_jobs`, `poll`, `apply`, `payment_context`, `payment_summary`, `all_edo`, `partial_invoice_text`, `reconcile_partial_invoice` (+3) |
| `telegram-bridge/periodic_schedule.py` | Рабочий модуль | Persistent rate gate for read-only watchers, including process restarts. | `claim`, `claim_daily` |
| `telegram-bridge/pilot_match_installer_reports.py` | Рабочий модуль | Read-only pilot: map four installer reports to live Megaplan deal positions. | `plain`, `norm`, `score`, `deal_for`, `load_deals`, `suggest_position`, `header`, `body_style`, `main` |
| `telegram-bridge/procurement_attachments.py` | Рабочий модуль | Verified originals for accountant delivery; OneDrive remains an internal archive. | `download`, `build`, `email_messages` |
| `telegram-bridge/procurement_intake_runtime.py` | Рабочий модуль | Supplier document ingestion and new line matching, independent of visiting a deal. | `infer_document`, `status`, `process_commands`, `ingest`, `automatic`, `poll`, `poll_in_environment` |
| `telegram-bridge/product_matching_runtime.py` | Рабочий модуль | Background semantic matching through the bot's existing Codex connection. | `infer`, `poll` |
| `telegram-bridge/qa_autopilot.py` | Рабочий модуль | Scheduled QA execution, technical handoff, and owner digest. | `run`, `owner_messages_allowed`, `reviewable`, `technical`, `approve_technical`, `defer_external`, `digest` |
| `telegram-bridge/qa_handoff.py` | Рабочий модуль | Human-approved handoff from QA findings to the existing developer agent. | `now`, `ready`, `summarize`, `developer_prompt`, `mark_notified`, `decide`, `claim`, `finish`, `defer_external`, `resume_waiting` |
| `telegram-bridge/qa_schedule.py` | Рабочий модуль | The approved AI-tester schedule (docs/architecture/QA_SCHEDULE.json). | `validate`, `handoff_config`, `load`, `moscow`, `human_interval_seconds`, `full_daily_utc_hour`, `in_night_window`, `night_sequence`, `digest_due`, `focus`, `missions_for`, `plan_text` |
| `telegram-bridge/reconcile_operations.py` | Рабочий модуль | Local operator tool. Never calls a remote write or automatically replays input. | `main` |
| `telegram-bridge/requisites_card.py` | Рабочий модуль | Deterministic extraction of Russian company requisites from PDF/Word text. | `compact_digits`, `document_text`, `value_after_label`, `parse`, `is_requisites_card`, `parse_document`, `parse_document_from_text` |
| `telegram-bridge/runtime_guards.py` | Рабочий модуль | Incremental adapter around existing business functions, not an AI router. | `install`, `decorate` |
| `telegram-bridge/safe_reload.py` | Рабочий модуль | Reload only between polling batches and after all workers have exited. | `bundle_manifest`, `request`, `pending_reviewed`, `apply_if_idle` |
| `telegram-bridge/settlement_view.py` | Рабочий модуль | Read-only combined settlement view. Never rewrites historical allocations. | `combined` |
| `telegram-bridge/statement_document_context.py` | Рабочий модуль | Recognize requested statement documents locally; never infer a project or post money. | `match_document`, `prompt_context`, `recent_context`, `deal_candidates`, `exclude_documents` |
| `telegram-bridge/supplier_completion.py` | Рабочий модуль | Keep committed procurement separate from completion of files and archives. | `pending_steps`, `record`, `summary` |
| `telegram-bridge/test_bridge_protocol.py` | Тест | Узкоспециализированная утилита «test bridge protocol»; интерфейс перечислен справа. | `ProtocolTest` |
| `telegram-bridge/test_catalog_conversation.py` | Тест | Узкоспециализированная утилита «test catalog conversation»; интерфейс перечислен справа. | `RoutingTests`, `ActualRoutingBlockTests` |
| `telegram-bridge/test_closing_protection_retry.py` | Тест | Узкоспециализированная утилита «test closing protection retry»; интерфейс перечислен справа. | `ClosingProtectionRetryTest` |
| `telegram-bridge/test_closing_runtime.py` | Тест | Узкоспециализированная утилита «test closing runtime»; интерфейс перечислен справа. | `ClosingIntegrationTests`, `EdoScreenshotTests` |
| `telegram-bridge/test_closing_workflow.py` | Тест | Узкоспециализированная утилита «test closing workflow»; интерфейс перечислен справа. | `ClosingTests` |
| `telegram-bridge/test_company_cards.py` | Тест | Узкоспециализированная утилита «test company cards»; интерфейс перечислен справа. | `CardsTest` |
| `telegram-bridge/test_creation_attachment.py` | Тест | Узкоспециализированная утилита «test creation attachment»; интерфейс перечислен справа. | `CreationAttachmentTests` |
| `telegram-bridge/test_creation_scenario.py` | Тест | Узкоспециализированная утилита «test creation scenario»; интерфейс перечислен справа. | `CreationScenarioTest` |
| `telegram-bridge/test_crm_runtime_python.py` | Тест | Узкоспециализированная утилита «test crm runtime python»; интерфейс перечислен справа. | `RuntimePythonTests` |
| `telegram-bridge/test_dashboard_navigation.py` | Тест | Узкоспециализированная утилита «test dashboard navigation»; интерфейс перечислен справа. | `DashboardNavigationTests` |
| `telegram-bridge/test_deal_creation_review.py` | Тест | Узкоспециализированная утилита «test deal creation review»; интерфейс перечислен справа. | `ReviewTest` |
| `telegram-bridge/test_decision_channel.py` | Тест | Узкоспециализированная утилита «test decision channel»; интерфейс перечислен справа. | `DecisionChannelTest` |
| `telegram-bridge/test_delivery_steps.py` | Тест | Узкоспециализированная утилита «test delivery steps»; интерфейс перечислен справа. | `DeliveryTest` |
| `telegram-bridge/test_effect_runner.py` | Тест | Узкоспециализированная утилита «test effect runner»; интерфейс перечислен справа. | `EffectsTest` |
| `telegram-bridge/test_email_notification_ui.py` | Тест | Узкоспециализированная утилита «test email notification ui»; интерфейс перечислен справа. | `EmailNotificationTests` |
| `telegram-bridge/test_full_transfer_stage_path.py` | Тест | Узкоспециализированная утилита «test full transfer stage path»; интерфейс перечислен справа. | `FullTransferPathTests` |
| `telegram-bridge/test_handoff_watcher.py` | Тест | Узкоспециализированная утилита «test handoff watcher»; интерфейс перечислен справа. | `task_text`, `FakeGit`, `HandoffWatcherTests`, `ReportVerificationTests`, `BridgeHandoffTests` |
| `telegram-bridge/test_historical_partial_prepare.py` | Тест | Узкоспециализированная утилита «test historical partial prepare»; интерфейс перечислен справа. | `HistoricalPrepareTests`, `PartialPaymentContextTests`, `AdvanceDeadlineTests`, `ShipmentIdentityTests`, `ShipmentRoundingTests` |
| `telegram-bridge/test_hogart_closing.py` | Тест | Узкоспециализированная утилита «test hogart closing»; интерфейс перечислен справа. | `HogartClosingTests` |
| `telegram-bridge/test_human_fixtures.py` | Тест | Узкоспециализированная утилита «test human fixtures»; интерфейс перечислен справа. | `fake_crm`, `HumanFixtureTests` |
| `telegram-bridge/test_human_intents.py` | Тест | Узкоспециализированная утилита «test human intents»; интерфейс перечислен справа. | `HumanIntentTests` |
| `telegram-bridge/test_human_journeys.py` | Тест | Human journeys: a person operates the real bot through Telegram controls. | `office`, `open_deal_by_number`, `DealInformationJourneys`, `PayerJourneys`, `InvoiceJourneys`, `DealStatusJourneys`, `DealCreationJourneys` |
| `telegram-bridge/test_human_journeys_documents.py` | Тест | Human journeys, third wave: contract, proposal, navigation and help. | `no_contract`, `to_contract_menu`, `ContractJourneys`, `EconomicsJourneys`, `ProposalJourneys`, `NavigationJourneys` |
| `telegram-bridge/test_human_journeys_edge.py` | Тест | Human journeys, second wave: how real people actually misuse a bot. | `writes`, `DealReadingVariants`, `PayerEdgeCases`, `InvoiceEdgeCases`, `DealCreationVariants` |
| `telegram-bridge/test_human_operator_journey.py` | Тест | Узкоспециализированная утилита «test human operator journey»; интерфейс перечислен справа. | `TelegramOperator`, `TelegramPollingMechanicsTests` |
| `telegram-bridge/test_human_phrasings.py` | Тест | The same request in the many ways people actually say it. | `PhrasingTests` |
| `telegram-bridge/test_human_qa_explorer.py` | Тест | Узкоспециализированная утилита «test human qa explorer»; интерфейс перечислен справа. | `ScriptedBrain`, `ExplorerTests` |
| `telegram-bridge/test_human_qa_isolation.py` | Тест | The QA stand must never read or write production business stores. | `StandIsolationTests` |
| `telegram-bridge/test_human_recovery.py` | Тест | Human journeys across a bot restart: what a person sees and what is written. | `open_invoice_preview`, `writes`, `RestartJourneys` |
| `telegram-bridge/test_human_workflow.py` | Тест | Узкоспециализированная утилита «test human workflow»; интерфейс перечислен справа. | `HumanWorkflowTests` |
| `telegram-bridge/test_incoming_dispatch.py` | Тест | Узкоспециализированная утилита «test incoming dispatch»; интерфейс перечислен справа. | `InboxTests` |
| `telegram-bridge/test_installation_dialog_safety.py` | Тест | Узкоспециализированная утилита «test installation dialog safety»; интерфейс перечислен справа. | `InstallerDialogTest` |
| `telegram-bridge/test_installation_handoff.py` | Тест | Узкоспециализированная утилита «test installation handoff»; интерфейс перечислен справа. | `HandoffTest` |
| `telegram-bridge/test_installer_bundle_entry.py` | Тест | Узкоспециализированная утилита «test installer bundle entry»; интерфейс перечислен справа. | `BundleEntryTests` |
| `telegram-bridge/test_installer_material_delivery.py` | Тест | Узкоспециализированная утилита «test installer material delivery»; интерфейс перечислен справа. | `MaterialAccessTests` |
| `telegram-bridge/test_installer_onboarding.py` | Тест | Узкоспециализированная утилита «test installer onboarding»; интерфейс перечислен справа. | `OnboardingTests` |
| `telegram-bridge/test_installer_report_intake.py` | Тест | New documents must be read, never substituted with historical pilot rows. | `IntakeTests` |
| `telegram-bridge/test_installer_workbook_intake.py` | Тест | Узкоспециализированная утилита «test installer workbook intake»; интерфейс перечислен справа. | `OwnWorkbookTests`, `AttachmentCollisionTests`, `StaleWorkbookTests` |
| `telegram-bridge/test_invoice_continuation.py` | Тест | Узкоспециализированная утилита «test invoice continuation»; интерфейс перечислен справа. | `InvoiceContinuationTests` |
| `telegram-bridge/test_invoice_tasks.py` | Тест | Узкоспециализированная утилита «test invoice tasks»; интерфейс перечислен справа. | `InvoiceTaskTests` |
| `telegram-bridge/test_kp_jobs.py` | Тест | Узкоспециализированная утилита «test kp jobs»; интерфейс перечислен справа. | `JobTests` |
| `telegram-bridge/test_legacy_ledger_safety.py` | Тест | Узкоспециализированная утилита «test legacy ledger safety»; интерфейс перечислен справа. | `LegacySafety` |
| `telegram-bridge/test_legacy_report_ui.py` | Тест | Узкоспециализированная утилита «test legacy report ui»; интерфейс перечислен справа. | `LegacyUITests`, `MaterialDecisionTests` |
| `telegram-bridge/test_migration_transition_guard.py` | Тест | Узкоспециализированная утилита «test migration transition guard»; интерфейс перечислен справа. | `GuardTests` |
| `telegram-bridge/test_model_recovery.py` | Тест | Узкоспециализированная утилита «test model recovery»; интерфейс перечислен справа. | `ModelRecoveryTests`, `StatementDocumentTests`, `FailedLedgerTests` |
| `telegram-bridge/test_operation_status.py` | Тест | Узкоспециализированная утилита «test operation status»; интерфейс перечислен справа. | `StatusTests` |
| `telegram-bridge/test_order_continuation.py` | Тест | Узкоспециализированная утилита «test order continuation»; интерфейс перечислен справа. | `OrderContinuationTests`, `RecoveryHintTests` |
| `telegram-bridge/test_partial_invoice_recovery.py` | Тест | Узкоспециализированная утилита «test partial invoice recovery»; интерфейс перечислен справа. | `PartialInvoiceRecoveryTest` |
| `telegram-bridge/test_partial_invoice_text.py` | Тест | Узкоспециализированная утилита «test partial invoice text»; интерфейс перечислен справа. | `PartialInvoiceTextTest` |
| `telegram-bridge/test_partial_shipments.py` | Тест | Узкоспециализированная утилита «test partial shipments»; интерфейс перечислен справа. | `PartialShipmentIntegrationTests` |
| `telegram-bridge/test_periodic_schedule.py` | Тест | Узкоспециализированная утилита «test periodic schedule»; интерфейс перечислен справа. | `ScheduleTests` |
| `telegram-bridge/test_polling_isolation.py` | Тест | Узкоспециализированная утилита «test polling isolation»; интерфейс перечислен справа. | `PollingIsolationTests` |
| `telegram-bridge/test_procurement_attachments.py` | Тест | Узкоспециализированная утилита «test procurement attachments»; интерфейс перечислен справа. | `AttachmentTests` |
| `telegram-bridge/test_product_matching_runtime.py` | Тест | Узкоспециализированная утилита «test product matching runtime»; интерфейс перечислен справа. | `RuntimeMatchingTests` |
| `telegram-bridge/test_qa_autopilot.py` | Тест | Узкоспециализированная утилита «test qa autopilot»; интерфейс перечислен справа. | `AutopilotTest` |
| `telegram-bridge/test_qa_handoff.py` | Тест | Узкоспециализированная утилита «test qa handoff»; интерфейс перечислен справа. | `QaHandoffTests` |
| `telegram-bridge/test_qa_schedule.py` | Тест | Узкоспециализированная утилита «test qa schedule»; интерфейс перечислен справа. | `QaScheduleTests` |
| `telegram-bridge/test_requisites_card.py` | Тест | Узкоспециализированная утилита «test requisites card»; интерфейс перечислен справа. | `RequisitesCardTests` |
| `telegram-bridge/test_runtime_integration.py` | Тест | Узкоспециализированная утилита «test runtime integration»; интерфейс перечислен справа. | `IntegrationTest` |
| `telegram-bridge/test_runtime_load.py` | Тест | Local contention/load checks. No Telegram, model, CRM or supplier requests. | `LoadTests` |
| `telegram-bridge/test_safe_reload.py` | Тест | Узкоспециализированная утилита «test safe reload»; интерфейс перечислен справа. | `ReloadTests` |
| `telegram-bridge/test_settlement_view.py` | Тест | Узкоспециализированная утилита «test settlement view»; интерфейс перечислен справа. | `ViewTests` |
| `telegram-bridge/test_smartbild_shipment.py` | Тест | Узкоспециализированная утилита «test smartbild shipment»; интерфейс перечислен справа. | `SmartBildShipmentTests` |
| `telegram-bridge/test_supplier_completion.py` | Тест | Узкоспециализированная утилита «test supplier completion»; интерфейс перечислен справа. | `SupplierCompletionTests` |
| `telegram-bridge/test_ui_context.py` | Тест | Узкоспециализированная утилита «test ui context»; интерфейс перечислен справа. | `ContextTests` |
| `telegram-bridge/test_workflow_runtime.py` | Тест | Узкоспециализированная утилита «test workflow runtime»; интерфейс перечислен справа. | `RuntimeTests` |
| `telegram-bridge/ui_context.py` | Рабочий модуль | Atomic legacy-state adapter with per-message snapshots and stale-worker guard. | `Context`, `StateStore` |
| `telegram-bridge/workflow_runtime.py` | Рабочий модуль | Durable operations, receipts and owner questions; no Telegram/CRM dependency. | `Conflict`, `stamp`, `dump`, `Store` |

## `megaplan-crm`

| Файл | Тип | Назначение | Публичный интерфейс |
|---|---|---|---|
| `megaplan-crm/apply_work_statement.py` | Рабочий модуль | "Ведомость работ" -> "Монтажные работы" pricing (2026-08-25) - the write-back half of | `find_montage_entry`, `main` |
| `megaplan-crm/archive_outbox.py` | Рабочий модуль | Durable archive delivery; contains no financial-operation writer. | `connect`, `enqueue`, `drain` |
| `megaplan-crm/bank_matcher.py` | Рабочий модуль | Suggest unambiguous Megaplan deals for imported bank transactions. | `normalized_number`, `references`, `deal_id_from_standard_contract`, `fetch_invoices`, `build_index`, `load_index`, `match_transaction`, `suggest` |
| `megaplan-crm/bank_statement.py` | Рабочий модуль | Import Alfa Bank XLSX statements and keep an auditable deal-assignment registry. | `text`, `amount`, `date_text`, `load_registry`, `save_registry`, `fingerprint`, `parse_xlsx`, `read_1c_text`, `parse_pairs`, `parse_1c`, `parse_statement`, `commission_group` (+6) |
| `megaplan-crm/build_deal_work_statement.py` | Рабочий модуль | Build an installer-facing work statement without deal economics. | `normalize_status`, `is_post_signing_status`, `statement_rows`, `build_xlsx`, `main` |
| `megaplan-crm/build_profitability_report.py` | Рабочий модуль | "Расчёт рентабельности сделки" (2026-08-25) - whole-deal economics, the second document | `norm`, `is_aggregate_montage_line`, `load_installation_items`, `load_procurement_items`, `compute_profitability`, `build_xlsx`, `money_field_matches`, `main` |
| `megaplan-crm/build_work_statement.py` | Рабочий модуль | "Ведомость работ" calculator (2026-08-25) - last piece of the roadmap item started by | `compute_statement`, `build_xlsx`, `main` |
| `megaplan-crm/closing_documents.py` | Рабочий модуль | Общие функции оформления закрывающих DOCX-документов. | `font`, `p`, `heading`, `table`, `base`, `signs`, `floating_picture`, `special_notes`, `money`, `sign_block`, `validate_contract_rows`, `act_number` (+6) |
| `megaplan-crm/contract_invoice.py` | Рабочий модуль | Create a one-line Megaplan invoice from a payment clause in the latest deal contract. | `money`, `megaplan_date`, `contract_basis`, `basis_from_deal`, `document_text`, `parse_contract`, `specification_text`, `contract_scope`, `latest_contract`, `preview_fingerprint`, `validate_contract_context`, `preview` (+14) |
| `megaplan-crm/currency_fixation.py` | Рабочий модуль | Freeze sale rows from an explicitly approved contract total; never reprice by today's FX. | `dec`, `cents`, `signature`, `plan`, `target_matches`, `apply` |
| `megaplan-crm/currency_planning.py` | Рабочий модуль | Safe planning conversion for supplier invoices in a foreign currency. | `CurrencyPlanningError`, `invoice_date`, `parse_cbr_markup`, `fetch_cbr_rate`, `plan_invoice_spec` |
| `megaplan-crm/deal_browser.py` | Рабочий модуль | Read/search Megaplan deals and perform validated, explicit state transitions. | `contract_upload_preflight`, `megaplan_reachable`, `ref_names`, `money_value`, `summary`, `enrich_cached_deal`, `fetch_all`, `refresh_cache_background`, `update_cached_deal`, `search_employees`, `set_executor`, `hydrate` (+5) |
| `megaplan-crm/deal_ledger.py` | Рабочий модуль | Local per-deal cost/price ledger (2026-08-23, Phase 1b). | `load`, `save`, `atomic_json`, `record_deal`, `list_recent_deals` |
| `megaplan-crm/deal_proposal.py` | Рабочий модуль | Client-only proposal from live CRM amounts. No supplier APIs or deal creation. | `dec`, `money`, `num`, `snapshot`, `render`, `read`, `save`, `publish`, `verify_attachment`, `scan`, `ack` |
| `megaplan-crm/document_bundle.py` | Рабочий модуль | Validate actual outgoing PDFs against current CRM parties, not filenames. | `validate_invoice`, `validate` |
| `megaplan-crm/document_order.py` | Рабочий модуль | Finish a requested contract + full invoice with per-stage durable receipts. | `OrderStepError`, `document_fingerprint`, `named_invoice_file`, `norm`, `plan`, `fulfill`, `main` |
| `megaplan-crm/document_renderer.py` | Рабочий модуль | Run the same LibreOffice build without requiring FUSE in the bot service. | `office_command` |
| `megaplan-crm/document_tax_policy.py` | Рабочий модуль | Guard the existing no-VAT contract template; never silently relabel tax. | `require_no_vat`, `settings`, `company_rate`, `approved_deal`, `vat`, `tax_label`, `row_rates`, `require_document_tax`, `decorate`, `creation_rate`, `contract_positions`, `payment_tax` (+1) |
| `megaplan-crm/email_payment_monitor.py` | Рабочий модуль | Read bank payment notifications over IMAP without changing mailbox state. | `load_json`, `save_json`, `load_env`, `message_text`, `parse_notification`, `match_invoices`, `poll`, `update_status`, `list_candidates`, `main` |
| `megaplan-crm/export_client_deals.py` | Рабочий модуль | Export every live Megaplan deal for one contractor to a readable XLSX table. | `run` |
| `megaplan-crm/financial_amounts.py` | Рабочий модуль | Canonical interpretation of a deal line's monetary values. | `crm_money_in_main`, `load_overrides`, `component_values`, `audit_entry`, `audit_rows` |
| `megaplan-crm/financial_archive.py` | Рабочий модуль | Immutable OneDrive archive for documents that affect a deal's finances. | `clean`, `safe`, `brief_essence`, `deal_folder_name`, `sha256`, `load_registry`, `save_registry`, `rclone_copy`, `archive_document`, `main` |
| `megaplan-crm/freeze_accepted_amounts.py` | Рабочий модуль | Freeze existing accrued values without changing accepted quantities or totals. | `freeze` |
| `megaplan-crm/generate_contract.py` | Рабочий модуль | Build a Cliwell deal contract from live Megaplan data. | `money_value`, `rubles`, `rubles_words`, `lower_first`, `subject_for_title`, `subject_for_body`, `is_full_person_name`, `contract_data`, `all_paragraphs`, `table_paragraphs`, `set_paragraph_text`, `replace_in_runs` (+17) |
| `megaplan-crm/harvest_work_rates.py` | Рабочий модуль | One-off harvest (2026-08-24): pull unique position names/units/"Себес работ" (labour | `fetch_real_deals`, `unique_positions`, `build_xlsx` |
| `megaplan-crm/historical_handoff.py` | Рабочий модуль | One-time owner-authorized handoff of ongoing legacy objects. | `apply` |
| `megaplan-crm/historical_installation_migration.py` | Рабочий модуль | Idempotent import of already approved historical installer reports. | `n`, `number`, `report_date`, `discover`, `parse_workbook`, `dry_run`, `registry_plan`, `apply_registry`, `mark_registry_migrations_historical`, `apply`, `repair_units`, `live_scope` (+1) |
| `megaplan-crm/historical_work_link.py` | Рабочий модуль | Audited operator-only reconciliation of approved legacy work to a CRM row. | `preview`, `apply`, `merge_approved` |
| `megaplan-crm/hogart_procurement.py` | Рабочий модуль | Create one Hogart supplier order when a Megaplan deal reaches «Закупка». | `order_items`, `ensure_order` |
| `megaplan-crm/import_work_rates.py` | Рабочий модуль | Import step for the "ведомость работ" tariff-seeding flow (see harvest_work_rates.py's | `parse_xlsx`, `build_work_rates`, `main` |
| `megaplan-crm/installation_materials.py` | Рабочий модуль | Read-only, price-free installation supply view. No CRM writes or notifications. | `unit`, `conflicts`, `build_view`, `mobile_sheet`, `mobile_pdf`, `export` |
| `megaplan-crm/installation_scope_restore.py` | Рабочий модуль | Refresh current work scope without changing approved historical report facts. | `norm`, `plan`, `apply` |
| `megaplan-crm/installation_workflow.py` | Рабочий модуль | Transactional installation handoff, cumulative reports and OneDrive archive. | `now`, `clean`, `safe`, `money_value`, `brief_essence`, `is_project_document`, `connect`, `audit`, `deal_source`, `ledger_work`, `folder_name`, `prepare` (+47) |
| `megaplan-crm/invoice_pdf_versions.py` | Рабочий модуль | Approved PDF corrections for immutable issued CRM invoices. | `fingerprint`, `approved_pdf` |
| `megaplan-crm/legacy_report_commit.py` | Рабочий модуль | Atomic local acceptance of a reviewed multi-deal installation report. | `prepare`, `preview`, `accept`, `sync_ledger` |
| `megaplan-crm/legacy_report_plan.py` | Рабочий модуль | Read-only bridge from an old reviewed report to canonical installation rows. | `norm`, `unit`, `number`, `plan` |
| `megaplan-crm/megaplan_api.py` | Рабочий модуль | Thin client for Megaplan CRM's official REST API v3 (cclimat.megaplan.ru). | `comparable_contractor_name`, `comparable_contractor_tokens`, `meaningful_contractor_tokens`, `natural_name_fragments`, `upsert_deal_browser_cache`, `load_env`, `MegaplanAPIError`, `MegaplanAPI` |
| `megaplan-crm/megaplan_finance.py` | Рабочий модуль | Create confirmed, idempotent Megaplan expense operations from bank email candidates. | `load`, `save`, `operation_form`, `megaplan_operations`, `existing_operation`, `record_procurement_payments`, `create`, `main` |
| `megaplan-crm/megaplan_transport.py` | Рабочий модуль | Cross-process CRM budgets and circuit breaker. Never replay a write here. | `ProtectionPause`, `connect`, `retry_seconds`, `paused`, `reachable`, `foreground_waiting`, `acquire_slot`, `urlopen`, `notify_status` |
| `megaplan-crm/megaplan_webhook.py` | Рабочий модуль | Webhook receiver for the "Отправить в ТГ" button the owner configures inside | `load_env`, `get_api`, `find_invoice`, `invoice_pdf`, `download_pdf`, `format_invoice_date`, `invoice_filename`, `invoice_caption`, `send_telegram_document`, `BoundedHTTPServer`, `Handler`, `fetch_invoice_pdf_cli` |
| `megaplan-crm/offer_catalog_cache.py` | Рабочий модуль | Local cache of Megaplan's Offer catalog, for name-matching (Phase 1b's "check Мегаплан's | `refresh`, `find_candidate` |
| `megaplan-crm/own_companies.py` | Рабочий модуль | Canonical directory of the legal entities used by SmartBild. | `load_directory`, `normalize_name`, `companies`, `company_by_id`, `resolve_company`, `default_selling_company` |
| `megaplan-crm/payer_manager.py` | Рабочий модуль | Create/reuse a client's payer and attach it to an existing Megaplan deal. | `digits`, `valid_inn`, `normalize`, `payer_matches`, `contractor_name`, `resolve_contractor`, `apply`, `main` |
| `megaplan-crm/payer_signatory_store.py` | Рабочий модуль | Persistent contract signatory profiles keyed by the Megaplan payer ID. | `get_signatory`, `save_signatory` |
| `megaplan-crm/position_type_migration.py` | Рабочий модуль | Reconcile document types without replacing immutable OfferRow/Offer clones. | `plan`, `invariant`, `apply` |
| `megaplan-crm/position_types.py` | Рабочий модуль | Single product/service boundary. Explicit CRM document type is authoritative. | `name_kind`, `crm_type`, `classify_position`, `new_offer_type`, `resolve`, `category_for`, `prepare_offer` |
| `megaplan-crm/procurement_projection.py` | Рабочий модуль | Read projection combining direct invoice rows and later stock allocations once. | `effective_registry`, `confirmed_totals` |
| `megaplan-crm/procurement_workflow.py` | Рабочий модуль | Auditable procurement snapshot and supplier-invoice registry for Megaplan deals. | `empty_registry`, `ensure_schema`, `normalized_item_name`, `item_similarity`, `suggest_distribution`, `put_unallocated_stock`, `record_excluded_remainder`, `list_unallocated_stock`, `consume_unallocated_stock`, `export_unallocated_stock`, `suggest_stock_for_deal`, `company_ref` (+30) |
| `megaplan-crm/reconcile_publications.py` | Рабочий модуль | Read CRM comments and recover a known attachment's local publication receipt. | `find_comment`, `installation`, `economics` |
| `megaplan-crm/registry_transaction.py` | Рабочий модуль | Reentrant process/thread locking around an entire JSON read-modify-write. | `locked`, `transaction` |
| `megaplan-crm/reissue_ip_contract.py` | Рабочий модуль | Create a replacement seller version without changing agreed payment terms. | `build` |
| `megaplan-crm/replace_deal_from_kp.py` | Рабочий модуль | Atomically replace an existing deal's rows with a confirmed KP specification. | `normalize_spec`, `backup_deal`, `deal_fingerprint`, `validate_rows`, `run` |
| `megaplan-crm/report_media_store.py` | Рабочий модуль | Retain installer evidence locally before acknowledging it or queuing upload. | `digest`, `retain` |
| `megaplan-crm/restore_historical_detail.py` | Рабочий модуль | Restore approved detail in-place, without approving or paying a report again. | `digest`, `approved_rows`, `preview`, `apply` |
| `megaplan-crm/seller_documents.py` | Рабочий модуль | Seller selection shared by contract and invoice generation. | `normalize_party_fonts`, `selected_seller`, `invoice_settings`, `apply_ip_supplier` |
| `megaplan-crm/shipment_finance.py` | Рабочий модуль | Delivery-only settlement operations. Cash and bank-payment ledgers are untouched. | `cents`, `plans`, `form`, `verify`, `Backend`, `load`, `save`, `ensure` |
| `megaplan-crm/smartbild_act.py` | Рабочий модуль | Approved SmartBild IP act layout, populated from any confirmed shipment. | `document` |
| `megaplan-crm/specification_unit_fixture.py` | Рабочий модуль | Фикстура единиц измерения спецификации для совместимости документов. | — |
| `megaplan-crm/stale_deal_watcher.py` | Рабочий модуль | Daily digest of "stuck" bot-created deals - positions still unresolved ("[ЖДЁТ ЦЕНЫ]", | `load_env`, `send_message`, `stuck_positions`, `build_digest` |
| `megaplan-crm/sync_deal_to_contract.py` | Рабочий модуль | Synchronise commercial rows of a deal with a signed contract snapshot. | `key`, `load_snapshot`, `backup`, `match_rows`, `sync` |
| `megaplan-crm/test_act_number.py` | Тест | Узкоспециализированная утилита «test act number»; интерфейс перечислен справа. | `ActNumberTests` |
| `megaplan-crm/test_archive_outbox.py` | Тест | Узкоспециализированная утилита «test archive outbox»; интерфейс перечислен справа. | `OutboxTests` |
| `megaplan-crm/test_atomic_registry.py` | Тест | Узкоспециализированная утилита «test atomic registry»; интерфейс перечислен справа. | `RegistryTest` |
| `megaplan-crm/test_bank_matcher.py` | Тест | Узкоспециализированная утилита «test bank matcher»; интерфейс перечислен справа. | `MatcherTest` |
| `megaplan-crm/test_bank_statement.py` | Тест | Узкоспециализированная утилита «test bank statement»; интерфейс перечислен справа. | `BankStatementTest` |
| `megaplan-crm/test_build_deal_work_statement.py` | Тест | Узкоспециализированная утилита «test build deal work statement»; интерфейс перечислен справа. | `WorkStatementTest` |
| `megaplan-crm/test_build_profitability_report.py` | Тест | Узкоспециализированная утилита «test build profitability report»; интерфейс перечислен справа. | `ProfitabilityPlanFactTest` |
| `megaplan-crm/test_confirmed_contract_generation.py` | Тест | Узкоспециализированная утилита «test confirmed contract generation»; интерфейс перечислен справа. | `ConfirmedGenerationTest` |
| `megaplan-crm/test_confirmed_contractor.py` | Тест | Узкоспециализированная утилита «test confirmed contractor»; интерфейс перечислен справа. | `ConfirmedContractorTest` |
| `megaplan-crm/test_contract_invoice.py` | Тест | Узкоспециализированная утилита «test contract invoice»; интерфейс перечислен справа. | `ContractInvoiceTests` |
| `megaplan-crm/test_contract_position_types.py` | Тест | Узкоспециализированная утилита «test contract position types»; интерфейс перечислен справа. | `position`, `ContractPositionTypesTests` |
| `megaplan-crm/test_contractor_matching.py` | Тест | Узкоспециализированная утилита «test contractor matching»; интерфейс перечислен справа. | `ContractorMatchingTest` |
| `megaplan-crm/test_contractor_natural_query.py` | Тест | Узкоспециализированная утилита «test contractor natural query»; интерфейс перечислен справа. | `NaturalContractorQueryTest` |
| `megaplan-crm/test_currency_fixation.py` | Тест | Узкоспециализированная утилита «test currency fixation»; интерфейс перечислен справа. | `FixationTests` |
| `megaplan-crm/test_currency_planning.py` | Тест | Узкоспециализированная утилита «test currency planning»; интерфейс перечислен справа. | `fixed_rate`, `CurrencyPlanningTest` |
| `megaplan-crm/test_customer_contract_selection.py` | Тест | Узкоспециализированная утилита «test customer contract selection»; интерфейс перечислен справа. | `CustomerContractSelectionTests`, `ServiceUnitRegression`, `SpecificationUnitRegression` |
| `megaplan-crm/test_deal_executor.py` | Тест | Узкоспециализированная утилита «test deal executor»; интерфейс перечислен справа. | `API`, `DealExecutorTests` |
| `megaplan-crm/test_deal_natural_search.py` | Тест | Узкоспециализированная утилита «test deal natural search»; интерфейс перечислен справа. | `DealNaturalSearchTest` |
| `megaplan-crm/test_deal_proposal.py` | Тест | Узкоспециализированная утилита «test deal proposal»; интерфейс перечислен справа. | `example`, `ProposalTests` |
| `megaplan-crm/test_document_bundle.py` | Тест | Узкоспециализированная утилита «test document bundle»; интерфейс перечислен справа. | `BundleTests` |
| `megaplan-crm/test_document_order.py` | Тест | Узкоспециализированная утилита «test document order»; интерфейс перечислен справа. | `DocumentOrderTests` |
| `megaplan-crm/test_document_tax_policy.py` | Тест | Узкоспециализированная утилита «test document tax policy»; интерфейс перечислен справа. | `TaxPolicyTests` |
| `megaplan-crm/test_economics_attachment.py` | Тест | Узкоспециализированная утилита «test economics attachment»; интерфейс перечислен справа. | `FakeAPI`, `EconomicsAttachmentTest` |
| `megaplan-crm/test_email_payment_monitor.py` | Тест | Узкоспециализированная утилита «test email payment monitor»; интерфейс перечислен справа. | `EmailPaymentTests` |
| `megaplan-crm/test_final_addendum.py` | Тест | Узкоспециализированная утилита «test final addendum»; интерфейс перечислен справа. | `FinalAddendumTests` |
| `megaplan-crm/test_financial_amounts.py` | Тест | Узкоспециализированная утилита «test financial amounts»; интерфейс перечислен справа. | `FinancialAmountsTest` |
| `megaplan-crm/test_financial_archive.py` | Тест | Узкоспециализированная утилита «test financial archive»; интерфейс перечислен справа. | `FinancialArchiveTest` |
| `megaplan-crm/test_financial_fail_closed.py` | Тест | Узкоспециализированная утилита «test financial fail closed»; интерфейс перечислен справа. | `FinancialValidationTest` |
| `megaplan-crm/test_freeze_accepted_amounts.py` | Тест | Узкоспециализированная утилита «test freeze accepted amounts»; интерфейс перечислен справа. | `FreezeTest` |
| `megaplan-crm/test_generate_contract.py` | Тест | Узкоспециализированная утилита «test generate contract»; интерфейс перечислен справа. | `ContractFilenameTests` |
| `megaplan-crm/test_historical_handoff.py` | Тест | Узкоспециализированная утилита «test historical handoff»; интерфейс перечислен справа. | `HandoffTests` |
| `megaplan-crm/test_historical_installation_migration.py` | Тест | Узкоспециализированная утилита «test historical installation migration»; интерфейс перечислен справа. | `HistoricalMigrationTests` |
| `megaplan-crm/test_historical_work_link.py` | Тест | Узкоспециализированная утилита «test historical work link»; интерфейс перечислен справа. | `LinkTests` |
| `megaplan-crm/test_hogart_procurement.py` | Тест | Узкоспециализированная утилита «test hogart procurement»; интерфейс перечислен справа. | `FakeAPI`, `HogartProcurementTest` |
| `megaplan-crm/test_installation_materials.py` | Тест | Узкоспециализированная утилита «test installation materials»; интерфейс перечислен справа. | `MaterialsTests` |
| `megaplan-crm/test_installation_scope_restore.py` | Тест | Узкоспециализированная утилита «test installation scope restore»; интерфейс перечислен справа. | `ScopeTests` |
| `megaplan-crm/test_installation_workflow.py` | Тест | Узкоспециализированная утилита «test installation workflow»; интерфейс перечислен справа. | `InstallationWorkflowTests` |
| `megaplan-crm/test_invoice_pdf_versions.py` | Тест | Узкоспециализированная утилита «test invoice pdf versions»; интерфейс перечислен справа. | `PDFVersionsTest` |
| `megaplan-crm/test_invoice_readback.py` | Тест | Узкоспециализированная утилита «test invoice readback»; интерфейс перечислен справа. | `InvoiceReadbackTest` |
| `megaplan-crm/test_legacy_report_commit.py` | Тест | Узкоспециализированная утилита «test legacy report commit»; интерфейс перечислен справа. | `LegacyCommitTests` |
| `megaplan-crm/test_legacy_report_plan.py` | Тест | Узкоспециализированная утилита «test legacy report plan»; интерфейс перечислен справа. | `LegacyPlanTests` |
| `megaplan-crm/test_megaplan_discounts.py` | Тест | Узкоспециализированная утилита «test megaplan discounts»; интерфейс перечислен справа. | `MegaplanDiscountLedgerTest` |
| `megaplan-crm/test_megaplan_transport.py` | Тест | Узкоспециализированная утилита «test megaplan transport»; интерфейс перечислен справа. | `TransportTest` |
| `megaplan-crm/test_payer_manager.py` | Тест | Узкоспециализированная утилита «test payer manager»; интерфейс перечислен справа. | `FakeAPI`, `PayerManagerTests` |
| `megaplan-crm/test_payer_signatory_store.py` | Тест | Узкоспециализированная утилита «test payer signatory store»; интерфейс перечислен справа. | `PayerSignatoryStoreTests` |
| `megaplan-crm/test_position_type_source.py` | Тест | Узкоспециализированная утилита «test position type source»; интерфейс перечислен справа. | `PositionTypeSourceTests`, `ExistingCatalogTypeTests` |
| `megaplan-crm/test_procurement_workflow.py` | Тест | Узкоспециализированная утилита «test procurement workflow»; интерфейс перечислен справа. | `ProcurementPaymentTest` |
| `megaplan-crm/test_reconcile_publications.py` | Тест | Узкоспециализированная утилита «test reconcile publications»; интерфейс перечислен справа. | `PublicationRecoveryTests` |
| `megaplan-crm/test_replace_deal_preview.py` | Тест | Узкоспециализированная утилита «test replace deal preview»; интерфейс перечислен справа. | `PreviewTests` |
| `megaplan-crm/test_restore_historical_detail.py` | Тест | Узкоспециализированная утилита «test restore historical detail»; интерфейс перечислен справа. | `RestoreTests` |
| `megaplan-crm/test_shipment_finance.py` | Тест | Узкоспециализированная утилита «test shipment finance»; интерфейс перечислен справа. | `Fake`, `ShipmentFinanceTests` |
| `megaplan-crm/test_sync_deal_to_contract.py` | Тест | Узкоспециализированная утилита «test sync deal to contract»; интерфейс перечислен справа. | `SignedContractSyncTests` |
| `megaplan-crm/test_vat_transition.py` | Тест | Узкоспециализированная утилита «test vat transition»; интерфейс перечислен справа. | `VatTransitionTests` |
| `megaplan-crm/test_work_contract_scope.py` | Тест | Узкоспециализированная утилита «test work contract scope»; интерфейс перечислен справа. | `WorkContractTests` |
| `megaplan-crm/work_contract_scope.py` | Рабочий модуль | Explicit reviewed mapping for a work contract without a specification table. | `clause`, `is_work_contract`, `apply`, `validate` |
| `megaplan-crm/xlsx_brand_style.py` | Рабочий модуль | SmartBild brand styling for openpyxl reports (2026-08-25). Colors taken from | `write_title_banner`, `write_header_row`, `style_data_row`, `apply_warning_fill`, `style_total_row` |

## `hogart-scraper`

| Файл | Тип | Назначение | Публичный интерфейс |
|---|---|---|---|
| `hogart-scraper/dashboard/deploy/activate_bot.py` | Сервер/модель веб-пульта | Configure only the owner's Mini App menu and deliver the requested dashboard. | `call` |
| `hogart-scraper/dashboard/deploy/ensure_route.py` | Сервер/модель веб-пульта | Reconcile only this dashboard route through Caddy's local admin API. | `request`, `main` |
| `hogart-scraper/dashboard/matching_store.py` | Сервер/модель веб-пульта | SQLite-очередь кандидатов, решений и исполнения сопоставления товаров. | `candidate`, `candidates`, `connection`, `project`, `decide`, `claim`, `finish`, `fail` |
| `hogart-scraper/dashboard/model.py` | Сервер/модель веб-пульта | Построение денежной модели и проекции данных для веб-пульта. | `cents`, `money`, `stamp`, `load`, `ref_index`, `project`, `build` |
| `hogart-scraper/dashboard/product_matching.py` | Сервер/модель веб-пульта | Deterministic equivalence and vetoes. Never use fuzzy string similarity. | `canonical`, `attributes`, `compare` |
| `hogart-scraper/dashboard/server.py` | Сервер/модель веб-пульта | Private dashboard API and static app, bound to loopback behind Caddy. | `read_env`, `credentials`, `verify_telegram`, `ClosingConnection`, `connect`, `initialize`, `digest`, `new_session`, `session_user`, `snapshot`, `task_rows`, `save_task` (+4) |
| `hogart-scraper/dashboard/shipment_procurement.py` | Сервер/модель веб-пульта | Проверка покрытия отгрузки подтверждёнными закупками. | `number`, `normalized`, `coverage` |
| `hogart-scraper/dashboard/shipment_workspace.py` | Сервер/модель веб-пульта | One shipment ledger shared by the dashboard and the document worker. | `decimal`, `digest`, `connection`, `book`, `request`, `save_book`, `pending_books`, `shipments`, `patch`, `used`, `projection`, `select` (+6) |
| `hogart-scraper/dashboard/static/app.js` | Клиент веб-пульта | JavaScript-модуль: app. | См. exports/обработчики в исходнике |
| `hogart-scraper/dashboard/static/shipments.js` | Клиент веб-пульта | JavaScript-модуль: shipments. | См. exports/обработчики в исходнике |
| `hogart-scraper/dashboard/static/supplier-allocation.js` | Клиент веб-пульта | JavaScript-модуль: supplier allocation. | См. exports/обработчики в исходнике |
| `hogart-scraper/dashboard/static/supplier-document.js` | Клиент веб-пульта | JavaScript-модуль: supplier document. | См. exports/обработчики в исходнике |
| `hogart-scraper/dashboard/static/workspace.js` | Клиент веб-пульта | JavaScript-модуль: workspace. | См. exports/обработчики в исходнике |
| `hogart-scraper/dashboard/supplier_documents.py` | Сервер/модель веб-пульта | Поиск, разбор координат и рендеринг страниц документов поставщика. | `resolve`, `parse_bbox`, `compact`, `locate`, `describe`, `render` |
| `hogart-scraper/dashboard/sync.py` | Сервер/модель веб-пульта | Read-only Megaplan snapshot. Publish only complete paginated collections. | `atomic`, `fetch`, `main` |
| `hogart-scraper/dashboard/test_matching_store.py` | Тест | Узкоспециализированная утилита «test matching store»; интерфейс перечислен справа. | `MatchingStoreTests` |
| `hogart-scraper/dashboard/test_product_matching.py` | Тест | Узкоспециализированная утилита «test product matching»; интерфейс перечислен справа. | `ProductMatchingTests` |
| `hogart-scraper/dashboard/test_shipment_procurement.py` | Тест | Узкоспециализированная утилита «test shipment procurement»; интерфейс перечислен справа. | `ShipmentProcurementTests` |
| `hogart-scraper/dashboard/test_shipment_workspace.py` | Тест | Узкоспециализированная утилита «test shipment workspace»; интерфейс перечислен справа. | `ShipmentWorkspaceTests`, `ShipmentReleaseGuardTests`, `CardProgressTests` |
| `hogart-scraper/dashboard/test_supplier_documents.py` | Тест | Узкоспециализированная утилита «test supplier documents»; интерфейс перечислен справа. | `SupplierDocumentsTests` |
| `hogart-scraper/dashboard/tests/make_auth.py` | Тест | Create short-lived signed test data locally without printing credentials. | `signed` |
| `hogart-scraper/dashboard/tests/run_browser_checks.py` | Тест | Browser acceptance on loopback with fake auth and isolated write stores. | `main` |
| `hogart-scraper/dashboard/tests/test_dashboard.py` | Тест | Узкоспециализированная утилита «test dashboard»; интерфейс перечислен справа. | `m`, `operation`, `deal`, `snapshot`, `ProjectionTests`, `AuthTests`, `TaskTests` |
| `hogart-scraper/dashboard/tests/test_workspace.py` | Тест | Узкоспециализированная утилита «test workspace»; интерфейс перечислен справа. | `WorkspaceTests` |
| `hogart-scraper/dashboard/workspace.py` | Сервер/модель веб-пульта | Object workspace, plans and read-only installation projection. No CRM writes. | `Conflict`, `initialize`, `text`, `ident`, `audit`, `save_object`, `save_plan`, `validate_dependency`, `source_day`, `installations`, `projection`, `history` (+1) |
| `hogart-scraper/export_section.mjs` | Рабочий модуль | JavaScript-модуль: export section. | См. exports/обработчики в исходнике |
| `hogart-scraper/fetch_images.mjs` | Рабочий модуль | JavaScript-модуль: fetch images. | См. exports/обработчики в исходнике |
| `hogart-scraper/finance/allocation_apply.py` | Финансовый контур | Confirmed allocation execution in the existing review registry. | `ledger`, `targets`, `prepare`, `public`, `request`, `public_job`, `update`, `commit` |
| `hogart-scraper/finance/allocation_workspace.py` | Финансовый контур | Validated allocation drafts in the single review registry; no CRM writes. | `Conflict`, `number`, `cents`, `fingerprint`, `prorate`, `source_document`, `public_document`, `projection`, `preview`, `save_draft` |
| `hogart-scraper/finance/archive_reconciled.py` | Финансовый контур | Copy reconciled originals to OneDrive, retaining versions and unresolved documents. | `copy`, `CachedAPI`, `folder` |
| `hogart-scraper/finance/audit45_comments.py` | Финансовый контур | Узкоспециализированная утилита «audit45 comments»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/audit45_contacts.py` | Финансовый контур | Узкоспециализированная утилита «audit45 contacts»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/audit45_crm.py` | Финансовый контур | Узкоспециализированная утилита «audit45 crm»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/audit45_extract.py` | Финансовый контур | Узкоспециализированная утилита «audit45 extract»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/audit45_mail.py` | Финансовый контур | Узкоспециализированная утилита «audit45 mail»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/audit45_primary_mail.py` | Финансовый контур | Узкоспециализированная утилита «audit45 primary mail»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/audit45_report.py` | Финансовый контур | Evidence ledger for the original 45 groups; preserves incomplete search boundaries. | — |
| `hogart-scraper/finance/crm_context.py` | Финансовый контур | Read existing Megaplan registries. Enrich reports, never create CRM payments. | `read`, `norm`, `money`, `enrich` |
| `hogart-scraper/finance/daily.py` | Финансовый контур | Read-only IMAP intake + atomic local import. Never sends or deletes mail. | `health`, `main` |
| `hogart-scraper/finance/daily_notice.py` | Финансовый контур | Concrete import receipts and outstanding owner questions. | `money`, `import_notice`, `notify_status` |
| `hogart-scraper/finance/deep_fetch_additional.py` | Финансовый контур | Узкоспециализированная утилита «deep fetch additional»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/deep_fetch_mail.py` | Финансовый контур | Узкоспециализированная утилита «deep fetch mail»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/deep_fetch_print.py` | Финансовый контур | Узкоспециализированная утилита «deep fetch print»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/document_review.py` | Финансовый контур | Reconciled supplier documents and a concise request list; no guessed allocations. | `refs`, `apply`, `main` |
| `hogart-scraper/finance/fetch_crm_evidence.py` | Финансовый контур | Узкоспециализированная утилита «fetch crm evidence»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/fetch_deal_comments.py` | Финансовый контур | Узкоспециализированная утилита «fetch deal comments»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/fetch_deal_files.py` | Финансовый контур | Узкоспециализированная утилита «fetch deal files»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/fetch_final_receipts.py` | Финансовый контур | Узкоспециализированная утилита «fetch final receipts»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/fetch_mail_documents.py` | Финансовый контур | Узкоспециализированная утилита «fetch mail documents»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/final_mail_search.py` | Финансовый контур | Узкоспециализированная утилита «final mail search»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/index_documents.py` | Финансовый контур | Узкоспециализированная утилита «index documents»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/info_extract.py` | Финансовый контур | Узкоспециализированная утилита «info extract»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/info_fetch.py` | Финансовый контур | Узкоспециализированная утилита «info fetch»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/info_review.py` | Финансовый контур | Audit each remaining supplier group against fetched info mailbox evidence. | `normalize` |
| `hogart-scraper/finance/info_scan.py` | Финансовый контур | Узкоспециализированная утилита «info scan»; интерфейс перечислен справа. | `dec` |
| `hogart-scraper/finance/installer_context.py` | Финансовый контур | Reconcile bank movements with existing installer settlements, without posting twice. | `cents`, `apply` |
| `hogart-scraper/finance/kav_candidates.py` | Финансовый контур | Узкоспециализированная утилита «kav candidates»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/kav_commit_review.py` | Финансовый контур | Persist manually reviewed mail evidence; all originals/version hashes retained. | — |
| `hogart-scraper/finance/kav_extract.py` | Финансовый контур | Узкоспециализированная утилита «kav extract»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/kav_fetch.py` | Финансовый контур | Узкоспециализированная утилита «kav fetch»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/kav_scan.py` | Финансовый контур | Узкоспециализированная утилита «kav scan»; интерфейс перечислен справа. | `dec` |
| `hogart-scraper/finance/ledger.py` | Финансовый контур | Auditable cash ledger. No accounting postings; money is integer kopecks. | `digest`, `cents`, `date`, `parse`, `connect`, `import_zip`, `invoice_refs`, `classify`, `records`, `main` |
| `hogart-scraper/finance/mail_evidence.py` | Финансовый контур | Декодирование и нормализация почтовых доказательств финансовой сверки. | `decode` |
| `hogart-scraper/finance/mail_intake.py` | Финансовый контур | Read-only, replay-safe intake of 1C bank ZIPs; unknown senders await review. | `inspect_archive`, `retrieve` |
| `hogart-scraper/finance/payment_allocations.py` | Финансовый контур | Preserve cash identity when a bank payment covers both projects and own needs. | `normalize_allocations`, `allocation_key` |
| `hogart-scraper/finance/payment_semantics.py` | Финансовый контур | Trade payments never imply delivery; explicitly identified bank services/income settle without goods. | `cents`, `verified_company_operation`, `company_settled`, `expected_secondary_cents`, `semantics_label`, `cash_form`, `invoice_cash_status`, `verify_cash_operation` |
| `hogart-scraper/finance/post_confirmed.py` | Финансовый контур | Post reviewed bank payments, with a durable journal and native deal links. | `wait_budget`, `v1_call`, `atomic`, `cents`, `money_match`, `select_existing`, `main` |
| `hogart-scraper/finance/procurement_intake.py` | Финансовый контур | Canonical supplier document intake. Parsing never posts money or changes sales. | `read`, `digest`, `money`, `extract`, `allocate_goods_discount`, `parse`, `validate`, `source_meta`, `convert_source`, `archive_source`, `discover`, `register` (+5) |
| `hogart-scraper/finance/procurement_match.py` | Финансовый контур | Find new invoice-to-deal links, before any offer_row_id exists on the invoice. | `unit`, `candidates`, `suggestions`, `auto_parts` |
| `hogart-scraper/finance/procurement_specs.py` | Финансовый контур | Read CRM specifications before matching; preserve confirmed local allocations. | `merge`, `request`, `refresh` |
| `hogart-scraper/finance/procurement_usage.py` | Финансовый контур | Shared confirmed purchase quantities and costs. | — |
| `hogart-scraper/finance/procurement_workspace.py` | Финансовый контур | Commands for supplier documents share the existing review queue. | `ledgers`, `projection`, `command`, `finish` |
| `hogart-scraper/finance/report.py` | Финансовый контур | Rebuild review workbook from ledger; workbook is a report, never the source database. | `op_values`, `sheet`, `main`, `date_text` |
| `hogart-scraper/finance/research.py` | Финансовый контур | Document-backed enrichment; never represents research as owner approval. | `enrich` |
| `hogart-scraper/finance/review_registry.py` | Финансовый контур | Single working queue. Ledger and procurement are facts, reports are projections. | `read`, `atomic`, `current_tasks`, `sync`, `active`, `owner_context`, `document_projection`, `resolve_manual`, `record_processing_followup` |
| `hogart-scraper/finance/save_verified_links.py` | Финансовый контур | Save evidenced links to existing bank registry, preserving prior assignments. | `main` |
| `hogart-scraper/finance/send_report.py` | Финансовый контур | Deliver the requested workbook to the owner's existing bot chat. | — |
| `hogart-scraper/finance/sent_evidence.py` | Финансовый контур | Декодирование доказательств ранее отправленных сообщений. | `decode` |
| `hogart-scraper/finance/sync_existing.py` | Финансовый контур | Merge a fully validated ZIP into the existing bot bank registry, preserving assignments. | `commission_group`, `merge` |
| `hogart-scraper/finance/test_allocation_apply.py` | Тест | Узкоспециализированная утилита «test allocation apply»; интерфейс перечислен справа. | `AllocationApplyTests`, `ExecutionTests`, `CurrencyPreflightTests` |
| `hogart-scraper/finance/test_allocation_workspace.py` | Тест | Узкоспециализированная утилита «test allocation workspace»; интерфейс перечислен справа. | `AllocationTests` |
| `hogart-scraper/finance/test_company_expenses.py` | Тест | Узкоспециализированная утилита «test company expenses»; интерфейс перечислен справа. | `CompanyExpenseTests`, `CompanyIncomeTests`, `CommissionSemanticsTests`, `ReviewedCompanyTests` |
| `hogart-scraper/finance/test_crm_context.py` | Тест | Узкоспециализированная утилита «test crm context»; интерфейс перечислен справа. | `ContextTests` |
| `hogart-scraper/finance/test_daily_notice.py` | Тест | Узкоспециализированная утилита «test daily notice»; интерфейс перечислен справа. | `NoticeTests` |
| `hogart-scraper/finance/test_ledger.py` | Тест | Узкоспециализированная утилита «test ledger»; интерфейс перечислен справа. | `LedgerTests` |
| `hogart-scraper/finance/test_mail_intake.py` | Тест | Узкоспециализированная утилита «test mail intake»; интерфейс перечислен справа. | `MailIntakeTests`, `MailReconnectTests` |
| `hogart-scraper/finance/test_payment_allocations.py` | Тест | Узкоспециализированная утилита «test payment allocations»; интерфейс перечислен справа. | `SplitTests` |
| `hogart-scraper/finance/test_payment_semantics.py` | Тест | Узкоспециализированная утилита «test payment semantics»; интерфейс перечислен справа. | `PaymentSemantics`, `CompanyMovementGuards` |
| `hogart-scraper/finance/test_procurement_flow.py` | Тест | Узкоспециализированная утилита «test procurement flow»; интерфейс перечислен справа. | `FlowTests` |
| `hogart-scraper/finance/test_procurement_specs.py` | Тест | Узкоспециализированная утилита «test procurement specs»; интерфейс перечислен справа. | `SpecsTests`, `InvoiceNumbersTests`, `LegacyUsageTests`, `AddedReceiptTests`, `BundleReceiptTests`, `HistoricalBasisTests`, `ForeignInvoiceTests`, `ServiceClassificationTests`, `CrmCurrencyTests`, `SharedRegistryTests`, `LegacySourceDiscoveryTests`, `ArchiveDiscoveryTests` (+1) |
| `hogart-scraper/finance/test_review_registry.py` | Тест | Узкоспециализированная утилита «test review registry»; интерфейс перечислен справа. | `ReviewRegistryTests` |
| `hogart-scraper/finance/test_reviewed_allocations.py` | Тест | Узкоспециализированная утилита «test reviewed allocations»; интерфейс перечислен справа. | `ReviewedAllocations` |
| `hogart-scraper/finance/test_split_payment.py` | Тест | Узкоспециализированная утилита «test split payment»; интерфейс перечислен справа. | `SplitPaymentTests` |
| `hogart-scraper/finance/test_sync_existing.py` | Тест | Узкоспециализированная утилита «test sync existing»; интерфейс перечислен справа. | `SyncTests` |
| `hogart-scraper/finance/tools/apply_final_answers.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «apply final answers»; интерфейс перечислен справа. | `prepare_company` |
| `hogart-scraper/finance/tools/apply_last_six.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «apply last six»; интерфейс перечислен справа. | `project`, `own` |
| `hogart-scraper/finance/tools/apply_owner_workbook.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «apply owner workbook»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/archive_art_technology.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «archive art technology»; интерфейс перечислен справа. | `Cached`, `copy` |
| `hogart-scraper/finance/tools/archive_deep_review.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «archive deep review»; интерфейс перечислен справа. | `Cached`, `copy` |
| `hogart-scraper/finance/tools/archive_diaflex6856.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «archive diaflex6856»; интерфейс перечислен справа. | `Cached`, `copy` |
| `hogart-scraper/finance/tools/archive_filters1280.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «archive filters1280»; интерфейс перечислен справа. | `Cached`, `copy` |
| `hogart-scraper/finance/tools/archive_final111_clients.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «archive final111 clients»; интерфейс перечислен справа. | `Cached`, `copy`, `download` |
| `hogart-scraper/finance/tools/archive_final_answers.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «archive final answers»; интерфейс перечислен справа. | `Cached`, `copy` |
| `hogart-scraper/finance/tools/archive_final_outside.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «archive final outside»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/archive_finish_company_docs.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «archive finish company docs»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/archive_finish_receipts.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «archive finish receipts»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/archive_invoice1624.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «archive invoice1624»; интерфейс перечислен справа. | `Cached`, `copy` |
| `hogart-scraper/finance/tools/archive_last_six.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «archive last six»; интерфейс перечислен справа. | `Cached`, `copy` |
| `hogart-scraper/finance/tools/archive_mirkli65835.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «archive mirkli65835»; интерфейс перечислен справа. | `Cached`, `copy` |
| `hogart-scraper/finance/tools/archive_oct6_links.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «archive oct6 links»; интерфейс перечислен справа. | `Cached`, `copy` |
| `hogart-scraper/finance/tools/archive_oct6b_links.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «archive oct6b links»; интерфейс перечислен справа. | `Cached`, `copy` |
| `hogart-scraper/finance/tools/archive_oct6c.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «archive oct6c»; интерфейс перечислен справа. | `Cached`, `copy` |
| `hogart-scraper/finance/tools/archive_owner_workbook.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «archive owner workbook»; интерфейс перечислен справа. | `Cached`, `copy` |
| `hogart-scraper/finance/tools/archive_telecom.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «archive telecom»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/archive_trio_confirmed.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «archive trio confirmed»; интерфейс перечислен справа. | `Cached`, `copy` |
| `hogart-scraper/finance/tools/audit_final111.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «audit final111»; интерфейс перечислен справа. | `check` |
| `hogart-scraper/finance/tools/audit_finish_all.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «audit finish all»; интерфейс перечислен справа. | `check` |
| `hogart-scraper/finance/tools/build_archive_catalog.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «build archive catalog»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/build_deep_questions.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «build deep questions»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/build_deposit_plan.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «build deposit plan»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/build_finish_company.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «build finish company»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/build_finish_questions.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «build finish questions»; интерфейс перечислен справа. | `add`, `signature` |
| `hogart-scraper/finance/tools/build_intercompany_plan.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «build intercompany plan»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/build_nikolay_kp_runtime.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «build nikolay kp runtime»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/build_posting_plan.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «build posting plan»; интерфейс перечислен справа. | `allocation_key` |
| `hogart-scraper/finance/tools/check_catalog_routing_runtime.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «check catalog routing runtime»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/check_filters.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «check filters»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/check_invoice1624_runtime.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «check invoice1624 runtime»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/clear_reconciled_deep_fence.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «clear reconciled deep fence»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/close_invoice1624.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «close invoice1624»; интерфейс перечислен справа. | `link_payment` |
| `hogart-scraper/finance/tools/close_mirkli_question.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «close mirkli question»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/commit_art_technology.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «commit art technology»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/commit_deep_company.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «commit deep company»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/commit_oct5_invoices.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «commit oct5 invoices»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/commit_oct6_links.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «commit oct6 links»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/commit_oct6b_links.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «commit oct6b links»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/complete_invoice1624.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «complete invoice1624»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/confirm_diaflex6856.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «confirm diaflex6856»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/confirm_mirkli65835.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «confirm mirkli65835»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/confirm_trio_oct6.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «confirm trio oct6»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/connect_info_mail.py` | Операторская/историческая финансовая утилита | Interactively rotate the bot's mail app password after IMAP/SMTP verification. | `read_env`, `replace_credentials`, `main` |
| `hogart-scraper/finance/tools/connect_kav_mail.py` | Операторская/историческая финансовая утилита | Run interactively on the server; never echo credentials or pass them as arguments. | — |
| `hogart-scraper/finance/tools/correct_all_payments.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «correct all payments»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/correct_expense_pilot.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «correct expense pilot»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/correct_pilot.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «correct pilot»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/create_apartment_electrics.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «create apartment electrics»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/deep_all_deals.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «deep all deals»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/deep_hogart_documents.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «deep hogart documents»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/deep_hogart_download.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «deep hogart download»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/deep_hogart_orders.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «deep hogart orders»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/deep_hogart_read.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «deep hogart read»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/deliver_final_answers.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «deliver final answers»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/deliver_last_six.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «deliver last six»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/expense_full_form.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «expense full form»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/final_deal_history.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «final deal history»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/final_mail_search.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «final mail search»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/final_prepare_crm.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «final prepare crm»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/final_report.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «final report»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/final_suppliers.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «final suppliers»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/find_supplier_contacts.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «find supplier contacts»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/find_supplier_names.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «find supplier names»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/finish_deep_vovchenko.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «finish deep vovchenko»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/fix_final111_invoice.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «fix final111 invoice»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/get_finance_schema.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «get finance schema»; интерфейс перечислен справа. | `get` |
| `hogart-scraper/finance/tools/inspect_final_answers.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «inspect final answers»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/inspect_finance.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «inspect finance»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/inspect_finance_correction.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «inspect finance correction»; интерфейс перечислен справа. | `save` |
| `hogart-scraper/finance/tools/inspect_finish_all.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «inspect finish all»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/inspect_interest_pilot.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «inspect interest pilot»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/inspect_invoices_correction.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «inspect invoices correction»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/inspect_owner_parties.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «inspect owner parties»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/inspect_owner_workbook.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «inspect owner workbook»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/inspect_real_accounts.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «inspect real accounts»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/inspect_supplier_identity.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «inspect supplier identity»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/list_finish_invoices.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «list finish invoices»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/list_payers_correction.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «list payers correction»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/oct6_batch_report.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «oct6 batch report»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/oct6b_report.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «oct6b report»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/payment_correction_report.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «payment correction report»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/prepare_art_technology.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «prepare art technology»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/prepare_deal848.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «prepare deal848»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/prepare_deal883.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «prepare deal883»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/prepare_deep_company.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «prepare deep company»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/prepare_deep_review.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «prepare deep review»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/prepare_deep_suppliers.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «prepare deep suppliers»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/prepare_deep_vovchenko.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «prepare deep vovchenko»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/prepare_finish_all.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «prepare finish all»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/prepare_mig.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «prepare mig»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/prepare_oct6b.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «prepare oct6b»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/prepare_oct6c.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «prepare oct6c»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/prepare_ozon_group.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «prepare ozon group»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/prepare_receipt_payments.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «prepare receipt payments»; интерфейс перечислен справа. | `add` |
| `hogart-scraper/finance/tools/prepare_rfk.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «prepare rfk»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/prepare_trio_confirmed.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «prepare trio confirmed»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/prepare_turkov.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «prepare turkov»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/reconcile_deep_502.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «reconcile deep 502»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/refresh_oct6_deals.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «refresh oct6 deals»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/remaining_report.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «remaining report»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/repair_supplier_payments.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «repair supplier payments»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/report_deep_questions.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «report deep questions»; интерфейс перечислен справа. | `clean` |
| `hogart-scraper/finance/tools/report_final111.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «report final111»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/report_final_answers.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «report final answers»; интерфейс перечислен справа. | `reason` |
| `hogart-scraper/finance/tools/report_finish_all.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «report finish all»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/report_last_six.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «report last six»; интерфейс перечислен справа. | `reason` |
| `hogart-scraper/finance/tools/report_owner_workbook.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «report owner workbook»; интерфейс перечислен справа. | `reason` |
| `hogart-scraper/finance/tools/resolve_salary_rejection.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «resolve salary rejection»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/review_telecom_vat.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «review telecom vat»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/run_posting.py` | Операторская/историческая финансовая утилита | Service entrypoint using installed reporting dependencies and existing CRM credentials. | — |
| `hogart-scraper/finance/tools/scan_current_deal_items.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «scan current deal items»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/settle_bank_fees.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «settle bank fees»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/sync_final111.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «sync final111»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/sync_final_answers_bot.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «sync final answers bot»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/sync_finish_all.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «sync finish all»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/sync_oct6_procurement_payments.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «sync oct6 procurement payments»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/verify_art_technology.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «verify art technology»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/verify_company_batch.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «verify company batch»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/verify_deep_review.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «verify deep review»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/verify_diaflex6856.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «verify diaflex6856»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/verify_filters1280.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «verify filters1280»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/verify_final_answers.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «verify final answers»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/verify_invoice1624.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «verify invoice1624»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/verify_last_six.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «verify last six»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/verify_mirkli65835.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «verify mirkli65835»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/verify_oct6_batch.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «verify oct6 batch»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/verify_oct6b_batch.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «verify oct6b batch»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/verify_oct6c.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «verify oct6c»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/verify_owner_workbook.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «verify owner workbook»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/verify_payment_correction.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «verify payment correction»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/tools/verify_trio_confirmed.py` | Операторская/историческая финансовая утилита | Узкоспециализированная утилита «verify trio confirmed»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/trio_deep_search.py` | Финансовый контур | Узкоспециализированная утилита «trio deep search»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/trio_local_audit.py` | Финансовый контур | Узкоспециализированная утилита «trio local audit»; интерфейс перечислен справа. | — |
| `hogart-scraper/finance/user_rules.py` | Финансовый контур | Apply explicit owner answers, retaining original bank data and decision provenance. | `apply` |
| `hogart-scraper/finance/xlsx_compat.py` | Финансовый контур | Write plain XLSX worksheets with XlsxWriter, without structured-table metadata. | `save_workbook` |
| `hogart-scraper/generate_kp.py` | Рабочий модуль | Generate a Cliwell-letterhead commercial proposal (KP) PDF from a JSON spec. | `die`, `get_hogart_api`, `live_lookup`, `get_daichi_catalog`, `daichi_lookup`, `full_price_of`, `contract_price_of`, `get_features`, `total_stock`, `availability_label`, `download_image`, `num_ru` (+6) |
| `hogart-scraper/get_photo.mjs` | Рабочий модуль | JavaScript-модуль: get photo. | См. exports/обработчики в исходнике |
| `hogart-scraper/hogart_api.py` | Рабочий модуль | Thin client for the official Hogart / B2B Motion REST API (admin.b2b.hogart.ru/api/v1/). | `load_env`, `HogartAPIError`, `HogartAPI`, `image_url` |
| `hogart-scraper/kemix_price_reminder.py` | Рабочий модуль | Checks kemix_prices.json staleness and nags the owner in Telegram if it's gotten old | `load_env`, `send_message` |
| `hogart-scraper/login.mjs` | Рабочий модуль | JavaScript-модуль: login. | См. exports/обработчики в исходнике |
| `hogart-scraper/parse_economics_xlsx.py` | Рабочий модуль | Extract every priced row from a Cliwell economics workbook without aggregation. | `clean`, `number`, `find_sheet_and_header`, `parse`, `parse_split_calculation` |
| `hogart-scraper/pipe_reference.py` | Рабочий модуль | KP economics for two line items, per owner's spec (2026-08-21): | `pipe_diameters_for_capacity`, `hogart_freon_line_cost_per_meter`, `install_price_for_capacity`, `parse_cooling_capacity_kw`, `ceil_to_50`, `kemix_prices_age_days`, `labor_price_for_capacity`, `freon_line_price_per_meter` |
| `hogart-scraper/price_install_addons.py` | Рабочий модуль | Compute install/freon-line addon prices for hogart-sourced equipment, for use OUTSIDE | `live_lookup`, `get_features`, `main` |
| `hogart-scraper/price_spec_items.py` | Рабочий модуль | Tiered price/cost resolution for raw spec items (Phase 1b, 2026-08-23) - covers the | `hogart_lookup`, `kemiks_lookup`, `main` |
| `hogart-scraper/search_live.mjs` | Рабочий модуль | JavaScript-модуль: search live. | См. exports/обработчики в исходнике |
| `hogart-scraper/spec_review_xlsx.py` | Рабочий модуль | Review-file builder for Phase 1b's "спецификация без цен" deal-creation flow (2026-08-23). | `build` |
| `hogart-scraper/test_generate_kp_manual.py` | Тест | Узкоспециализированная утилита «test generate kp manual»; интерфейс перечислен справа. | `ManualLinesTest` |
| `hogart-scraper/test_generate_kp_multisplit.py` | Тест | Узкоспециализированная утилита «test generate kp multisplit»; интерфейс перечислен справа. | `MultisplitTests` |
| `hogart-scraper/test_hogart_api.py` | Тест | Узкоспециализированная утилита «test hogart api»; интерфейс перечислен справа. | `HogartTokenTest` |
| `hogart-scraper/test_parse_economics_xlsx.py` | Тест | Узкоспециализированная утилита «test parse economics xlsx»; интерфейс перечислен справа. | `ProcurementSpecificationTest` |
| `hogart-scraper/update_kemix_prices.py` | Рабочий модуль | Apply a new КЕМИКС price snapshot to kemix_prices.json, with a diff report. | `die`, `load_current`, `apply_update`, `save_update` |
| `hogart-scraper/xlsx_report.py` | Рабочий модуль | Standalone xlsx builder for the KP economics breakdown. | `build` |

## `daichi-scraper`

| Файл | Тип | Назначение | Публичный интерфейс |
|---|---|---|---|
| `daichi-scraper/daichi_api.py` | Рабочий модуль | Thin client for the official Daichi Business B2B API. | `load_env`, `DaichiAPIError`, `DaichiAPI` |
| `daichi-scraper/daichi_catalog_cache.py` | Рабочий модуль | Local cache of Daichi's full catalog + per-store stock/price (2026-08-26) - mirrors | `refresh`, `load_or_refresh` |
| `daichi-scraper/daichi_search.py` | Рабочий модуль | Daichi catalog search for the Telegram bridge's DAICHI_SEARCH marker (2026-08-26) - | `search`, `main` |
| `daichi-scraper/full_login_flow.mjs` | Рабочий модуль | JavaScript-модуль: full login flow. | См. exports/обработчики в исходнике |
| `daichi-scraper/test_daichi_catalog_cache.py` | Тест | Узкоспециализированная утилита «test daichi catalog cache»; интерфейс перечислен справа. | `RefreshTests` |

## Итого

- Python: 532
- JavaScript/MJS: 11
