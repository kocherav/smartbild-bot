"""Audit each remaining supplier group against fetched info mailbox evidence."""
import json,re,html
from pathlib import Path
R=Path(__file__).resolve().parent
E=R/'evidence/info_reconnected'
def normalize(s):
 return re.sub(r'[^a-zа-я0-9]','',s.lower().replace('ё','е'))
groups=json.loads((R/'reports/document_requests.json').read_text())['pending_assistant_review']
docs=json.loads((E/'documents.json').read_text()) if (E/'documents.json').exists() else []
headers=json.loads((E/'headers.json').read_text());messages=[]
for h in headers:
 p=E/(h['key']+'_'+h['uid']+'.json')
 if p.exists():
  d=json.loads(p.read_text());t=html.unescape(re.sub('<[^>]*>',' ',d.get('text','')))
  messages.append((d,normalize(t+' '+d.get('Subject','')),p))
result=[]
for g in groups:
 refs=[normalize(n) for n in g[3].split('; ') if n!='Номер отсутствует'];hits=[]
 for d in docs:
  t=normalize(d['text'])
  if g[1] in t or any(len(n)>=5 and n in t for n in refs):
   hits.append({'kind':'attachment','path':d['path'],'inn_match':g[1] in t,'refs_match':[n for n in refs if n in t]})
 for d,t,p in messages:
  if g[1] in t or any(len(n)>=5 and n in t for n in refs):
   hits.append({'kind':'message','path':str(p),'uid':d['uid'],'subject':d['Subject'],'inn_match':g[1] in t,'refs_match':[n for n in refs if n in t]})
 result.append({'supplier':g[0],'inn':g[1],'company':g[2],'refs':g[3],'amount':g[6],'candidates':hits})
 if hits:print(g[0],g[3],json.dumps(hits,ensure_ascii=False))
coverage={'mailbox':'info@innsis.ru','login':'verified','since':'2025-12-01','before':'2026-10-07','headers':len(headers),'messages_fetched':len(messages),'documents_extracted':len(docs),'pending_fetch':[{'folder':h['folder'],'uid':h['uid']} for h in headers if not (E/(h['key']+'_'+h['uid']+'.json')).exists()],'groups':len(result)}
(E/'group_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));(E/'coverage.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2));print('coverage',json.dumps(coverage,ensure_ascii=False)[:700])
