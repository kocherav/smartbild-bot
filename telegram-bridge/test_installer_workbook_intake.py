import unittest,tempfile,os
from unittest.mock import patch
from openpyxl import Workbook
import installer_workbook_intake as own
import installer_report_intake as intake

class OwnWorkbookTests(unittest.TestCase):
 def make(self,folder,current=False,accepted=0):
  w=Workbook();s=w.active;s.title='Монтажная ведомость';s.append(['Сделка №890 - Объект']);s.append(['ID','Работа','Ед.','План','Расценка','Плановая сумма','Выполнено всего','Осталось','Принято к оплате']+([own.CURRENT] if current else []));s.append([254,'Монтаж трубы','м',56,350,19600,56,56,0]+([12] if current else []));p=os.path.join(folder,'report.xlsx');w.save(p)
  return p,{'254':{'id':254,'name':'Монтаж трубы','unit':'м','planned_qty':56,'rate':350,'accepted_qty':accepted}}
 def test_old_cumulative_quantity_is_not_money(self):
  with tempfile.TemporaryDirectory() as d:
   p,works=self.make(d)
   with patch.object(own,'canonical',return_value=works):s=intake.build_session(p)
   self.assertEqual(s['net_total'],19600);self.assertEqual(s['source_deal_id'],'890');self.assertEqual(s['exceptions'][0]['table_rows'][0]['work_item_id'],254);self.assertFalse(s['approved'])
 def test_subtract_accepted_and_repeat_no_new_completion(self):
  with tempfile.TemporaryDirectory() as d:
   p,works=self.make(d,accepted=20)
   with patch.object(own,'canonical',return_value=works):self.assertEqual(intake.build_session(p)['net_total'],12600)
   works['254']['accepted_qty']=56
   with patch.object(own,'canonical',return_value=works),self.assertRaisesRegex(ValueError,'Нового выполнения нет'):intake.build_session(p)
 def test_explicit_current_quantity_and_overflow(self):
  with tempfile.TemporaryDirectory() as d:
   p,works=self.make(d,current=True,accepted=20)
   with patch.object(own,'canonical',return_value=works):s=intake.build_session(p)
   self.assertEqual(s['net_total'],4200);self.assertEqual(s['exceptions'][0]['table_rows'][0]['cumulative_qty'],32)
   works['254']['accepted_qty']=50
   with patch.object(own,'canonical',return_value=works),self.assertRaisesRegex(ValueError,'превышает остаток'):intake.build_session(p)
 def test_attached_table_same_quantity_contract_and_changed_plan(self):
  with tempfile.TemporaryDirectory() as d:
   p,works=self.make(d);t=[{'type':'table','deal_id':'890','amount':19600}]
   with patch.object(own,'canonical',return_value=works):intake.attach_tables(t,[p])
   self.assertTrue(t[0]['completion_matches_report']);self.assertEqual(t[0]['table_rows'][0]['current_qty'],56)
   works['254']['rate']=400
   with patch.object(own,'canonical',return_value=works),self.assertRaisesRegex(ValueError,'расценка изменились'):intake.build_session(p)

class AttachmentCollisionTests(unittest.TestCase):
 def test_two_photos_in_same_second_preserve_both(self):
  import bridge,io
  with tempfile.TemporaryDirectory() as d,patch.object(bridge,'INCOMING_DIR',d),patch.object(bridge.time,'time',return_value=123),patch.object(bridge,'tg_api',return_value={'ok':True,'result':{'file_path':'photos/a.jpg'}}),patch.object(bridge.urllib.request,'urlopen',side_effect=lambda *a,**k:io.BytesIO(b'image')):
   a,e=bridge.download_telegram_photo('test',[{'file_id':'one','width':1,'height':1}]);b,f=bridge.download_telegram_photo('test',[{'file_id':'two','width':1,'height':1}])
   self.assertIsNone(e);self.assertIsNone(f);self.assertNotEqual(a,b);self.assertTrue(os.path.exists(a));self.assertTrue(os.path.exists(b))

class StaleWorkbookTests(unittest.TestCase):
 def test_approval_plan_rejects_changed_baseline_even_with_room_left(self):
  import sys
  sys.path.insert(0,'/home/kocher.av/megaplan-crm')
  import legacy_report_plan as plan
  works={'890':[{'id':254,'name':'Монтаж трубы','unit':'м','planned_qty':56,'rate':350,'accepted_qty':10}]}
  session={'exceptions':[{'type':'table','deal_id':'890','table_rows':[{'name':'Монтаж трубы','unit':'м','work_item_id':254,'current_qty':2,'current_amount':700,'accepted_baseline':0}]}]}
  r=plan.plan(session,works);self.assertFalse(r['ready']);self.assertIn('изменился',r['review'][0]['reason'])
