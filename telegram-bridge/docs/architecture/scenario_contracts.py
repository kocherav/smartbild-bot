"""Versioned scenario ownership for the current bridge and its successor.

This is an inventory/classification tool, not a production router. Unknown states
fail classification so new branches cannot silently disappear from the audit.
"""
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BRIDGE = ROOT.parents[1] / 'bridge.py'
PREFIXES = (
    ('bank_', 'BANK'), ('email_', 'EMAIL'), ('contract_', 'CONTRACT'),
    ('document_order_', 'CONTRACT'),
    ('deal_create_', 'CRM-CREATE'), ('developer_', 'DEV'),
    ('human_', 'HUMAN-DEAL'),
    ('installation_', 'MNT'), ('installer_', 'MNT-LEGACY'),
    ('payer_', 'PAYER'), ('procurement_', 'BUY'), ('supplier_', 'BUY-INVOICE'),
    ('unallocated_', 'STOCK'), ('proposal_', 'KP-DEAL'),
    ('transition_invoice_', 'INVOICE'), ('current_execution_', 'MNT-LEGACY'),
)
EXACT = {'invoice_file': 'BUY-INVOICE', 'invoice_menu': 'INVOICE',
         'invoice_download': 'INVOICE', 'invoice_full_confirm': 'INVOICE',
         'menu': 'NAV', 'deal_sync_confirm':'KP-DEAL',
         'price_catalog_confirm':'CATALOG', 'work_price_confirm':'MNT-LEGACY'}

def owner(state):
    if state in EXACT:
        return EXACT[state]
    for prefix, scenario in PREFIXES:
        if state.startswith(prefix):
            return scenario
    raise ValueError('Unclassified state: ' + state)

def values(node,constants=None):
    constants=constants or {}
    if isinstance(node,ast.Name):return constants.get(node.id,set())
    if isinstance(node, ast.Constant):
        return {node.value} if isinstance(node.value, str) else set()
    if isinstance(node, ast.IfExp):
        return values(node.body,constants) | values(node.orelse,constants)
    return set()

def inventory(source):
    tree = ast.parse(source)
    constants={target.id:values(node.value) for node in tree.body if isinstance(node,ast.Assign)
               for target in node.targets if isinstance(target,ast.Name)}
    definitions, readers, dynamic = {}, {}, []
    for fn in tree.body:
        if not isinstance(fn, ast.FunctionDef):
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and ((isinstance(node.func, ast.Name) and node.func.id == 'update_deal_ui_state') or
                    (isinstance(node.func,ast.Attribute) and node.func.attr=='update_deal_ui_state')):
                for kw in node.keywords:
                    if kw.arg != 'pending':
                        continue
                    found = values(kw.value,constants)
                    for state in found:
                        definitions.setdefault(state, []).append({'function': fn.name, 'line': node.lineno})
                    if not found and not isinstance(kw.value, ast.Constant):
                        dynamic.append({'function': fn.name, 'line': node.lineno, 'expression': ast.unparse(kw.value)})
            if isinstance(node, ast.If) and 'pending' in ast.unparse(node.test):
                for child in ast.walk(node.test):
                    if isinstance(child, ast.Constant) and isinstance(child.value, str):
                        readers.setdefault(child.value, []).append({'function': fn.name, 'line': node.lineno})
    return {'states': {s: {'scenario': owner(s), 'writers': places, 'readers': readers.get(s, [])}
                       for s, places in sorted(definitions.items())}, 'dynamic_state_writes': dynamic}

if __name__ == '__main__':
    result = inventory(BRIDGE.read_text(encoding='utf-8'))
    for path in [BRIDGE.with_name('legacy_report_ui.py')]:
        extra=inventory(path.read_text(encoding='utf-8'))
        for state,entry in extra['states'].items():
            for writer in entry['writers']:writer['source']=path.name
            result['states'][state]=entry
        result['dynamic_state_writes'].extend(extra['dynamic_state_writes'])
    (ROOT / 'STATE_ROUTES.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'classified_states': len(result['states']), 'dynamic_writes': len(result['dynamic_state_writes'])}))
