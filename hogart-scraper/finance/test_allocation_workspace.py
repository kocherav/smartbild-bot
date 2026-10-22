import copy
import json
from pathlib import Path
import tempfile
import unittest
import allocation_workspace as a
import review_registry as q

class AllocationTests(unittest.TestCase):
    def setUp(self):
        self.deals=[{'id':'1','name':'A'},{'id':'2','name':'B'}]
        self.p={'invoices':[{'document_key':'invoice','number':'10','supplier':'S','total':100,
                 'allocations':[{'deal_id':'1','amount':60}], 'paid_total':50,
                 'payments':[{'transaction_id':'p','amount':50}]}],
                'unallocated_stock':[{'id':'line','document_key':'invoice','name':'Cable','unit':'m',
                                     'available_qty':4,'available_amount':40,'allocations':[]}]}
        self.body={'document_key':'invoice','source_revision':a.fingerprint(a.source_document(self.p,'invoice')),
                   'allocations':[{'line_id':'line','deal_id':'2','qty':3}], 'draft_revision':0}
    def test_partial_allocation_cost_and_payment_conserve_total(self):
        p=a.preview(self.body,self.deals,self.p)
        self.assertEqual(3000,p['allocated_now_cents']);self.assertEqual(1000,p['remaining_cents'])
        by={s['deal_id']:s for s in p['summary']}
        self.assertEqual(6000,by['1']['cost_cents']);self.assertEqual(3000,by['1']['proposed_payment_cents'])
        self.assertEqual(1500,by['2']['proposed_payment_cents'])
        self.assertEqual(500,by['unallocated']['proposed_payment_cents'])
        self.assertFalse(p['crm_applied'])
    def test_overallocation_unknown_deal_nan_duplicate_and_stale_rejected(self):
        for patch in [{'qty':5},{'qty':'NaN'},{'qty':'Infinity'},{'deal_id':'999'},{'line_id':'missing'}]:
            b=copy.deepcopy(self.body);b['allocations'][0].update(patch)
            with self.assertRaises(ValueError):a.preview(b,self.deals,self.p)
        b=copy.deepcopy(self.body);b['allocations']*=2
        with self.assertRaises(ValueError):a.preview(b,self.deals,self.p)
        b['source_revision']='old'
        with self.assertRaises(a.Conflict):a.preview(b,self.deals,self.p)
    def test_rounding_split_has_no_lost_kopecks(self):
        self.assertEqual(sum(a.prorate(100,{'1':1,'2':1,'remaining':1}).values()),100)
        self.assertEqual(a.prorate(100,{'1':1,'2':1,'remaining':1})['1'],34)
    def test_absent_payments_are_unknown_not_zero(self):
        self.p['invoices'][0]['payments']=[]
        self.body['source_revision']=a.fingerprint(a.source_document(self.p,'invoice'))
        p=a.preview(self.body,self.deals,self.p)
        self.assertIsNone(p['paid_cents']);self.assertTrue(p['payment_warning'])
    def test_payment_summary_mismatch_blocks_preview(self):
        self.p['invoices'][0]['paid_total']=100
        self.body['source_revision']=a.fingerprint(a.source_document(self.p,'invoice'))
        with self.assertRaises(ValueError):a.preview(self.body,self.deals,self.p)
    def test_draft_persists_across_daily_sync_and_rejects_stale_save(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);q.sync([],root,self.p);proc=root/'proc.json';proc.write_text(json.dumps(self.p))
            out=a.save_draft(self.body,self.deals,7,root,proc)
            self.assertEqual(out['revision'],1)
            reg=q.sync([],root,self.p)
            self.assertEqual(reg['allocation_drafts']['invoice']['allocations'],out['allocations'])
            self.assertEqual(len(reg['workflow_audit']),1)
            with self.assertRaises(a.Conflict):a.save_draft(self.body,self.deals,7,root,proc)
            self.assertEqual(json.loads(proc.read_text()),self.p)

if __name__=='__main__':unittest.main()
