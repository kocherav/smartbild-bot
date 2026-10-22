import ast,unittest
from pathlib import Path
class RuntimePythonTests(unittest.TestCase):
 def test_all_bridge_crm_cli_calls_use_prepared_runtime(self):
  tree=ast.parse(Path(__file__).with_name('bridge.py').read_text());found=0
  for n in ast.walk(tree):
   if isinstance(n,ast.List) and len(n.elts)>1 and isinstance(n.elts[1],ast.Call):
    if 'megaplan_api.py' in ast.unparse(n.elts[1]):
     found+=1;self.assertEqual(ast.unparse(n.elts[0]),'REPORT_VENV_PY')
  self.assertGreaterEqual(found,5)
 def test_preflight_before_creation(self):
  p=Path(__file__).parent.parent/'megaplan-crm'/'megaplan_api.py';s=p.read_text().split('if __name__ == "__main__":',1)[1]
  self.assertLess(s.index('from procurement_workflow import set_deal_company'),s.index('api.create_deal('))
  self.assertIn('"no_effect": True',s)
 def test_all_python_cli_launches_use_prepared_runtime(self):
  tree=ast.parse(Path(__file__).with_name('bridge.py').read_text());found=0
  for n in ast.walk(tree):
   if isinstance(n,ast.List) and n.elts:
    first=n.elts[0]
    if isinstance(first,ast.Constant):self.assertNotIn(first.value,('python3','python'))
    if isinstance(first,ast.Name) and first.id=='REPORT_VENV_PY':found+=1
  self.assertGreaterEqual(found,15)
 def test_upload_wrapper_preserves_proven_no_effect(self):
  import json,os
  from types import SimpleNamespace
  from unittest.mock import Mock,MagicMock
  tree=ast.parse(Path(__file__).with_name('bridge.py').read_text())
  node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_deal_browser')
  result={'ok':False,'no_effect':True,'error_code':'dependency_missing','error':'missing library'}
  run=Mock(return_value=SimpleNamespace(stdout=json.dumps(result),stderr='',returncode=0))
  ns={'REPORT_VENV_PY':'/prepared/python','MEGAPLAN_DIR':'/crm','os':os,'json':json,
      'socket':MagicMock(),'subprocess':SimpleNamespace(run=run)}
  exec(compile(ast.Module(body=[node],type_ignores=[]),'bridge-wrapper','exec'),ns)
  self.assertEqual(ns['run_deal_browser']({'action':'upload_contracts'}),result)
  self.assertEqual(run.call_args.args[0][0],'/prepared/python')
