#!/usr/bin/env python3
"""Read/search Megaplan deals and perform validated, explicit state transitions.

JSON stdin actions:
  {"action":"list","limit":5|10|15}
  {"action":"search_client","query":"JetCar","limit":5}
  {"action":"search_address","query":"Москва","limit":5}
  {"action":"get","deal_id":"887"}
  {"action":"get_contract","deal_id":"887"}
  {"action":"search_employees","query":"Сергей"}
  {"action":"set_executor","deal_id":"887","employee_id":"1000010"}
  {"action":"upload_contracts","deal_id":"887","paths":["...docx","...pdf"]}
  {"action":"attach_bank_operation","deal_id":"887","operation":{...}}
  {"action":"move_status","deal_id":"887","state_id":"130"}
"""
import json
import os
import re
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
import subprocess
import fcntl
import socket
from concurrent.futures import ThreadPoolExecutor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from megaplan_api import (MegaplanAPI, MegaplanAPIError, comparable_contractor_name,
                          meaningful_contractor_tokens, natural_name_fragments)

CACHE_PATH = os.path.join(BASE_DIR, "deal_browser_cache.json")
CACHE_TTL = 900
CACHE_REFRESH_LOCK = CACHE_PATH + ".refresh.lock"
ECONOMICS_ATTACHMENTS_PATH = os.path.join(BASE_DIR, "economics_attachments.json")
ECONOMICS_ATTACHMENTS_LOCK = ECONOMICS_ATTACHMENTS_PATH + ".lock"
LIST_FIELDS = [
    "state", "contractor", "program", "manager", "description", "timeCreated", "timeUpdated",
    "price", "positionsCount", "possibleTransitions",
    "Category1000068CustomFieldAdresObEkta", "Category1000068CustomFieldIspolnitel",
]


def contract_upload_preflight():
    """Only this pre-write import boundary can prove absence of a remote effect."""
    try:
        from generate_contract import contract_data, validate_confirmed_source
        from contract_invoice import CONTRACT_SOURCES, document_text, contract_scope
        from closing_documents import validate_contract_rows
    except ImportError as exc:
        return {"ok": False, "no_effect": True, "error_code": "dependency_missing",
                "error": "Загрузчик договора не готов: " + str(exc)}
    return {"ok": True}


def megaplan_reachable(timeout=0.7):
    """Cheap guard: do not start a multi-minute refresh during a CRM outage."""
    import megaplan_transport
    return megaplan_transport.reachable(timeout=timeout)


def ref_names(value):
    if not value:
        return []
    values = value if isinstance(value, list) else [value]
    return [v.get("name") or " ".join(filter(None, [v.get("firstName"), v.get("lastName")]))
            for v in values if isinstance(v, dict)]


def money_value(value):
    return value.get("value") if isinstance(value, dict) else value


def summary(d):
    contractor = d.get("contractor") or {}
    state = d.get("state") or {}
    created = (d.get("timeCreated") or {}).get("value")
    transitions = [
        {"transition_id": t.get("id"), "state_id": (t.get("to") or {}).get("id"),
         "name": (t.get("to") or {}).get("name"), "enabled": t.get("enabled", True)}
        for t in (d.get("possibleTransitions") or []) if (t.get("to") or {}).get("id")
    ]
    return {
        "id": str(d.get("id")),
        "name": d.get("name"),
        "description": d.get("description") or "",
        "client": contractor.get("name") or " ".join(filter(None, [contractor.get("firstName"), contractor.get("lastName")])) or "не указан",
        "address": d.get("Category1000068CustomFieldAdresObEkta") or "",
        "executors": ref_names(d.get("Category1000068CustomFieldIspolnitel")),
        "status_id": str(state.get("id")) if state.get("id") is not None else None,
        "status": state.get("name") or "не указан",
        "program": (d.get("program") or {}).get("name"),
        "created_at": created,
        "updated_at": (d.get("timeUpdated") or {}).get("value"),
        "price": money_value(d.get("price")),
        "positions_count": d.get("positionsCount"),
        "transitions": transitions,
    }


