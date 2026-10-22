import json,tempfile,unittest,sys
from pathlib import Path
from unittest.mock import patch
import bridge,supplier_completion as completion
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'hogart-scraper/finance'))
import review_registry as queue

class SupplierCompletionTests(unittest.TestCase):
    def test_failed_economics_keeps_committed_cost_and_records_followup(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);queue.sync([],root,{})
            result_file=root/'economics.xlsx';result_file.write_bytes(b'workbook')
            spec={'deal_id':'42','invoice':{'supplier':'Vendor','number':'10','source_path':'invoice.pdf'},'updates':[{'qty_used':1}]}
            original=completion.record
            with patch.object(bridge,'run_procurement_workflow',return_value={'ok':True}) as registry, \
                 patch.object(bridge,'run_supplier_invoice_apply',return_value={'ok':True}) as apply, \
                 patch.object(bridge,'run_deal_browser',return_value={'ok':True}), \
                 patch.object(bridge,'build_and_store_profitability',return_value={'ok':False,'path':str(result_file),'error':'HTTP 403'}), \
                 patch.object(bridge,'build_and_store_procurement_register',return_value={'ok':True}), \
                 patch.object(completion,'record',side_effect=lambda s,r:original(s,r,root)):
                result=bridge.apply_distributed_invoice_spec(spec)
            self.assertTrue(result['ok']);self.assertFalse(result['complete']);apply.assert_called_once()
            self.assertEqual(registry.call_count,2);self.assertTrue(result_file.exists())
            self.assertIn('HTTP 403',completion.summary([result]));self.assertNotIn('Экономика и реестр закупок обновлены',completion.summary([result]))
            active=queue.active(json.loads((root/'data/review_registry.json').read_text()))
            self.assertEqual(len(active),1);self.assertEqual(active[0]['kind'],'processing_followup')
            queue.sync([],root,{})
            self.assertEqual(len(queue.active(json.loads((root/'data/review_registry.json').read_text()))),1)
            complete={**result,'economics':{'ok':True}}
            original(spec,complete,root)
            self.assertEqual(queue.active(json.loads((root/'data/review_registry.json').read_text())),[])
    def test_archive_warning_is_not_reported_as_complete(self):
        result={'upload':{'ok':True},'economics':{'ok':True,'archive_warning':'offline'},'procurement_register':{'ok':True}}
        self.assertIn('OneDrive',completion.pending_steps(result)[0])
    def test_full_success_has_no_pending_steps(self):
        self.assertEqual(completion.pending_steps({k:{'ok':True} for k in ('upload','economics','procurement_register')}),[])

if __name__=='__main__':unittest.main()
