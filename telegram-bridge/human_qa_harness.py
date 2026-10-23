"""Human QA stand: the real bridge.main() talks to a virtual operator.

The operator sees only what a person sees in Telegram: bot messages, sent
files, the bottom keyboard and inline buttons under the latest messages.  It
can type text, press a *visible* button or send a file.  Every external system
behind the bridge is replaced at the process boundary (``subprocess.run``):
megaplan-crm CLIs are served by a stateful in-memory Megaplan double, Codex by a
scripted model, curl/sendDocument by the Telegram double.  Bridge code itself,
including its wrappers, runtime guards, UI state and workflow store, runs
unchanged.

Nothing here writes to production paths: all bridge state files are redirected
into a temporary directory and any other write attempt is blocked and recorded
as an isolation finding.
"""
import copy
import datetime as dt
import hashlib
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import types
from unittest.mock import patch


REPO = Path(__file__).resolve().parent.parent
# Pure local document generators: no network, no CRM, output path given on stdin.
# They run for real so that a person receives the actual file.
LOCAL_GENERATORS = {
    'spec_review_xlsx.py': REPO / 'hogart-scraper' / 'spec_review_xlsx.py',
    'build_deal_work_statement.py': REPO / 'megaplan-crm' / 'build_deal_work_statement.py',
}
_REAL_RUN = subprocess.run


def run_script_in_process(path, stdin_text):
    """Execute a stdin->stdout CLI script in this process.

    The isolated offline runner forbids child processes, so a local generator is
    executed with redirected standard streams instead.  Returns (rc, out, err).
    """
    import contextlib
    import io
    import runpy
    out, err = io.StringIO(), io.StringIO()
    saved_stdin, saved_path = sys.stdin, list(sys.path)
    sys.stdin = io.StringIO(stdin_text)
    sys.path.insert(0, str(Path(path).parent))
    code = 0
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            runpy.run_path(str(path), run_name='__main__')
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    except Exception as exc:  # the generator's own failure is a result, not a stand crash
        err.write(f'{type(exc).__name__}: {exc}')
        code = 1
    finally:
        sys.stdin = saved_stdin
        sys.path[:] = saved_path
    return code, out.getvalue(), err.getvalue()


class JourneyStop(BaseException):
    """Ends bridge.main() when the scripted person has nothing more to do."""


class SimulatedCrash(BaseException):
    """The bot process dies right after an external write (power loss, OOM, kill)."""


class ForkedChildDone(BaseException):
    """Raised instead of os._exit() in a branch that would run in a child."""


def _labels(markup):
    rows = (markup or {}).get('inline_keyboard') or (markup or {}).get('keyboard') or []
    return [button.get('text') for row in rows for button in row if button.get('text')]


# ---------------------------------------------------------------------------
# Telegram double


class FakeTelegram:
    def __init__(self, owner_chat='owner'):
        self.owner_chat = owner_chat
        self.update_id = 0
        self.message_id = 100
        self.events = []          # full chronological record (bot + tester)
        self.screen = []          # bot events since the tester's last action
        self.bottom = []          # labels of the persistent reply keyboard
        self.callbacks = {}       # label -> callback data for visible inline buttons
        self.callback_answers = []
        self.driver = None

    # -- bot side -----------------------------------------------------------
    def api(self, _token, method, params=None, **_kwargs):
        params = params or {}
        if method == 'sendMessage':
            self.message_id += 1
            markup = json.loads(params.get('reply_markup') or '{}')
            text = params.get('text') or ''
            if text == '⁣':      # remove_bottom_keyboard helper
                self.bottom = []
                return {'ok': True, 'result': {'message_id': self.message_id}}
            event = {'actor': 'bot', 'kind': 'message', 'chat': str(params.get('chat_id')),
                     'text': text, 'buttons': [], 'message_id': self.message_id}
            if markup.get('inline_keyboard'):
                event['buttons'] = _labels(markup)
                for row in markup['inline_keyboard']:
                    for button in row:
                        if button.get('callback_data'):
                            self.callbacks[button['text']] = (button['callback_data'], self.message_id)
            elif markup.get('keyboard'):
                self.bottom = _labels(markup)
                event['keyboard'] = list(self.bottom)
            elif markup.get('remove_keyboard'):
                self.bottom = []
            self._bot_event(event)
            return {'ok': True, 'result': {'message_id': self.message_id}}
        if method == 'getUpdates':
            return {'ok': True, 'result': self.driver.next_updates()}
        if method == 'answerCallbackQuery':
            self.callback_answers.append(params.get('text'))
            # Telegram shows this text as a pop-up over the chat: the person sees it.
            if params.get('text') and params.get('text') != 'Принято':
                self._bot_event({'actor': 'bot', 'kind': 'toast', 'chat': self.owner_chat,
                                 'text': '[всплывающее] ' + params['text'], 'buttons': []})
            return {'ok': True, 'result': True}
        return {'ok': True, 'result': {}}

    def document(self, chat_id, path, caption=None, filename=None):
        exists = bool(path) and os.path.exists(path)
        event = {'actor': 'bot', 'kind': 'document', 'chat': str(chat_id),
                 'text': caption or '', 'filename': filename or (os.path.basename(path) if path else ''),
                 'size': os.path.getsize(path) if exists else 0, 'exists': exists}
        self._bot_event(event)
        return exists

    def _bot_event(self, event):
        self.events.append(event)
        if event.get('chat') == self.owner_chat:
            self.screen.append(event)

    # -- tester side --------------------------------------------------------
    def begin_action(self, kind, text):
        self.events.append({'actor': 'tester', 'kind': kind, 'text': text})
        self.screen = []

    def visible_inline(self):
        return dict(self.callbacks)

    def next_update(self, payload):
        self.update_id += 1
        return {'update_id': self.update_id, **payload}


# ---------------------------------------------------------------------------
# Megaplan double


def _money(value):
    return float(value or 0)


