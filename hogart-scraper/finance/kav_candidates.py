import json,re
from pathlib import Path
from document_review import refs
root=Path(__file__).resolve().parent
rows=json.loads((root/'reports/ledger.json').read_text());docs=json.loads((root/'evidence/kav/documents.json').read_text())
for r in rows:
 if r['direction']!='out' or r['status']!='Требует уточнения' or r['group']!='Внешняя' or r['inn'] in ('7743926877','7743151323','7728168971'):continue
 for d in docs:
  text=d['text'];rr=refs(r)
  if r['inn'] not in text or ('7743926877' if r['account'].endswith('1572') else '7743151323') not in text:continue
  if rr and not any(re.search(r'(?<![\w])'+re.escape(ref)+r'(?![\w])',text,re.I) for ref in rr):continue
  lines=[l.strip() for l in text.splitlines() if re.search(r'сч[её]т.*(?:№|N)|итого|всего к оплате|на сумму|оплатить|всего наименований',l,re.I)]
  if lines:print(r['inn'],' / '.join(rr),r['amount_cents']/100,Path(d['path']).name, ' || '.join(lines)[:900])
