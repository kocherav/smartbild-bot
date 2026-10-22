import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tempfile
import unittest
from unittest.mock import patch
import sqlite3
import server,workspace

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.dbpatch=patch.object(server,'DB',Path(self.tmp.name)/'app.sqlite3');self.dbpatch.start();server.initialize()
        self.deals=[{'id':str(i),'is_purchase':False,'client':'Клиент '+str(i),'address':''} for i in range(1,5)]
        self.snap=patch.object(server,'snapshot',return_value={'deals':self.deals});self.snap.start()
    def tearDown(self): self.snap.stop();self.dbpatch.stop();self.tmp.cleanup()
    def obj(self,oid='object001',ids=None,revision=0,**kw):
        with server.connect() as db:return workspace.save_object(db,{'id':oid,'name':'Объект','address':'Москва','revision':revision,'deal_ids':ids or ['1','2'],**kw},123,self.deals)
    def plan(self,**kw):
        body={'id':'plan00001','revision':0,'deal_id':'1','kind':'income','title':'Аванс','due':'2026-11-01','certainty':'tentative','amount':12345,'owner':'Иван','note':'','status':'open',**kw}
        with server.connect() as db:return workspace.save_plan(db,body,123,self.deals)
    def task(self,did='1',**kw): return server.save_task({'deal_id':did,'title':'Работа','owner':'','due':'','note':'','done':False,**kw},123)
    def test_idempotent_migration_preserves_tasks(self):
        t=self.task();server.initialize()
        self.assertEqual(server.task_rows()[0]['id'],t['id'])
        self.assertEqual(server.task_rows()[0]['depends_on'],'')
    def test_same_client_does_not_auto_merge(self):
        with server.connect() as db: p=workspace.projection(db,self.deals,123,({},'ok'))
        self.assertEqual(len(p['objects']),4);self.assertTrue(all(not o['confirmed'] for o in p['objects']))
    def test_unique_links_revision_and_detach(self):
        self.obj()
        with self.assertRaises(ValueError):self.obj('object002',['2','3'])
        with self.assertRaises(workspace.Conflict):self.obj(revision=0)
        self.obj(ids=['1'],revision=1)
        with server.connect() as db:
            p=workspace.projection(db,self.deals,123,({},'ok'));history=workspace.history(db,['2'])
        self.assertTrue(any(o['id']=='deal:2' for o in p['objects']))
        self.assertEqual(len(history),2)
    def test_invalid_links(self):
        for ids in [['1','1'],['999'],['1',None]]:
            with self.assertRaises(ValueError):self.obj(ids=ids)
    def test_plan_money_validation_and_conflict(self):
        for amount in [True,0,-1,1.1,None,10**15]:
            with self.assertRaises(ValueError):self.plan(amount=amount)
        p=self.plan();self.assertEqual(p['amount'],12345)
        with self.assertRaises(workspace.Conflict):self.plan()
        p=self.plan(revision=1,status='done');self.assertEqual(p['revision'],2)
        with server.connect() as db:self.assertEqual(len(workspace.history(db,['1'])),2)
    def test_agreed_date_requires_evidence_and_delivery_has_no_money(self):
        with self.assertRaises(ValueError):self.plan(certainty='agreed')
        p=self.plan(kind='delivery',certainty='agreed',note='Согласовано 09.10',amount=999)
        self.assertIsNone(p['amount'])
    def test_dependency_block_cycle_reopen_and_split(self):
        self.obj();a=self.task();b=self.task('2',depends_on=a['id'])
        with self.assertRaises(ValueError):self.task('2',**{**b,'done':True})
        with self.assertRaises(ValueError):self.task(**{**a,'depends_on':b['id']})
        with self.assertRaises(ValueError):self.obj(ids=['1'],revision=1)
        a=self.task(**{**a,'done':True});b=self.task('2',**{**b,'done':True})
        with self.assertRaises(ValueError):self.task(**{**a,'done':False})
    def test_dependency_cannot_cross_objects(self):
        a=self.task()
        with self.assertRaises(ValueError):self.task('2',depends_on=a['id'])
    def test_views_validation_and_ownership(self):
        with server.connect() as db:workspace.save_view(db,{'id':'view00001','name':'Мои','filters':{'year':'2026'}},123)
        with server.connect() as db:
            with self.assertRaises(workspace.Conflict):workspace.save_view(db,{'id':'view00001','name':'Мои','filters':{}},456)
        with server.connect() as db:
            with self.assertRaises(ValueError):workspace.save_view(db,{'id':'view00002','name':'Мои','filters':{'evil':True}},123)
    def test_installation_missing_is_not_empty_success(self):
        self.assertEqual(workspace.installations(Path(self.tmp.name)/'missing'),({},'missing'))
    def test_installation_accepted_only_and_read_only(self):
        path=Path(self.tmp.name)/'install.sqlite3'
        db=sqlite3.connect(path)
        db.executescript('''CREATE TABLE installations(deal_id TEXT,client TEXT,address TEXT,installer_name TEXT,status TEXT,updated_at TEXT);
        INSERT INTO installations VALUES('1','Client','Address','Installer','transferred','2026-10-09');
        CREATE TABLE work_items(id INTEGER,deal_id TEXT,name TEXT,unit TEXT,planned_qty REAL,rate REAL,active INTEGER,cost_kind TEXT,sort_order INTEGER);
        INSERT INTO work_items VALUES(1,'1','Pipe','m',10,10,1,'work',1);
        CREATE TABLE reports(id INTEGER,deal_id TEXT,status TEXT,report_no INTEGER,report_date TEXT,approved_at TEXT,manager_comment TEXT);
        INSERT INTO reports VALUES(1,'1','approved',1,'30.09.2026','',''),(2,'1','draft',2,'02.10.2026','','');
        CREATE TABLE report_items(work_item_id INTEGER,report_id INTEGER,accepted_qty REAL);
        INSERT INTO report_items VALUES(1,1,3),(1,2,100);
        CREATE TABLE project_versions(id INTEGER,deal_id TEXT,version_no INTEGER,status TEXT);
        CREATE TABLE project_documents(version_id INTEGER,name TEXT,created_at TEXT,id INTEGER);''');db.close()
        before=path.read_bytes();out,status=workspace.installations(path)
        self.assertEqual(status,'ok');self.assertEqual(out['1']['works'][0]['accepted_qty'],3);self.assertEqual(before,path.read_bytes());self.assertEqual([r['report_date'] for r in out['1']['reports']],['2026-10-02','2026-09-30'])

if __name__=='__main__':unittest.main()
