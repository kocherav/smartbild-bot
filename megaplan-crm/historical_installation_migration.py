#!/usr/bin/env python3
"""Idempotent import of already approved historical installer reports.

It never creates a Megaplan financial operation and never recalculates an old
report.  Historical quantities and amounts are copied verbatim from the
previous approved workbook into the new installation ledger.
"""
import argparse, json, os, re, sqlite3
from datetime import datetime
from tempfile import NamedTemporaryFile

from openpyxl import load_workbook
from megaplan_api import MegaplanAPI
import installation_workflow as iw

REGISTRY_PATH = os.environ.get(
    "INSTALLER_APPROVED_REPORTS_FILE",
    "/home/kocher.av/telegram-bridge/installer_approved_reports.json",
)

def n(value): return iw.norm(value)
def number(value):
    if value in (None, ''): return 0.0
    return float(str(value).replace(' ', '').replace(',', '.'))


def report_date(name):
    match = re.search(r'(\d{2}\.\d{2}\.\d{4})', str(name))
    if not match: raise ValueError(f'в имени отчёта нет даты: {name}')
    return match.group(1)


def discover(deal_id, api):
    comments = api._call('GET', f'/deal/{deal_id}/comments').get('data') or []
    result=[]
    for comment in comments:
        if 'выполнение монтажных работ' not in n(comment.get('content')): continue
        for item in comment.get('attaches') or []:
            if str(item.get('extension') or '').casefold() not in ('xlsx','xlsm'): continue
            result.append({'comment_id':str(comment['id']), 'file_id':str(item['id']),
                           'name':item.get('name') or 'Отчёт.xlsx', 'path':item.get('path') or '',
                           'date':report_date(item.get('name'))})
    return sorted(result, key=lambda x: datetime.strptime(x['date'], '%d.%m.%Y'))


def _find_header(ws, phrase):
    for row in range(1, min(ws.max_row, 150)+1):
        for col in range(1, min(ws.max_column, 20)+1):
            if phrase in n(ws.cell(row, col).value): return row
    return None


def parse_workbook(path):
    """Extract only the already accepted columns of the historical format."""
    ws=load_workbook(path, data_only=True, read_only=True).active
    header=_find_header(ws, 'позиция монтажной ведомости')
    if not header: raise ValueError('не найдена детализация по монтажной ведомости')
    cols={n(ws.cell(header,c).value):c for c in range(1,ws.max_column+1)}
    required=tuple(n(x) for x in ('позиция монтажной ведомости','ед','план кол во','расценка','закрыто сейчас','сумма отчёта'))
    def col(token):
        # `ед` must be matched as a column heading, not as a fragment of
        # "ведомости" in "Позиция монтажной ведомости".
        if token == 'ед':
            return next((v for k,v in cols.items() if k in ('ед','ед изм','единица измерения') or k.startswith('ед ')), None)
        return next((v for k,v in cols.items() if token in k), None)
    indexes={token:col(token) for token in required}
    if any(v is None for v in indexes.values()): raise ValueError('в историческом отчёте нет обязательных колонок')
    details=[]
    for row in range(header+1, ws.max_row+1):
        name=iw.clean(ws.cell(row,indexes[n('позиция монтажной ведомости')]).value)
        if not name: continue
        qty=number(ws.cell(row,indexes[n('закрыто сейчас')]).value)
        amount=number(ws.cell(row,indexes[n('сумма отчёта')]).value)
        if amount <= 0 and qty <= 0: continue
        rate=number(ws.cell(row,indexes[n('расценка')]).value)
        plan=number(ws.cell(row,indexes[n('план кол во')]).value)
        if qty > 0 and rate <= 0: rate=amount/qty
        if qty <= 0: qty=1.0; rate=amount; plan=max(plan,1.0)
        if abs(qty*rate-amount)>0.05: raise ValueError(f'не сходится сумма строки «{name}»')
        details.append({'name':name,'unit':iw.clean(ws.cell(row,indexes[n('ед')]).value) or 'усл.',
                        'plan':max(plan,qty),'rate':rate,'qty':qty,'amount':amount})
    if not details: raise ValueError('в отчёте нет принятых строк')
    # A standalone historical line is the old "Всякая всячина".  Summary totals
    # such as "Выполнение по таблице" are deliberately excluded: their detail is
    # already present below and must not be duplicated.
    summary=_find_header(ws, 'исходная строка')
    extras=[]
    if summary:
        headings={n(ws.cell(summary,c).value):c for c in range(1,ws.max_column+1)}
        name_col=next((v for k,v in headings.items() if 'исходная строка' in k),None)
        type_col=next((v for k,v in headings.items() if k=='тип'),None)
        amount_col=next((v for k,v in headings.items() if k=='сумма'),None)
        if name_col and type_col and amount_col:
            for row in range(summary+1,header):
                title=iw.clean(ws.cell(row,name_col).value); kind=n(ws.cell(row,type_col).value); amount=number(ws.cell(row,amount_col).value)
                if not title or amount<=0 or 'работа по таблице' in kind or 'выполнение по таблице' in n(title): continue
                extras.append({'name':f'Всякая всячина — {title}','unit':'усл.','plan':1.0,'rate':amount,'qty':1.0,'amount':amount})
    return {'details':details,'extras':extras,'total':round(sum(x['amount'] for x in details+extras),2)}


