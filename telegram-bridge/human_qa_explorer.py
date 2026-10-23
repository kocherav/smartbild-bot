"""AI exploratory tester: a language model plays the manager on the QA stand.

Scripted journeys check what we already thought of.  The explorer finds what
we did not: it receives a business goal in ordinary words, sees only what a
person sees in Telegram (messages, files, buttons), decides what to type or
press, and finally a judge reviews the whole conversation together with the
CRM writes that actually happened.

Everything runs on the QA stand: bridge.main() is real, Megaplan is the
in-memory double (optionally filled from a read-only CRM snapshot), so no
business data is changed whatever the model does.  By default the bot's own
model is the real Codex (read-only, fresh thread), because the explorer must
exercise the real dialogue, not a script.

    python human_qa_explorer.py --output DIR [--missions N] [--seed TEXT] [--scripted-bot]

The receipt has the offline_tests format, so qa_agent.py records findings as
QA tasks (profile ``explore``).  Findings need the owner's review before any
developer work: a model's judgement is evidence, not proof.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import human_fixtures
import qa_schedule
from human_qa_harness import Stand, codex_jsonl, press, say, render_transcript, _REAL_RUN
from test_human_journeys import office


ROOT = Path(__file__).resolve().parent
_MISSIONS_RELATIVE = Path('docs') / 'architecture' / 'EXPLORE_MISSIONS.json'
# The isolated runner copies only sources; the mission list is then read in place.
MISSIONS_FILE = next((path for path in (
    Path(os.environ['QA_EXPLORE_MISSIONS_FILE']) if os.environ.get('QA_EXPLORE_MISSIONS_FILE') else None,
    ROOT / _MISSIONS_RELATIVE,
    Path(os.environ.get('SMARTBILD_HOME', '/home/kocher.av')) / 'telegram-bridge' / _MISSIONS_RELATIVE,
) if path and path.exists()), ROOT / _MISSIONS_RELATIVE)
CODEX_BIN = os.environ.get('BRIDGE_CODEX_BIN', os.path.expanduser('~/.local/bin/codex'))
MAX_SCREEN_CHARS = 3500

ACTOR_RULES = """Ты — тестировщик, который играет роль менеджера компании SmartBild (климатическое
оборудование и монтаж). Ты общаешься с рабочим Telegram-ботом компании, как обычный человек.
Ты видишь только то, что видно в Telegram: сообщения бота, присланные файлы и кнопки.
Можно: написать сообщение (say) или нажать ОДНУ из видимых кнопок (press) — точный текст кнопки.
Нельзя: нажимать кнопки, которых нет в списке; придумывать номера сделок, которых нет в задании;
подсказывать боту внутренние команды. Если бот запутался — веди себя как живой человек:
переформулируй, вернись в меню, попробуй кнопки. Когда цель достигнута или стало ясно, что бот
не может её выполнить (3–4 безуспешные попытки), заверши (finish).
Ответь ТОЛЬКО JSON без пояснений: {"action": "say"|"press"|"finish", "value": "текст", "thought": "зачем"}"""

JUDGE_RULES = """Ты — строгий QA-инженер. Оцени разговор менеджера с рабочим ботом SmartBild.
Тебе дана цель менеджера, критерии успеха, полный диалог и список записей, которые бот реально
сделал в CRM (это единственный источник правды о записи: слова бота «сделано» без записи — ложь).
Найди дефекты: цель не достигнута; бот сделал не ту запись или две записи вместо одной;
бот заявил успех без записи; бот потерял контекст; непонятный или технический текст;
человек был вынужден угадывать; бот не предложил следующий шаг; неверные суммы/количества/формат денег;
лишние вопросы; молчание бота. Не придумывай требования, которых нет в цели и критериях.
Налоговый режим, рассчитанный по действующей политике продавца и показанный в предпросмотре до
подтверждения, не является самовольным условием пользователя. Не считай дефектом то, что требует бизнес-решения владельца.
Кроме дефектов ты — изобретатель и оптимизатор: не стесняйся предлагать улучшения функционала,
которые реально помогли бы менеджеру в этом разговоре: сократить число шагов и нажатий, убрать
лишний вопрос, предложить следующий шаг заранее, объединить действия, автоматизировать рутину,
сделать ответ понятнее. Только конкретно и с опорой на увиденное в диалоге (какой шаг, сколько
нажатий сейчас и сколько могло бы быть); не повторяй дефекты; не больше трёх идей.
Ответь ТОЛЬКО JSON: {"achieved": true|false,
 "defects": [{"severity": "P1"|"P2"|"P3", "title": "кратко", "evidence": "цитата/шаг", "expected": "как должно быть"}],
 "ideas": [{"title": "суть улучшения", "why": "что мешало в диалоге", "how": "как сделать", "value": "высокая"|"средняя"|"низкая"}],
 "summary": "одна-две фразы"}
