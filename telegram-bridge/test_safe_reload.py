import tempfile
from pathlib import Path
from unittest.mock import Mock
import unittest
import safe_reload

class ReloadTests(unittest.TestCase):
    def test_only_valid_request_pauses_background_scheduling(self):
        with tempfile.TemporaryDirectory() as tmp:
            code=Path(tmp)/'app.py';code.write_text('value=1')
            request=Path(tmp)/'reload.json'
            self.assertFalse(safe_reload.pending_reviewed(request,code))
            safe_reload.request(request,str(code))
            self.assertTrue(safe_reload.pending_reviewed(request,code))
            code.write_text('value=2')
            self.assertFalse(safe_reload.pending_reviewed(request,code))
            request.write_text('{broken')
            self.assertFalse(safe_reload.pending_reviewed(request,code))

    def test_finance_dependency_is_part_of_reviewed_bundle(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);bot=root/'telegram-bridge';bot.mkdir()
            code=bot/'bridge.py';code.write_text('value=1')
            finance=root/'hogart-scraper/finance';finance.mkdir(parents=True)
            dependency=finance/'review_registry.py';dependency.write_text('value=1')
            request=bot/'reload.json';safe_reload.request(request,code)
            dependency.write_text('value=2')
            self.assertFalse(safe_reload.pending_reviewed(request,code))

    def test_active_worker_is_never_interrupted(self):
        with tempfile.TemporaryDirectory() as tmp:
            code=Path(tmp)/'app.py'; code.write_text('value=1'); request=str(Path(tmp)/'reload.json')
            safe_reload.request(request,str(code)); restart=Mock()
            self.assertFalse(safe_reload.apply_if_idle(request,str(code),True,restart))
            restart.assert_not_called(); self.assertTrue(Path(request).exists())
            self.assertTrue(safe_reload.apply_if_idle(request,str(code),False,restart))
            restart.assert_called_once(); self.assertFalse(Path(request).exists())
    def test_unreviewed_edit_is_not_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            code=Path(tmp)/'app.py'; code.write_text('value=1'); request=str(Path(tmp)/'reload.json')
            safe_reload.request(request,str(code)); code.write_text('value=2'); restart=Mock()
            self.assertFalse(safe_reload.apply_if_idle(request,str(code),False,restart)); restart.assert_not_called()
    def test_failed_restart_preserves_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            code=Path(tmp)/'app.py'; code.write_text('value=1'); request=str(Path(tmp)/'reload.json')
            safe_reload.request(request,str(code))
            with self.assertRaises(OSError): safe_reload.apply_if_idle(request,str(code),False,Mock(side_effect=OSError()))
            self.assertTrue(Path(request).exists())

    def test_changed_imported_module_blocks_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            code=Path(tmp)/'app.py'; code.write_text('import helper')
            helper=Path(tmp)/'helper.py';helper.write_text('value=1')
            request=str(Path(tmp)/'reload.json');safe_reload.request(request,str(code))
            helper.write_text('value=2');restart=Mock()
            self.assertFalse(safe_reload.apply_if_idle(request,str(code),False,restart));restart.assert_not_called()
            safe_reload.request(request,str(code))
            self.assertTrue(safe_reload.apply_if_idle(request,str(code),False,restart))

    def test_invalid_dependency_does_not_crash_running_poller(self):
        with tempfile.TemporaryDirectory() as tmp:
            code=Path(tmp)/'app.py';code.write_text('import helper')
            helper=Path(tmp)/'helper.py';helper.write_text('value=1')
            request=str(Path(tmp)/'reload.json');safe_reload.request(request,str(code))
            helper.write_text('def broken(');restart=Mock()
            self.assertFalse(safe_reload.apply_if_idle(request,str(code),False,restart))
            restart.assert_not_called();self.assertTrue(Path(request).exists())

if __name__=='__main__': unittest.main()
