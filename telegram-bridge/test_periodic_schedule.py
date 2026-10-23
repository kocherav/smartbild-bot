import tempfile
import datetime as dt
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import unittest
import periodic_schedule as schedule
import qa_schedule

class ScheduleTests(unittest.TestCase):
    def test_restart_and_initialization_cannot_increase_poll_frequency(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=str(Path(temporary)/'schedule.json')
            self.assertFalse(schedule.claim(path,'mail',3600,now=100,delay_first=True))
            self.assertFalse(schedule.claim(path,'mail',3600,now=200,delay_first=True))
            self.assertTrue(schedule.claim(path,'mail',3600,now=3700,delay_first=True))
            self.assertFalse(schedule.claim(path,'mail',3600,now=3701,delay_first=True))
            self.assertFalse(schedule.claim(path,'mail',3600,now=50,delay_first=True))

    def test_concurrent_ticks_allow_one_reader(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=str(Path(temporary)/'schedule.json')
            with ThreadPoolExecutor(max_workers=8) as pool:
                results=list(pool.map(lambda _:schedule.claim(path,'mail',3600,now=100),range(20)))
            self.assertEqual(1,sum(results))

    def test_corrupt_schedule_does_not_bypass_rate_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'schedule.json';path.write_text('{broken')
            with self.assertRaises(ValueError):schedule.claim(str(path),'mail',3600,now=100)
            self.assertEqual('{broken',path.read_text())

    def test_daily_schedule_runs_once_after_hour(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=str(Path(temporary)/'schedule.json')
            before=dt.datetime(2026,10,21,0,59,tzinfo=dt.timezone.utc)
            after=dt.datetime(2026,10,21,1,0,tzinfo=dt.timezone.utc)
            self.assertFalse(schedule.claim_daily(path,'qa',1,now=before))
            self.assertTrue(schedule.claim_daily(path,'qa',1,now=after))
            self.assertFalse(schedule.claim_daily(path,'qa',1,now=after))

    def test_morning_brief_is_due_only_on_weekdays_after_configured_time(self):
        plan={**qa_schedule.DEFAULT, 'morning_brief': {**qa_schedule.DEFAULT['morning_brief'], 'at_moscow':'09:00'}}
        self.assertFalse(qa_schedule.morning_brief_due(dt.datetime(2026,10,23,5,59,tzinfo=dt.timezone.utc),plan))
        self.assertTrue(qa_schedule.morning_brief_due(dt.datetime(2026,10,23,6,0,tzinfo=dt.timezone.utc),plan))
        self.assertFalse(qa_schedule.morning_brief_due(dt.datetime(2026,10,24,7,0,tzinfo=dt.timezone.utc),plan))

if __name__=='__main__':unittest.main()
