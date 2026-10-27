"""The approved AI-tester schedule (docs/architecture/QA_SCHEDULE.json).

The bridge asks this module *whether* a QA profile is due; it never decides
on its own.  An unreadable or invalid file falls back to the built-in default,
which equals the schedule the bridge used before the file existed.
"""
import datetime as dt
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent
_RELATIVE = Path('docs') / 'architecture' / 'QA_SCHEDULE.json'
PATH = next((p for p in (ROOT / _RELATIVE,
                         Path(os.environ.get('SMARTBILD_HOME', '/home/kocher.av')) / 'telegram-bridge' / _RELATIVE)
             if p.exists()), ROOT / _RELATIVE)
MOSCOW = dt.timezone(dt.timedelta(hours=3))
WEEKDAYS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')
PROFILES = {'full', 'browser', 'human', 'explore'}
DEFAULT = {
    'human': {'every_hours': 4},
    'full': {'daily_at_moscow_hour': 4},
    'night': {'window_moscow_hours': [0, 7], 'sequence': ['full', 'browser', 'human', 'explore']},
    'digest': {'after_moscow': '17:30'},
    'morning_brief': {'weekdays_only': True, 'at_moscow': '09:00', 'invoice_overdue_days': 7,
                      'deal_stale_days': 14, 'completed_statuses': ['заверш', 'закрыт', 'отказ']},
    'explore': {'missions_per_night': 4, 'weekly_focus': {}},
}


def validate(value):
    if not isinstance(value, dict):
        raise ValueError('расписание должно быть объектом')
    hours = float(value['human']['every_hours'])
    if not 1 <= hours <= 24:
        raise ValueError('human.every_hours: от 1 до 24')
    if int(value['full']['daily_at_moscow_hour']) not in range(24):
        raise ValueError('full.daily_at_moscow_hour: 0–23')
    start, end = value['night']['window_moscow_hours']
    if not (0 <= int(start) < int(end) <= 24):
        raise ValueError('night.window_moscow_hours: [начало, конец) в пределах суток')
    sequence = value['night']['sequence']
    if not sequence or set(sequence) - PROFILES or len(set(sequence)) != len(sequence):
        raise ValueError('night.sequence: неизвестный или повторный профиль')
    digest_hour, digest_minute = (int(x) for x in value['digest']['after_moscow'].split(':'))
    if digest_hour not in range(24) or digest_minute not in range(60):
        raise ValueError('digest.after_moscow: ЧЧ:ММ')
    if not 0 <= int(value['explore']['missions_per_night']) <= 20:
        raise ValueError('explore.missions_per_night: 0–20')
    if set(value['explore'].get('weekly_focus') or {}) - set(WEEKDAYS):
        raise ValueError('explore.weekly_focus: дни mon…sun')
    handoff = value.get('handoff')
    if handoff is not None:
        if not 5 <= int(handoff.get('every_minutes', 15)) <= 24 * 60:
            raise ValueError('handoff.every_minutes: от 5 минут до суток')
        if 'release' in (handoff.get('auto_kinds') or []):
            raise ValueError('handoff.auto_kinds: выпуск всегда подтверждает владелец')
    brief = value.get('morning_brief') or DEFAULT['morning_brief']
    brief_hour, brief_minute = (int(x) for x in brief['at_moscow'].split(':'))
    if brief_hour not in range(24) or brief_minute not in range(60):
        raise ValueError('morning_brief.at_moscow: ЧЧ:ММ')
    if not 1 <= int(brief['invoice_overdue_days']) <= 365 or not 1 <= int(brief['deal_stale_days']) <= 365:
        raise ValueError('morning_brief: пороги должны быть от 1 до 365 дней')
    return value


def handoff_config(schedule=None):
    import handoff_watcher
    return {**handoff_watcher.DEFAULT_CONFIG, **((schedule or load()).get('handoff') or {})}


def load(path=None):
    try:
        return validate(json.loads(Path(path or PATH).read_text(encoding='utf-8')))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'[qa_schedule] используется расписание по умолчанию: {exc}')
        return DEFAULT


def moscow(moment=None):
    moment = moment or dt.datetime.now(dt.timezone.utc)
    if moment.tzinfo is None:
        raise ValueError('Расписание QA требует время с часовым поясом')
    return moment.astimezone(MOSCOW)


def human_interval_seconds(schedule=None):
    return int(float((schedule or load())['human']['every_hours']) * 3600)


def full_daily_utc_hour(schedule=None):
    return (int((schedule or load())['full']['daily_at_moscow_hour']) - 3) % 24


def in_night_window(moment=None, schedule=None):
    start, end = (schedule or load())['night']['window_moscow_hours']
    return int(start) <= moscow(moment).hour < int(end)


def night_sequence(schedule=None):
    return tuple((schedule or load())['night']['sequence'])


def digest_due(moment=None, schedule=None):
    hour, minute = (int(x) for x in (schedule or load())['digest']['after_moscow'].split(':'))
    local = moscow(moment)
    return (local.hour, local.minute) >= (hour, minute)


def morning_brief_config(schedule=None):
    return {**DEFAULT['morning_brief'], **((schedule or load()).get('morning_brief') or {})}


def morning_brief_due(moment=None, schedule=None):
    config = morning_brief_config(schedule)
    local = moscow(moment)
    hour, minute = (int(x) for x in config['at_moscow'].split(':'))
    return (not config.get('weekdays_only') or local.weekday() < 5) and (local.hour, local.minute) >= (hour, minute)


def focus(day, schedule=None):
    """Theme of the night that *started* on ``day`` (Moscow date)."""
    return ((schedule or load())['explore'].get('weekly_focus') or {}).get(WEEKDAYS[day.weekday()]) or {}


def missions_for(day, missions, schedule=None):
    """The night's missions: the day's focus areas first, then a stable rotation."""
    schedule = schedule or load()
    count = int(schedule['explore']['missions_per_night'])
    ordered = sorted(missions, key=lambda m: m['id'])
    # A round-robin walk instead of a daily hash: every mission comes up in turn
    # however many missions are added (18 since 27.10).
    offset = (day.toordinal() * count) % len(ordered) if ordered else 0
    rotation = ordered[offset:] + ordered[:offset]
    areas = set(focus(day, schedule).get('areas') or [])
    # The day's theme takes at most all but one slot: the rotation always advances.
    chosen = [m for m in rotation if areas & set(m.get('areas') or [])][:max(count - 1, 1)]
    chosen += [m for m in rotation if m not in chosen][:count - len(chosen)]
    return chosen


def plan_text(day=None, schedule=None, missions=()):
    """One owner-readable paragraph: what the tester does tonight."""
    schedule = schedule or load()
    day = day or moscow().date()
    theme = focus(day, schedule).get('theme') or 'ротация всех миссий'
    start, end = schedule['night']['window_moscow_hours']
    chosen = missions_for(day, missions, schedule) if missions else []
    return (f"План AI-тестировщика на ночь {day:%d.%m}: {start:02d}:00–{end:02d}:00 МСК — "
            f"{' → '.join(schedule['night']['sequence'])}. Тема исследователя: {theme}"
            + (f" ({', '.join(m['id'] for m in chosen)})" if chosen else '') +
            f". Днём человеческие маршруты каждые {schedule['human']['every_hours']} ч, сводка после "
            f"{schedule['digest']['after_moscow']}.")