def enrich_cached_deal(deal, all_deals):
    """Fill names omitted from Megaplan's compact references using this cache."""
    item = dict(deal)
    contractor_names = {}
    state_names = {}
    executor_names = {}
    for source in all_deals:
        contractor = source.get("contractor") or {}
        if contractor.get("id") is not None and contractor.get("name"):
            contractor_names[str(contractor["id"])] = contractor["name"]
        state = source.get("state") or {}
        if state.get("id") is not None and state.get("name"):
            state_names[str(state["id"])] = state["name"]
        for transition in source.get("possibleTransitions") or []:
            target = transition.get("to") or {}
            if target.get("id") is not None and target.get("name"):
                state_names[str(target["id"])] = target["name"]
        executors = source.get("Category1000068CustomFieldIspolnitel") or []
        executors = executors if isinstance(executors, list) else [executors]
        for executor in executors:
            if not isinstance(executor, dict) or executor.get("id") is None:
                continue
            name = executor.get("name") or " ".join(filter(None, [executor.get("firstName"), executor.get("lastName")]))
            if name:
                executor_names[str(executor["id"])] = name
    contractor = dict(item.get("contractor") or {})
    if contractor.get("id") is not None and not contractor.get("name"):
        contractor["name"] = contractor_names.get(str(contractor["id"]))
        item["contractor"] = contractor
    state = dict(item.get("state") or {})
    if state.get("id") is not None and not state.get("name"):
        state["name"] = state_names.get(str(state["id"]))
        item["state"] = state
    executors = item.get("Category1000068CustomFieldIspolnitel") or []
    was_list = isinstance(executors, list)
    enriched_executors = []
    for source in (executors if was_list else [executors]):
        executor = dict(source) if isinstance(source, dict) else source
        if isinstance(executor, dict) and executor.get("id") is not None and not executor.get("name"):
            executor["name"] = executor_names.get(str(executor["id"]))
        enriched_executors.append(executor)
    if executors:
        item["Category1000068CustomFieldIspolnitel"] = enriched_executors if was_list else enriched_executors[0]
    transitions = []
    for source in item.get("possibleTransitions") or []:
        transition = dict(source)
        target = dict(transition.get("to") or {})
        if target.get("id") is not None and not target.get("name"):
            target["name"] = state_names.get(str(target["id"]))
            transition["to"] = target
        transitions.append(transition)
    if transitions:
        item["possibleTransitions"] = transitions
    return item


