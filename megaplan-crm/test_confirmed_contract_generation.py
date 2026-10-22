import json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import contract_invoice as source
from generate_contract import validate_confirmed_source

class ConfirmedGenerationTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);self.patch=patch.object(source,'CONTRACT_SOURCES',self.root);self.patch.start();self.addCleanup(self.patch.stop)
  self.api=Mock();self.data={'deal_id':'858','total':2000000,'positions':[{'id':'7579','name':'Монтажные работы','unit':'шт.','quantity':1,'total':'463730.00'}]}
 def pin(self,**extra):
  (self.root/'858-source.json').write_text(json.dumps({'signed_file_id':'confirmed','confirmed_total':'2000000.00',**extra}))
 def test_wrong_crm_total_rejected_before_download(self):
  self.pin();self.data['total']=1848250
  with patch.object(source,'latest_contract') as download:
   with self.assertRaisesRegex(ValueError,'Сумма сделки'):validate_confirmed_source(self.api,self.data)
   download.assert_not_called()
 def test_same_total_changed_row_still_rejected(self):
  self.pin();p=self.root/'contract.txt';p.write_text('СПЕЦИФИКАЦИЯ\nМонтажные работы    шт.    1    450 000,00 руб.    450 000,00 руб.')
  with patch.object(source,'latest_contract',return_value=({},str(p))),patch.object(source,'document_text',side_effect=lambda x:Path(x).read_text()):
   with self.assertRaisesRegex(ValueError,'сумма позиции'):validate_confirmed_source(self.api,self.data)
  self.assertFalse(p.exists())
 def test_matching_source_allowed(self):
  self.pin();p=self.root/'contract.txt';p.write_text('СПЕЦИФИКАЦИЯ\nМонтажные работы    шт.    1    463 730,00 руб.    463 730,00 руб.')
  with patch.object(source,'latest_contract',return_value=({},str(p))),patch.object(source,'document_text',side_effect=lambda x:Path(x).read_text()):validate_confirmed_source(self.api,self.data)
  self.assertFalse(p.exists())
 def test_confirmed_but_not_attached_does_not_generate_substitute(self):
  self.pin(signed_file_id=None)
  with self.assertRaisesRegex(ValueError,'закрепите'):validate_confirmed_source(self.api,self.data)
 def test_new_deal_without_confirmed_contract_is_supported(self):
  validate_confirmed_source(self.api,self.data);self.api.assert_not_called()
if __name__=='__main__':unittest.main()
