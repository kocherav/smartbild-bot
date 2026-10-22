"""Print an AST-checked mechanical patch; never edit source directly."""
import ast
from pathlib import Path

p=Path(__file__).resolve().parents[2]/'bridge.py'
s=p.read_text(); lines=s.splitlines(keepends=True); tree=ast.parse(s)
m=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
loop=next(n for n in ast.walk(m) if isinstance(n,ast.For) and isinstance(n.target,ast.Name) and n.target.id=='update')
idx=next(i for i,n in enumerate(loop.body) if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='document_job' for x in n.targets))
nodes=loop.body[idx:]; start=nodes[0].lineno; end=nodes[-1].end_lineno
old=''.join(lines[start-1:end]).rstrip('\n'); offsets=[0]
for line in lines: offsets.append(offsets[-1]+len(line))
base=offsets[start-1]; changes=[]
def point(line,col): return offsets[line-1]+len(lines[line-1].encode()[:col].decode())-base
def walk(node):
    if isinstance(node,(ast.For,ast.While,ast.AsyncFor,ast.FunctionDef,ast.AsyncFunctionDef)): return
    if isinstance(node,ast.Continue): changes.append((point(node.lineno,node.col_offset),point(node.end_lineno,node.end_col_offset)))
    for child in ast.iter_child_nodes(node): walk(child)
for n in nodes: walk(n)
converted=old
for a,b in sorted(changes,reverse=True): converted=converted[:a]+'return'+converted[b:]
helper='    def process_business_message(msg, chat_id, is_owner, is_installer):\n'+ '\n'.join(line[4:] if line.startswith('    ') else line for line in converted.split('\n'))+'\n\n'
replacement='''            if any(key in msg for key in ('document','photo','video')) or str(current_deal_ui_state(chat_id).get('pending') or '').startswith('payer_'):
                run_background_job(lambda: process_business_message(msg,chat_id,is_owner,is_installer), token,chat_id,
                                   operation='получение файла/плательщик', allow_stale=True)
            else:
                process_business_message(msg,chat_id,is_owner,is_installer)'''
proposed=s.replace(old,replacement,1).replace('    next_procurement_check = 0',helper+'    next_procurement_check = 0',1)
compile(proposed,str(p),'exec')
patch='*** Begin Patch\n*** Update File: '+str(p)+'\n@@\n-    next_procurement_check = 0\n'+'\n'.join('+'+x for x in helper.split('\n'))+'\n+    next_procurement_check = 0\n@@\n'+'\n'.join('-'+x for x in old.split('\n'))+'\n'+'\n'.join('+'+x for x in replacement.split('\n'))+'\n*** End Patch'
print(patch)