P1 — неверная или ложная запись денег/данных, потеря данных; P2 — цель не достигается обычным путём;
P3 — неудобство, неточность текста."""


# ---------------------------------------------------------------------------
# Brains


class CodexBrain:
    """Fresh, read-only Codex turn per decision; the same CLI the bot already uses."""

    def __init__(self, binary=CODEX_BIN, timeout=180):
        self.binary, self.timeout = binary, timeout
        self.calls = 0

    def __call__(self, prompt):
        self.calls += 1
        command = [self.binary, 'exec', '--json', '--ignore-user-config', '--ignore-rules',
                   '--ephemeral', '--skip-git-repo-check', '--sandbox', 'read-only',
                   '--cd', os.path.expanduser('~'), '-c', 'features.shell_tool=false',
                   '-c', 'web_search="disabled"', '-']
        completed = _REAL_RUN(command, input=prompt, capture_output=True, text=True, timeout=self.timeout)
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
            raise RuntimeError('Codex не вернул ответ: ' + (completed.stderr or '')[-300:])
        return messages[-1]


class CommandBrain:
    """Any command that reads a prompt on stdin and prints the answer (QA_EXPLORER_BRAIN_CMD)."""

    def __init__(self, command):
        self.command = command

    def __call__(self, prompt):
        completed = _REAL_RUN(self.command, input=prompt, capture_output=True, text=True, timeout=300, shell=True)
        return completed.stdout


def parse_json(text):
    match = re.search(r'\{.*\}', text or '', re.S)
    if not match:
        raise ValueError('ответ модели не содержит JSON')
    return json.loads(match.group(0))


# ---------------------------------------------------------------------------
# Missions


def load_missions(path=MISSIONS_FILE):
    return json.loads(Path(path).read_text(encoding='utf-8'))['missions']


def choose(missions, count, seed):
    """A stable rotation: every mission is explored within a few nights."""
    ordered = sorted(missions, key=lambda m: hashlib.sha256((seed + m['id']).encode()).hexdigest())
    return ordered[:count] if count else ordered


def screen_for_actor(person):
    lines = []
    for event in person.telegram.screen:
        if event['kind'] == 'document':
            lines.append(f"[Бот прислал файл «{event['filename']}»: {event.get('text') or ''}]")
        else:
            lines.append('Бот: ' + (event.get('text') or ''))
    text = '\n'.join(lines) or '(бот ничего не ответил)'
    return text[-MAX_SCREEN_CHARS:]


def explore(mission, brain, stand, max_steps=16):
    """Let the model operate the bot; returns the decision log."""
    decisions = []

    def journey(person):
        history = []
        for step in range(int(mission.get('max_steps') or max_steps)):
            buttons = person.visible_buttons()
            prompt = (ACTOR_RULES + '\n\nТВОЯ ЦЕЛЬ:\n' + mission['goal'] +
                      ('\n\nТВОЙ СТИЛЬ ОБЩЕНИЯ: ' + mission['persona'] if mission.get('persona') else '') +
                      '\n\nЧТО УЖЕ БЫЛО (кратко):\n' + ('\n'.join(history[-12:]) or 'ничего') +
                      '\n\nСЕЙЧАС НА ЭКРАНЕ:\n' + screen_for_actor(person) +
                      '\n\nВИДИМЫЕ КНОПКИ:\n' + ('\n'.join('• ' + b for b in buttons) or 'нет') +
                      f'\n\nШаг {step + 1}. Твоё действие (JSON):')
            try:
                decision = parse_json(brain(prompt))
            except Exception as exc:  # a broken model answer ends this mission, it is not a bot defect
                decisions.append({'step': step + 1, 'error': f'{type(exc).__name__}: {exc}'})
                return
            action, value = decision.get('action'), str(decision.get('value') or '').strip()
            if action == 'press' and value not in buttons:
                decisions.append({'step': step + 1, 'invalid': decision})
                history.append(f'(ты попытался нажать несуществующую кнопку «{value}»)')
                continue
            decisions.append({'step': step + 1, **decision})
            if action == 'finish' or not value:
                return
            history.append(('Ты нажал: ' if action == 'press' else 'Ты написал: ') + value)
            yield press(value) if action == 'press' else say(value)

    stand.run(journey, timeout=int(mission.get('timeout') or 900))
    return decisions


def judge(mission, receipt, brain):
    writes = [{'где': w['script'], 'действие': w['action'],
               'данные': (w.get('spec') or {})}
              for w in receipt['crm_writes']]
    prompt = (JUDGE_RULES + '\n\nЦЕЛЬ МЕНЕДЖЕРА:\n' + mission['goal'] +
              '\n\nКРИТЕРИИ УСПЕХА:\n' + '\n'.join('- ' + c for c in mission.get('success') or []) +
              '\n\nДИАЛОГ:\n' + render_transcript(receipt)[-12000:] +
              '\n\nЗАПИСИ В CRM (факт):\n' + json.dumps(writes, ensure_ascii=False)[:4000] +
              ('\n\nСБОЙ СТЕНДА: ' + receipt['failure'] if receipt.get('failure') else '') +
              '\n\nТвоя оценка (JSON):')
    return parse_json(brain(prompt))


def case_from(mission, receipt, verdict, decisions):
    observations = [{'expected': 'Цель достигнута: ' + mission['goal'][:200],
                     'actual': verdict.get('summary') or '', 'verdict': 'passed' if verdict.get('achieved') else 'failed'}]
    for defect in verdict.get('defects') or []:
        observations.append({'expected': f"[{defect.get('severity', 'P3')}] {defect.get('expected') or ''}",
                             'actual': f"{defect.get('title')}: {defect.get('evidence') or ''}", 'verdict': 'failed'})
    serious = [d for d in verdict.get('defects') or [] if d.get('severity') in ('P1', 'P2')]
    passed = bool(verdict.get('achieved')) and not serious
    ranked = sorted(serious, key=lambda d: d.get('severity'))
    title = (ranked[0].get('title') if ranked else None) or ('Цель не достигнута' if not verdict.get('achieved') else None)
    return {'id': 'explore:' + mission['id'], 'status': 'passed' if passed else 'failed',
            'severity': ranked[0]['severity'] if ranked else 'P2', 'title': title,
            'transcript': receipt['transcript'], 'observations': observations,
            'crm_writes': receipt['crm_writes'], 'decisions': decisions,
            'unexpected_external': receipt['unexpected_external'], 'judge': verdict,
            # Improvement ideas are proposals for the owner, never a failure.
            'ideas': [{**idea, 'mission': mission['id']} for idea in (verdict.get('ideas') or [])[:3]
                      if isinstance(idea, dict) and idea.get('title')]}


def fixture_from(snapshot_registry):
    if snapshot_registry:
        snapshot, problem = human_fixtures.verified_snapshot(snapshot_registry)
        if snapshot and not problem:
            return lambda crm: (office(crm), human_fixtures.load(crm, snapshot))
    return office


def live_model_stand(stand):
    """Route the bot's own model to the real Codex instead of the script."""
    original = stand.subprocess_run

    def run(cmd, *args, input=None, **kwargs):
        import bridge
        argv = [str(x) for x in (cmd if isinstance(cmd, (list, tuple)) else [cmd])]
        if argv and argv[0] == bridge.CODEX_BIN:
            stand.model.prompts.append(input or '')
            return _REAL_RUN(cmd, *args, input=input, **kwargs)
        return original(cmd, *args, input=input, **kwargs)
    stand.subprocess_run = run
    return stand


