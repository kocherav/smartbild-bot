import os
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import installation_handoff as delivery
import installation_workflow as iw
import bridge


class HandoffTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.db=os.path.join(self.tmp.name,'installations.sqlite3')
        p=patch.object(iw,'DB',self.db);p.start();self.addCleanup(p.stop)
        db=iw.connect()
        db.execute("INSERT INTO installations(deal_id,client,essence,status,installer_ref,created_at,updated_at) VALUES('890','Client','Works','approved','1000142','now','now')")
        db.commit();db.close()

    def transfer(self):
        with patch.object(iw,'local_publication_result',return_value={}):return iw.transfer('890','test')

    def test_transfer_is_idempotent_and_event_is_durable(self):
        self.transfer();self.transfer()
        with sqlite3.connect(self.db) as db:
            self.assertEqual(1,db.execute('SELECT count(*) FROM handoff_events').fetchone()[0])
            self.assertEqual(1,db.execute("SELECT count(*) FROM audit_log WHERE action='transferred'").fetchone()[0])
        self.assertEqual('transferred',iw.get_installation('890')['status'])

    def test_draft_not_transferred(self):
        with sqlite3.connect(self.db) as db:db.execute("UPDATE installations SET status='draft'")
        with self.assertRaises(ValueError):self.transfer()
        with sqlite3.connect(self.db) as db:self.assertEqual(0,db.execute('SELECT count(*) FROM handoff_events').fetchone()[0])

    def test_delivery_retries_only_failed_recipient(self):
        self.transfer();calls=[]
        def send(chat,text):calls.append(chat);return chat=='test'
        result=delivery.deliver(self.db,lambda profile:{'real','test'},send)
        self.assertEqual({'sent':1,'pending':1},result)
        calls.clear()
        delivery.deliver(self.db,lambda profile:{'real','test'},lambda chat,text:calls.append(chat) or True)
        self.assertEqual(['real'],calls)
        calls.clear()
        delivery.deliver(self.db,lambda profile:{'real','test'},lambda chat,text:calls.append(chat) or True)
        self.assertEqual([],calls)

    def test_bridge_completion_uses_transfer_and_delivery(self):
        with patch.object(bridge,'run_installation_workflow',return_value={'ok':True}) as command,patch.object(bridge,'deliver_installation_handoffs',return_value={'pending':0}) as notify:
            self.assertTrue(bridge.complete_installation_handoff('token','890','owner')['ok'])
            self.assertEqual('transfer',command.call_args.args[0]['action']);notify.assert_called_once()

    def test_transfer_failure_does_not_send(self):
        with patch.object(bridge,'run_installation_workflow',return_value={'ok':False}),patch.object(bridge,'deliver_installation_handoffs') as notify:
            self.assertFalse(bridge.complete_installation_handoff('token','890')['ok']);notify.assert_not_called()

    def test_stage_button_completes_handoff_without_second_button(self):
        state={'installation_deal_id':'890','pending':'installation_status_ready'}
        with patch.object(bridge,'current_deal_ui_state',return_value=state), \
             patch.object(bridge,'run_installation_workflow',return_value={'ok':True,'result':{'status':'approved'}}), \
             patch.object(bridge,'run_deal_browser',return_value={'ok':True}), \
             patch.object(bridge,'complete_installation_handoff',return_value={'ok':True}) as handoff, \
             patch.object(bridge,'update_deal_ui_state'),patch.object(bridge,'send_message') as send:
            bridge.handle_deal_ui('token','owner','✅ Перевести сделку в Монтаж',_background=True)
            handoff.assert_called_once_with('token','890','owner')
            self.assertNotEqual(bridge.INSTALLATION_TRANSFER_KEYBOARD,send.call_args.args[-1])

    def test_watcher_reconciles_already_seen_stage_without_touching_dialog(self):
        watch=os.path.join(self.tmp.name,'watch.json')
        with open(watch,'w') as f:json.dump({'890':'монтаж'},f)
        with patch.multiple(bridge,MEGAPLAN_DIR=self.tmp.name,PROCUREMENT_WATCH_FILE=watch), \
             patch.object(bridge,'fetch_recent_deals',return_value=[]), \
             patch.object(bridge,'run_deal_browser',return_value={'ok':True,'deals':[{'id':'890','status':'Монтаж'}]}), \
             patch.object(bridge,'current_deal_ui_state',return_value={'pending':'supplier_invoice_confirm'}), \
             patch.object(bridge,'run_installation_workflow',return_value={'ok':True,'result':{'status':'approved'}}), \
             patch.object(bridge,'complete_installation_handoff',return_value={'ok':True}) as handoff, \
             patch.object(bridge,'update_deal_ui_state') as state, \
             patch('migration_transition_guard.blocked',return_value=False):
            bridge.check_external_procurement_transitions('token','owner')
            handoff.assert_called_once_with('token','890','status-reconciliation')
            state.assert_not_called()

    def test_watcher_does_not_transfer_unapproved_sheet(self):
        watch=os.path.join(self.tmp.name,'watch.json')
        with open(watch,'w') as f:json.dump({'890':'монтаж'},f)
        with patch.multiple(bridge,MEGAPLAN_DIR=self.tmp.name,PROCUREMENT_WATCH_FILE=watch), \
             patch.object(bridge,'fetch_recent_deals',return_value=[]), \
             patch.object(bridge,'run_deal_browser',return_value={'ok':True,'deals':[{'id':'890','status':'Монтаж'}]}), \
             patch.object(bridge,'current_deal_ui_state',return_value={}), \
             patch.object(bridge,'run_installation_workflow',return_value={'ok':True,'result':{'status':'draft'}}), \
             patch.object(bridge,'complete_installation_handoff') as handoff, \
             patch('migration_transition_guard.blocked',return_value=False):
            bridge.check_external_procurement_transitions('token','owner');handoff.assert_not_called()


if __name__=='__main__':unittest.main()