class FakeMegaplan:
    """Stateful CRM with the shapes produced by the real megaplan-crm CLIs."""

    def __init__(self, root):
        self.root = Path(root)
        self.deals = {}
        self.contractors = {}
        self.invoices = {}
        self.employees = {}
        self.statuses = {'1': 'Новая', '2': 'Выставление счета', '3': 'Закупка', '4': 'Монтаж', '5': 'Завершена'}
        self.calls = []
        self.writes = []
        self.failures = {}     # (script, action) -> error text
        self.reachable = True
        self.economics = {}             # deal_id -> published economics file (survives a bot restart)
        self.crash_after_write = set()   # (script, action): the process dies after this write
        self.crash_before_write = set()  # operation was claimed, CRM received no write
        self.duplicate_after_write = set()
        self.pending_crash = False
        self.next_deal = 990100
        self.next_invoice = 5000
        self.next_payer = 7000

    # -- fixtures -----------------------------------------------------------
    def add_client(self, client_id, name, kind='company', payers=()):
        self.contractors[str(client_id)] = {
            'id': str(client_id), 'name': name, 'kind': kind,
            'payers': [{'id': str(p[0]), 'name': p[1], 'inn': p[2] if len(p) > 2 else ''} for p in payers]}
        return self.contractors[str(client_id)]

    def add_deal(self, deal_id, client_id, description='', status_id='1', address='', executors=(),
                 payer_id=None, positions=(), contract=None, created_at=None):
        positions = [dict(name=p[0], qty=p[1], price=p[2], cost_material=(p[3] if len(p) > 3 else None),
                          cost_work=(p[4] if len(p) > 4 else None)) for p in positions]
        self.deals[str(deal_id)] = {
            'id': str(deal_id), 'client_id': str(client_id), 'description': description,
            'status_id': str(status_id), 'address': address, 'executors': list(executors),
            'payer_id': str(payer_id) if payer_id else None, 'positions': positions,
            'contract': contract, 'created_at': created_at or '2026-10-01T10:00:00+03:00'}
        return self.deals[str(deal_id)]

    def add_invoice(self, deal_id, rows, number=None, status='drawn'):
        self.next_invoice += 1
        invoice_id = str(self.next_invoice)
        self.invoices[invoice_id] = {
            'id': invoice_id, 'deal_id': str(deal_id), 'number': number or invoice_id[-3:],
            'date': '20.10.2026', 'created_at': dt.datetime.now(dt.timezone.utc).isoformat(),
            'status': status, 'rows': rows,
            'sum': round(sum(r['qty'] * r['price'] for r in rows), 2)}
        return self.invoices[invoice_id]

    def add_employee(self, employee_id, name):
        self.employees[str(employee_id)] = {'id': str(employee_id), 'name': name}

    # -- summaries ----------------------------------------------------------
    def price(self, deal):
        return round(sum(_money(p['qty']) * _money(p['price']) for p in deal['positions']), 2)

    def summary(self, deal):
        client = self.contractors.get(deal['client_id']) or {}
        transitions = [{'transition_id': 't' + sid, 'state_id': sid, 'name': name, 'enabled': True}
                       for sid, name in self.statuses.items() if sid != deal['status_id']]
        return {'id': deal['id'], 'name': deal['description'][:60], 'description': deal['description'],
                'client': client.get('name') or 'не указан', 'address': deal['address'],
                'executors': list(deal['executors']), 'status_id': deal['status_id'],
                'status': self.statuses.get(deal['status_id'], 'не указан'), 'program': 'Продажи',
                'created_at': deal['created_at'], 'price': self.price(deal),
                'positions_count': len(deal['positions']), 'transitions': transitions}

    def ledger(self, deal):
        return [{'name': p['name'], 'qty': p['qty'], 'sell_price': p['price'], 'unit': 'шт',
                 'cost_material': p.get('cost_material'), 'cost_work': p.get('cost_work'),
                 'offer_row_id': f"{deal['id']}-{index}"}
                for index, p in enumerate(deal['positions'], 1)]

    def payer(self, deal):
        client = self.contractors.get(deal['client_id']) or {}
        return next((p for p in client.get('payers') or [] if p['id'] == deal.get('payer_id')), None)

    def invoice_view(self, invoice):
        rows = invoice['rows']
        return {'id': invoice['id'], 'number': invoice['number'], 'date': invoice['date'],
                'status': invoice['status'], 'sum': invoice['sum'], 'rows_count': len(rows),
                'line': rows[0]['name'] if len(rows) == 1 else None,
                'lines': [row['name'] for row in rows], 'created_at': invoice.get('created_at'), 'template': 'Счёт'}

    def _deal(self, spec):
        deal = self.deals.get(str(spec.get('deal_id') or spec.get('dealId') or ''))
        if not deal:
            raise ValueError('сделка не найдена')
        return deal

    def _write(self, script, action, spec):
        self.writes.append({'script': script, 'action': action, 'spec': copy.deepcopy(spec)})
        self.pending_crash = (script, action) in self.crash_after_write

    # -- CLI dispatch -------------------------------------------------------
    CRM_SCRIPTS = {'deal_browser', 'payer_manager', 'contract_invoice', 'megaplan_webhook', 'megaplan_api',
                   'generate_contract', 'deal_proposal'}

    def handle(self, script, args, spec):
        script = script[:-3] if script.endswith('.py') else script
        action = (args[0] if args else None) or (spec or {}).get('action') or 'apply'
        self.calls.append({'script': script, 'action': action, 'spec': copy.deepcopy(spec)})
        failure = self.failures.get((script, action))
        if failure:
            return {'ok': False, 'error': failure}
        if not self.reachable and script in self.CRM_SCRIPTS:
            # What the real CLIs print when Megaplan does not answer.
            return {'ok': False, 'error': 'техническая ошибка Мегаплана: <urlopen error timed out>'}
        if (script, action) in self.crash_before_write:
            self.crash_before_write.discard((script, action))
            raise SimulatedCrash(f'{script} {action} before write')
        handler = getattr(self, 'cli_' + script.replace('-', '_'), None)
        if handler is None:
            return None
        try:
            result = handler(action, spec or {})
        except ValueError as exc:
            return {'ok': False, 'error': str(exc)}
        if self.pending_crash:
            self.pending_crash = False
            self.crash_after_write.discard((script, action))
            raise SimulatedCrash(f'{script} {action}')
        return result

    def cli_deal_browser(self, action, spec):
        if action in ('get', 'get_cached'):
            return {'ok': True, 'deal': self.summary(self._deal(spec)), **({'cached': True} if action == 'get_cached' else {})}
        if action in ('get_many', 'get_many_cached'):
            ids = {str(x) for x in spec.get('deal_ids') or []}
            return {'ok': True, 'deals': [self.summary(d) for d in self.deals.values() if d['id'] in ids]}
        ordered = sorted(self.deals.values(), key=lambda d: int(d['id']), reverse=True)
        if action == 'list':
            found = ordered[:max(1, min(int(spec.get('limit', 5)), 15))]
            return {'ok': True, 'deals': [self.summary(d) for d in found], 'total_count': len(found)}
        if action in ('search_any', 'search_client', 'search_address'):
            query = str(spec.get('query') or '').strip().casefold().replace('ё', 'е')
            if not query:
                raise ValueError('пустая строка поиска')
            def haystack(deal):
                summary = self.summary(deal)
                if action == 'search_client':
                    return summary['client']
                if action == 'search_address':
                    return summary['address']
                return ' '.join([summary['name'] or '', summary['client'], summary['address']])
            words = [w for w in re.split(r'\W+', query) if len(w) > 2] or [query]
            found = [d for d in ordered if any(w in haystack(d).casefold().replace('ё', 'е') for w in words)]
            return {'ok': True, 'deals': [self.summary(d) for d in found[:15]], 'total_count': len(found)}
        if action == 'move_status':
            deal = self._deal(spec)
            if str(spec.get('state_id')) not in self.statuses:
                raise ValueError('переход недоступен')
            self._write('deal_browser', action, spec)
            deal['status_id'] = str(spec['state_id'])
            return {'ok': True, 'deal': self.summary(deal)}
        if action == 'search_employees':
            query = str(spec.get('query') or '').casefold()
            return {'ok': True, 'employees': [e for e in self.employees.values() if query in e['name'].casefold()]}
        if action == 'set_executor':
            deal = self._deal(spec)
            employee = self.employees.get(str(spec.get('employee_id')))
            if not employee:
                raise ValueError('сотрудник не найден')
            self._write('deal_browser', action, spec)
            deal['executors'] = [employee['name']]
            return {'ok': True, 'deal': self.summary(deal), 'employee': employee}
        if action == 'upsert_profitability_file':
            # Mirrors deal_browser.replace_economics_attachment: same numbers and
            # the published file still present -> no write.
            deal = self._deal(spec)
            published = self.economics.get(deal['id'])
            if (spec.get('data_fingerprint') and published
                    and published['data_fingerprint'] == spec['data_fingerprint'] and published['present']):
                return {'ok': True, **published, 'unchanged': True}
            self._write('deal_browser', action, spec)
            self.economics[deal['id']] = {'file_id': f"econ-{len(self.writes)}", 'present': True,
                                          'data_fingerprint': spec.get('data_fingerprint')}
            return {'ok': True, 'file_id': self.economics[deal['id']]['file_id']}
        if action == 'upload_contracts':
            deal = self._deal(spec)
            self._write('deal_browser', action, spec)
            names = [Path(p).name for p in spec.get('paths') or []]
            deal['contract'] = next((n for n in names if n.endswith('.pdf')), names[0] if names else None)
            return {'ok': True, 'files': [{'name': n} for n in names]}
        if action == 'get_contract':
            deal = self._deal(spec)
            if not deal.get('contract'):
                return {'ok': False, 'error': 'в сделке нет договора'}
            path = self.root / f"contract-{deal['id']}.pdf"
            path.write_bytes(b'%PDF-1.4 contract')
            return {'ok': True, 'path': str(path), 'filename': deal['contract']}
        return None

    def cli_payer_manager(self, action, spec):
        deal = self._deal(spec) if spec.get('deal_id') else None
        if action == 'list_deal_payers':
            client = self.contractors.get(deal['client_id'])
            if not client:
                raise ValueError('у сделки не указан клиент, плательщика не к чему привязать')
            return {'ok': True, 'deal_id': deal['id'], 'client_id': client['id'], 'client_name': client['name'],
                    'payers': [{**p, 'selected': p['id'] == deal.get('payer_id')} for p in client['payers']]}
        if action == 'apply' and (spec.get('payer_id') or spec.get('payer_name')):
            if not deal:
                raise ValueError('для привязки существующего плательщика нужна сделка')
            client = self.contractors[deal['client_id']]
            wanted = [p for p in client['payers'] if p['id'] == str(spec.get('payer_id') or '')
                      or p['name'].casefold() == str(spec.get('payer_name') or '').strip().casefold()]
            if len(wanted) != 1:
                raise ValueError('плательщик не найден у клиента сделки или найден неоднозначно')
            self._write('payer_manager', 'link', spec)
            deal['payer_id'] = wanted[0]['id']
            return {'ok': True, 'deal_id': deal['id'], 'payer_id': wanted[0]['id'], 'payer_name': wanted[0]['name'],
                    'client_id': client['id'], 'client_name': client['name'], 'created': False, 'attached': True,
                    'deal_url': f"https://cclimat.megaplan.ru/deals/{deal['id']}/card/"}
        if action == 'apply' and spec.get('payer'):
            card = spec['payer']
            client = self.contractors[deal['client_id']] if deal else None
            if not client:
                raise ValueError('у сделки не указан клиент, плательщика не к чему привязать')
            existing = next((p for p in client['payers'] if card.get('inn') and p.get('inn') == card.get('inn')), None)
            created = existing is None
            if created:
                self.next_payer += 1
                existing = {'id': str(self.next_payer), 'name': card.get('name') or 'Плательщик', 'inn': card.get('inn') or ''}
                client['payers'].append(existing)
            self._write('payer_manager', 'card', spec)
            deal['payer_id'] = existing['id']
            return {'ok': True, 'deal_id': deal['id'], 'payer_id': existing['id'], 'payer_name': existing['name'],
                    'client_id': client['id'], 'client_name': client['name'], 'created': created, 'attached': True,
                    'deal_url': f"https://cclimat.megaplan.ru/deals/{deal['id']}/card/"}
        if action in ('save_director', 'save_signatory'):
            payer = self.payer(deal)
            if not payer:
                raise ValueError('в сделке не выбран плательщик')
            self._write('payer_manager', action, spec)
            payer['director'] = spec.get('director')
            return {'ok': True, 'deal_id': deal['id'], 'payer_id': payer['id'], 'payer_name': payer['name'],
                    'director': spec.get('director'), 'saved': True}
        return None

    def _full_rows(self, deal):
        return [{'name': p['name'], 'quantity': p['qty'], 'price': p['price']} for p in deal['positions']]

    def cli_contract_invoice(self, action, spec):
        deal = self._deal(spec)
        payer = self.payer(deal)
        if action == 'list':
            invoices = [self.invoice_view(i) for i in self.invoices.values() if i['deal_id'] == deal['id']]
            invoices.sort(key=lambda item: int(item['id']), reverse=True)
            return {'ok': True, 'deal_id': deal['id'], 'invoices': invoices}
        if action in ('preview_full', 'create_full'):
            if not payer:
                raise ValueError('к сделке не привязан плательщик')
            if not deal['positions']:
                raise ValueError('в сделке нет позиций для полного счёта')
            rows = self._full_rows(deal)
            fingerprint = f"{deal['id']}:{payer['id']}:{self.price(deal)}"
            data = {'ok': True, 'deal_id': deal['id'], 'payer_id': payer['id'], 'payer_name': payer['name'],
                    'basis': f"Спецификация к сделке №{deal['id']}", 'rows': rows,
                    'total': str(self.price(deal)), 'recipient_id': '1', 'template_id': '1',
                    'fingerprint': fingerprint}
            if action == 'preview_full':
                return data
            if spec.get('expected_fingerprint') and spec['expected_fingerprint'] != fingerprint:
                return {'ok': False, 'no_effect': True,
                        'error': 'Спецификация, плательщик или наша организация изменены. Подготовьте счёт заново.'}
            self._write('contract_invoice', action, spec)
            invoice = self.add_invoice(deal['id'], [{'name': r['name'], 'qty': r['quantity'], 'price': r['price']} for r in rows])
            if ('contract_invoice', action) in self.duplicate_after_write:
                self.add_invoice(deal['id'], copy.deepcopy(invoice['rows']))
            return {'ok': True, 'deal_id': deal['id'], 'invoice_id': invoice['id'], 'invoice_number': invoice['number'],
                    'invoice_status': 'drawn', 'rows_count': len(rows), 'basis': data['basis'],
                    'public_download_link': None}
        if action in ('preview', 'create'):
            contract = deal.get('contract')
            if not contract:
                raise ValueError('в сделке не найден подписанный договор')
            if not payer:
                raise ValueError('к сделке не привязан плательщик')
            clause = str(spec.get('clause') or '')
            shares = {'6.4.1': 0.5, '6.4.2': 0.4, '6.4.3': 0.1}
            if clause not in shares:
                raise ValueError('пункт оплаты не найден в договоре')
            amount = round(self.price(deal) * shares[clause], 2)
            line = f"Оплата по договору №{deal['id']}-Д согласно п.{clause}"
            data = {'ok': True, 'deal_id': deal['id'], 'payer_id': payer['id'], 'payer_name': payer['name'],
                    'contract_file_id': 'f1', 'contract_filename': contract, 'clause': clause,
                    'contract_number': deal['id'] + '-Д', 'contract_date': '01.10.2026', 'line': line,
                    'amount': amount, 'tax_id': '1', 'fingerprint': f"{deal['id']}:{clause}:{amount}"}
            if action == 'preview':
                return data
            if spec.get('expected_fingerprint') and spec['expected_fingerprint'] != data['fingerprint']:
                return {'ok': False, 'no_effect': True,
                        'error': 'Договор, плательщик или наша организация изменены. Подготовьте счёт заново.'}
            self._write('contract_invoice', action, spec)
            invoice = self.add_invoice(deal['id'], [{'name': line, 'qty': 1, 'price': amount}])
            if ('contract_invoice', action) in self.duplicate_after_write:
                self.add_invoice(deal['id'], copy.deepcopy(invoice['rows']))
            return {**data, 'invoice_id': invoice['id'], 'invoice_number': invoice['number'],
                    'invoice_status': 'drawn', 'public_download_link': None}
        if action == 'delete':
            invoice = self.invoices.get(str(spec.get('invoice_id')))
            if not invoice or invoice['deal_id'] != deal['id']:
                raise ValueError('счёт не относится к выбранной сделке')
            self._write('contract_invoice', action, spec)
            del self.invoices[invoice['id']]
            return {'ok': True, 'deal_id': deal['id'], 'invoice_id': invoice['id']}
        return None

    def cli_megaplan_webhook(self, action, spec):
        if action != 'fetch-invoice-pdf':
            return None
        if spec.get('invoiceId'):
            invoice = self.invoices.get(str(spec['invoiceId']))
            if not invoice:
                return {'ok': False, 'error': 'счёт не найден'}
        else:
            deal = self.deals.get(str(spec.get('dealId')))
            if not deal:
                return {'ok': False, 'error': 'сделка не найдена'}
            own = sorted((i for i in self.invoices.values() if i['deal_id'] == deal['id']), key=lambda i: int(i['id']))
            if not own:
                return {'ok': False, 'error': f"у сделки {deal['id']} нет счетов"}
            invoice = own[-1]
        path = self.root / f"invoice-{invoice['id']}-{time.monotonic_ns()}.pdf"
        path.write_bytes(b'%PDF-1.4 invoice ' + invoice['id'].encode())
        return {'ok': True, 'path': str(path), 'filename': f"Счёт №{invoice['number']}.pdf",
                'caption': f"Счёт №{invoice['number']} от {invoice['date']} на {invoice['sum']:.2f} ₽ (сделка №{invoice['deal_id']})"}

    def cli_megaplan_api(self, action, spec):
        if action == 'search-contractors':
            query = str(spec.get('name') or '').casefold().replace('ё', 'е').strip(' «»"')
            words = [w for w in re.split(r'\W+', query) if len(w) > 2] or [query]
            found = [c for c in self.contractors.values()
                     if any(w in c['name'].casefold().replace('ё', 'е') for w in words)]
            return {'ok': True, 'clients': [{'id': c['id'], 'kind': c['kind'], 'name': c['name']} for c in found]}
        if action in ('create-full-deal', 'create-deal-from-spec'):
            client_id = spec.get('client_id')
            if client_id and str(client_id) not in self.contractors:
                return {'ok': False, 'error': 'клиент не найден'}
            if not client_id:
                client_id = str(800000 + len(self.contractors))
                self.add_client(client_id, spec.get('client_name') or 'Новый клиент', spec.get('client_kind') or 'company')
            self._write('megaplan_api', action, spec)
            self.next_deal += 1
            deal = self.add_deal(self.next_deal, client_id, spec.get('description') or '',
                                 positions=[(i['name'], i['qty'], i.get('unit_price') or 0,
                                             i.get('cost_material'), i.get('cost_work')) for i in spec.get('items') or []])
            return {'ok': True, 'id': deal['id'], 'url': f"https://cclimat.megaplan.ru/deals/{deal['id']}/card/",
                    'positions_count': len(deal['positions']), 'ledger': self.ledger(deal)}
        if action == 'sync-deal-ledger':
            deal = self._deal(spec)
            return {'ok': True, 'deal_id': deal['id'], 'ledger': self.ledger(deal)}
        return None

    def cli_generate_contract(self, action, spec):
        deal = self._deal(spec)
        payer = self.payer(deal)
        if not payer:
            return {'ok': False, 'error': 'в сделке не выбран плательщик'}
        signer = {k: str((spec.get('customer_signatory') or {}).get(k) or payer.get('signatory', {}).get(k) or '').strip()
                  for k in ('name', 'position', 'authority')}
        missing = [label for key, label in (('name', 'ФИО подписанта'), ('position', 'должность подписанта'),
                                            ('authority', 'основание полномочий подписанта')) if not signer[key]]
        if not deal['address']:
            missing.insert(0, 'адрес объекта')
        goods = sum(p['qty'] * p['price'] for p in deal['positions'] if p.get('cost_work') is None)
        works = sum(p['qty'] * p['price'] for p in deal['positions'] if p.get('cost_work') is not None)
        preview = {'deal_id': deal['id'], 'payer_id': payer['id'], 'number': deal['id'] + '-Д', 'date': '22.10.2026',
                   'client': self.summary(deal)['client'], 'address': deal['address'], 'subject': deal['description'],
                   'payer_name': payer['name'], 'equipment': goods, 'materials': 0.0, 'advance': goods,
                   'works': works, 'total': goods + works, 'tax_text': 'Без НДС', 'positions_count': len(deal['positions']),
                   'missing': missing, 'positions': [], 'signatory': signer}
        fingerprint = f"{deal['id']}:{payer['id']}:{self.price(deal)}:{sorted(signer.items())}"
        if spec.get('action', 'preview') == 'preview':
            return {'ok': True, 'preview': {**preview, 'fingerprint': fingerprint, 'seller_name': 'ООО «КЛИВЭЛ»'}}
        if spec.get('expected_fingerprint') and spec['expected_fingerprint'] != fingerprint:
            return {'ok': False, 'no_effect': True, 'error': 'Данные договора или наша организация изменились после просмотра. Проверьте договор заново.'}
        if missing:
            return {'ok': False, 'error': 'не заполнены обязательные данные', 'missing': missing}
        payer['signatory'] = signer
        docx, pdf = self.root / f"Договор {deal['id']}-Д.docx", self.root / f"Договор {deal['id']}-Д (подписан).pdf"
        docx.write_bytes(b'PK docx'); pdf.write_bytes(b'%PDF-1.4 contract')
        return {'ok': True, 'preview': preview, 'docx_path': str(docx), 'pdf_path': str(pdf)}

    def cli_deal_proposal(self, action, spec):
        deal = self._deal(spec)
        if action == 'publish':
            if not deal['positions']:
                return {'ok': False, 'error': 'в сделке нет позиций'}
            self._write('deal_proposal', action, spec)
            path = self.root / f"КП по сделке {deal['id']}.pdf"
            path.write_bytes(b'%PDF-1.4 proposal')
            return {'ok': True, 'path': str(path), 'count': len(deal['positions']), 'total': self.price(deal)}
        if action == 'ack':
            return {'ok': True}
        return None

    def cli_build_profitability_report(self, action, spec):
        deal = self.deals.get(str(action))
        if not deal:
            return {'ok': False, 'error': 'сделка не найдена'}
        revenue = self.price(deal)
        cost = sum(p['qty'] * float(p.get('cost_material') or 0) + p['qty'] * float(p.get('cost_work') or 0)
                   for p in deal['positions'])
        path = self.root / f"Рентабельность {deal['id']}.xlsx"
        path.write_bytes(b'PK xlsx')
        figures = [(p['name'], p['qty'], p['price'], p.get('cost_material'), p.get('cost_work')) for p in deal['positions']]
        return {'ok': True, 'path': str(path), 'total_revenue': revenue, 'total_cost': cost,
                'total_profit': revenue - cost, 'margin_pct': (revenue - cost) / revenue * 100 if revenue else 0,
                'data_fingerprint': hashlib.sha256(json.dumps(figures, sort_keys=True).encode()).hexdigest()}

    def cli_deal_ledger(self, action, spec):
        if action == 'list-recent':
            return [{'deal_id': d['id'], 'client_name': (self.contractors.get(d['client_id']) or {}).get('name')}
                    for d in sorted(self.deals.values(), key=lambda d: int(d['id']), reverse=True)[:10]]
        return None

    def cli_financial_archive(self, action, spec):
        return {'ok': True, 'archived': True, 'queued': False}

    def cli_bank_statement(self, action, spec):
        if action == 'list':
            return {'ok': True, 'transactions': []}
        return None