def main(argv=None):
    parser = argparse.ArgumentParser(description='AI-исследователь бота SmartBild')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--missions', type=int, default=None, help='сколько миссий (иначе по QA_SCHEDULE.json)')
    parser.add_argument('--seed', default=qa_schedule.moscow().date().isoformat())
    parser.add_argument('--mission', action='append', help='только указанные миссии')
    parser.add_argument('--scripted-bot', action='store_true', help='не вызывать реальную модель бота')
    parser.add_argument('--registry', default=os.environ.get('QA_HUMAN_REGISTRY'))
    args = parser.parse_args(argv)
    if args.missions is None and os.environ.get('QA_EXPLORE_MISSIONS'):
        args.missions = int(os.environ['QA_EXPLORE_MISSIONS'])
    args.missions_explicit = args.missions is not None
    command = os.environ.get('QA_EXPLORER_BRAIN_CMD')
    brain = CommandBrain(command) if command else CodexBrain()
    missions = load_missions()
    if args.mission:
        selected = [m for m in missions if m['id'] in args.mission]
    elif args.missions_explicit:
        selected = choose(missions, args.missions, args.seed)
    else:
        # The approved weekly plan picks tonight's theme (QA_SCHEDULE.json).
        selected = qa_schedule.missions_for(dt.date.fromisoformat(args.seed), missions)
    setup = fixture_from(args.registry)
    cases = []
    started = dt.datetime.now(dt.timezone.utc)
    for mission in selected:
        stand = Stand(mission.get('bot_model_rules') or ())
        try:
            setup(stand.crm)
            if not args.scripted_bot:
                live_model_stand(stand)
            decisions = explore(mission, brain, stand)
            receipt = stand.receipt()
            if stand.blocked_writes:
                cases.append({'id': 'isolation:explore:' + mission['id'], 'status': 'failed',
                              'transcript': receipt['transcript'], 'observations': [], 'blocked': stand.blocked_writes})
                continue
            try:
                verdict = judge(mission, receipt, brain)
            except Exception as exc:
                cases.append({'id': 'infra:explore-judge:' + mission['id'], 'status': 'blocked',
                              'transcript': receipt['transcript'], 'observations': [],
                              'reason': f'{type(exc).__name__}: {exc}'})
                continue
            cases.append(case_from(mission, receipt, verdict, decisions))
        finally:
            stand.close()
    report = {'ran_at': started.isoformat(), 'profile': 'explore', 'tests': len(cases),
              'successful': all(c['status'] == 'passed' for c in cases) and bool(cases),
              'cases': cases, 'brain_calls': getattr(brain, 'calls', None),
              'missions': [m['id'] for m in selected],
              'ideas': [idea for case in cases for idea in case.get('ideas') or []],
              'theme': qa_schedule.focus(dt.date.fromisoformat(args.seed)).get('theme')}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'LAST_TEST_RUN.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('ran_at', 'tests', 'successful', 'missions')}, ensure_ascii=False))
    return 0 if report['successful'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
