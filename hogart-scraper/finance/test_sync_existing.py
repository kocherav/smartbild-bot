import tempfile,unittest,sys
from pathlib import Path
from unittest.mock import patch
import sync_existing
from test_ledger import LedgerTests

class SyncTests(unittest.TestCase):
    def test_short_commission_label(self):
        row={'purpose':'Ком-я за перевод','counterparty_inn':'7728168971','account':'a','date':'01.10.2026','direction':'expense','counterparty_account':'b'}
        self.assertIsNotNone(sync_existing.commission_group(row))
        row['counterparty_inn']='other';self.assertIsNone(sync_existing.commission_group(row))
    def test_aggregate_matches_detailed_commissions(self):
        base={'account':'a','date':'01.10.2026','direction':'expense','counterparty_inn':'7728168971','counterparty_account':'b'}
        old=[dict(base,id='a',purpose='Комиссия',amount='39.00'),dict(base,id='b',purpose='Ком-я за перевод',amount='796.50')]
        new=[dict(base,id='c',purpose='Комиссия за день',amount='835.50')]
        self.assertEqual(sync_existing.bank_statement.remove_cross_format_duplicates(new,old),[])
if __name__=='__main__':unittest.main()
