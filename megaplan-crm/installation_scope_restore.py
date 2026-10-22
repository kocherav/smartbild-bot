"""Refresh current work scope without changing approved historical report facts."""
import json
import sqlite3
from datetime import datetime,timezone
import financial_amounts
from megaplan_api import MegaplanAPI
from restore_historical_detail import digest
import re

def norm(v):return re.sub(r'[^a-zа-я0-9]+',' ',str(v or '').casefold().replace('ё','е')).strip()

def plan(path,deal,unit_names=None,retained_extras=()):
    db=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    try:
        did=str(deal['id'])
        existing=[dict(r) for r in db.execute('SELECT * FROM work_items WHERE deal_id=? ORDER BY id',(did,))]
        facts=[dict(r) for r in db.execute('SELECT ri.* FROM report_items ri JOIN reports r ON r.id=ri.report_id WHERE r.deal_id=? ORDER BY ri.id',(did,))]
        entries=MegaplanAPI.ledger_from_deal(deal)
        proposals=[];used=set();unpriced=[]
        for order,entry in enumerate(entries,1):
            entry['unit']=entry['unit'] or (unit_names or {}).get(str(entry.get('unit_id')),'')
            rate=financial_amounts.component_values(did,entry,'cost_work')['unit']
            if rate<=0:
                unpriced.append(entry['name']);continue
            if not entry['unit']:raise ValueError('Не разрешена единица измерения: '+entry['name'])
            if any(x['component']=='cost_work' for x in financial_amounts.audit_entry(did,entry)):
                raise ValueError('Требуется подтверждённая база расценки: '+entry['name'])
            key='deal:'+str(entry['offer_row_id'])
            candidates=[w for w in existing if w['source_key']==key]
            if not candidates:candidates=[w for w in existing if norm(w['name'])==norm(entry['name']) and norm(w['unit'])==norm(entry['unit'])]
            if len(candidates)>1:raise ValueError('Неоднозначное соответствие: '+entry['name'])
            old=candidates[0] if candidates else None
            if old:
                if old['id'] in used:raise ValueError('Одна старая работа соответствует двум позициям')
                used.add(old['id'])
            proposals.append({'id':old['id'] if old else None,'source_key':key,'name':entry['name'],
                'unit':entry['unit'],'planned_qty':entry['qty'],
                # An existing installation rate has already been used/approved.
                'rate':old['rate'] if old else rate,'sort_order':order,'active':old['active'] if old else 1})
        if not proposals:raise ValueError('В текущей сделке нет заполненных расценок работ')
        extras=set(retained_extras)
        if extras-used != extras:raise ValueError('Дополнительная работа уже сопоставлена спецификации')
        if extras-{w['id'] for w in existing if w['active']}:raise ValueError('Дополнительная работа не найдена')
        result={'deal_id':did,'existing':existing,'facts':facts,'proposals':proposals,
                'retained_extras':sorted(extras),
                'unmatched_existing':[w['id'] for w in existing if w['active'] and w['id'] not in used and w['id'] not in extras],
                'unpriced_positions':unpriced}
        result['fingerprint']=digest(result);return result
    finally:db.close()

def apply(path,deal,expected,actor,unit_names=None,retained_extras=()):
    db=sqlite3.connect(path);db.row_factory=sqlite3.Row
    try:
        db.execute('BEGIN IMMEDIATE')
        prepared=plan(path,deal,unit_names,retained_extras)
        if prepared['fingerprint']!=expected:raise ValueError('Монтажная база изменилась после проверки')
        if prepared['unmatched_existing']:
            raise ValueError('Сначала сопоставьте исторические работы или подтвердите их как отдельные: '+str(prepared['unmatched_existing']))
        did=prepared['deal_id'];stamp=datetime.now(timezone.utc).isoformat()
        for row in prepared['proposals']:
            values=[row[k] for k in ('source_key','name','unit','planned_qty','rate','sort_order','active')]
            if row['id']:
                db.execute('UPDATE work_items SET source_key=?,name=?,unit=?,planned_qty=?,rate=?,sort_order=?,active=? WHERE id=?',values+[row['id']])
            else:
                db.execute('INSERT INTO work_items(source_key,name,unit,planned_qty,rate,sort_order,active,deal_id) VALUES(?,?,?,?,?,?,?,?)',values+[did])
        # Unmatched approved work stays intact until its relationship is resolved;
        # never merge by fuzzy text or discard facts from a changed specification.
        actual=[dict(r) for r in db.execute('SELECT ri.* FROM report_items ri JOIN reports r ON r.id=ri.report_id WHERE r.deal_id=? ORDER BY ri.id',(did,))]
        if actual!=prepared['facts']:raise ValueError('Изменились исторические факты')
        db.execute('INSERT INTO audit_log(deal_id,entity,entity_id,action,actor,payload,created_at) VALUES(?,?,?,?,?,?,?)',
            (did,'installation',expected,'current_scope_restored',actor,json.dumps(prepared,ensure_ascii=False),stamp))
        db.execute("INSERT INTO publication_jobs(deal_id,updated_at) VALUES(?,?) ON CONFLICT(deal_id) DO UPDATE SET revision=revision+1,status='pending',updated_at=excluded.updated_at,error=NULL",(did,stamp))
        db.commit();return {'deal_id':did,'current_rows':len(prepared['proposals']),'unmatched_existing':prepared['unmatched_existing']}
    except Exception:db.rollback();raise
    finally:db.close()