def fetch_all(api, force=False):
    if not force and os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, encoding="utf-8") as f:
                cached = json.load(f)
            # Serve the complete last-known list immediately. Refresh an old cache in
            # a detached process so a menu click never waits while 800+ deals are read.
            if (time.time() - os.path.getmtime(CACHE_PATH) >= CACHE_TTL
                    and megaplan_reachable()):
                subprocess.Popen(
                    [sys.executable, os.path.abspath(__file__), "--refresh-cache"],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            return cached
        except (OSError, json.JSONDecodeError):
            pass
    deals = []
    params = {"limit": 100, "fields": LIST_FIELDS}
    while True:
        result = api._call("GET", "/deal", params=params)
        data = result.get("data") or []
        deals.extend(data)
        if not data or not result.get("meta", {}).get("pagination", {}).get("hasMoreNext"):
            break
        params = {"limit": 100, "fields": LIST_FIELDS,
                  "pageAfter": {"contentType": "Deal", "id": data[-1]["id"]}}
    deals.sort(key=lambda d: int(d["id"]), reverse=True)
    tmp = f"{CACHE_PATH}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(deals, f, ensure_ascii=False)
    os.replace(tmp, CACHE_PATH)
    return deals


def refresh_cache_background():
    os.environ['MEGAPLAN_PRIORITY']='background'
    with open(CACHE_REFRESH_LOCK, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        fetch_all(MegaplanAPI(), force=True)


def update_cached_deal(updated):
    """Refresh one cached deal without re-reading the entire CRM after a transition."""
    try:
        with open(CACHE_PATH, encoding="utf-8") as source:
            deals = json.load(source)
    except (OSError, json.JSONDecodeError):
        return
    updated_id = str(updated.get("id"))
    deals = [updated if str(deal.get("id")) == updated_id else deal for deal in deals]
    with open(CACHE_PATH, "w", encoding="utf-8") as target:
        json.dump(deals, target, ensure_ascii=False)


def search_employees(api, query):
    query = str(query or "").strip()
    if not query:
        raise ValueError("укажите имя или фамилию сотрудника")
    found = api._call("GET", "/employee/search", params={"q": query, "limit": 30}).get("data") or []
    employees = []
    for item in found:
        name = item.get("name") or " ".join(filter(None, [item.get("lastName"), item.get("firstName"), item.get("middleName")]))
        if item.get("id") is not None and name:
            employees.append({"id": str(item["id"]), "name": name})
    return {"ok": True, "employees": employees}


def set_executor(api, deal_id, employee_id):
    deal_id, employee_id = str(deal_id), str(employee_id)
    candidate = api._call("GET", f"/employee/{employee_id}").get("data") or {}
    if str(candidate.get("id") or "") != employee_id:
        raise ValueError("сотрудник не найден")
    api._call("POST", f"/deal/{deal_id}", json_body={
        "contentType": "Deal",
        "Category1000068CustomFieldIspolnitel": [
            {"contentType": "Employee", "id": employee_id},
        ],
    })
    updated = api._call("GET", f"/deal/{deal_id}")["data"]
    assigned = updated.get("Category1000068CustomFieldIspolnitel") or []
    assigned = assigned if isinstance(assigned, list) else [assigned]
    if [str(item.get("id")) for item in assigned if isinstance(item, dict)] != [employee_id]:
        raise ValueError("обратное чтение не подтвердило исполнителя")
    assigned = [dict(item) if isinstance(item, dict) else item for item in assigned]
    employee_name = candidate.get("name") or " ".join(filter(None, [candidate.get("lastName"), candidate.get("firstName"), candidate.get("middleName")]))
    for item in assigned:
        if isinstance(item, dict) and str(item.get("id")) == employee_id and not item.get("name"):
            item["name"] = employee_name
    updated["Category1000068CustomFieldIspolnitel"] = assigned
    update_cached_deal(updated)
    return {"ok": True, "deal": summary(updated), "employee": {
        "id": employee_id,
        "name": employee_name
    }}


def hydrate(api, deals):
    # Detail calls are independent. Fetching 5-15 cards sequentially made a menu
    # click wait tens of seconds on normal Megaplan latency.
    def fetch(deal):
        return MegaplanAPI()._call("GET", f"/deal/{deal['id']}")["data"]

    with ThreadPoolExecutor(max_workers=min(8, len(deals) or 1)) as pool:
        return list(pool.map(fetch, deals))


def contractor_ids(api, query):
    ids = set()
    for endpoint in ("/contractorCompany/search", "/contractorHuman/search"):
        try:
            for item in api._call("GET", endpoint, params={"q": query}).get("data") or []:
                if item.get("id") is not None:
                    ids.add(str(item["id"]))
        except MegaplanAPIError:
            continue
    return ids


def natural_match_score(query, value):
    """Rank a stored client/object string against a free-form user sentence."""
    query_tokens = meaningful_contractor_tokens(query)
    value_tokens = meaningful_contractor_tokens(value)
    overlap = query_tokens & value_tokens
    if not overlap:
        return 0
    compact_query = comparable_contractor_name(query)
    compact_value = comparable_contractor_name(value)
    exact_bonus = 100 if compact_value and compact_value in compact_query else 0
    coverage = int(50 * len(overlap) / max(1, len(value_tokens)))
    return exact_bonus + coverage + sum(min(len(token), 20) for token in overlap)


def comparable_client_name(value):
    """Normalize Russian/Latin spelling used for the same brand (e.g. Джеткар/JetCar)."""
    return comparable_contractor_name(value)


def replace_economics_attachment(api, deal_id, path, data_fingerprint=None):
    """Publish one current economics workbook and retire the previous bot copy.

    The new attachment is created and verified first.  Therefore a failed upload
    never removes the last usable report from the deal.  When the numbers are
    unchanged (same ``data_fingerprint``) and the published file is still in the
    deal, nothing is written: a read button must not rewrite CRM files.
    """
    with open(ECONOMICS_ATTACHMENTS_LOCK, "a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            with open(ECONOMICS_ATTACHMENTS_PATH, encoding="utf-8") as source:
                registry = json.load(source)
        except FileNotFoundError:
            registry = {}

        def save_registry():
            fd,tmp=tempfile.mkstemp(prefix='.economics-',dir=os.path.dirname(ECONOMICS_ATTACHMENTS_PATH))
            try:
                with os.fdopen(fd,'w',encoding='utf-8') as target:
                    json.dump(registry,target,ensure_ascii=False,indent=2,allow_nan=False)
                    target.flush(); os.fsync(target.fileno())
                os.replace(tmp,ECONOMICS_ATTACHMENTS_PATH)
            finally:
                if os.path.exists(tmp): os.unlink(tmp)

        previous = registry.get(str(deal_id)) or {}
        if previous.get('pending_comment_create'):
            raise ValueError('Результат первой публикации экономики неизвестен. Требуется сверка комментария по сохранённому ID файла; повторное создание остановлено')
        if data_fingerprint and previous.get('data_fingerprint') == data_fingerprint and previous.get('file_id'):
            current = api._call("GET", f"/deal/{deal_id}/allFiles", params={"limit": 100}).get("data") or []
            if str(previous['file_id']) in {str(item.get("id")) for item in current}:
                return {**previous, "unchanged": True}
            # The registered copy disappeared from the deal: publish it once more.
        uploaded = api.upload_file(path)
        comment_payload = {
            "contentType": "Comment",
            "subject": {"contentType": "Deal", "id": str(deal_id)},
            "content": (
                "Актуальная экономика сделки: план, фактические закупки, прогноз "
                "себестоимости и прибыли. Файл обновляется ботом при изменении данных."
            ),
            "attaches": [{"contentType": "File", "id": str(uploaded["id"])}],
        }
        old_comment_id = str(previous.get("comment_id") or "")
        def create_comment():
            registry[str(deal_id)]={**previous,'pending_comment_create':True,'pending_file_id':str(uploaded['id'])}
            save_registry()
            created=api._call('POST',f'/deal/{deal_id}/comments',json_body=comment_payload).get('data') or {}
            if not created.get('id'): raise ValueError('Мегаплан не подтвердил ID публикации экономики')
            registry[str(deal_id)]={'comment_id':str(created['id']),'file_id':str(uploaded['id']),
                                   'filename':uploaded.get('name') or os.path.basename(path)}
            save_registry()
            return created
        # A previous comment may belong to another account. A forbidden edit
        # trips the shared circuit breaker and prevents a fallback create.
        # Publish a new version directly; retire the known old file only after
        # the new attachment has been verified below.
        comment = create_comment()
        files = api._call("GET", f"/deal/{deal_id}/allFiles", params={"limit": 100}).get("data") or []
        if str(uploaded["id"]) not in {str(item.get("id")) for item in files}:
            raise ValueError("Мегаплан не подтвердил файл экономики в карточке сделки")

        # Editing a comment is forbidden when an earlier bot run used another
        # Megaplan account.  In that case we have to publish a new comment, but
        # the old attachment otherwise remains in allFiles under the *same name*.
        # Users then cannot tell the current workbook from a stale one.  Once the
        # new upload has been verified, remove only obsolete bot-generated
        # economics files for this exact deal.  Historical reports with other
        # names are deliberately left untouched.
        managed_name = f"Экономика сделки №{deal_id} — план и факт.xlsx"
        for item in files:
            stale_id = str(item.get("id") or "")
            if (stale_id and stale_id == str(previous.get('file_id') or '') and stale_id != str(uploaded["id"])
                    and str(item.get("name") or "") == managed_name):
                try:
                    api._call("DELETE", f"/file/{stale_id}")
                except MegaplanAPIError:
                    # The current report is already safely attached.  Lack of
                    # rights to retire an old file must not break recalculation.
                    pass

        registry[str(deal_id)] = {
            "comment_id": str(comment.get("id") or old_comment_id),
            "file_id": str(uploaded["id"]),
            "filename": uploaded.get("name") or os.path.basename(path),
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **({"data_fingerprint": data_fingerprint} if data_fingerprint else {}),
        }
        save_registry()
        return registry[str(deal_id)]


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--refresh-cache":
        refresh_cache_background()
        return
    spec = json.load(sys.stdin)
    action = spec.get("action")
    api = MegaplanAPI()
    if action == "get":
        deal = api._call("GET", f"/deal/{spec['deal_id']}")["data"]
        print(json.dumps({"ok": True, "deal": summary(deal)}, ensure_ascii=False))
        return
    if action == "get_cached":
        deals = fetch_all(api)
        deal = next((item for item in deals if str(item.get("id")) == str(spec["deal_id"])), None)
        if not deal:
            raise ValueError("сделка не найдена в локальном списке")
        print(json.dumps({"ok": True, "deal": summary(enrich_cached_deal(deal, deals)), "cached": True}, ensure_ascii=False))
        return
    if action == "get_many":
        ids = {str(value) for value in spec.get("deal_ids") or []}
        deals = [deal for deal in fetch_all(api) if str(deal.get("id")) in ids]
        print(json.dumps({"ok": True, "deals": [summary(d) for d in hydrate(api, deals)]}, ensure_ascii=False))
        return
    if action == "get_many_cached":
        # Background stage watchers only need fields already present in
        # LIST_FIELDS (most importantly state).  Do not turn a periodic check
        # into one live HTTP request per deal.
        ids = {str(value) for value in spec.get("deal_ids") or []}
        all_deals = fetch_all(api)
        deals = [deal for deal in all_deals if str(deal.get("id")) in ids]
        print(json.dumps({"ok": True, "deals": [summary(enrich_cached_deal(d, all_deals)) for d in deals]}, ensure_ascii=False))
        return
    if action == "get_contract":
        deal_id = str(spec["deal_id"])
        files = api._call("GET", f"/deal/{deal_id}/allFiles", params={"limit": 100}).get("data") or []
        contracts = [
            f for f in files
            if "договор" in (f.get("name") or "").casefold()
            or "contract" in (f.get("name") or "").casefold()
        ]
        if spec.get("format"):
            wanted = "." + str(spec["format"]).strip().casefold().lstrip(".")
            contracts = [f for f in contracts if os.path.splitext(f.get("name") or "")[1].casefold() == wanted]
        if not contracts:
            print(json.dumps({"ok": False, "error": "в сделке пока нет сформированного файла договора"}, ensure_ascii=False))
            return
        contracts.sort(
            key=lambda f: ((f.get("timeCreated") or {}).get("value") or "", int(f.get("id") or 0)),
            reverse=True,
        )
        selected = contracts[0]
        remote_path = selected.get("path")
        if not remote_path:
            raise ValueError("у файла договора нет ссылки для скачивания")
        safe_name = re.sub(
            r"[^0-9A-Za-zА-Яа-яЁё._ -]+", "_",
            selected.get("name") or f"Договор_{deal_id}.docx",
        )
        suffix = os.path.splitext(safe_name)[1] or ".bin"
        fd, local_path = tempfile.mkstemp(prefix=f"deal-{deal_id}-contract-", suffix=suffix)
        os.close(fd)
        url = remote_path if remote_path.startswith("http") else f"https://{api.domain}{remote_path}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api.token}"})
        try:
            import megaplan_transport
            with megaplan_transport.urlopen(req, timeout=60) as response, open(local_path, "wb") as out:
                out.write(response.read())
        except Exception:
            try:
                os.remove(local_path)
            except OSError:
                pass
            raise
        print(json.dumps({
            "ok": True, "path": local_path, "filename": safe_name,
            "file_id": str(selected.get("id")),
        }, ensure_ascii=False))
        return
    if action == "update_contract_fields":
        deal_id = str(spec["deal_id"])
        payload = {"contentType": "Deal"}
        if spec.get("contract_date"):
            parsed = datetime.strptime(str(spec["contract_date"]), "%d.%m.%Y")
            payload["Category1000068CustomFieldDataDogovora"] = {
                "contentType": "DateOnly", "year": parsed.year,
                "month": parsed.month - 1, "day": parsed.day,
            }
        if spec.get("address"):
            payload["Category1000068CustomFieldAdresObEkta"] = str(spec["address"]).strip()
        if len(payload) == 1:
            raise ValueError("не переданы дата договора или адрес объекта")
        api._call("POST", f"/deal/{deal_id}", json_body=payload)
        updated = api._call("GET", f"/deal/{deal_id}")["data"]
        update_cached_deal(updated)
        print(json.dumps({"ok": True, "deal": summary(updated)}, ensure_ascii=False))
        return
    if action == "change_contractor":
        deal_id = str(spec["deal_id"])
        contractor_id = str(spec["contractor_id"])
        contractor_type = str(spec.get("contractor_type") or "")
        if contractor_type not in ("ContractorCompany", "ContractorHuman"):
            raise ValueError("нужен тип клиента ContractorCompany или ContractorHuman")
        # Only the client reference is changed; positions, prices, documents and
        # custom fields remain untouched in Megaplan.
        api._call("POST", f"/deal/{deal_id}", json_body={
            "contentType": "Deal",
            "contractor": {"contentType": contractor_type, "id": contractor_id},
        })
        updated = api._call("GET", f"/deal/{deal_id}")["data"]
        update_cached_deal(updated)
        print(json.dumps({"ok": True, "deal": summary(updated)}, ensure_ascii=False))
        return
    if action == "search_employees":
        print(json.dumps(search_employees(api, spec.get("query")), ensure_ascii=False))
        return
    if action == "set_executor":
        print(json.dumps(set_executor(api, spec["deal_id"], spec["employee_id"]), ensure_ascii=False))
        return
    if action == "upload_contracts":
        readiness = contract_upload_preflight()
        if not readiness['ok']:
            print(json.dumps(readiness, ensure_ascii=False))
            return
        deal_id = str(spec["deal_id"])
        paths = [os.path.realpath(str(path)) for path in spec.get("paths") or []]
        if len(paths) != 2 or {os.path.splitext(path)[1].casefold() for path in paths} != {".docx", ".pdf"}:
            raise ValueError("для загрузки нужны договоры в форматах DOCX и PDF")
        for path in paths:
            if not os.path.isfile(path):
                raise ValueError(f"файл договора не найден: {os.path.basename(path)}")
            if not path.startswith("/tmp/contract-"):
                raise ValueError("разрешена загрузка только договоров, сформированных ботом")
        deal = api._call("GET", f"/deal/{deal_id}")["data"]
        from generate_contract import contract_data, validate_confirmed_source
        from contract_invoice import CONTRACT_SOURCES, document_text, contract_scope
        if (CONTRACT_SOURCES / (deal_id + '-source.json')).exists():
            data = contract_data(deal, {})
            validate_confirmed_source(api, data)
            from closing_documents import validate_contract_rows
            for path in paths:
                validate_contract_rows(document_text(path), contract_scope(data['positions'], deal_id))
        uploaded = [api.upload_file(path) for path in paths]
        attaches = [{"contentType": "File", "id": str(item["id"])} for item in uploaded]
        comment = api._call("POST", f"/deal/{deal_id}/comments", json_body={
            "contentType": "Comment",
            "subject": {"contentType": "Deal", "id": deal_id},
            "content": "Договоры сформированы и загружены Telegram-ботом: редактируемый Word без подписи и PDF с подписью и печатью.",
            "attaches": attaches,
        }).get("data") or {}
        files = api._call("GET", f"/deal/{deal_id}/allFiles", params={"limit": 100}).get("data") or []
        uploaded_ids = {str(item["id"]) for item in uploaded}
        confirmed_ids = {str(item.get("id")) for item in files if str(item.get("id")) in uploaded_ids}
        if confirmed_ids != uploaded_ids:
            raise ValueError("Мегаплан принял комментарий, но не подтвердил оба файла в карточке сделки")
        uploaded_files = [
            {"id": str(item["id"]), "name": item.get("name") or os.path.basename(path)}
            for item, path in zip(uploaded, paths)
        ]
        print(json.dumps({
            "ok": True,
            "deal_id": deal_id,
            "comment_id": str(comment.get("id") or ""),
            "files": uploaded_files,
        }, ensure_ascii=False))
        return
    if action == "upload_execution_file":
        deal_id = str(spec["deal_id"])
        path = os.path.realpath(str(spec["path"]))
        if not os.path.isfile(path) or os.path.splitext(path)[1].casefold() != ".xlsx":
            raise ValueError("файл выполнения не найден или имеет неверный формат")
        if not path.startswith("/tmp/installer-report-deal-"):
            raise ValueError("разрешена загрузка только файла выполнения, сформированного ботом")
        api._call("GET", f"/deal/{deal_id}")
        uploaded = api.upload_file(path)
        comment = api._call("POST", f"/deal/{deal_id}/comments", json_body={
            "contentType": "Comment",
            "subject": {"contentType": "Deal", "id": deal_id},
            "content": f"Выполнение монтажных работ за отчётный период. Файл: {os.path.basename(path)}",
            "attaches": [{"contentType": "File", "id": str(uploaded["id"])}],
        }).get("data") or {}
        files = api._call("GET", f"/deal/{deal_id}/allFiles", params={"limit": 100}).get("data") or []
        if str(uploaded["id"]) not in {str(item.get("id")) for item in files}:
            raise ValueError("Мегаплан принял комментарий, но не подтвердил файл в карточке сделки")
        print(json.dumps({"ok": True, "deal_id": deal_id, "file_id": str(uploaded["id"]), "comment_id": str(comment.get("id") or ""), "name": uploaded.get("name") or os.path.basename(path)}, ensure_ascii=False))
        return
    if action == "upload_procurement_file":
        deal_id = str(spec["deal_id"])
        path = os.path.realpath(str(spec["path"]))
        if not os.path.isfile(path) or os.path.splitext(path)[1].casefold() != ".xlsx":
            raise ValueError("закупочная ведомость не найдена или имеет неверный формат")
        if not path.startswith(f"/tmp/procurement-{deal_id}-"):
            raise ValueError("разрешена загрузка только закупочной ведомости, сформированной ботом")
        api._call("GET", f"/deal/{deal_id}")
        uploaded = api.upload_file(path)
        comment = api._call("POST", f"/deal/{deal_id}/comments", json_body={
            "contentType": "Comment", "subject": {"contentType": "Deal", "id": deal_id},
            "content": "Закупочная ведомость: оборудование, материалы, заказы поставщикам и состояние счетов.",
            "attaches": [{"contentType": "File", "id": str(uploaded["id"])}],
        }).get("data") or {}
        print(json.dumps({"ok": True, "deal_id": deal_id, "file_id": str(uploaded["id"]),
                          "filename": uploaded.get("name") or os.path.basename(path),
                          "comment_id": str(comment.get("id") or "")}, ensure_ascii=False))
        return
    if action == "upload_supplier_invoice":
        deal_id = str(spec["deal_id"])
        path = os.path.realpath(str(spec["path"]))
        incoming_root = os.path.realpath(os.path.expanduser("~/hogart-scraper/incoming")) + os.sep
        if not os.path.isfile(path) or not path.startswith(incoming_root):
            raise ValueError("исходный счёт поставщика не найден")
        if os.path.splitext(path)[1].casefold() not in (".pdf", ".doc", ".docx", ".xls", ".xlsx"):
            raise ValueError("неподдерживаемый формат счёта поставщика")
        api._call("GET", f"/deal/{deal_id}")
        uploaded = api.upload_file(path)
        number = str(spec.get("number") or "б/н")
        supplier = str(spec.get("supplier") or "поставщик не указан")
        comment = api._call("POST", f"/deal/{deal_id}/comments", json_body={
            "contentType": "Comment", "subject": {"contentType": "Deal", "id": deal_id},
            "content": f"Счёт поставщика №{number}: {supplier}. Учтён в фактической себестоимости закупки.",
            "attaches": [{"contentType": "File", "id": str(uploaded["id"])}],
        }).get("data") or {}
        print(json.dumps({"ok": True, "deal_id": deal_id, "file_id": str(uploaded["id"]),
                          "filename": uploaded.get("name") or os.path.basename(path),
                          "comment_id": str(comment.get("id") or "")}, ensure_ascii=False))
        return
    if action == "upload_supplier_closing":
        deal_id = str(spec["deal_id"])
        path = os.path.realpath(str(spec["path"]))
        incoming_root = os.path.realpath(os.path.expanduser("~/hogart-scraper/incoming")) + os.sep
        if not os.path.isfile(path) or not path.startswith(incoming_root):
            raise ValueError("исходный закрывающий документ не найден")
        if os.path.splitext(path)[1].casefold() not in (".pdf", ".doc", ".docx", ".xls", ".xlsx"):
            raise ValueError("неподдерживаемый формат закрывающего документа")
        api._call("GET", f"/deal/{deal_id}")
        uploaded = api.upload_file(path)
        number = str(spec.get("invoice_number") or "б/н")
        doc_type = str(spec.get("document_type") or "УПД")
        comment = api._call("POST", f"/deal/{deal_id}/comments", json_body={
            "contentType": "Comment", "subject": {"contentType": "Deal", "id": deal_id},
            "content": f"{doc_type} поставщика по счёту №{number}. Документ привязан к закупке.",
            "attaches": [{"contentType": "File", "id": str(uploaded["id"])}],
        }).get("data") or {}
        print(json.dumps({"ok": True, "deal_id": deal_id, "file_id": str(uploaded["id"]),
                          "filename": uploaded.get("name") or os.path.basename(path),
                          "comment_id": str(comment.get("id") or "")}, ensure_ascii=False))
        return
    if action == "upsert_profitability_file":
        deal_id = str(spec["deal_id"])
        path = os.path.realpath(str(spec["path"]))
        if not os.path.isfile(path) or os.path.splitext(path)[1].casefold() != ".xlsx":
            raise ValueError("файл экономики не найден или имеет неверный формат")
        allowed_name = os.path.basename(path).startswith(f"Экономика сделки №{deal_id}")
        if not allowed_name:
            raise ValueError("разрешена загрузка только экономики, сформированной ботом")
        api._call("GET", f"/deal/{deal_id}")
        stored = replace_economics_attachment(api, deal_id, path, spec.get("data_fingerprint"))
        print(json.dumps({"ok": True, "deal_id": deal_id, **stored}, ensure_ascii=False))
        return
    if action == "record_procurement_receipt":
        deal_id = str(spec["deal_id"])
        name = str(spec.get("name") or "Позиция")
        qty = float(spec.get("qty") or 0)
        unit = str(spec.get("unit") or "")
        if qty <= 0:
            raise ValueError("количество поступления должно быть больше нуля")
        api._call("GET", f"/deal/{deal_id}")
        comment = api._call("POST", f"/deal/{deal_id}/comments", json_body={
            "contentType": "Comment", "subject": {"contentType": "Deal", "id": deal_id},
            "content": f"Поступление по закупке: {name} — {qty:g} {unit}. Записано Telegram-ботом.",
        }).get("data") or {}
        print(json.dumps({"ok": True, "deal_id": deal_id, "comment_id": str(comment.get("id") or "")}, ensure_ascii=False))
        return
    if action == "close_procurement":
        deal_id = str(spec["deal_id"])
        api._call("GET", f"/deal/{deal_id}")
        comment = api._call("POST", f"/deal/{deal_id}/comments", json_body={
            "contentType": "Comment", "subject": {"contentType": "Deal", "id": deal_id},
            "content": "Закупка закрыта: счета поставщиков учтены, оплаты подтверждены, оборудование и материалы получены полностью.",
        }).get("data") or {}
        print(json.dumps({"ok": True, "deal_id": deal_id, "comment_id": str(comment.get("id") or "")}, ensure_ascii=False))
        return
    if action == "attach_bank_operation":
        deal_id = str(spec["deal_id"])
        operation = spec.get("operation") or {}
        api._call("GET", f"/deal/{deal_id}")
        direction = "Расход" if operation.get("direction") == "expense" else "Приход"
        content = (
            f"Банковская операция привязана Telegram-ботом.\n"
            f"{direction}: {operation.get('amount')} руб.\n"
            f"Дата: {operation.get('date')}; документ: {operation.get('document_number') or 'б/н'}.\n"
            f"Контрагент: {operation.get('counterparty') or 'не указан'}; "
            f"ИНН: {operation.get('counterparty_inn') or 'не указан'}.\n"
            f"Назначение: {operation.get('purpose') or 'не указано'}.\n"
            f"ID банковской операции: {operation.get('id')}"
        )
        comment = api._call("POST", f"/deal/{deal_id}/comments", json_body={
            "contentType": "Comment", "subject": {"contentType": "Deal", "id": deal_id},
            "content": content,
        }).get("data") or {}
        print(json.dumps({"ok": True, "deal_id": deal_id,
                          "comment_id": str(comment.get("id") or "")}, ensure_ascii=False))
        return
    if action == "move_status":
        deal = api._call("GET", f"/deal/{spec['deal_id']}")["data"]
        target = str(spec["state_id"])
        # Retrying a confirmed transition is safe: if the first POST succeeded
        # but its verification response was lost, report the already-reached
        # state instead of trying to apply a second transition.
        if str((deal.get("state") or {}).get("id")) == target:
            update_cached_deal(deal)
            print(json.dumps({"ok": True, "deal": summary(deal), "already_applied": True}, ensure_ascii=False))
            return
        allowed = {str((t.get("to") or {}).get("id")): t for t in deal.get("possibleTransitions") or [] if t.get("enabled", True)}
        if target not in allowed:
            raise ValueError("выбранный переход сейчас недоступен для этой сделки")
        # `state` is ignored when an existing deal is edited. Workflow movement has
        # its own endpoint and accepts the ProgramTransition itself, not ProgramState.
        transition = allowed[target]
        api._call("POST", f"/deal/{spec['deal_id']}/applyTransition", json_body={
            "contentType": "ProgramTransition", "id": str(transition["id"]),
        })
        updated = api._call("GET", f"/deal/{spec['deal_id']}")["data"]
        actual = str((updated.get("state") or {}).get("id"))
        if actual != target:
            actual_name = (updated.get("state") or {}).get("name") or "неизвестный"
            raise ValueError(
                f"Мегаплан не применил переход: после записи фактический статус «{actual_name}»"
            )
        update_cached_deal(updated)
        print(json.dumps({"ok": True, "deal": summary(updated)}, ensure_ascii=False))
        return

    deals = fetch_all(api)
    if action == "list":
        found = deals[:max(1, min(int(spec.get("limit", 5)), 15))]
    elif action == "search_any":
        query = str(spec.get("query") or "").strip().casefold().replace("ё", "е")
        if not query:
            raise ValueError("пустая строка поиска")
        def searchable(deal):
            contractor = deal.get("contractor") or {}
            values = [
                deal.get("name"), contractor.get("name"),
                " ".join(filter(None, [contractor.get("firstName"), contractor.get("lastName")])),
                deal.get("Category1000068CustomFieldAdresObEkta"), (deal.get("program") or {}).get("name"),
            ]
            return " ".join(str(value or "") for value in values).casefold().replace("ё", "е")
        ranked = [(natural_match_score(query, searchable(deal)), deal) for deal in deals]
        found = [deal for score, deal in sorted(ranked, key=lambda row: (row[0], int(row[1].get('id') or 0)), reverse=True) if score]
        found = found[:max(1, min(int(spec.get("limit", 10)), 20))]
    elif action in ("search_client", "search_address"):
        query = str(spec.get("query") or "").strip().casefold()
        if not query:
            raise ValueError("пустая строка поиска")
        if action == "search_client":
            names_by_id = {}
            for deal in deals:
                contractor = deal.get("contractor") or {}
                name = contractor.get("name") or " ".join(filter(None, [
                    contractor.get("firstName"), contractor.get("lastName"),
                ]))
                if contractor.get("id") is not None and name:
                    names_by_id[str(contractor["id"])] = name
            matched_ids = {contractor_id for contractor_id, name in names_by_id.items()
                           if natural_match_score(query, name)}
            # The live contractor lookup covers names absent from every compact deal
            # reference; local phonetic matching covers Джеткар <-> JetCar.
            if not matched_ids:
                for fragment in natural_name_fragments(query):
                    matched_ids.update(contractor_ids(api, fragment))
            def client_id(deal):
                contractor = deal.get("contractor") or {}
                return str(contractor.get("id"))
            found = [d for d in deals if client_id(d) in matched_ids]
            # Compact Megaplan references often contain only contractor.id.
            # Reuse a full occurrence of that same contractor already present
            # in the cache, without paying for one HTTP request per deal.
            enriched = []
            for deal in found:
                item = dict(deal)
                contractor = dict(item.get("contractor") or {})
                known_name = names_by_id.get(str(contractor.get("id")))
                if known_name and not contractor.get("name"):
                    contractor["name"] = known_name
                    item["contractor"] = contractor
                enriched.append(item)
            found = enriched
        else:
            found = [d for d in deals if query in summary(d)["address"].casefold()]
        total_count = len(found)
        found = found[:max(1, min(int(spec.get("limit", 15)), 15))]
    else:
        raise ValueError("неизвестное действие")
    # LIST_FIELDS already contains everything needed by every list/search card.
    # Opening the selected deal uses action=get and is live.  Re-fetching each
    # search result here made an ordinary client search issue up to 15 extra CRM
    # requests and fail whenever just one card was slow.
    result_deals = [enrich_cached_deal(item, deals) for item in found]
    print(json.dumps({"ok": True, "deals": [summary(d) for d in result_deals],
                      "total_count": locals().get("total_count", len(found))}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)
    except MegaplanAPIError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)
    except Exception as e:
        # The bridge must always receive structured output; an uncaught network
        # timeout previously became an empty stdout and an unhelpful
        # "list index out of range" loop in the parent process.
        print(json.dumps({"ok": False, "error": f"техническая ошибка Мегаплана: {e}"}, ensure_ascii=False))
        sys.exit(1)