# ---------------------------------------------------------------------------
# Model double


class ScriptedModel:
    """Codex replacement.  Rules are (substring-or-regex, reply) pairs.

    A deterministic menu action that reaches the model is itself a finding, so
    every prompt is recorded for the journey's observations.
    """

    def __init__(self, rules=()):
        self.rules = list(rules)
        self.prompts = []

    def reply(self, prompt):
        self.prompts.append(prompt)
        user_part = prompt.split('СООБЩЕНИЕ ПОЛЬЗОВАТЕЛЯ:', 1)[-1]
        for pattern, answer in self.rules:
            matched = pattern.search(user_part) if hasattr(pattern, 'search') else pattern in user_part
            if matched:
                return answer(prompt) if callable(answer) else answer
        return 'Уточните, пожалуйста, что нужно сделать.'


def codex_jsonl(text, thread='thread-qa'):
    events = [{'type': 'thread.started', 'thread_id': thread},
              {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': text}}]
    return '\n'.join(json.dumps(e, ensure_ascii=False) for e in events) + '\n'


# ---------------------------------------------------------------------------
# Operator and journey driver


class Action:
    def __init__(self, kind, value, **extra):
        self.kind, self.value, self.extra = kind, value, extra


def say(text):
    return Action('text', text)


def press(label):
    return Action('press', label)


def press_old(label):
    """Press a button on an earlier message: double taps and scrolled-up screens."""
    return Action('press_old', label)


def send_voice(seconds=4):
    """A dictated message: Telegram delivers it as ``voice`` without text."""
    return Action('voice', seconds)


def send_file(path, name=None, caption=''):
    return Action('file', str(path), name=name or os.path.basename(str(path)), caption=caption)


class Operator:
    """What the person currently sees, plus assertions phrased as a person would."""

    def __init__(self, stand):
        self.stand = stand
        self.observations = []

    @property
    def telegram(self):
        return self.stand.telegram

    def screen_text(self):
        return '\n'.join(e.get('text') or '' for e in self.telegram.screen)

    def messages(self):
        return [e for e in self.telegram.screen if e['kind'] == 'message']

    def documents(self):
        return [e for e in self.telegram.screen if e['kind'] == 'document']

    def visible_buttons(self):
        visible = [b for e in self.telegram.screen for b in e.get('buttons') or []]
        return visible + [b for b in self.telegram.bottom if b not in visible]

    def observe(self, expected, actual, ok):
        self.observations.append({'expected': expected, 'actual': str(actual)[:600],
                                  'verdict': 'passed' if ok else 'failed'})
        if not ok:
            raise AssertionError(f'{expected}\nПолучено: {str(actual)[:600]}')

    def sees(self, *fragments, expected=None):
        text = self.screen_text()
        missing = [f for f in fragments if f.casefold() not in text.casefold()]
        self.observe(expected or ('Бот показал: ' + '; '.join(fragments)), text or '(бот промолчал)', not missing)

    def not_sees(self, *fragments, expected=None):
        text = self.screen_text()
        present = [f for f in fragments if f.casefold() in text.casefold()]
        self.observe(expected or ('Бот не показал: ' + '; '.join(fragments)), text or '(бот промолчал)', not present)

    def sees_button(self, label, expected=None):
        self.observe(expected or f'Видна кнопка «{label}»', ', '.join(self.visible_buttons()) or '(кнопок нет)',
                     label in self.visible_buttons())

    def got_document(self, name_fragment='', expected=None):
        docs = self.documents()
        ok = any(d['exists'] and d['size'] > 0 and name_fragment.casefold() in (d['filename'] or '').casefold()
                 for d in docs)
        self.observe(expected or f'Пришёл файл {name_fragment}'.strip(),
                     [(d['filename'], d['size']) for d in docs] or '(файлов нет)', ok)

    def answered(self, expected='Бот ответил на действие человека'):
        self.observe(expected, self.screen_text() or '(бот промолчал)', bool(self.telegram.screen))

    def check(self, expected, actual, ok):
        self.observe(expected, actual, bool(ok))


class Stand:
    """Owns patches, temporary storage and the bridge run for one journey."""

    def __init__(self, model_rules=(), owner_chat='owner'):
        self.temporary = tempfile.TemporaryDirectory(prefix='smartbild-human-qa-')
        self.root = Path(self.temporary.name)
        (self.root / 'crm').mkdir()
        (self.root / 'state').mkdir()
        self.telegram = FakeTelegram(owner_chat)
        self.telegram.driver = self
        self.crm = FakeMegaplan(self.root / 'crm')
        self.model = ScriptedModel(model_rules)
        self.operator = Operator(self)
        self.owner_chat = owner_chat
        self.journey = None
        self.failure = None
        self.unexpected = []      # external calls without a double
        self.blocked_writes = []
        self.finished = False

    # -- driver -------------------------------------------------------------
    def next_updates(self):
        if self.finished:
            raise JourneyStop()
        try:
            action = next(self.journey) if self.journey_started else self.journey.send(None)
        except StopIteration:
            self.finished = True
            raise JourneyStop()
        except AssertionError as exc:
            self.failure = exc
            self.finished = True
            raise JourneyStop()
        self.journey_started = True
        return [self.update_for(action)]

    def update_for(self, action):
        chat = {'id': self.owner_chat, 'type': 'private'}
        sender = {'id': self.owner_chat}
        if action.kind == 'press':
            label = action.value
            inline = {b for e in self.telegram.screen for b in e.get('buttons') or []}
            if label in inline:
                data, message_id = self.telegram.callbacks[label]
                self.telegram.begin_action('button', label)
                return self.telegram.next_update({'callback_query': {
                    'id': f'cb-{self.telegram.update_id + 1}', 'from': sender, 'data': data,
                    'message': {'message_id': message_id, 'chat': chat}}})
            if label in self.telegram.bottom:
                self.telegram.begin_action('button', label)
                return self.telegram.next_update({'message': {
                    'message_id': self.telegram.update_id + 1, 'date': time.time(), 'chat': chat,
                    'from': sender, 'text': label}})
            visible = ', '.join(self.operator.visible_buttons()) or 'кнопок нет'
            self.failure = AssertionError(f'Человек не видит кнопку «{label}». На экране: {visible}')
            self.finished = True
            raise JourneyStop()
        if action.kind == 'press_old':
            if action.value not in self.telegram.callbacks:
                self.failure = AssertionError(f'Кнопка «{action.value}» никогда не показывалась')
                self.finished = True
                raise JourneyStop()
            data, message_id = self.telegram.callbacks[action.value]
            self.telegram.begin_action('button', action.value + ' (старое сообщение)')
            return self.telegram.next_update({'callback_query': {
                'id': f'cb-{self.telegram.update_id + 1}', 'from': sender, 'data': data,
                'message': {'message_id': message_id, 'chat': chat}}})
        if action.kind == 'voice':
            self.telegram.begin_action('voice', f'(голосовое, {action.value} с)')
            return self.telegram.next_update({'message': {
                'message_id': self.telegram.update_id + 1, 'date': time.time(), 'chat': chat, 'from': sender,
                'voice': {'file_id': 'voice-1', 'file_unique_id': 'voice-1', 'duration': action.value}}})
        if action.kind == 'file':
            self.telegram.begin_action('file', f"{action.extra['name']} {action.extra.get('caption') or ''}".strip())
            file_id = 'file-' + str(len(self.telegram.events))
            self.uploads[file_id] = (action.value, action.extra['name'])
            message = {'message_id': self.telegram.update_id + 1, 'date': time.time(), 'chat': chat, 'from': sender,
                       'document': {'file_id': file_id, 'file_unique_id': file_id, 'file_name': action.extra['name']}}
            if action.extra.get('caption'):
                message['caption'] = action.extra['caption']
            return self.telegram.next_update({'message': message})
        self.telegram.begin_action('message', action.value)
        return self.telegram.next_update({'message': {
            'message_id': self.telegram.update_id + 1, 'date': time.time(), 'chat': chat,
            'from': sender, 'text': action.value}})

    # -- process boundary ---------------------------------------------------
    def subprocess_run(self, cmd, *args, input=None, **kwargs):
        import bridge
        argv = [str(x) for x in (cmd if isinstance(cmd, (list, tuple)) else [cmd])]
        done = lambda rc, out='', err='': subprocess.CompletedProcess(argv, rc, out, err)
        if argv and argv[0] == bridge.CODEX_BIN:
            return done(0, codex_jsonl(self.model.reply(input or '')))
        if argv and argv[0] == 'curl' and any('sendDocument' in a for a in argv):
            fields = dict(argv[i + 1].split('=', 1) for i, a in enumerate(argv) if a == '-F' and '=' in argv[i + 1])
            document = fields.get('document', '').lstrip('@')
            path, _, filename = document.partition(';filename=')
            sent = self.telegram.document(fields.get('chat_id'), path, fields.get('caption'), filename or None)
            return done(0, json.dumps({'ok': sent}))
        script = next((Path(a).name for a in argv[1:] if a.endswith('.py')), None)
        if script in LOCAL_GENERATORS:
            return done(*run_script_in_process(LOCAL_GENERATORS[script], input or ''))
        if script:
            position = next(i for i, a in enumerate(argv) if a.endswith('.py'))
            extra = [a for a in argv[position + 1:] if not a.startswith('-')]
            try:
                spec = json.loads(input) if input else {}
            except ValueError:
                spec = {'raw': input}
            result = self.crm.handle(script, extra, spec)
            if result is not None:
                text = json.dumps(result, ensure_ascii=False)
                ok = not isinstance(result, dict) or result.get('ok', True) is not False
                return done(0 if ok else 1, text + '\n')
        self.unexpected.append(' '.join(argv)[:300])
        return done(1, '', 'external process is not available on the QA stand')

    def download_document(self, _token, document):
        source, name = self.uploads.get(document.get('file_id'), (None, None))
        if not source:
            return None, 'Файл не найден'
        target = self.root / 'state' / f"upload-{document['file_id']}-{name}"
        shutil.copy(source, target)
        return str(target), None

    # -- run ----------------------------------------------------------------
    def run(self, journey, timeout=60):
        """Run one journey (a generator taking the Operator) through bridge.main()."""
        import bridge
        import installer_onboarding
        import invoice_tasks
        import decision_channel
        import statement_document_context
        self.uploads = getattr(self, 'uploads', {})
        self.finished = False
        self.runs = getattr(self, 'runs', 0) + 1
        if self.runs > 1:
            # Same storage, fresh process: what a service restart looks like to a person.
            self.telegram.events.append({'actor': 'system', 'kind': 'restart', 'text': '— бот перезапущен —',
                                         'chat': self.owner_chat})
            self.telegram.screen = []
        # The owner has used the bot before: Telegram keeps its persistent menu.
        if not self.telegram.bottom:
            self.telegram.bottom = _labels(bridge.MAIN_KEYBOARD)
        self.journey = journey(self.operator)
        self.journey_started = False
        state = self.root / 'state'
        finance_state = self.root / 'finance'
        statement_recent_context = statement_document_context.recent_context
        statement_deal_candidates = statement_document_context.deal_candidates
        statement_match_document = statement_document_context.match_document
        statement_exclude_documents = statement_document_context.exclude_documents
        paths = {name: str(state / Path(value).name) for name, value in vars(bridge).items()
                 if re.fullmatch(r'[A-Z_]+_(FILE|DIR|LOG)', name) and isinstance(value, str)
                 and value.startswith(bridge.BASE_DIR) and name != 'BASE_DIR'}
        real_os, real_time = bridge.os, bridge.time

        class ChildOS(types.ModuleType):
            def __getattr__(self, name):
                return getattr(real_os, name)
        child_os = ChildOS('os')
        child_os.fork = lambda: 0
        def child_exit(_code=0):
            raise ForkedChildDone()
        child_os._exit = child_exit
        child_os.execv = lambda *a: (_ for _ in ()).throw(AssertionError('execv на QA-стенде запрещён'))
        quick_time = types.ModuleType('time')
        quick_time.__dict__.update({k: getattr(real_time, k) for k in dir(real_time) if not k.startswith('__')})
        quick_time.sleep = lambda _seconds: None

        original_bg = bridge.run_background_job
        def background(job, *args, **kwargs):
            try:
                original_bg(job, *args, **kwargs)
            except ForkedChildDone:
                pass
        def foreground(job):
            try:
                job()
            except ForkedChildDone:
                pass

        started = time.monotonic()
        def deadline_guard():
            if time.monotonic() - started > timeout:
                self.failure = AssertionError(f'Сценарий не завершился за {timeout} с')
                raise JourneyStop()

        guard_state = {'on': True}
        sandbox = self.root.resolve()
        allowed_prefixes = (str(sandbox), tempfile.gettempdir(), '/dev/')
        def audit(event, args):
            if not guard_state['on'] or event != 'open':
                return
            path, mode, flags = args
            if not isinstance(path, (str, bytes)):
                return
            write = isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            resolved = os.path.realpath(os.fsdecode(path))
            if resolved.startswith(allowed_prefixes) or '__pycache__' in resolved:
                return
            if write:
                self.blocked_writes.append(resolved)
                raise PermissionError('QA-стенд: запись вне песочницы запрещена: ' + resolved)
            if production_store(resolved):
                # Reading production state makes a journey depend on live data
                # and can leak it into evidence: the stand must see only its own.
                self.blocked_writes.append('read:' + resolved)
                raise PermissionError('QA-стенд: чтение рабочего хранилища запрещено: ' + resolved)
        _install_audit(audit)

        patches = [
            patch.multiple(bridge, RUNTIME_ACTIVE=False, UI_CONTEXT=None, MANAGER_CHAT_ID=None,
                           INSTALLER_NOTIFY_CHAT_ID=None, BASE_DIR=str(state), **paths),
            patch.object(bridge, 'os', child_os),
            patch.object(bridge, 'time', quick_time),
            patch.object(bridge.subprocess, 'run', self.subprocess_run),
            patch.object(bridge, 'load_env', return_value={'TELEGRAM_BOT_TOKEN': 'qa', 'TELEGRAM_CHAT_ID': self.owner_chat}),
            patch.object(bridge, 'tg_api', side_effect=lambda *a, **k: (deadline_guard(), self.telegram.api(*a, **k))[1]),
            patch.object(bridge, 'download_telegram_document', side_effect=self.download_document),
            patch.object(bridge, 'get_offset', return_value=0), patch.object(bridge, 'save_offset'),
            patch.object(bridge, 'run_background_job', side_effect=background),
            patch.object(bridge, 'run_foreground', side_effect=foreground),
            # Periodic watchers are out of scope: a person's journey is the input.
            patch.object(bridge, 'run_singleton_background_job'),
            patch.object(bridge, 'show_qa_findings'),
            patch.object(bridge.periodic_schedule, 'claim', return_value=False),
            patch.object(bridge.periodic_schedule, 'claim_daily', return_value=False),
            patch.object(bridge.socket, 'create_connection',
                         side_effect=lambda *a, **k: _Connection() if self.crm.reachable else (_ for _ in ()).throw(OSError('down'))),
            patch.object(installer_onboarding, 'members', return_value=set()),
            patch.object(invoice_tasks, 'STORE', state / 'invoice_tasks.json'),
            patch.object(decision_channel, 'BASE', state),
            # Default arguments in statement_document_context capture the
            # production FINANCE path at import time. Route every entry point
            # explicitly to the stand, including read-only greeting context.
            patch.object(statement_document_context, 'recent_context',
                         side_effect=lambda chat_id: statement_recent_context(chat_id, finance_state)),
            patch.object(statement_document_context, 'deal_candidates',
                         side_effect=lambda caption: statement_deal_candidates(caption, finance_state)),
            patch.object(statement_document_context, 'match_document',
                         side_effect=lambda path, text, chat_id: statement_match_document(
                             path, text, chat_id, finance_state)),
            patch.object(statement_document_context, 'exclude_documents',
                         side_effect=lambda chat_id, hashes: statement_exclude_documents(
                             chat_id, hashes, finance_state)),
        ]
        for item in patches:
            item.start()
        try:
            bridge.DEAL_LEDGER_CACHE.clear()
            bridge.main()
        except JourneyStop:
            pass
        except SimulatedCrash:
            # The person did nothing wrong; the next part of the journey starts
            # after the restart and sees whatever the bot recovered.
            self.finished = True
        except AssertionError as exc:
            self.failure = self.failure or exc
        finally:
            guard_state['on'] = False
            for item in reversed(patches):
                item.stop()
        return self

    def receipt(self):
        tester = [e for e in self.telegram.events if e['actor'] == 'tester']
        return {'transcript': [{'actor': e['actor'], 'kind': e['kind'], 'text': e.get('text') or e.get('filename') or ''}
                               for e in self.telegram.events
                               if e['actor'] in ('tester', 'system') or e.get('chat') == self.owner_chat],
                'observations': self.operator.observations, 'actions': len(tester),
                'crm_writes': self.crm.writes, 'unexpected_external': self.unexpected,
                'blocked_writes': self.blocked_writes, 'model_prompts': len(self.model.prompts),
                'failure': str(self.failure) if self.failure else None}

    def close(self):
        self.temporary.cleanup()


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# Server-local runtime state and business stores (see .gitignore).  Code,
# templates and versioned configuration stay readable.
PRODUCTION_STORE_RE = re.compile(
    r'(?:\.sqlite3?|\.sqlite-\w+|_state\.json|_registry\.json|_cache\.json|\.jsonl|/\.env'
    r'|/(?:model_failures|invoice_tasks|watcher_schedule|document_jobs|deal_ui_state|pending_deal_transitions'
    r'|procurement_status_watch|installer_settlements|installer_approved_reports|user_rules|token)\.json'
    r'|/offset\.txt|/session_id[^/]*\.txt|/developer_session_id\.txt)$'
    r'|/(?:incoming|inbox|archive|output|reports|human-fixtures|qa-agent-evidence)/')


def production_store(path):
    return bool(PRODUCTION_STORE_RE.search(path))


_AUDIT = []


def _install_audit(hook):
    """sys.addaudithook cannot be removed; one dispatcher serves every stand."""
    if not _AUDIT:
        sys.addaudithook(lambda event, args: _AUDIT[-1](event, args) if _AUDIT else None)
    _AUDIT.append(hook)


class HumanJourneyCase:
    """Mixin for unittest cases: exposes transcript/observations to offline_tests."""

    def play(self, journey, model_rules=(), setup=None, timeout=60):
        """``journey`` may be a list: the bot is restarted between its parts."""
        stand = Stand(model_rules)
        self.addCleanup(stand.close)
        if setup:
            setup(stand.crm)
        for part in (journey if isinstance(journey, (list, tuple)) else [journey]):
            stand.run(part, timeout=timeout)
            if stand.failure or not stand.finished:
                break
        receipt = stand.receipt()
        self.qa_transcript = receipt['transcript']
        self.qa_observations = receipt['observations']
        self.qa_receipt = receipt
        if stand.failure:
            raise AssertionError(str(stand.failure) + '\n\n' + render_transcript(receipt)
                                 + ('\n\nВнешние вызовы без двойника: ' + '; '.join(stand.unexpected)
                                    if stand.unexpected else ''))
        if stand.blocked_writes:
            raise AssertionError('Бот обращался к рабочим хранилищам вне песочницы: ' + ', '.join(stand.blocked_writes[:5]))
        if not stand.finished:
            raise AssertionError('Бот завершил работу раньше, чем человек закончил сценарий.\n\n' + render_transcript(receipt))
        return stand


def render_transcript(receipt):
    lines = []
    for event in receipt['transcript']:
        if event['actor'] == 'system':
            lines.append(event['text'])
            continue
        who = 'Человек' if event['actor'] == 'tester' else 'Бот'
        verb = {'button': 'нажал', 'file': 'прислал файл', 'document': 'прислал файл'}.get(event['kind'], 'написал')
        lines.append(f"{who} {verb}: {event['text'][:400]}")
    return '\n'.join(lines)
