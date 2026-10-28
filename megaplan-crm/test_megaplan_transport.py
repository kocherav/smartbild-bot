import io
import json
import os
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
import megaplan_transport as t


class TransportTest(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        p=patch.multiple(t,DB=os.path.join(tmp.name,'guard.db'),MIN_INTERVAL=0)
        p.start();self.addCleanup(p.stop)
        # The service may launch the gate with background priority.  Most
        # transport tests exercise the normal user budget and must not inherit
        # that process-wide deployment detail; dedicated tests below set both
        # background and user priorities explicitly.
        priority=patch.dict(os.environ,{'MEGAPLAN_PRIORITY':'user'})
        priority.start();self.addCleanup(priority.stop)

    def request(self,method='GET',body=None):
        return urllib.request.Request('https://cclimat.megaplan.ru/api/v3/deal',data=body,method=method)

    def success(self,req=None):
        with patch.object(urllib.request,'urlopen',return_value=io.BytesIO(b'{}')):
            with t.urlopen(req or self.request()) as r:return r.read()

    def error(self,code,method='GET',headers=None):
        exc=urllib.error.HTTPError('url',code,'error',headers or {},io.BytesIO(b'{}'))
        with patch.object(urllib.request,'urlopen',side_effect=exc):
            with self.assertRaises(urllib.error.HTTPError):
                with t.urlopen(self.request(method,b'{}' if method=='POST' else None)):pass

    def test_interactive_request_gets_next_slot_before_background_scan(self):
        import threading,fcntl
        directory=t.DB+'.waiters';os.makedirs(directory)
        order=[]
        def worker(label,background):
            with open(t.DB+'.lock','a') as lock:
                t.acquire_slot(lock,background=background);order.append(label)
        with open(t.DB+'.lock','a') as occupied:
            fcntl.flock(occupied,fcntl.LOCK_EX)
            foreground=threading.Thread(target=worker,args=('foreground',False));foreground.start()
            deadline=time.monotonic()+2
            while not os.listdir(directory) and time.monotonic()<deadline:time.sleep(.01)
            self.assertTrue(os.listdir(directory))
            background=threading.Thread(target=worker,args=('background',True));background.start()
        foreground.join(3);background.join(3)
        self.assertEqual(order,['foreground','background']);self.assertEqual(os.listdir(directory),[])

    def test_background_wait_is_configurable_and_still_bounded(self):
        # 28.10: the morning brief gave up after 10 s of a busy queue every morning.
        import fcntl
        clock = iter([0, 0, 15, 15, 95])
        with open(t.DB+'.lock','a') as occupied, open(t.DB+'.lock','a') as lock, \
             patch.dict(os.environ, {'MEGAPLAN_BACKGROUND_WAIT': '90'}), \
             patch.object(t.time, 'monotonic', side_effect=lambda: next(clock)), \
             patch.object(t.time, 'sleep'):
            fcntl.flock(occupied, fcntl.LOCK_EX)
            with self.assertRaises(t.ProtectionPause):
                t.acquire_slot(lock, background=True)
            self.assertEqual([], list(clock), 'ждал дольше 10 с, но не бесконечно')

    def test_429_retry_after_and_fail_fast(self):
        self.error(429,headers={'Retry-After':'120'})
        with t.connect() as db:self.assertGreater(db.execute('SELECT until FROM circuits').fetchone()[0],time.time()+115)
        with patch.object(urllib.request,'urlopen') as network:
            with self.assertRaises(t.ProtectionPause):
                with t.urlopen(self.request()):pass
            network.assert_not_called()

    def test_retry_after_date(self):
        self.assertEqual(120,t.retry_seconds('Thu, 01 Jan 1970 00:02:00 GMT',0))

    def test_reachability_is_shared_and_suppressed_during_pause(self):
        from unittest.mock import MagicMock
        with patch.object(t.socket,'create_connection',return_value=MagicMock()) as probe:
            self.assertTrue(t.reachable());self.assertTrue(t.reachable());probe.assert_called_once()
            self.error(503);self.assertFalse(t.reachable());probe.assert_called_once()

    def test_minute_budget(self):
        with patch.object(t,'MINUTE_LIMIT',1):
            self.success()
            with self.assertRaises(t.ProtectionPause):self.success()

    def test_rolling_budget_after_spacing_allows_continuous_pagination(self):
        clock=[997.1]
        with t.connect() as db:
            db.executemany('INSERT INTO calls(at,host,method,path,status) VALUES(?,?,?,?,?)',
                           [(940+i*3,'cclimat.megaplan.ru','GET','/read','ok') for i in range(20)])
        def sleep(seconds):clock[0]+=seconds
        with patch.object(t,'MIN_INTERVAL',3),patch.object(t.time,'time',side_effect=lambda:clock[0]),patch.object(t.time,'sleep',side_effect=sleep):
            for _ in range(35):self.success()
        with t.connect() as db:
            stamps=[r[0] for r in db.execute('SELECT at FROM calls ORDER BY at')]
        self.assertEqual(55,len(stamps))
        self.assertTrue(all(b-a>=3 for a,b in zip(stamps,stamps[1:])))
        self.assertTrue(all(sum(v-60<x<=v for x in stamps)<=20 for v in stamps))

    def test_budget_pause_carries_window_expiry(self):
        with patch.object(t,'HOUR_LIMIT',1):
            self.success()
            with self.assertRaises(t.ProtectionPause) as exc:self.success()
            self.assertTrue(exc.exception.retryable)
            self.assertGreater(exc.exception.retry_after,3500)

    def test_lock_serializes_concurrent_workers(self):
        import threading
        active=0;maximum=0;errors=[]
        @__import__('contextlib').contextmanager
        def opener(*a,**kw):
            nonlocal active,maximum
            active+=1;maximum=max(maximum,active)
            try:time.sleep(.05);yield io.BytesIO(b'{}')
            finally:active-=1
        def worker():
            try:
                with t.urlopen(self.request()) as r:r.read()
            except Exception as exc:errors.append(exc)
        with patch.object(urllib.request,'urlopen',side_effect=opener):
            threads=[threading.Thread(target=worker) for _ in range(3)]
            for thread in threads:thread.start()
            for thread in threads:thread.join()
        self.assertEqual([],errors);self.assertEqual(1,maximum)

    def test_uncertain_write_never_replayed_after_timeout(self):
        req=self.request('POST',b'{"price":10}')
        with patch.object(urllib.request,'urlopen',side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                with t.urlopen(req):pass
        with t.connect() as db:db.execute('UPDATE circuits SET until=0')
        with patch.object(urllib.request,'urlopen') as network:
            with self.assertRaisesRegex(t.ProtectionPause,'сверки'):
                with t.urlopen(req):pass
            network.assert_not_called()

    def test_success_clears_write_fence(self):
        self.success(self.request('POST',b'{}'))
        with t.connect() as db:self.assertEqual(0,db.execute('SELECT count(*) FROM uncertain').fetchone()[0])

    def test_rejected_write_is_not_unknown(self):
        self.error(429,'POST')
        with t.connect() as db:self.assertEqual(0,db.execute('SELECT count(*) FROM uncertain').fetchone()[0])

    def test_server_error_write_is_unknown(self):
        self.error(500,'POST')
        with t.connect() as db:self.assertEqual(1,db.execute('SELECT count(*) FROM uncertain').fetchone()[0])

    def test_malformed_json_pauses(self):
        with patch.object(urllib.request,'urlopen',return_value=io.BytesIO(b'<html>')):
            with self.assertRaises(ValueError):
                with t.urlopen(self.request()) as r:json.loads(r.read())
        self.assertTrue(t.paused())

    def test_401_does_not_cause_login_storm(self):
        self.error(401)
        with self.assertRaises(t.ProtectionPause):self.success()

    def test_403_endpoint_stays_blocked_after_short_global_pause(self):
        self.error(403)
        with self.assertRaises(t.ProtectionPause):self.success()

    def test_forbidden_comment_update_does_not_block_readonly_verification(self):
        request=urllib.request.Request('https://cclimat.megaplan.ru/api/v3/comment/17',data=b'{}',method='POST')
        exc=urllib.error.HTTPError('url',403,'forbidden',{},io.BytesIO(b'{}'))
        with patch.object(urllib.request,'urlopen',side_effect=exc):
            with self.assertRaises(urllib.error.HTTPError):
                with t.urlopen(request):pass
        read=urllib.request.Request('https://cclimat.megaplan.ru/api/v3/comment/17',method='GET')
        self.assertEqual(b'{}',self.success(read))
        with patch.object(urllib.request,'urlopen') as network:
            with self.assertRaises(t.ProtectionPause):
                with t.urlopen(request):pass
            network.assert_not_called()

    def test_shared_budget_reserves_capacity_for_user(self):
        with patch.multiple(t,BACKGROUND_LIMIT=1,HOUR_LIMIT=2):
            self.success()
            with patch.dict(os.environ,{'MEGAPLAN_PRIORITY':'background'}):
                with self.assertRaises(t.ProtectionPause):self.success()
            with patch.dict(os.environ,{'MEGAPLAN_PRIORITY':'user'}):
                self.success()
                with self.assertRaises(t.ProtectionPause):self.success()

    def test_notice_once_and_only_confirmed_recovery(self):
        self.error(503);messages=[]
        send=lambda msg:messages.append(msg) or True
        t.notify_status(send);t.notify_status(send);self.assertEqual(1,len(messages))
        with t.connect() as db:db.execute('UPDATE circuits SET until=0')
        t.notify_status(send);self.assertEqual(1,len(messages))
        self.success();t.notify_status(send);self.assertEqual(1,len(messages))
        with t.connect() as db:db.execute("UPDATE calls SET at=at-601 WHERE status!='ok'")
        t.notify_status(send);self.assertEqual(2,len(messages))

    def test_flapping_different_errors_does_not_spam(self):
        messages=[];send=lambda msg:messages.append(msg) or True
        for code in (503,502,429,401):
            with t.connect() as db:db.execute('UPDATE circuits SET until=0')
            self.error(code);t.notify_status(send)
            with t.connect() as db:db.execute('UPDATE circuits SET until=0')
            self.success();t.notify_status(send)
        self.assertEqual(1,len(messages))

    def test_failed_notice_delivery_is_retried(self):
        self.error(503);t.notify_status(lambda msg:False)
        messages=[];t.notify_status(lambda msg:messages.append(msg) or True)
        self.assertEqual(1,len(messages))

    def test_denied_endpoint_does_not_emit_false_outage_or_recovery(self):
        self.error(403);messages=[];send=lambda msg:messages.append(msg) or True
        t.notify_status(send)
        with t.connect() as db:
            db.execute("UPDATE circuits SET until=0,reason=''")
            db.execute('UPDATE calls SET at=at-601')
        t.notify_status(send);self.assertEqual([],messages)

    def test_query_and_body_not_logged(self):
        req=urllib.request.Request('https://cclimat.megaplan.ru/api/v3/deal?secret=value',data=b'password',method='POST')
        self.success(req)
        with t.connect() as db:
            records=repr([tuple(r) for r in db.execute('SELECT * FROM calls')])
            self.assertNotIn('secret',records);self.assertNotIn('password',records)

    def test_inflight_write_is_not_announced_as_failed(self):
        with t.connect() as db:db.execute('INSERT INTO uncertain VALUES(?,?,?,?,?)',('hash','cclimat.megaplan.ru','POST','/deal',time.time()))
        messages=[];t.notify_status(lambda msg:messages.append(msg) or True)
        self.assertEqual([],messages)

    def test_upload_random_boundary_cannot_bypass_uncertain_fence(self):
        def req(boundary):return urllib.request.Request('https://cclimat.megaplan.ru/api/file',data=('--'+boundary+'\nDATA').encode(),headers={'Content-Type':'multipart/form-data; boundary='+boundary})
        with patch.object(urllib.request,'urlopen',side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                with t.urlopen(req('AAA')):pass
        with t.connect() as db:db.execute('UPDATE circuits SET until=0')
        with self.assertRaises(t.ProtectionPause):self.success(req('BBB'))


if __name__=='__main__':unittest.main()
