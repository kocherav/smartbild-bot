import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

import qa_schedule


UTC = dt.timezone.utc
MISSIONS = [{'id': f'm{i}', 'areas': [area]} for i, area in enumerate(
    ['invoice', 'invoice', 'payer', 'contract', 'robustness', 'deal-read', 'status', 'proposal'])]


class QaScheduleTests(unittest.TestCase):
    def test_repository_schedule_is_valid_and_matches_previous_behaviour(self):
        schedule = qa_schedule.load(qa_schedule.PATH)
        self.assertIsNot(schedule, qa_schedule.DEFAULT, 'утверждённый файл должен читаться')
        self.assertEqual(4 * 3600, qa_schedule.human_interval_seconds(schedule))
        self.assertEqual(('full', 'browser', 'human', 'explore'), qa_schedule.night_sequence(schedule))
        self.assertEqual(set(qa_schedule.WEEKDAYS), set(schedule['explore']['weekly_focus']))

    def test_night_window_and_digest_use_moscow_time(self):
        schedule = qa_schedule.DEFAULT
        self.assertTrue(qa_schedule.in_night_window(dt.datetime(2026, 10, 22, 21, 0, tzinfo=UTC), schedule))  # 00:00 МСК
        self.assertFalse(qa_schedule.in_night_window(dt.datetime(2026, 10, 23, 4, 0, tzinfo=UTC), schedule))  # 07:00 МСК
        self.assertFalse(qa_schedule.digest_due(dt.datetime(2026, 10, 23, 14, 29, tzinfo=UTC), schedule))
        self.assertTrue(qa_schedule.digest_due(dt.datetime(2026, 10, 23, 14, 30, tzinfo=UTC), schedule))
        with self.assertRaises(ValueError):
            qa_schedule.in_night_window(dt.datetime(2026, 10, 23, 1, 0), schedule)

    def test_daily_full_hour_is_converted_to_utc(self):
        schedule = copy.deepcopy(qa_schedule.DEFAULT)
        schedule['full']['daily_at_moscow_hour'] = 2
        self.assertEqual(23, qa_schedule.full_daily_utc_hour(schedule))

    def test_focus_missions_first_then_rotation(self):
        schedule = copy.deepcopy(qa_schedule.DEFAULT)
        schedule['explore'] = {'missions_per_night': 3,
                               'weekly_focus': {'wed': {'theme': 'Счета', 'areas': ['invoice']}}}
        wednesday = dt.date(2026, 10, 21)
        chosen = qa_schedule.missions_for(wednesday, MISSIONS, schedule)
        self.assertEqual(3, len(chosen))
        self.assertEqual({'m0', 'm1'}, {m['id'] for m in chosen[:2]})
        self.assertEqual(chosen, qa_schedule.missions_for(wednesday, MISSIONS, schedule))
        self.assertIn('Счета', qa_schedule.plan_text(wednesday, schedule, MISSIONS))

    def test_every_mission_is_reached_within_two_weeks(self):
        schedule = qa_schedule.load(qa_schedule.PATH)
        import human_qa_explorer
        missions = human_qa_explorer.load_missions()
        seen = set()
        for offset in range(14):
            seen |= {m['id'] for m in qa_schedule.missions_for(dt.date(2026, 10, 26) + dt.timedelta(days=offset),
                                                               missions, schedule)}
        self.assertEqual({m['id'] for m in missions}, seen)

    def test_every_weekday_area_has_a_mission(self):
        schedule = qa_schedule.load(qa_schedule.PATH)
        import human_qa_explorer
        covered = {area for m in human_qa_explorer.load_missions() for area in m.get('areas') or []}
        for day, focus in schedule['explore']['weekly_focus'].items():
            for area in focus.get('areas') or []:
                with self.subTest(day=day, area=area):
                    self.assertIn(area, covered)

    def test_invalid_file_falls_back_to_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'schedule.json'
            broken = copy.deepcopy(qa_schedule.DEFAULT)
            broken['night']['sequence'] = ['full', 'delete-everything']
            path.write_text(json.dumps(broken))
            self.assertIs(qa_schedule.DEFAULT, qa_schedule.load(path))
            path.write_text('{oops')
            self.assertIs(qa_schedule.DEFAULT, qa_schedule.load(path))


if __name__ == '__main__':
    unittest.main()
