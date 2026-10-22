from pathlib import Path as _QueuePath
if (_QueuePath(__file__).resolve().parents[1]/'data/review_registry.json').exists():
    raise SystemExit('Архивный обработчик отключён: рабочий реестр — finance/data/review_registry.json; обновление — finance/review_registry.py')
import json
from pathlib import Path
R=Path(__file__).resolve().parents[1];D=R/'evidence/mirkli65835';v=json.loads((D/'verified.json').read_text());assert not v['errors'] and len(v['operations'])==1
p=R/'evidence/finish_all/owner_questions.json';q=json.loads(p.read_text());found=[x for x in q['groups'] if x['number']==12]
if found:
 assert len(found)==1 and found[0]['invoices']=='У65 835'
 q.setdefault('resolved_groups',[]).append({**found[0],'answer':'Полностью Примавера, сделка862: 44600 ₽','operation_ids':[x['operation_id'] for x in v['operations']]});q['groups']=[x for x in q['groups'] if x['number']!=12]
j=json.loads((R/'data/posting_journal.json').read_text())['operations'];done={x['bank_operation_id'] for x in j.values() if x['state']=='linked'};q['posted_bank_rows']=len(done);q['unposted_rows']=337-len(done)-q['installer_rows'];p.write_text(json.dumps(q,ensure_ascii=False,indent=2))
lines=['ОСТАТОК ПО ВЫПИСКЕ — 06.10.2026','Нумерация вопросов сохранена. Закрыты вопросы: '+', '.join(str(x['number']) for x in q['resolved_groups']), '']
for x in q['groups']:lines.extend([f"{x['number']}. {x['supplier']} — {x['invoices'] or x['kind']}",x['payments'],x['question'],('Уже проверено: '+x['evidence']) if x['evidence'] else '', ''])
(R/'reports/Только_вопросы_по_выписке.txt').write_text('\n'.join(lines));print('Question12 resolved')
