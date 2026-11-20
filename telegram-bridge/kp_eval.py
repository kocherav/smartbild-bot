"""Read-only, isolated evaluation of KP requests through the real bridge.

The bot model and ``bridge.main`` are real.  Telegram and Megaplan are the
human QA doubles; only the Hogart/Daichi search CLIs and the local KP generator
are allowed through the process boundary.  Every other external call fails.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import tempfile
import time
from unittest.mock import patch

from human_qa_explorer import CODEX_BIN, parse_json
from human_qa_harness import Stand, _REAL_RUN, render_transcript, say


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
CORPUS = ROOT / 'docs' / 'architecture' / 'KP_REQUEST_CORPUS.json'
HOGART = Path(os.environ.get('KP_EVAL_HOGART_DIR', '/home/kocher.av/hogart-scraper'))
DAICHI = Path(os.environ.get('KP_EVAL_DAICHI_DIR', '/home/kocher.av/daichi-scraper'))
ACTOR = """Ты играешь клиента в проверке КП. Ответь ТОЛЬКО JSON
{"action":"say"|"finish","value":"..."}. Если бот задал вопрос, отвечай только
фактами ниже; если ответа в фактах нет — «на ваше усмотрение». Если вопроса нет,
заверши. Не проси создать сделку и не нажимай кнопки."""

JUDGE = """Ты строгий судья КП. Получаешь полный диалог без обрезки, все BUILD_KP,
результаты поисков и факты изоляции. Для КАЖДОГО переданного критерия верни pass/fail
и короткое объяснение. Не додумывай данные каталога. Ответь ТОЛЬКО JSON:
{"checks":[{"id":"G1","pass":true,"explanation":"..."}]}"""


def load_cases(path=CORPUS):
    return json.loads(Path(path).read_text(encoding='utf-8'))['requests']


def select_cases(cases, only=None, limit=None, seed=''):
    selected = [case for case in cases if not only or case['id'] in only]
    selected.sort(key=lambda case: hashlib.sha256((str(seed) + case['id']).encode()).hexdigest())
    return selected[:limit] if limit is not None else selected


def judge_checks(case):
    general = json.loads(CORPUS.read_text(encoding='utf-8'))['general']
    checks = []
    for value in general:
        key, _, text = value.partition(':')
        if key == 'G5' and case.get('tiers', True) is False:
            continue
        checks.append({'id': key, 'text': text.strip()})
    checks.extend({'id': f'check-{index}', 'text': text}
                  for index, text in enumerate(case.get('checks') or [], 1))
    return checks


def isolation_failures(receipt, scenario_chat):
    failures = []
    if receipt.get('crm_writes'):
        failures.append('Запрещённая запись в CRM')
    if receipt.get('blocked_writes'):
        failures.append('Запись вне временного evidence: ' + ', '.join(receipt['blocked_writes'][:3]))
    if receipt.get('unexpected_external'):
        failures.append('Неизолированный внешний вызов: ' + ', '.join(receipt['unexpected_external'][:3]))
    outsiders = sorted({str(chat) for chat in receipt.get('telegram_chats') or []
                        if str(chat) != str(scenario_chat)})
    if outsiders:
        failures.append('Попытка отправки Telegram людям: ' + ', '.join(outsiders))
    return failures


class KPEvalStand(Stand):
    """QA stand which admits exactly two read-only searches and KP generation."""

    def __init__(self, evidence, owner_chat):
        super().__init__(owner_chat=owner_chat)
        self.evidence = Path(evidence)
        self.searches = []
        self.build_specs = []

    def subprocess_run(self, cmd, *args, input=None, **kwargs):
        argv = [str(item) for item in (cmd if isinstance(cmd, (list, tuple)) else [cmd])]
        script = next((Path(item).name for item in argv if item.endswith('.py')), '')
        if script in ('hogart_api.py', 'daichi_search.py'):
            completed = _REAL_RUN(cmd, *args, input=input, **kwargs)
            self.searches.append({'source': 'hogart' if script == 'hogart_api.py' else 'daichi',
                                  'request': argv, 'returncode': completed.returncode,
                                  'stdout': completed.stdout or '', 'stderr': completed.stderr or ''})
            return completed
        if script == 'generate_kp.py':
            try:
                spec_path = Path(argv[-1])
                spec = json.loads(spec_path.read_text(encoding='utf-8'))
                self.evidence.mkdir(parents=True, exist_ok=True)
                spec['output'] = str((self.evidence / f'kp-{len(self.build_specs) + 1}.pdf').resolve())
                spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding='utf-8')
                self.build_specs.append(spec)
            except Exception as exc:
                self.build_specs.append({'capture_error': f'{type(exc).__name__}: {exc}'})
            completed = _REAL_RUN(cmd, *args, input=input, **kwargs)
            return completed
        return super().subprocess_run(cmd, *args, input=input, **kwargs)

    def receipt(self):
        value = super().receipt()
        value['telegram_chats'] = sorted({str(event.get('chat')) for event in self.telegram.events
                                           if event.get('actor') == 'bot' and event.get('chat') is not None})
        return value


class EvalBrain:
    """Ephemeral model turn with no tools and a writable evidence workspace."""

    def __init__(self, workdir, codex_home, binary=CODEX_BIN, timeout=180):
        self.workdir, self.codex_home = str(workdir), str(codex_home)
        self.binary, self.timeout = binary, timeout

    def __call__(self, prompt):
        command = [self.binary, 'exec', '--json', '--ignore-user-config', '--ignore-rules',
                   '--ephemeral', '--skip-git-repo-check', '--sandbox', 'workspace-write',
                   '--cd', self.workdir, '-c', 'features.shell_tool=false',
                   '-c', 'web_search="disabled"', '-']
        env = {**os.environ, 'CODEX_HOME': self.codex_home}
        completed = _REAL_RUN(command, input=prompt, capture_output=True, text=True,
                              timeout=self.timeout, env=env)
        messages = []
        for line in (completed.stdout or '').splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            item = event.get('item') or {}
            if event.get('type') == 'item.completed' and item.get('type') == 'agent_message':
                messages.append(item.get('text') or '')
        if not messages:
            raise RuntimeError('Codex не вернул ответ: ' + (completed.stderr or '')[-500:])
        return messages[-1]


def live_model_stand(stand):
    """Run the bridge model in the writable stand root; model tools stay sandboxed."""
    original = stand.subprocess_run
    codex_home = stand.root / '.codex'
    prepare_codex_home(codex_home)

    def run(cmd, *args, input=None, **kwargs):
        import bridge
        argv = [str(item) for item in (cmd if isinstance(cmd, (list, tuple)) else [cmd])]
        if argv and argv[0] == bridge.CODEX_BIN:
            argv = list(argv)
            argv = ['workspace-write' if item == 'read-only' else item for item in argv]
            if '--cd' in argv:
                argv[argv.index('--cd') + 1] = str(stand.root)
            kwargs['cwd'] = str(stand.root)
            kwargs['env'] = {**os.environ, 'CODEX_HOME': str(codex_home)}
            return _REAL_RUN(argv, *args, input=input, **kwargs)
        return original(cmd, *args, input=input, **kwargs)
    stand.subprocess_run = run
    return stand


def prepare_codex_home(target):
    """Copy only runtime credentials/config to an auto-cleaned temporary home."""
    source = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex'))
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    for name in ('auth.json', 'config.toml', 'installation_id', 'models_cache.json'):
        path = source / name
        if path.is_file():
            shutil.copy2(path, target / name)


def _facts_text(case):
    return json.dumps(case.get('facts') or {}, ensure_ascii=False, indent=2)


def run_dialog(case, stand, brain, max_turns=8, timeout=900):
    followups = list(case.get('followups') or [])
    decisions = []

    def journey(person):
        yield say(case['text'])
        for turn in range(1, max_turns):
            if followups:
                value = followups.pop(0)
                decisions.append({'turn': turn + 1, 'source': 'followup', 'value': value})
                yield say(value)
                continue
            screen = '\n'.join(event.get('text') or '' for event in person.telegram.screen)
            prompt = (ACTOR + '\n\nФАКТЫ:\n' + _facts_text(case) +
                      '\n\nПОСЛЕДНИЙ ОТВЕТ БОТА:\n' + (screen or '(нет ответа)'))
            decision = parse_json(brain(prompt))
            decisions.append({'turn': turn + 1, 'source': 'actor', **decision})
            if decision.get('action') != 'say' or not str(decision.get('value') or '').strip():
                return
            yield say(str(decision['value']).strip())

    import bridge
    with patch.object(bridge, 'HOGART_DIR', str(HOGART)), patch.object(bridge, 'DAICHI_DIR', str(DAICHI)):
        stand.run(journey, timeout=timeout)
    return decisions


def judge(case, receipt, searches, build_specs, brain, isolation):
    criteria = judge_checks(case)
    prompt = (JUDGE + '\n\nКРИТЕРИИ:\n' + json.dumps(criteria, ensure_ascii=False) +
              '\n\nДИАЛОГ:\n' + render_transcript(receipt, message_limit=None) +
              '\n\nBUILD_KP:\n' + json.dumps(build_specs, ensure_ascii=False) +
              '\n\nПОИСКИ:\n' + json.dumps(searches, ensure_ascii=False) +
              '\n\nИЗОЛЯЦИЯ:\n' + json.dumps(isolation, ensure_ascii=False))
    result = parse_json(brain(prompt))
    returned = {str(item.get('id')): item for item in result.get('checks') or []}
    normalized = []
    for criterion in criteria:
        item = returned.get(criterion['id']) or {}
        normalized.append({'id': criterion['id'], 'text': criterion['text'],
                           'pass': bool(item.get('pass')),
                           'explanation': str(item.get('explanation') or 'Судья не вернул оценку')})
    return normalized


def _copy_documents(stand, case_dir):
    copied = []
    for event in stand.telegram.events:
        if event.get('actor') != 'bot' or event.get('kind') != 'document':
            continue
        source = Path(event.get('path') or '')
        if source.is_file() and source.suffix.lower() in ('.pdf', '.xlsx'):
            target = case_dir / source.name
            if source.resolve() != target.resolve():
                shutil.copy2(source, target)
            copied.append(target.name)
    return copied


def write_case_evidence(case_dir, receipt, searches, specs):
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / 'transcript.md').write_text(render_transcript(receipt, message_limit=None), encoding='utf-8')
    (case_dir / 'build_kp.json').write_text(json.dumps(specs, ensure_ascii=False, indent=2), encoding='utf-8')
    (case_dir / 'searches.json').write_text(json.dumps(searches, ensure_ascii=False, indent=2), encoding='utf-8')


def build_summary(cases):
    passed = sum(bool(case.get('success')) for case in cases)
    total = len(cases)
    return {'total': total, 'passed': passed,
            'success_pct': round(100 * passed / total, 2) if total else 0.0,
            'cases': cases}


def write_summary(output, summary):
    output = Path(output)
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = [f"# KP eval: {summary['passed']}/{summary['total']} ({summary['success_pct']:.2f}%)", '',
             '| id | успех | проваленные пункты | ходов | время, с |',
             '|---|---:|---|---:|---:|']
    for case in summary['cases']:
        failed = ', '.join(case.get('failed_checks') or []) or '—'
        lines.append(f"| {case['id']} | {'да' if case.get('success') else 'нет'} | {failed} | "
                     f"{case.get('turns', 0)} | {case.get('duration_sec', 0):.1f} |")
    (output / 'summary.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Изолированный прогон КП через настоящий bridge.py')
    parser.add_argument('--only', help='id через запятую')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--seed', default='')
    parser.add_argument('--timeout', type=int, default=900)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    only = {item.strip() for item in (args.only or '').split(',') if item.strip()}
    selected = select_cases(load_cases(), only, args.limit, args.seed)
    if only - {case['id'] for case in selected}:
        parser.error('неизвестные или исключённые --only: ' + ', '.join(sorted(only - {c['id'] for c in selected})))
    stamp = dt.datetime.now().strftime('%Y%m%d-%H%M%S')
    output = args.output or (REPO / 'evidence' / f'{stamp}-kp-eval')
    output.mkdir(parents=True, exist_ok=False)
    results = []
    actor_home_tmp = tempfile.TemporaryDirectory(prefix='kp-eval-codex-')
    prepare_codex_home(actor_home_tmp.name)
    brain = EvalBrain(output, actor_home_tmp.name)
    for index, case in enumerate(selected, 1):
        case_dir = output / case['id']
        chat = f'kp-eval-{stamp}-{index}'
        stand = KPEvalStand(case_dir, chat)
        started = time.monotonic()
        try:
            live_model_stand(stand)
            decisions = run_dialog(case, stand, brain, timeout=args.timeout)
            receipt = stand.receipt()
            isolation = isolation_failures(receipt, chat)
            write_case_evidence(case_dir, receipt, stand.searches, stand.build_specs)
            documents = _copy_documents(stand, case_dir)
            checks = judge(case, receipt, stand.searches, stand.build_specs, brain, isolation)
            if isolation:
                checks.append({'id': 'isolation', 'pass': False, 'explanation': '; '.join(isolation)})
            failed = [item['id'] for item in checks if not item.get('pass')]
            result = {'id': case['id'], 'success': not failed, 'failed_checks': failed,
                      'turns': 1 + len(decisions), 'duration_sec': round(time.monotonic() - started, 2),
                      'checks': checks, 'documents': documents}
        except Exception as exc:
            result = {'id': case['id'], 'success': False, 'failed_checks': ['runner'], 'turns': 0,
                      'duration_sec': round(time.monotonic() - started, 2),
                      'error': f'{type(exc).__name__}: {exc}'}
        finally:
            stand.close()
        results.append(result)
    actor_home_tmp.cleanup()
    summary = build_summary(results)
    write_summary(output, summary)
    print(output)
    return 0 if summary['passed'] == summary['total'] and summary['total'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