def dry_run(deal_id, api=None):
    api=api or MegaplanAPI(); reports=[]
    for source in discover(deal_id,api):
        item={'id':source['file_id'],'name':source['name'],'path':source['path']}
        path=iw._download_megaplan(api,item)
        try: parsed=parse_workbook(path)
        finally: os.unlink(path)
        reports.append({**source, **parsed, 'external_id':f"megaplan-comment-{source['comment_id']}-file-{source['file_id']}"})
    return {'deal_id':str(deal_id),'reports':reports,'accepted_total':round(sum(x['total'] for x in reports),2),
            'report_count':len(reports)}


def registry_plan(deal_id, registry_path=REGISTRY_PATH):
    """Read previously manager-approved report allocations without interpreting them.

    The pre-cabinet registry is authoritative for historical accepted amounts.  It
    includes several old report layouts that cannot be safely reparsed as a single
    workbook.  Each allocated row therefore becomes an immutable accepted item;
    it is deliberately *not* sent through today's report approval or payroll flow.
    """
    try:
        with open(registry_path, encoding="utf-8") as source:
            registry = json.load(source)
    except OSError as error:
        raise ValueError(f"не удалось прочитать утверждённый реестр отчётов: {error}")
    target = str(deal_id)
    reports = []
    for report in registry.get("reports") or []:
        allocation = next((item for item in report.get("deals") or []
                           if str(item.get("deal_id") or "") == target), None)
        if not allocation:
            continue
        rows = []
        for index, row in enumerate(allocation.get("rows") or [], 1):
            amount = round(number(row.get("amount")), 2)
            title = iw.clean(row.get("source"))
            if not title or amount <= 0:
                continue
            rows.append({"source": title, "amount": amount, "unit": "усл.", "qty": 1.0,
                         "key": f"registry:{report.get('id')}:{index}"})
        if not rows:
            continue
        total = round(sum(row["amount"] for row in rows), 2)
        declared = round(number(allocation.get("amount")), 2)
        # A mismatch is unsafe: old aggregate rows sometimes accidentally included
        # their own detail, so never infer which number is correct.
        if declared and abs(declared - total) > 0.01:
            raise ValueError(
                f"в утверждённом реестре отчёт {report.get('id')} для сделки №{target} "
                f"не сходится: строки {total:.2f} ₽, итог {declared:.2f} ₽"
            )
        reports.append({
            "external_id": f"registry:{report.get('id')}:deal-{target}",
            "report_id": str(report.get("id") or ""),
            "date": str(report.get("date") or ""),
            "rows": rows, "total": total,
            "source_path": str(report.get("excel_path") or report.get("source_file") or ""),
        })
    reports.sort(key=lambda item: datetime.strptime(item["date"], "%d.%m.%Y"))
    return {"deal_id": target, "reports": reports,
            "report_count": len(reports),
            "accepted_total": round(sum(item["total"] for item in reports), 2)}


