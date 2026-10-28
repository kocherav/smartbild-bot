"""Read-only CRM snapshots for human journeys.

``capture`` calls the real megaplan-crm CLIs with read actions only and stores
what they return.  ``load`` turns that snapshot into the in-memory Megaplan of
the QA stand, so a journey can run on real deals, clients, payers and invoices
while every write still lands in the double.

Snapshots contain client data: they live next to the production registry and
are never committed (see .gitignore).
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess


HOME = Path(os.environ.get('SMARTBILD_HOME', '/home/kocher.av'))
MEGAPLAN_DIR = HOME / 'megaplan-crm'
PYTHON = os.environ.get('QA_PYTHON', str(HOME / '.report-venv' / 'bin' / 'python3'))

# The only calls capture may make.  Anything else is refused before execution.
READ_ONLY = {
    ('deal_browser.py', 'get'),
    ('payer_manager.py', 'list_deal_payers'),
    ('contract_invoice.py', 'list'),
    ('megaplan_api.py', 'sync-deal-ledger'),
}


def crm_cli(script, spec, args=(), runner=subprocess.run):
    action = args[0] if args else spec.get('action')
    if (script, action) not in READ_ONLY:
        raise PermissionError(f'Снимок CRM допускает только чтение: {script} {action}')
    completed = runner([PYTHON, str(MEGAPLAN_DIR / script), *args], cwd=str(MEGAPLAN_DIR),
                       input=json.dumps(spec, ensure_ascii=False), capture_output=True, text=True, timeout=90)
    lines = (completed.stdout or '').strip().splitlines()
    if not lines:
        return {'ok': False, 'error': (completed.stderr or 'пустой ответ').strip()[-300:]}
    return json.loads(lines[-1])


def capture(deal_ids, target, runner=subprocess.run):
    deals, problems = [], []
    for deal_id in [str(x) for x in deal_ids]:
        card = crm_cli('deal_browser.py', {'action': 'get', 'deal_id': deal_id}, runner=runner)
        if not card.get('ok'):
            problems.append(f'{deal_id}: {card.get("error")}')
            continue
        payers = crm_cli('payer_manager.py', {'action': 'list_deal_payers', 'deal_id': deal_id}, runner=runner)
        invoices = crm_cli('contract_invoice.py', {'action': 'list', 'deal_id': deal_id}, runner=runner)
        ledger = crm_cli('megaplan_api.py', {'deal_id': deal_id}, args=('sync-deal-ledger',), runner=runner)
        deals.append({'deal': card['deal'],
                      'client_id': payers.get('client_id') if payers.get('ok') else None,
                      'client_name': payers.get('client_name') if payers.get('ok') else card['deal'].get('client'),
                      'payers': payers.get('payers') or [] if payers.get('ok') else [],
                      'invoices': invoices.get('invoices') or [] if invoices.get('ok') else [],
                      'ledger': ledger.get('ledger') or [] if ledger.get('ok') else []})
    snapshot = {'source': 'crm-readonly', 'captured_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                'deals': deals, 'problems': problems}
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(snapshot, ensure_ascii=False, indent=2).encode()
    temporary = target.with_suffix('.tmp')
    temporary.write_bytes(payload)
    os.chmod(temporary, 0o600)
    os.replace(temporary, target)
    return snapshot, hashlib.sha256(payload).hexdigest()


PROVENANCE = Path('human-fixtures') / 'provenance.json'


def provenance_path(registry_path):
    """Server-local record of the current snapshot, next to the versioned registry."""
    return Path(registry_path).parent / PROVENANCE


def register(registry_path, snapshot_path, digest, captured_at):
    """Record the fresh snapshot for every automated journey.

    The journey registry is versioned in Git; the snapshot record is server
    state and lives in the git-ignored human-fixtures folder, so a deployment
    never conflicts with, or erases, the last capture.
    """
    registry_path = Path(registry_path)
    try:
        evidence = os.path.relpath(snapshot_path, registry_path.parent)
    except ValueError:
        evidence = str(snapshot_path)
    record = {'source': 'crm-readonly', 'captured_at': captured_at, 'evidence': evidence, 'sha256': digest}
    target = provenance_path(registry_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, target)
    return record


def current_provenance(registry_path, journey=None):
    """The shared snapshot record; a legacy per-journey record is still honoured."""
    try:
        record = json.loads(provenance_path(registry_path).read_text(encoding='utf-8'))
        if isinstance(record, dict) and record.get('source') == 'crm-readonly':
            return record
    except (OSError, ValueError):
        pass
    if journey is not None:
        return journey.get('fixture_provenance') or {}
    try:
        registry = json.loads(Path(registry_path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return next((j.get('fixture_provenance') for j in registry.get('journeys') or []
                 if (j.get('fixture_provenance') or {}).get('source') == 'crm-readonly'), {})


def verified_snapshot(registry_path):
    """The registered snapshot, only if its hash still matches."""
    registry_path = Path(registry_path)
    if not registry_path.exists():
        return None, 'реестр HUMAN_JOURNEYS.json не прочитан'
    provenance = current_provenance(registry_path)
    if not provenance:
        return None, 'снимок CRM ещё не снят: qa_agent.py capture --deal <номер>'
    path = Path(provenance['evidence'])
    path = path if path.is_absolute() else registry_path.parent / path
    try:
        payload = path.read_bytes()
    except OSError:
        return None, f'файл снимка недоступен: {path}'
    if hashlib.sha256(payload).hexdigest() != provenance.get('sha256'):
        return None, 'снимок изменён после регистрации'
    return json.loads(payload), None


def load(crm, snapshot):
    """Fill a FakeMegaplan with the captured deals."""
    for item in snapshot.get('deals') or []:
        deal = item['deal']
        client_id = str(item.get('client_id') or ('client-' + deal['id']))
        if client_id not in crm.contractors:
            crm.add_client(client_id, item.get('client_name') or deal.get('client') or 'Клиент',
                           payers=[(p['id'], p.get('name') or '', p.get('inn') or '') for p in item.get('payers') or []])
        selected = next((p['id'] for p in item.get('payers') or [] if p.get('selected')), None)
        positions = [(row.get('name') or 'Позиция', float(row.get('qty') or 0),
                      float(row.get('sell_price') if row.get('sell_price') is not None else row.get('unit_price') or 0),
                      row.get('cost_material'), row.get('cost_work')) for row in item.get('ledger') or []]
        crm.add_deal(deal['id'], client_id, deal.get('description') or deal.get('name') or '',
                     status_id=str(deal.get('status_id') or '1'), address=deal.get('address') or '',
                     executors=deal.get('executors') or [], payer_id=selected, positions=positions,
                     created_at=deal.get('created_at'), status_name=deal.get('status'),
                     transitions=deal.get('transitions') or [])
        for invoice in item.get('invoices') or []:
            amount = float(invoice.get('sum') or 0)
            rows = [{'name': invoice.get('line') or 'Счёт по спецификации', 'qty': 1, 'price': amount}]
            created = crm.add_invoice(deal['id'], rows, number=str(invoice.get('number') or invoice.get('id')),
                                      status=invoice.get('status') or 'drawn')
            created['date'] = invoice.get('date') or created['date']
    return crm
