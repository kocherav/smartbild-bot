"""Atomic legacy-state adapter with per-message snapshots and stale-worker guard."""
from contextlib import contextmanager
import copy
from dataclasses import dataclass
import fcntl
import json
import os
import uuid
from pathlib import Path


@dataclass
class Context:
    actor: str
    update_id: str
    revision: int
    state: dict
    confirmed_control: bool = False


class StateStore:
    def __init__(self, path, lock):
        self.path, self.lock = Path(path), Path(lock)

    def read_all(self):
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return {}
        if not isinstance(value, dict):
            raise ValueError('Invalid dialog state; automatic reset is forbidden')
        return value

    @contextmanager
    def transaction(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock.open('a') as lock:
            os.chmod(self.lock, 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def save(self, value):
        temporary = self.path.with_name(self.path.name + f'.{os.getpid()}.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as target:
            json.dump(value, target, ensure_ascii=False, indent=2, allow_nan=False)
            target.flush(); os.fsync(target.fileno())
        os.replace(temporary, self.path)

    def bind(self, actor, update_id):
        actor, update_id = str(actor), str(update_id)
        with self.transaction():
            all_state = self.read_all()
            state = all_state.setdefault(actor, {})
            if state.get('_last_update_id') == update_id:
                return None
            state['_revision'] = int(state.get('_revision') or 0) + 1
            state['_last_update_id'] = update_id
            self.save(all_state)
            return Context(actor, update_id, state['_revision'], copy.deepcopy(state))

    def current(self, actor, context=None):
        if context is not None and context.actor == str(actor):
            return copy.deepcopy(context.state)
        return self.read_all().get(str(actor), {})

    def fresh(self, context):
        if context is None:
            return True
        actual = self.read_all().get(context.actor, {})
        return int(actual.get('_revision') or 0) == context.revision

    def begin_idle(self,actor,expected_revision,values):
        """Claim an unsolicited dialog only if no input/workflow intervened."""
        actor=str(actor)
        with self.transaction():
            all_state=self.read_all();state=all_state.setdefault(actor,{})
            if int(state.get('_revision') or 0)!=int(expected_revision or 0):return None
            if state.get('pending') or state.get('deal_creation_active'):return None
            for key,value in values.items():
                if key.startswith('_'):raise ValueError('Reserved dialog metadata')
                if value is None:state.pop(key,None)
                else:state[key]=value
            if 'confirm' in str(values.get('pending') or ''):state['_confirmation_id']=uuid.uuid4().hex
            state['_revision']=int(state.get('_revision') or 0)+1
            self.save(all_state)
            return Context(actor,'background:'+uuid.uuid4().hex,state['_revision'],copy.deepcopy(state))

    def update(self, actor, values, context=None):
        actor = str(actor)
        with self.transaction():
            all_state = self.read_all()
            state = all_state.setdefault(actor, {})
            bound = context is not None and context.actor == actor
            if bound and int(state.get('_revision') or 0) != context.revision:
                return False, copy.deepcopy(state)
            for key, value in values.items():
                if key.startswith('_revision') or key == '_last_update_id':
                    raise ValueError('Reserved dialog metadata')
                if value is None:
                    state.pop(key, None)
                else:
                    state[key] = value
            # A persisted preview identity survives retries and is not derived
            # from the latest Telegram message or current wall-clock second.
            pending = str(values.get('pending') or '')
            if pending and ('confirm' in pending or pending in ('installation_ready_to_transfer', 'installation_report_review')):
                if not state.get('_confirmation_id') or (bound and context.state.get('pending') != pending):
                    state['_confirmation_id'] = uuid.uuid4().hex
            state['_revision'] = int(state.get('_revision') or 0) + 1
            self.save(all_state)
            if bound:
                context.revision = state['_revision']
                context.state = copy.deepcopy(state)
            return True, copy.deepcopy(state)

    def invoice_queue(self, actor, spec, remove=False, context=None):
        """Queue completion is durable even when its original screen is stale."""
        actor = str(actor)
        fingerprint = json.dumps(spec, sort_keys=True, ensure_ascii=False, allow_nan=False)
        with self.transaction():
            all_state = self.read_all()
            state = all_state.setdefault(actor, {})
            queue = list(state.get('supplier_invoice_queue') or [])
            index = next((i for i, x in enumerate(queue) if json.dumps(x, sort_keys=True, ensure_ascii=False, allow_nan=False) == fingerprint), None)
            if remove and index is not None:
                queue.pop(index)
            elif not remove and index is None:
                queue.append(copy.deepcopy(spec))
            state['supplier_invoice_queue'] = queue
            bound = context is not None and context.actor == actor
            fresh = not bound or context.revision == int(state.get('_revision') or 0)
            if fresh:
                if queue:
                    state['supplier_invoice_preview'] = queue[0]
                    state['pending'] = 'supplier_invoice_confirm'
                    state['current_deal_id'] = str(queue[0].get('deal_id') or state.get('current_deal_id') or '')
                else:
                    state.pop('supplier_invoice_preview', None)
                    state['pending'] = 'procurement_menu'
                state['_confirmation_id'] = uuid.uuid4().hex
                state['_revision'] = int(state.get('_revision') or 0) + 1
                if bound:
                    context.revision = state['_revision']
                    context.state = copy.deepcopy(state)
            self.save(all_state)
            return copy.deepcopy(queue)
