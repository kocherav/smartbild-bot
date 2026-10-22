"""Incremental adapter around existing business functions, not an AI router."""
from functools import wraps
import effect_runner

# Only calls that write business entities. Generation/read/cache calls remain
# outside, so a confirmed write's archive/report can finish after UI navigation.
WRITE_ACTIONS = {
    'run_create_megaplan_deal': None,
    'run_payer_card_apply': None,
    'run_supplier_invoice_apply': None,
    'run_sync_deal_kp': None,
    'run_apply_work_statement': None,
    'run_update_kemix_prices': None,
    'run_contract_invoice': {'create', 'create_full', 'delete'},
    'run_deal_browser': {'update_contract_fields', 'change_contractor', 'move_status',
                         'record_procurement_receipt', 'close_procurement', 'attach_bank_operation','upload_contracts','upload_execution_file',
                         'set_executor'},
    'run_installation_workflow': {'approve', 'transfer', 'approve_report', 'record_payment',
                                  'return_report', 'import_workbook', 'attach_project', 'without_project',
                                  'select_contact', 'create_contact', 'update_details',
                                  'create_report', 'submit_report', 'import_legacy_workbook','accept_legacy_report','sync_executor'},
    'run_procurement_workflow': {'consume_unallocated_stock', 'record_invoice', 'put_unallocated_stock',
                                'record_excluded_remainder', 'record_receipt', 'close',
                                'record_intercompany_settlement', 'set_deal_company', 'record_closing_document'},
    'run_megaplan_finance': None,
    'run_bank_statement': {'assign'},
    'run_installer_settlements': {'record_payment', 'accrual'},
}

# A generated service block or copied button label is not user confirmation.
CONFIRMED_ACTIONS = {
    'run_create_megaplan_deal': None, 'run_payer_card_apply': {'apply'},
    'run_supplier_invoice_apply': None, 'run_sync_deal_kp': None,
    'run_contract_invoice': {'create','create_full','delete'},
    'run_installation_workflow': {'approve','transfer','approve_report','record_payment','accept_legacy_report','sync_executor'},
    'run_installer_settlements': {'record_payment','accrual'},
    'run_megaplan_finance': None,
    'run_apply_work_statement': None, 'run_update_kemix_prices': None,
    'run_deal_browser': {'upload_contracts','upload_execution_file','set_executor'},
}


def install(namespace):
    for name, actions in WRITE_ACTIONS.items():
        fn = namespace.get(name)
        if fn is None or getattr(fn, '_runtime_guard', False):
            continue
        namespace[name] = decorate(namespace, name, fn, actions)


def decorate(namespace, name, fn, actions):
    @wraps(fn)
    def guarded(*args, **kwargs):
        ctx = namespace.get('UI_CONTEXT')
        if not namespace.get('RUNTIME_ACTIVE') or ctx is None:
            return fn(*args, **kwargs)
        spec = args[0] if args and isinstance(args[0], dict) else {}
        action = str(spec.get('action') or 'apply')
        if name == 'run_apply_work_statement' and kwargs.get('preview'):
            return fn(*args, **kwargs)
        if name == 'run_sync_deal_kp' and (spec.get('preview') or spec.get('dry_run')):
            return fn(*args, **kwargs)
        if actions is not None and action not in actions:
            return fn(*args, **kwargs)
        if name in CONFIRMED_ACTIONS and (CONFIRMED_ACTIONS[name] is None or action in CONFIRMED_ACTIONS[name]):
            if not ctx.confirmed_control:
                return {'ok':False,'no_effect':True,'error':'Для записи требуется подтверждение актуальной кнопкой под предварительным просмотром. Данные не изменены.'}
        if name == 'run_create_megaplan_deal' and ctx.state.get('pending') != 'deal_create_confirm':
            return {'ok':False,'no_effect':True,'error':'Создание возможно только после итогового просмотра черновика.'}
        target = {key: str(spec[key]) for key in ('deal_id', 'report_id', 'invoice_id', 'id','source_digest') if spec.get(key) is not None}
        payload = {'args': list(args), 'kwargs': kwargs}
        intent = ctx.state.get('_confirmation_id') or ctx.update_id
        return effect_runner.execute(namespace['WorkflowStore'](namespace['WORKFLOW_DB_FILE']),
            ctx.actor, name + ':' + action, intent, target, payload, lambda: fn(*args, **kwargs),
            fresh=namespace['request_is_current'])
    guarded._runtime_guard = True
    return guarded
