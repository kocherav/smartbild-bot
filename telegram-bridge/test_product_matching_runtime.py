import json,unittest
from unittest.mock import patch
import product_matching_runtime as runtime
class RuntimeMatchingTests(unittest.TestCase):
 def test_isolated_cli_and_structured_result(self):
  job={'id':'x','payload':{'row':{'name':'Товар'},'line':{'source_name':'Товар другой'}}}
  text=json.dumps({'results':[{'id':'x','same':False,'confidence':50,'reason':'Не хватает данных','conflicts':[]}]})
  with patch.object(runtime.subprocess,'run') as run:
   run.return_value.returncode=0;run.return_value.stdout=json.dumps({'type':'item.completed','item':{'type':'agent_message','text':text}})
   self.assertEqual(runtime.infer([job])[0]['confidence'],50)
   cmd=run.call_args.args[0];self.assertIn('--ignore-user-config',cmd);self.assertIn('--ephemeral',cmd);self.assertIn('features.shell_tool=false',cmd)
 def test_tools_rejected(self):
  with patch.object(runtime.subprocess,'run') as run:
   run.return_value.returncode=0;run.return_value.stdout=json.dumps({'type':'item.completed','item':{'type':'mcp_tool_call'}})
   with self.assertRaises(ValueError):runtime.infer([])
