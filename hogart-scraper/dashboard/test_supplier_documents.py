import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import supplier_documents as documents
from shipment_procurement import coverage

class SupplierDocumentsTests(unittest.TestCase):
    def registry(self,path):
        return {'invoices':[{'id':'inv','number':'502','date':'02.07.2026','supplier':'Поставщик','source_path':str(path),'allocations':[{'deal_id':'861','source_lines':[{'offer_row_id':'1','source_name':'ABB S201 C10 A','qty_used':13}]}]}]}
    def test_details(self):
        r=coverage('861',[{'id':'1','name':'ABB','quantity':13}],self.registry('/missing'))['1']['invoices'][0]
        self.assertEqual(r['date'],'02.07.2026');self.assertEqual(r['supplier'],'Поставщик');self.assertNotIn('source_path',r)
    def test_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'invoice.pdf';p.write_bytes(b'%PDF-1.4\n')
            with patch.object(documents,'ROOTS',(Path(tmp),)):
                self.assertEqual(documents.resolve(self.registry(p),'861','inv','1')[1],p)
                for deal,inv,row in [('999','inv','1'),('861','bad','1'),('861','inv','2'),('861','inv',None)]:
                    with self.assertRaises(ValueError):documents.resolve(self.registry(p),deal,inv,row)
            with patch.object(documents,'ROOTS',(Path(tmp)/'elsewhere',)):
                with self.assertRaises(ValueError):documents.resolve(self.registry(p),'861','inv','1')
    def test_exact_wrapped_match_and_ambiguous(self):
        words=[{'text':w,'x':i*10,'y':10,'w':8,'h':8} for i,w in enumerate(['ABB','S201','C10','A','other'])]
        pages=[{'width':100,'height':100,'words':words}]
        result=documents.locate(pages,[{'source_name':'ABB S201 C10 A'}]);self.assertEqual(len(result[0]),4)
        self.assertEqual(documents.locate(pages,[{'source_name':'ABB S201 C16 A'}]),{})
        self.assertEqual(documents.locate(pages*2,[{'source_name':'ABB S201 C10 A'}]),{})
    def test_bbox(self):
        xml=b'<html><body><doc><page width="100" height="200"><word xMin="1" yMin="2" xMax="9" yMax="12">ABB</word></page></doc></body></html>'
        p=documents.parse_bbox(xml);self.assertEqual(p[0]['words'][0]['text'],'ABB')