def apply_registry(deal_id, actor="", handoff=False, registry_path=REGISTRY_PATH, api=None):
    """Import all approved historical rows for one deal, exactly once.

    ``handoff`` makes the *internal* historical object visible to the installer;
    it never changes the Megaplan deal status or creates an expense/payment.
    """
    api = api or MegaplanAPI()
    plan = registry_plan(deal_id, registry_path)
    if not plan["reports"]:
        raise ValueError("в утверждённом реестре нет отчётов по этой сделке")
    source = iw.deal_source(str(deal_id), api)
    if "деревян" not in iw.norm(source.get("installer_name")):
        raise ValueError("сделка не назначена Сергею Деревянко; миграция остановлена")
    db = iw.connect()
    present = db.execute("SELECT COUNT(*) FROM reports WHERE deal_id=?", (str(deal_id),)).fetchone()[0]
    if present:
        db.close()
        raise ValueError("для сделки уже есть отчёты в новом кабинете; повторный импорт запрещён")
    stamp, folder = iw.now(), iw.folder_name(source)
    # Historical objects belong in a read-only history, never in the active work
    # queue.  ``handoff`` is kept only for backward-compatible CLI use.
    status = "historical" if not handoff else "transferred"
    try:
        db.execute('''INSERT INTO installations(deal_id,client,essence,address,contact_name,contact_phone,installer_name,installer_ref,status,folder_name,folder_remote,created_at,updated_at,transferred_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
          (str(deal_id), source["client"], source["essence"], source["address"],
           source["contact_name"], source["contact_phone"], source["installer_name"],
           source["installer_ref"], status, folder, f"{iw.ONEDRIVE_ROOT}/Активные/{folder}",
           stamp, stamp, stamp if handoff else None))
        work_ids = {}
        order = 0
        for report in plan["reports"]:
            report_no = db.execute("SELECT COALESCE(MAX(report_no),0)+1 FROM reports WHERE deal_id=?", (str(deal_id),)).fetchone()[0]
            report_id = db.execute('''INSERT INTO reports(deal_id,report_no,status,report_date,raw_text,submitted_at,approved_at,approved_by,manager_comment,external_id,source_path,imported)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,1)''',
              (str(deal_id), report_no, "approved", report["date"],
               f"Исторический утверждённый отчёт из реестра: {report['report_id']}",
               stamp, stamp, actor, "Импортирован как стартовый факт; повторное начисление запрещено.",
               report["external_id"], report["source_path"])).lastrowid
            for row in report["rows"]:
                key = f"legacy:{iw.norm(row['source'])}:{row['amount']:.2f}"
                if key not in work_ids:
                    order += 1
                    work_ids[key] = db.execute('''INSERT INTO work_items(deal_id,source_key,name,unit,planned_qty,rate,sort_order)
                      VALUES(?,?,?,?,?,?,?)''',
                      (str(deal_id), key, row["source"], row["unit"], 1.0, row["amount"], order)).lastrowid
                db.execute('''INSERT INTO report_items(report_id,work_item_id,source_text,declared_qty,accepted_qty,accepted_amount,status)
                  VALUES(?,?,?,?,?,?,?)''',
                  (report_id, work_ids[key], row["source"], 1.0, 1.0, row["amount"], "accepted"))
        iw.audit(db, deal_id, "installation", deal_id, "historical_registry_migration", actor,
                 {"reports": plan["report_count"], "accepted_total": plan["accepted_total"], "handoff": handoff})
        db.commit()
        result = iw.get_installation(deal_id, db)
        result["migration"] = plan
        result["workbook"] = iw.build_workbook(deal_id, db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    iw.backup_db()
    return result


def mark_registry_migrations_historical(actor="system"):
    """Move previously imported registry objects out of the active installer queue."""
    raise ValueError('Старый массовый перевод в историю отключён: исторический отчёт не означает завершённый объект. Закрывайте только выбранный объект по решению руководителя.')


def _retired_mark_registry_migrations_historical(actor="system"):
    """Retained implementation for audit only; no CLI or bot callers."""
    db = iw.connect()
    try:
        deal_ids = [row[0] for row in db.execute(
            "SELECT DISTINCT deal_id FROM audit_log WHERE action='historical_registry_migration'"
        )]
        for deal_id in deal_ids:
            db.execute("UPDATE installations SET status='historical',updated_at=? WHERE deal_id=?",
                       (iw.now(), deal_id))
            iw.audit(db, deal_id, "installation", deal_id, "historical_visibility_fixed", actor,
                     {"status": "historical"})
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    iw.backup_db()
    return {"updated_deal_ids": deal_ids, "count": len(deal_ids)}


def apply(deal_id, actor='', copy_media=True, api=None):
    api=api or MegaplanAPI(); plan=dry_run(deal_id,api)
    if not plan['reports']: raise ValueError('исторические отчёты не найдены')
    db=iw.connect()
    existing=db.execute('SELECT COUNT(*) FROM reports WHERE deal_id=?',(str(deal_id),)).fetchone()[0]
    if existing: db.close(); raise ValueError('для сделки уже есть отчёты в новом кабинете; повторный импорт запрещён')
    src=iw.deal_source(str(deal_id),api); stamp=iw.now(); fname=iw.folder_name(src); remote_root=f'{iw.ONEDRIVE_ROOT}/Активные/{fname}'
    downloads=[]
    try:
        db.execute('''INSERT INTO installations(deal_id,client,essence,address,contact_name,contact_phone,installer_name,installer_ref,status,folder_name,folder_remote,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',(str(deal_id),src['client'],src['essence'],src['address'],src['contact_name'],src['contact_phone'],src['installer_name'],src['installer_ref'],'migration_draft',fname,remote_root,stamp,stamp))
        works={}
        for report in plan['reports']:
            for row in report['details']+report['extras']:
                key=f"legacy:{n(row['name'])}:{row['rate']:.6f}"
                prior=works.setdefault(key,{**row,'key':key,'accepted':0.0})
                prior['plan']=max(prior['plan'],row['plan']); prior['accepted']+=row['qty']
        work_ids={}
        for order,row in enumerate(works.values(),1):
            if row['accepted']>row['plan']+1e-6: row['plan']=row['accepted']
            work_ids[row['key']]=db.execute('INSERT INTO work_items(deal_id,source_key,name,unit,planned_qty,rate,sort_order) VALUES(?,?,?,?,?,?,?)',
                (str(deal_id),row['key'],row['name'],row['unit'],row['plan'],row['rate'],order)).lastrowid
        for no,report in enumerate(plan['reports'],1):
            rid=db.execute('''INSERT INTO reports(deal_id,report_no,status,report_date,raw_text,submitted_at,approved_at,approved_by,manager_comment,external_id,source_path,imported)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,1)''',(str(deal_id),no,'approved',report['date'],
              f"Исторический утверждённый отчёт из комментария Мегаплана №{report['comment_id']}.",stamp,stamp,actor,
              'Импортирован как стартовый факт; повторное начисление запрещено.',report['external_id'],f"megaplan://comment/{report['comment_id']}/file/{report['file_id']}")).lastrowid
            for row in report['details']+report['extras']:
                key=f"legacy:{n(row['name'])}:{row['rate']:.6f}"
                db.execute('INSERT INTO report_items(report_id,work_item_id,source_text,declared_qty,accepted_qty,accepted_amount,status) VALUES(?,?,?,?,?,?,?)',
                  (rid,work_ids[key],row['name'],row['qty'],row['qty'],row['amount'],'accepted'))
            file_remote=''
            if copy_media:
                local=iw._download_megaplan(api,{'id':report['file_id'],'name':report['name'],'path':report['path']}); downloads.append(local)
                file_remote=f"{remote_root}/02 Отчёты монтажника/Отчёт №{no:03d} - {report['date']}/Документы/{iw.safe(report['name'])}"
                iw.rclone_copy(local,file_remote)
            db.execute('INSERT INTO media(report_id,telegram_file_id,telegram_unique_id,local_path,original_name,mime_type,size,sha256,onedrive_remote,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
              (rid,report['file_id'],f"megaplan-file-{report['file_id']}",f"megaplan://{report['file_id']}",report['name'],'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',0,'',file_remote,iw.now()))
        iw.audit(db,deal_id,'installation',deal_id,'historical_migration',actor,{'reports':plan['report_count'],'accepted_total':plan['accepted_total']})
        db.commit(); result=iw.get_installation(deal_id,db); result['migration']=plan
        result['workbook']=iw.build_workbook(deal_id,db)
    except Exception:
        db.rollback(); raise
    finally:
        db.close()
        for path in downloads:
            try: os.unlink(path)
            except OSError: pass
    iw.backup_db(); return result


def repair_units(deal_id, api=None):
    """Repair a migration made by older parser versions without touching facts."""
    api=api or MegaplanAPI(); plan=dry_run(deal_id, api); db=iw.connect(); changed=[]
    try:
        units={}
        for report in plan['reports']:
            for row in report['details']+report['extras']:
                units[f"legacy:{n(row['name'])}:{row['rate']:.6f}"]=row['unit']
        for source_key,unit in units.items():
            row=db.execute('SELECT id,unit FROM work_items WHERE deal_id=? AND source_key=?',(str(deal_id),source_key)).fetchone()
            if row and row['unit']!=unit:
                db.execute('UPDATE work_items SET unit=? WHERE id=?',(unit,row['id']))
                changed.append({'id':row['id'],'before':row['unit'],'after':unit})
        iw.audit(db,deal_id,'installation',deal_id,'migration_units_repaired','system',{'changed':changed})
        db.commit(); path=iw.build_workbook(deal_id,db)
    except Exception:
        db.rollback(); raise
    finally: db.close()
    iw.backup_db(); return {'deal_id':str(deal_id),'changed':changed,'workbook':path}


def live_scope(deal_id, api):
    """All deal rows having an approved per-unit installation rate."""
    deal=api._call('GET',f'/deal/{deal_id}')['data']; rows=[]
    for order,row in enumerate(deal.get('positions') or [],1):
        offer=row.get('offer') or {}; rate=(offer.get('Category1000045CustomFieldSebesRabot') or {}).get('value')
        if rate is None or float(rate)<=0 or float(row.get('quantity') or 0)<=0: continue
        unit=row.get('unit') or offer.get('unit') or {}
        rows.append({'source_key':f"deal:{row['id']}",'name':iw.clean(offer.get('name')),
                     'unit':iw.clean(unit.get('name')) or 'шт.','qty':float(row['quantity']),
                     'rate':float(rate),'sort_order':order})
    if not rows: raise ValueError('в сделке нет позиций с себестоимостью работ')
    return rows


def reconcile_full_scope(deal_id, api=None):
    raise ValueError('Старое слияние по названиям отключено. Используйте installation_scope_restore с просмотром, отпечатком и явным сопоставлением; принятые суммы не пересчитываются.')


def _retired_reconcile_full_scope(deal_id, api=None):
    """Expand a historical migration to the full current installation scope.

    Historical report amounts remain immutable (`accepted_amount`).  Therefore a
    current deal rate can replace an old rate for future work without rewriting
    previously approved payments.
    """
    api=api or MegaplanAPI(); plan=dry_run(deal_id,api); scope=live_scope(deal_id,api); db=iw.connect(); changed=[]
    try:
        # First persist each old report's approved amount before changing rates.
        source_by_date={r['date']:r for r in plan['reports']}
        reports=db.execute('SELECT id,report_date FROM reports WHERE deal_id=? AND imported=1',(str(deal_id),)).fetchall()
        for report in reports:
            source=source_by_date.get(report['report_date'])
            if not source: continue
            amounts={n(x['name']):x['amount'] for x in source['details']+source['extras']}
            for item in db.execute('SELECT id,source_text FROM report_items WHERE report_id=?',(report['id'],)):
                amount=amounts.get(n(item['source_text']))
                if amount is not None:
                    db.execute('UPDATE report_items SET accepted_amount=? WHERE id=?',(amount,item['id']))
        existing=[dict(x) for x in db.execute('SELECT * FROM work_items WHERE deal_id=? AND active=1 ORDER BY id',(str(deal_id),))]
        by_name={}
        for row in existing: by_name.setdefault(n(row['name']),[]).append(row)
        for item in scope:
            matches=by_name.get(n(item['name']),[])
            if matches:
                target=matches[0]
                for duplicate in matches[1:]:
                    db.execute('UPDATE report_items SET work_item_id=? WHERE work_item_id=?',(target['id'],duplicate['id']))
                    db.execute('DELETE FROM work_items WHERE id=?',(duplicate['id'],))
                db.execute('UPDATE work_items SET source_key=?,name=?,unit=?,planned_qty=?,rate=?,sort_order=?,active=1 WHERE id=?',
                  (item['source_key'],item['name'],item['unit'],item['qty'],item['rate'],item['sort_order'],target['id']))
                changed.append({'id':target['id'],'action':'matched_to_deal'})
            else:
                ident=db.execute('INSERT INTO work_items(deal_id,source_key,name,unit,planned_qty,rate,sort_order) VALUES(?,?,?,?,?,?,?)',
                  (str(deal_id),item['source_key'],item['name'],item['unit'],item['qty'],item['rate'],item['sort_order'])).lastrowid
                changed.append({'id':ident,'action':'added_from_deal'})
        iw.audit(db,deal_id,'installation',deal_id,'full_scope_reconciled','system',{'deal_rows':len(scope),'changes':len(changed)})
        db.commit(); path=iw.build_workbook(deal_id,db)
    except Exception:
        db.rollback(); raise
    finally: db.close()
    iw.backup_db(); return {'deal_id':str(deal_id),'deal_work_rows':len(scope),'changed':changed,'workbook':path}


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('deal_id', nargs='?'); parser.add_argument('--apply',action='store_true'); parser.add_argument('--repair-units',action='store_true'); parser.add_argument('--full-scope',action='store_true'); parser.add_argument('--registry',action='store_true'); parser.add_argument('--handoff',action='store_true'); parser.add_argument('--mark-registry-history',action='store_true'); parser.add_argument('--no-media-copy',action='store_true'); args=parser.parse_args()
    if args.mark_registry_history:
        result = mark_registry_migrations_historical()
    elif not args.deal_id:
        parser.error('укажите deal_id')
    elif args.registry:
        result = apply_registry(args.deal_id, handoff=args.handoff) if args.apply else registry_plan(args.deal_id)
    else:
        result=reconcile_full_scope(args.deal_id) if getattr(args, 'full_scope', False) else (repair_units(args.deal_id) if getattr(args, 'repair_units', False) else (apply(args.deal_id,copy_media=not args.no_media_copy) if args.apply else dry_run(args.deal_id)))
    print(json.dumps(result,ensure_ascii=False,indent=2))
