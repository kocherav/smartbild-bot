#!/usr/bin/env python3
"""
Thin client for Megaplan CRM's official REST API v3 (cclimat.megaplan.ru).
Docs: https://dev.megaplan.ru/apiv3/index.html

Auth: plain username/password against POST /api/v3/auth/access_token works directly on
this account (confirmed 2026-08-22) - no AccessId/SecretKey HMAC signing needed, that's
the older deprecated v1 API (dev.megaplan.ru/api/API_authorization.html). Token cached
in token.json (like hogart_api.py/daichi_api.py), re-logs in on 401 or if missing/expired.

Usage as a library:
    from megaplan_api import MegaplanAPI
    api = MegaplanAPI()
    deal = api.create_deal(description="...", program_id=16, state_id=129)
"""
import json
import mimetypes
import os
import re
import subprocess
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
import fcntl
import megaplan_transport

import deal_ledger
import offer_catalog_cache

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, ".env")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")
HOGART_DIR = os.path.expanduser("~/hogart-scraper")
UNRESOLVED_SUFFIX = " [ЖДЁТ ЦЕНЫ]"
DOP_PREFIX = "ДОП "
DEAL_BROWSER_CACHE = os.path.join(BASE_DIR, "deal_browser_cache.json")
DEAL_BROWSER_CACHE_LOCK = DEAL_BROWSER_CACHE + ".refresh.lock"

# "Продажа с монтажом" program, "Заявка" entry state - confirmed 2026-08-22 by creating
# a real test deal (id 871) and checking it landed here. These defaults apply only
# to explicitly confirmed deal creation. A KP request must not create a deal.
DEFAULT_PROGRAM_ID = "16"
DEFAULT_STATE_ID = "129"


def comparable_contractor_name(value):
    """Normalize Cyrillic phonetic spelling and Latin brand spelling for matching.

    This deliberately mirrors the proven deal-browser search behaviour: for example,
    `Джеткар`, `JetCar` and the JetCar part of `Автосалон JetCar` become comparable.
    It is used at the write boundary too, because finding a deal and choosing the
    contractor for a newly-created deal must follow the same rules.
    """
    value = str(value or "").casefold().replace("ё", "е")
    replacements = (("дж", "j"), ("а", "a"), ("б", "b"), ("в", "v"), ("г", "g"),
                    ("д", "d"), ("е", "e"), ("з", "z"), ("и", "i"), ("й", "i"),
                    ("к", "k"), ("л", "l"), ("м", "m"), ("н", "n"), ("о", "o"),
                    ("п", "p"), ("р", "r"), ("с", "s"), ("т", "t"), ("у", "u"),
                    ("ф", "f"), ("х", "h"), ("ц", "c"), ("ч", "ch"), ("ш", "sh"),
                    ("щ", "sh"), ("ы", "y"), ("э", "e"), ("ю", "u"), ("я", "ya"))
    for source, target in replacements:
        value = value.replace(source, target)
    return re.sub(r"[^0-9a-zа-я]+", "", value).replace("k", "c")


def comparable_contractor_tokens(value):
    """Order-independent key for a person's first name and surname.

    Megaplan may store the same person as either ``Имя Фамилия`` or
    ``Фамилия Имя``.  The old compact key preserved word order and therefore
    allowed a duplicate card to be created.
    """
    words = re.findall(r"[0-9A-Za-zА-Яа-яЁё]+", str(value or ""))
    return "".join(sorted(comparable_contractor_name(word) for word in words if word))


def upsert_deal_browser_cache(deal):
    """Make a newly created deal visible in instant cached menus immediately."""
    try:
        with open(DEAL_BROWSER_CACHE_LOCK, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                with open(DEAL_BROWSER_CACHE, encoding="utf-8") as source:
                    deals = json.load(source)
            except (OSError, json.JSONDecodeError):
                deals = []
            deal_id = str(deal.get("id"))
            deals = [deal] + [item for item in deals if str(item.get("id")) != deal_id]
            deals.sort(key=lambda item: int(item.get("id") or 0), reverse=True)
            tmp = f"{DEAL_BROWSER_CACHE}.{os.getpid()}.tmp"
            with open(tmp, "w", encoding="utf-8") as target:
                json.dump(deals, target, ensure_ascii=False)
            os.replace(tmp, DEAL_BROWSER_CACHE)
    except Exception:
        # Cache acceleration must never make a successful CRM write look failed.
        pass


def load_env():
    env = {}
    with open(ENV_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


class MegaplanAPIError(Exception):
    def __init__(self, status, body):
        self.status = status
        self.body = body
        super().__init__(f"Megaplan API error {status}: {body}")


class MegaplanAPI:
    def __init__(self):
        env = load_env()
        self.domain = env["MEGAPLAN_DOMAIN"]
        self.username = env["MEGAPLAN_USERNAME"]
        self.password = env["MEGAPLAN_PASSWORD"]
        self.base = f"https://{self.domain}/api/v3"
        self.token = self._load_cached_token()

    def _load_cached_token(self):
        if os.path.exists(TOKEN_FILE):
            data = json.load(open(TOKEN_FILE))
            # expires_in is seconds from when we got it; re-login if that's passed
            # (with a safety margin) rather than trust a token that might be dead.
            if data.get("obtained_at", 0) + data.get("expires_in", 0) - 3600 > time.time():
                return data["access_token"]
        return None

    def _save_token(self, data):
        data["obtained_at"] = time.time()
        temp=TOKEN_FILE+'.'+str(os.getpid())+'.tmp'
        fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        os.replace(temp,TOKEN_FILE)
        os.chmod(TOKEN_FILE, 0o600)

    def login(self):
        with open(TOKEN_FILE+'.login.lock','a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            cached=self._load_cached_token()
            if cached:
                self.token=cached
                return cached
            return self._login_once()

    def _login_once(self):
        body = urllib.parse.urlencode({
            "username": self.username, "password": self.password, "grant_type": "password",
        }).encode()
        req = urllib.request.Request(
            f"{self.base}/auth/access_token", data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST",
        )
        with megaplan_transport.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
        self.token = data["access_token"]
        self._save_token(data)
        return self.token

    def _invalidate_rejected_token(self):
        # Do not re-authenticate immediately after a 401. The transport pause
        # applies first; the next allowed request obtains a fresh token once.
        with open(TOKEN_FILE+'.login.lock','a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            if self._load_cached_token()==self.token:
                self._save_token({'access_token':self.token,'expires_in':0})
        self.token=None

    def _call(self, method, path, params=None, json_body=None, retry=True):
        if not self.token:
            self.login()
        url = f"{self.base}{path}"
        if params:
            # Megaplan v3 wants the ENTIRE query string to be one JSON object, not
            # standard key=value pairs (confirmed empirically 2026-08-22 - a normal
            # ?limit=5 gets rejected with "Query string should be json").
            url += "?" + urllib.parse.quote(json.dumps(params, ensure_ascii=False))
        data = json.dumps(json_body, ensure_ascii=False).encode() if json_body is not None else None
        req = urllib.request.Request(
            url, data=data, method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with megaplan_transport.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code==401:self._invalidate_rejected_token()
            body_bytes = e.read()
            try:
                parsed = json.loads(body_bytes)
            except Exception:
                parsed = {"raw": body_bytes.decode("utf-8", "replace")}
            raise MegaplanAPIError(e.code, parsed)

    def upload_file(self, path, retry=True):
        """Upload one local file to Megaplan's file staging endpoint.

        The returned File entity can then be attached to a comment or another CRM
        entity. Uploading alone does not link the file to a deal.
        """
        if not self.token:
            self.login()
        filename = os.path.basename(path)
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        boundary = "----MegaplanBot" + uuid.uuid4().hex
        with open(path, "rb") as source:
            content = source.read()
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="files[]"; filename="{filename}"\r\n'
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("ascii")
        req = urllib.request.Request(
            f"https://{self.domain}/api/file", data=body, method="POST",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        try:
            with megaplan_transport.urlopen(req, timeout=60) as resp:
                response = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code==401:self._invalidate_rejected_token()
            raw = exc.read()
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = {"raw": raw.decode("utf-8", "replace")}
            raise MegaplanAPIError(exc.code, parsed)

        def find_file(value):
            if isinstance(value, dict):
                if value.get("id") is not None and value.get("contentType") == "File":
                    return value
                for nested in value.values():
                    found = find_file(nested)
                    if found:
                        return found
            elif isinstance(value, list):
                for nested in value:
                    found = find_file(nested)
                    if found:
                        return found
            return None

        uploaded = find_file(response)
        if not uploaded:
            raise ValueError(f"Мегаплан загрузил файл, но не вернул его идентификатор: {response}")
        return uploaded

    def create_deal(self, description, name=None, program_id=DEFAULT_PROGRAM_ID, state_id=DEFAULT_STATE_ID):
        """Create a deal in the given program/state (defaults to "Продажа с монтажом" /
        "Заявка" - see module docstring). Megaplan auto-generates its own deal number
        regardless of what's passed as `name` (confirmed empirically) - `description` is
        the only free-text field that actually sticks, so that's where the KP context
        (client, items, total) goes."""
        payload = {
            "contentType": "Deal",
            "program": {"contentType": "Program", "id": str(program_id)},
            "state": {"contentType": "ProgramState", "id": str(state_id)},
            "description": description,
        }
        if name:
            payload["name"] = name
        result = self._call("POST", "/deal", json_body=payload)
        return result["data"]

    def deal_url(self, deal_id):
        return f"https://{self.domain}/deals/{deal_id}/card/"

    def search_contractors(self, name, kind="company"):
        """Find a client by name (ContractorCompany or ContractorHuman), create one if
        no match exists. `kind` is "company" or "human" - the bot should ask the owner
        which, rather than guess, when it's ambiguous from the chat text.

        This account's ContractorType config requires at least one Address in
        contactInfo to create a new contractor (confirmed empirically - 422 "Поле
        'Адреса' должно быть заполнено" with just a bare name). Rather than force the
        owner to dictate the client's registered address for every small deal, default
        to a placeholder when none is given - the owner can fill in the real address
        directly in Мегаплан later if it matters for this client."""
        preferred_endpoint = "/contractorCompany" if kind == "company" else "/contractorHuman"
        endpoints = (preferred_endpoint,
                     "/contractorHuman" if preferred_endpoint == "/contractorCompany" else "/contractorCompany")
        needle = comparable_contractor_name(name)
        token_needle = comparable_contractor_tokens(name)
        # Search both the user's spelling and its Latin comparable form. Megaplan's
        # own search does not transliterate: q=Джеткар cannot find Автосалон JetCar,
        # while q=jetcar does. Never create before both searches are exhausted.
        matches_by_id = {}
        # Search every name part too: a full phrase in inverse order is not
        # reliably found by Megaplan's contractor search.
        name_parts = re.findall(r"[0-9A-Za-zА-Яа-яЁё]+", str(name))
        for endpoint in endpoints:
            for query in dict.fromkeys((name, needle, *name_parts)):
                if not query:
                    continue
                result = self._call("GET", f"{endpoint}/search", params={"q": query})
                if not isinstance(result.get('data'), list):
                    raise ValueError('Поиск клиента вернул некорректный ответ; создание запрещено.')
                for match in result.get("data") or []:
                    if match.get("id") is not None:
                        match = dict(match)
                        actual_type = str(match.get("contentType") or "")
                        match["_contractor_kind"] = (
                            "company" if actual_type == "ContractorCompany" else
                            "human" if actual_type == "ContractorHuman" else
                            ("company" if endpoint == "/contractorCompany" else "human")
                        )
                        # Both Megaplan search endpoints can return both
                        # contractor types.  The stable entity ID, not the
                        # endpoint, is the deduplication key.
                        matches_by_id[str(match["id"])] = match
        matches = list(matches_by_id.values())
        comparable_matches = []
        for m in matches:
            # ContractorHuman has no plain "name" field (only firstName/lastName) -
            # build a comparable full name for it; ContractorCompany has "name" directly.
            m_name = m.get("name") or " ".join(filter(None, [m.get("firstName"), m.get("lastName")]))
            candidate = comparable_contractor_name(m_name)
            token_candidate = comparable_contractor_tokens(m_name)
            if ((needle and (needle in candidate or candidate in needle)) or
                    (token_needle and token_needle == token_candidate)):
                comparable_matches.append(m)
        return comparable_matches

    def resolve_confirmed_contractor(self, spec):
        """Use an explicit card selected from a successful read-only search."""
        selected = str(spec.get('client_id') or '')
        matches = self.search_contractors(spec['client_name'], spec.get('client_kind', 'company'))
        if selected:
            match = next((x for x in matches if str(x['id']) == selected), None)
            if match is None:
                raise ValueError('Выбранный ID клиента не подтверждён поиском. Выберите клиента повторно.')
            return match['id'], match['_contractor_kind']
        if spec.get('allow_new_client') is not True:
            raise ValueError('Сначала выберите существующую карточку клиента по ID либо подтвердите нового клиента.')
        if matches:
            raise ValueError('Найдены существующие клиенты. Создание новой карточки остановлено.')
        return self.find_or_create_contractor(spec['client_name'], spec.get('client_kind', 'company'))

    def find_or_create_contractor(self, name, kind="company", address=None):
        comparable_matches = self.search_contractors(name, kind)
        preferred_endpoint = '/contractorCompany' if kind == 'company' else '/contractorHuman'
        if len(comparable_matches) == 1:
            return comparable_matches[0]["id"], comparable_matches[0]["_contractor_kind"]
        if len(comparable_matches) > 1:
            # A human/company duplicate can exist due to older bot versions.
            # Prefer the card already used in the most deals; a tie is an
            # explicit ambiguity and blocks creation rather than making a third
            # duplicate.
            try:
                with open(DEAL_BROWSER_CACHE, encoding="utf-8") as source:
                    deals = json.load(source)
                counts = {}
                for deal in deals:
                    contractor = deal.get("contractor") or {}
                    key = str(contractor.get("id") or "")
                    counts[key] = counts.get(key, 0) + 1
                ranked = sorted(comparable_matches, key=lambda item: counts.get(str(item["id"]), 0), reverse=True)
                if counts.get(str(ranked[0]["id"]), 0) > counts.get(str(ranked[1]["id"]), 0):
                    return ranked[0]["id"], ranked[0]["_contractor_kind"]
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                pass
            names = [m.get("name") or " ".join(filter(None, [m.get("firstName"), m.get("lastName")])) for m in comparable_matches]
            raise ValueError(
                "найдено несколько похожих клиентов: " + ", ".join(names) +
                ". Укажите точное название клиента"
            )
        content_type = "ContractorCompany" if kind == "company" else "ContractorHuman"
        payload = {
            "contentType": content_type,
            "contactInfo": [{
                "contentType": "Address",
                "type": {"contentType": "AddressType", "id": "1"},
                "value": address or "не указан",
            }],
        }
        if kind == "company":
            payload["name"] = name
        else:
            # ContractorHuman has no plain "name" field - only firstName/lastName
            # (confirmed empirically, 422 "Имя обязательно" with a bare "name"). Split
            # best-effort; a single word (e.g. just a surname like "Ларичев") becomes
            # lastName alone rather than guessing a first name that isn't there.
            parts = name.strip().split(None, 1)
            if len(parts) == 2:
                payload["firstName"], payload["lastName"] = parts
            else:
                payload["lastName"] = name.strip()
        created = self._call("POST", preferred_endpoint, json_body=payload)
        return created["data"]["id"], kind

    @staticmethod
    def _cost_fields(cost_material, cost_work):
        """`cost_material`/`cost_work` are optional per-unit cost figures (RUB) - this
        account's "Заказ" grid has two custom cost columns per position ("Себестоимость
        материалов"/"Себестоимость работ") that the KP-building bot was never filling in
        (owner-reported 2026-08-23, real deal 878). They live on the *Offer* entity, not
        OfferRow - confirmed by inspecting a real deal's raw position JSON, not documented
        in dev.megaplan.ru's public schema: `Category1000045CustomFieldTsenaZakupki`
        ("Цена закупки" - materials/equipment cost) and `Category1000045CustomFieldSebesRabot`
        ("Себестоимость работ" - labour cost). Only set when the caller has a real figure
        - left at Megaplan's own default (0) otherwise, never guessed."""
        fields = {}
        if cost_material is not None:
            fields["Category1000045CustomFieldTsenaZakupki"] = {
                "contentType": "Money", "currency": "RUB", "value": cost_material,
            }
        if cost_work is not None:
            fields["Category1000045CustomFieldSebesRabot"] = {
                "contentType": "Money", "currency": "RUB", "value": cost_work,
            }
        return fields

    @staticmethod
    def _accumulate_position(entry, qty_used, material_cost_used, work_cost_used, markup_pct, open_ended=False):
        """Roll one supplier-invoice contribution into a ledger `entry` (mutated in
        place). Owner's algorithm (2026-08-24, real incident on deal 883): `cost_material`/
        `sell_price` are PER-UNIT figures - Мегаплан multiplies price by the row's own
        quantity to get the line total - so a batch's own TOTAL cost from an invoice
        must be divided by the row's quantity before being written, never stored as-is
        (the bug: a ductwork batch's total cost got written directly as "cost per м²",
        so Мегаплан's own qty x price math produced an astronomical total - 97 x a
        6-figure "per-unit" price).

        For a fixed-quantity spec position (`open_ended=False`) the divisor is the
        ORIGINAL spec quantity (`entry["qty"]`, never changed here) - a deliberate
        "spread cost-so-far across the full planned quantity" running average, so the
        line's reported total cost/price stays a meaningful (if partial) figure even
        before the full quantity has actually been invoiced, and converges to the true
        per-unit figure once `consumed_qty` reaches `qty`. Multiple invoices covering
        the same position accumulate via `consumed_qty`/`cumulative_cost_material`/
        `cumulative_cost_work` (all persisted in the ledger) rather than overwriting.

        If this contribution would push `consumed_qty` past the original spec `qty`,
        only the portion that still fits is applied here - the rest is returned as
        overage for the caller to route into a separate "ДОП <name>" position (real
        additional material beyond what the specification estimated, per the owner's
        explicit rule), never silently absorbed into the original line.

        For an open-ended "ДОП ..." position (`open_ended=True`) there is no fixed spec
        quantity to divide by - the row's own `qty` IS the real, growing consumed
        amount, so this is a plain weighted-average unit cost, and never produces
        further overage itself.

        Returns (overage_qty, overage_material_cost, overage_work_cost) - all zero
        unless a fixed-quantity position's spec quantity was exceeded."""
        consumed_before = entry.get("consumed_qty") or 0
        if open_ended:
            within_qty, overage_qty = qty_used, 0
        else:
            remaining = max(0, entry["qty"] - consumed_before)
            within_qty = min(qty_used, remaining)
            overage_qty = qty_used - within_qty

        material_rate = (material_cost_used / qty_used) if qty_used else 0
        work_rate = (work_cost_used / qty_used) if (work_cost_used and qty_used) else 0
        within_material = material_rate * within_qty
        within_work = work_rate * within_qty
        overage_material = material_cost_used - within_material
        overage_work = (work_cost_used or 0) - within_work

        if within_qty > 0:
            entry["consumed_qty"] = consumed_before + within_qty
            if open_ended:
                entry["qty"] = entry["consumed_qty"]
            entry["cumulative_cost_material"] = (entry.get("cumulative_cost_material") or 0) + within_material
            entry["cumulative_cost_work"] = (entry.get("cumulative_cost_work") or 0) + within_work
            divisor = entry["consumed_qty"] if open_ended else entry["qty"]
            entry["cost_material"] = entry["cumulative_cost_material"] / divisor
            if entry["cumulative_cost_work"]:
                entry["cost_work"] = entry["cumulative_cost_work"] / divisor
            # Cost-only updates must preserve the already-approved selling price from
            # the deal/KP. Recalculate it only when the owner explicitly supplied a
            # markup percentage.
            if markup_pct is not None:
                entry["sell_price"] = entry["cost_material"] * (1 + markup_pct / 100)

        return overage_qty, overage_material, overage_work

    def update_offer_cost(self, offer_id, cost_material=None, cost_work=None):
        """Set an existing Offer's cost fields directly by id - POST to /offer/{id} is
        this API's update-by-id route (confirmed via the account's own /api/v3/docs,
        same POST-for-both-create-and-update pattern as /deal). Used by
        apply-supplier-invoice (Phase 1b) once a real cost arrives for a position that
        was created at cost=unknown."""
        cost_fields = self._cost_fields(cost_material, cost_work)
        if cost_fields:
            self._call("POST", f"/offer/{offer_id}", json_body={"contentType": "Offer", **cost_fields})

    def clear_offer_material_cost(self, offer_id):
        """Explicitly clear a wrongly recorded material cost on an Offer.

        Megaplan's money custom fields do not accept omission as a clear
        operation; a zero RUB value is its supported empty economic value.
        This deliberately affects only materials, never labour cost.
        """
        self.update_offer_cost(offer_id, cost_material=0)

    def update_offer_row_price(self, offer_row_id, price, qty=None):
        """Update an existing OfferRow's sell price (and optionally its quantity)
        directly by id (same POST-by-id update pattern) - used when a supplier
        invoice's own suggested retail price, or an owner-approved markup, changes what
        a position should actually sell for. `qty` is only passed when an open-ended
        "ДОП ..." overflow row's own quantity needs to grow to reflect a further
        overage contribution (see `_accumulate_position`) - a fixed-spec position's qty
        is never changed here."""
        body = {
            "contentType": "OfferRow",
            "price": {"contentType": "Money", "currency": "RUB", "value": price},
        }
        if qty is not None:
            body["quantity"] = qty
        self._call("POST", f"/offerRow/{offer_row_id}", json_body=body)

    def add_position_to_deal(self, deal_id, offer_id, qty, unit_price):
        """Append a new position to an EXISTING deal - used when a supplier invoice
        contains a line item that wasn't in the original spec (owner confirmed adding
        it, see SUPPLIER_INVOICE_APPLY flow). Megaplan's `positions` field has no
        dedicated "add one row" endpoint, so this re-sends the deal's full positions
        array via the same POST-by-id update route. Each EXISTING row must be a pure
        link - `{"contentType":"OfferRow","id":...}` and NOTHING else - confirmed
        empirically: including offer/quantity/price alongside an id 422s ("Entity
        should be new (without id) or link (contains only id)"). Only the new row (no
        id) carries the full offer/quantity/price payload."""
        deal = self._call("GET", f"/deal/{deal_id}")["data"]
        positions = [
            {"contentType": "OfferRow", "id": p["id"]}
            for p in (deal.get("positions") or [])
        ]
        positions.append({
            "contentType": "OfferRow", "offer": {"contentType": "Offer", "id": str(offer_id)},
            "quantity": qty, "price": {"contentType": "Money", "currency": "RUB", "value": unit_price},
        })
        self._call("POST", f"/deal/{deal_id}", json_body={"contentType": "Deal", "positions": positions})

    def find_or_create_offer(self, name, price, cost_material=None, cost_work=None, unit_id="1"):
        """Find a catalog Offer by name, create one if no match exists (avoids spamming
        duplicate catalog entries across repeated similar orders). `price` is the sell
        price per unit in RUB. See `_cost_fields` for `cost_material`/`cost_work`."""
        cost_fields = self._cost_fields(cost_material, cost_work)
        result = self._call("GET", "/offer", params={"q": name})
        for m in result.get("data") or []:
            if m.get("name", "").strip().lower() == name.strip().lower():
                if cost_fields:
                    # Keep a reused catalog entry's cost fields fresh too (e.g. Hogart's
                    # contract price moves between deals).
                    self._call("POST", f"/offer/{m['id']}", json_body={
                        "contentType": "Offer", "unit": {"contentType": "Unit", "id": str(unit_id)},
                        **cost_fields,
                    })
                return m["id"]
        created = self._call("POST", "/offer", json_body={
            "contentType": "Offer", "name": name,
            "price": {"contentType": "Money", "currency": "RUB", "value": price},
            "unit": {"contentType": "Unit", "id": str(unit_id)},
            **cost_fields,
        })
        return created["data"]["id"]

    def create_deal_with_positions(self, contractor_id, contractor_kind, positions,
                                    program_id=DEFAULT_PROGRAM_ID, state_id=DEFAULT_STATE_ID,
                                    description=None, custom_fields=None, tax_id=None):
        """positions: list of {"offer_id": ..., "qty": ..., "unit_price": ...}. Each
        offer_id must already exist (see find_or_create_offer) - OfferRow requires a
        reference to a catalog Offer, there's no bare freeform-line-item endpoint.
        custom_fields: dict of raw Category1000068CustomField* keys to set (see program
        16's schema) - only pass ones the caller is confident about (e.g. address/subject
        parsed from chat text); leave contract-number/date/profitability to Megaplan's
        own triggers."""
        content_type = "ContractorCompany" if contractor_kind == "company" else "ContractorHuman"
        payload = {
            "contentType": "Deal",
            "program": {"contentType": "Program", "id": str(program_id)},
            "state": {"contentType": "ProgramState", "id": str(state_id)},
            "contractor": {"contentType": content_type, "id": str(contractor_id)},
            "positions": [
                {
                    "contentType": "OfferRow",
                    "offer": {"contentType": "Offer", "id": str(p["offer_id"])},
                    "quantity": p["qty"],
                    "price": {"contentType": "Money", "currency": "RUB", "value": p["unit_price"]},
                    **({"tax": {"contentType": "Tax", "id": str(tax_id)}} if tax_id else {}),
                }
                for p in positions
            ],
        }
        if description:
            payload["description"] = description
        if custom_fields:
            payload.update(custom_fields)
        result = self._call("POST", "/deal", json_body=payload)
        return result["data"]

    def resolve_tax_id(self, tax_mode):
        """Resolve none/5/22 to an existing Megaplan Tax id."""
        desired_rate = -1 if str(tax_mode).lower() in ("none", "no_vat", "без ндс") else int(tax_mode)
        taxes = self._call("GET", "/tax").get("data") or []
        for tax in taxes:
            if tax.get("rate") == desired_rate:
                return tax["id"]
        raise ValueError(
            f"ставка НДС {desired_rate}% отсутствует в справочнике Мегаплана; "
            "добавьте её в настройках Мегаплана и повторите создание сделки"
        )

    def update_deal_tax(self, deal_id, tax_mode):
        """Set one explicitly selected tax on every existing row of a deal."""
        tax_id = self.resolve_tax_id(tax_mode)
        deal = self._call("GET", f"/deal/{deal_id}")["data"]
        for row in deal.get("positions") or []:
            self._call("POST", f"/offerRow/{row['id']}", json_body={
                "contentType": "OfferRow", "tax": {"contentType": "Tax", "id": str(tax_id)},
            })
        return tax_id

    @staticmethod
    def ledger_from_deal(deal, price_source="user_stated"):
        """Build the local ledger from the deal's real OfferRows.

        This is also the recovery path for deals created before create-full-deal began
        persisting its ledger. Megaplan clones Offers when attaching them, so only the
        ids returned by GET /deal/{id} are safe for later cost updates.
        """
        def money_value(value):
            if not isinstance(value, dict):
                return None
            # A literal zero in Megaplan is valid data (especially for the split
            # material/work cost columns), not a missing value.
            return value.get("value")

        from document_tax_policy import stored_row_rate
        entries = []
        for row in deal.get("positions") or []:
            offer = row.get("offer") or {}
            price = row.get("price") or {}
            unit = row.get("unit") or offer.get("unit") or {}
            qty = float(row.get("quantity") or 0)
            # Megaplan's ``price`` is the list price.  A position-level discount
            # is applied separately and the authoritative client amount is in
            # ``sum``.  Economics must use the net unit price derived from that
            # amount; otherwise every discounted deal overstates revenue.
            row_sum = row.get("sum") or {}
            net_total = money_value(row_sum)
            list_price = money_value(price) or 0
            sell_price = (net_total / qty) if net_total is not None and qty else list_price
            entries.append({
                "offer_id": offer.get("id"),
                "offer_row_id": row.get("id"),
                "name": offer.get("name") or "Без названия",
                "unit_id": unit.get("id"),
                "unit": unit.get("name") or "",
                "qty": qty,
                "sell_price": sell_price,
                "list_price": list_price,
                "discount": row.get("discount") or None,
                "net_line_total": net_total,
                "tax_rate": stored_row_rate(row),
                "cost_material": money_value(offer.get("Category1000045CustomFieldTsenaZakupki")),
                "cost_work": money_value(offer.get("Category1000045CustomFieldSebesRabot")),
                "price_source": price_source,
                "needs_review": False,
                "matched_catalog_name": None,
            })
        return entries

    # Real deal 882 (2026-08-24) exposed a second catalog problem beyond the missing
    # search: names like "Монтажные работы"/"Демонтажные работы"/"Дренажная трасса"
    # exist in the catalog many times over with wildly different prices (e.g.
    # "Монтажные работы": 63 000 / 375 000 / 956 000 / 17 300 000 ₽) because labour and
    # job-specific routing is priced per-object, unlike a physical SKU (Komfovent unit,
    # diffuser) whose catalog price is a real constant. An exact-name match on these is
    # not a meaningful signal - the owner confirmed (2026-08-24): never resolve price
    # for this class of item from the catalog, always leave it unresolved instead.
    NON_CATALOG_KEYWORDS = ("работ", "трасса")

    def search_offer_candidate(self, name):
        """Phase 1b (2026-08-23): look for an EXISTING catalog Offer by name, for the
        "спецификация без цен" deal-creation flow - if the owner's own Мегаплан catalog
        already has this item, its price should be reused as-is (and flagged for the
        owner to confirm the match), rather than creating a duplicate or re-pricing it
        from an external source.

        Originally just `GET /offer?q=name`, first hit - turned out `q` is completely
        non-functional on this endpoint (confirmed empirically: zero results for every
        query tried, including an offer's own exact name/article - see
        offer_catalog_cache.py's docstring for the full story, real offer 13106). Now
        backed by a local cached+paginated catalog with client-side exact/fuzzy
        matching instead. Returns {"id", "name", "price"} or None.

        Skips lookup entirely for job-specific work/route items (see
        NON_CATALOG_KEYWORDS above) - those fall through to Hogart/Kemiks/unresolved
        like any other unmatched item."""
        lowered = name.lower()
        if any(kw in lowered for kw in self.NON_CATALOG_KEYWORDS):
            return None
        return offer_catalog_cache.find_candidate(self, name)

    def create_deal_from_spec(self, client_name, client_kind, items, description=None, custom_fields=None, tax_id=None, confirmed_contractor=None):
        """Phase 1b: the owner gives a raw spec (equipment/materials/services, NO
        prices) instead of already-priced items (that's create-full-deal/
        create_deal_with_positions above). Per the owner's algorithm (2026-08-23):
        1. Check Мегаплан's own Offer catalog first (search_offer_candidate) - if found,
           reuse its price and its existing offer id, flag needs_review (owner must
           confirm the match wasn't a false positive - a different product with a
           similar name).
        2. Otherwise, hand off to hogart-scraper/price_spec_items.py (Hogart, then
           Kemiks) - if found there, sell=retail (Hogart's defaultPrice / Kemiks
           markup), cost=purchase (Hogart's contractPrice / Kemiks price itself).
        3. Otherwise: sell=0, cost=None, name gets a visible " [ЖДЁТ ЦЕНЫ]" suffix so
           it's obviously incomplete even looking at the deal directly in Мегаплан, not
           just in the review file this feeds (see bridge.py/spec_review_xlsx.py).

        A spec item MAY already carry its own "unit_price" (the owner/Claude already
        settled a price for that one line, e.g. via an explicit rule in chat, mixed in
        with other lines that have none) - those skip catalog/Hogart/Kemiks resolution
        entirely and go straight into the deal as given, `price_source="user_stated"`.

        Returns (deal_dict, ledger_entries) - the caller (CLI below) writes the ledger
        and the recent-deals index; kept as a return value here (not a side effect
        inside this method) so it stays easily testable/inspectable."""
        preset_items = [it for it in items if it.get("unit_price") is not None]
        catalog_items, remaining = [], []
        for it in items:
            if it.get("unit_price") is not None:
                continue
            candidate = self.search_offer_candidate(it["name"])
            if candidate:
                catalog_items.append((it, candidate))
            else:
                remaining.append(it)

        resolved_by_tier, unresolved = [], []
        if remaining:
            result = subprocess.run(
                ["python3", os.path.join(HOGART_DIR, "price_spec_items.py")],
                cwd=HOGART_DIR, input=json.dumps({"items": remaining}, ensure_ascii=False),
                capture_output=True, text=True, timeout=90,
            )
            parsed = json.loads(result.stdout.strip().splitlines()[-1])
            if not parsed.get("ok"):
                raise MegaplanAPIError(500, {"price_spec_items_error": parsed.get("error")})
            resolved_by_tier = parsed.get("resolved") or []
            unresolved = parsed.get("unresolved") or []

        positions, ledger_entries = [], []

        for it in preset_items:
            offer_id = self.find_or_create_offer(
                it["name"], it["unit_price"],
                cost_material=it.get("cost_material"), cost_work=it.get("cost_work"),
            )
            positions.append({"offer_id": offer_id, "qty": it["qty"], "unit_price": it["unit_price"]})
            ledger_entries.append({
                "offer_id": offer_id, "name": it["name"], "qty": it["qty"],
                "sell_price": it["unit_price"],
                "cost_material": it.get("cost_material"), "cost_work": it.get("cost_work"),
                "price_source": "user_stated", "needs_review": False, "matched_catalog_name": None,
            })

        for it, candidate in catalog_items:
            # 2026-08-24: reused catalog Offers can already carry real cost data on
            # their own "Цена закупки"/"Себестоимость работ" fields (offer_catalog_cache
            # now surfaces both) - pull it into the ledger/review file too, instead of
            # showing a blank "Себестоимость" column for cost that was sitting right
            # there in Мегаплан the whole time. Still flagged needs_review - the owner
            # must confirm the catalog MATCH itself wasn't a false positive, which also
            # means confirming whatever cost came along with it.
            sell_price = candidate["price"]
            positions.append({"offer_id": candidate["id"], "qty": it["qty"], "unit_price": sell_price})
            ledger_entries.append({
                "offer_id": candidate["id"], "name": it["name"], "qty": it["qty"],
                "sell_price": sell_price,
                "cost_material": candidate.get("cost_material"), "cost_work": candidate.get("cost_work"),
                "price_source": "megaplan_catalog",
                "needs_review": True, "matched_catalog_name": candidate["name"],
            })

        for r in resolved_by_tier:
            offer_id = self.find_or_create_offer(r["name"], r["sell_price"], cost_material=r.get("cost_price"))
            positions.append({"offer_id": offer_id, "qty": r["qty"], "unit_price": r["sell_price"]})
            ledger_entries.append({
                "offer_id": offer_id, "name": r["name"], "qty": r["qty"],
                "sell_price": r["sell_price"],
                "cost_material": r.get("cost_price"), "cost_work": None,
                "price_source": r["price_source"], "needs_review": False, "matched_catalog_name": None,
                "supplier": r.get("supplier"), "supplier_sku": r.get("supplier_sku"),
                "supplier_product_id": r.get("supplier_product_id"),
            })

        for u in unresolved:
            name = u["name"] + UNRESOLVED_SUFFIX
            offer_id = self.find_or_create_offer(name, 0)
            positions.append({"offer_id": offer_id, "qty": u["qty"], "unit_price": 0})
            ledger_entries.append({
                "offer_id": offer_id, "name": name, "qty": u["qty"],
                "sell_price": 0, "cost_material": None, "cost_work": None, "price_source": "unresolved",
                "needs_review": False, "matched_catalog_name": None,
            })

        contractor_id, resolved_client_kind = confirmed_contractor or self.find_or_create_contractor(client_name, client_kind)
        deal = self.create_deal_with_positions(
            contractor_id, resolved_client_kind, positions, description=description, custom_fields=custom_fields,
            tax_id=tax_id,
        )
        # Re-fetch rather than trust the POST response to echo full position rows
        # (unverified whether it does) - GET /deal/{id} is already the established,
        # tested way to see real position/offer_row ids (see Phase 1's live tests).
        deal = self._call("GET", f"/deal/{deal['id']}")["data"]
        upsert_deal_browser_cache(deal)

        # IMPORTANT (discovered 2026-08-23, real deal 879): Мегаплан CLONES each
        # referenced Offer into a brand-new catalog entry when it's attached to a deal's
        # positions - the offer id we sent in `positions` is NOT the id the resulting
        # OfferRow actually points at (confirmed: sent offer 13251, the created OfferRow
        # referenced a freshly-cloned offer 13254 with the same name/price). So matching
        # returned rows back to our ledger entries by offer id is impossible - match by
        # POSITION ORDER instead (Мегаплан preserves submission order, confirmed) and
        # overwrite each entry's offer_id with the real (cloned) one, since that's what
        # future update_offer_cost/update_offer_row_price calls must target.
        returned_positions = deal.get("positions") or []
        for entry, row in zip(ledger_entries, returned_positions):
            entry["offer_id"] = row["offer"]["id"]
            entry["offer_row_id"] = row["id"]

        return deal, ledger_entries


if __name__ == "__main__":
    import sys
    api = MegaplanAPI()
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    try:
        if cmd == "login":
            print(api.login())
        elif cmd == "create-test-deal":
            deal = api.create_deal(description="Тест из CLI megaplan_api.py")
            print(json.dumps({"id": deal["id"], "url": api.deal_url(deal["id"])}, ensure_ascii=False))
        elif cmd == "create-kp-deal":
            # Reads {"description": "...", "name": "..." (optional)} from stdin - never
            # argv (ARG_MAX lesson, see project memory). This is what bridge.py shells
            # out to every time a KP is built.
            spec = json.load(sys.stdin)
            deal = api.create_deal(description=spec["description"], name=spec.get("name"))
            print(json.dumps({
                "ok": True, "id": deal["id"], "url": api.deal_url(deal["id"]),
            }, ensure_ascii=False))
        elif cmd == "search-contractors":
            spec = json.load(sys.stdin)
            matches = api.search_contractors(spec['name'])
            print(json.dumps({'ok': True, 'clients': [
                {'id': str(x['id']), 'kind': x['_contractor_kind'],
                 'name': x.get('name') or ' '.join(filter(None, [x.get('lastName'), x.get('firstName'), x.get('middleName')]))}
                for x in matches]}, ensure_ascii=False))
        elif cmd == "create-full-deal":
            # Reads {"client_name":..., "client_kind": "company"|"human",
            # "items": [{"name":..., "qty":..., "unit_price":...,
            # "cost_material":... (optional), "cost_work":... (optional)}],
            # "description": "...", "custom_fields": {...} (optional)} from stdin (never
            # argv, see above). This is what bridge.py shells out to for the
            # CREATE_MEGAPLAN_DEAL_* flow - finds/creates the contractor and each item's
            # catalog Offer (cost_material/cost_work go onto the Offer's own "Цена
            # закупки"/"Себестоимость работ" fields, see find_or_create_offer), then
            # creates a deal with real positions filled in.
            spec = json.load(sys.stdin)
            from document_tax_policy import creation_rate
            spec["tax_mode"]=creation_rate(spec)
            seller_id = spec.get("selling_company_id") or spec.get("seller_id") or "cliwell"
            from own_companies import company_by_id
            if not company_by_id(seller_id): raise ValueError("Неизвестная организация-продавец")
            tax_id = api.resolve_tax_id(spec["tax_mode"])
            contractor_id, resolved_client_kind = api.resolve_confirmed_contractor(spec)
            positions = []
            for item in spec["items"]:
                offer_id = api.find_or_create_offer(
                    item["name"], item["unit_price"],
                    cost_material=item.get("cost_material"), cost_work=item.get("cost_work"),
                    unit_id=item.get("unit_id", "1"),
                )
                positions.append({"offer_id": offer_id, "qty": item["qty"], "unit_price": item["unit_price"]})
            deal = api.create_deal_with_positions(
                contractor_id, resolved_client_kind, positions,
                description=spec.get("description"), custom_fields=spec.get("custom_fields"), tax_id=tax_id,
            )
            # Re-fetch to get the real cloned Offer ids and OfferRow ids, then persist
            # the same ledger/index used by supplier-invoice updates. Previously this
            # existed only in create-deal-from-spec, so fully-priced KP deals vanished
            # from "recent deals" and their positions looked empty (real deal 887).
            deal = api._call("GET", f"/deal/{deal['id']}")["data"]
            # Megaplan clones every catalog Offer attached to a deal. Cost fields set
            # on the source offer therefore do not reliably survive. Copy economics
            # to the actual cloned offers before building the ledger.
            for item, row in zip(spec["items"], deal.get("positions") or []):
                api.update_offer_cost(
                    (row.get("offer") or {}).get("id"),
                    cost_material=item.get("cost_material"),
                    cost_work=item.get("cost_work"),
                )
            deal = api._call("GET", f"/deal/{deal['id']}")["data"]
            upsert_deal_browser_cache(deal)
            ledger_entries = api.ledger_from_deal(deal, price_source="user_stated")
            # Supplier identity is transactional metadata. Preserve it locally because
            # Megaplan Offer rows have no reliable supplier/SKU fields.
            for item, entry in zip(spec["items"], ledger_entries):
                sku = item.get("hogart_sku") or (item.get("sku") if item.get("source") == "hogart" else None)
                if sku:
                    entry.update({"supplier": "hogart", "supplier_sku": sku,
                                  "supplier_product_id": item.get("supplier_product_id")})
            deal_ledger.save(deal["id"], ledger_entries)
            deal_ledger.record_deal(deal["id"], spec["client_name"])
            from procurement_workflow import set_deal_company
            set_deal_company(deal["id"], seller_id)
            print(json.dumps({
                "ok": True, "id": deal["id"], "url": api.deal_url(deal["id"]),
                "positions_count": deal.get("positionsCount"), "ledger": ledger_entries,
            }, ensure_ascii=False))
        elif cmd == "sync-deal-ledger":
            # Repair/import a deal whose local ledger is missing. This makes legacy or
            # externally-created deals usable by the supplier-invoice flow too.
            spec = json.load(sys.stdin)
            deal = api._call("GET", f"/deal/{spec['deal_id']}")["data"]
            live_entries = api.ledger_from_deal(deal, price_source="megaplan_live")
            if any(entry.get("unit_id") and not entry.get("unit") for entry in live_entries):
                units = {str(unit.get("id")): unit.get("name") or "" for unit in (api._call("GET", "/unit").get("data") or [])}
                for entry in live_entries:
                    entry["unit"] = entry.get("unit") or units.get(str(entry.get("unit_id")), "")
            old_entries = deal_ledger.load(deal["id"])
            old_by_row = {str(e.get("offer_row_id")): e for e in old_entries if e.get("offer_row_id")}
            old_by_name = {e.get("name"): e for e in old_entries if e.get("name")}
            ledger_entries = []
            for live in live_entries:
                old = old_by_row.get(str(live.get("offer_row_id"))) or old_by_name.get(live.get("name")) or {}
                # Live Megaplan values are authoritative for names, quantities, prices
                # and both cost columns. Preserve only invoice-accumulation metadata
                # that has no representation in Megaplan itself.
                merged = {**old, **live}
                if old.get("price_source"):
                    merged["price_source"] = old["price_source"]
                for key in ("consumed_qty", "cumulative_cost_material", "cumulative_cost_work"):
                    if key in old:
                        merged[key] = old[key]
                ledger_entries.append(merged)
            contractor = deal.get("contractor") or {}
            client_name = spec.get("client_name") or contractor.get("name") or f"Сделка {spec['deal_id']}"
            deal_ledger.save(deal["id"], ledger_entries)
            deal_ledger.record_deal(deal["id"], client_name)
            print(json.dumps({"ok": True, "id": deal["id"], "ledger": ledger_entries}, ensure_ascii=False))
        elif cmd == "create-deal-from-spec":
            # Phase 1b (2026-08-23): reads {"client_name":..., "client_kind":...,
            # "items": [{"name":..., "qty":..., "hogart_sku":... (optional, if Claude
            # already resolved one via HOGART_SEARCH)}], "description":...,
            # "custom_fields":... (optional)} from stdin (never argv, see above) - NO
            # unit_price per item, that's the whole point: this is for a raw spec the
            # owner hasn't priced at all. Writes deal_ledger + the recent-deals index on
            # success (this is what bridge.py's SUPPLIER_INVOICE_APPLY flow later reads).
            spec = json.load(sys.stdin)
            from document_tax_policy import creation_rate
            spec["tax_mode"]=creation_rate(spec)
            seller_id = spec.get("selling_company_id") or spec.get("seller_id") or "cliwell"
            from own_companies import company_by_id
            if not company_by_id(seller_id): raise ValueError("Неизвестная организация-продавец")
            confirmed_contractor = api.resolve_confirmed_contractor(spec)
            deal, ledger_entries = api.create_deal_from_spec(
                spec["client_name"], spec.get("client_kind", "company"), spec["items"],
                description=spec.get("description"), custom_fields=spec.get("custom_fields"),
                tax_id=api.resolve_tax_id(spec["tax_mode"]),
                confirmed_contractor=confirmed_contractor,
            )
            deal_ledger.save(deal["id"], ledger_entries)
            deal_ledger.record_deal(deal["id"], spec["client_name"])
            from procurement_workflow import set_deal_company
            set_deal_company(deal["id"], seller_id)
            print(json.dumps({
                "ok": True, "id": deal["id"], "url": api.deal_url(deal["id"]),
                "positions_count": deal.get("positionsCount"), "ledger": ledger_entries,
            }, ensure_ascii=False))
        elif cmd == "apply-supplier-invoice":
            # Phase 1b (2026-08-23); cost_material/cost_work split + qty-based
            # accumulation (2026-08-24, real incident on deal 883 - see
            # _accumulate_position's docstring for the full story). Reads
            # {"deal_id":..., "updates": [{"offer_id":..., "offer_row_id":...,
            # "qty_used":..., "material_cost_used":..., "work_cost_used":... (optional),
            # "markup_pct":...}], "additions": [{"name":..., "qty":..., "sell_price":...,
            # "cost_material":... (optional), "cost_work":... (optional)}]} from stdin
            # (never argv, see above). `offer_id`/`offer_row_id` in `updates` come from
            # the ledger entries Claude was shown via bridge.py's DEAL_LEDGER_REQUEST
            # round-trip - this CLI never re-derives which position is which by name,
            # that fuzzy matching already happened in the chat. Claude sends the RAW
            # contribution (how much of this position THIS invoice covers, and its total
            # cost for that amount) rather than a pre-computed per-unit figure - the
            # per-unit division/running-average math is exactly the kind of arithmetic
            # this project deliberately keeps out of the model's hands (same principle
            # as price_install_addons.py), since getting it wrong writes a wrong price
            # straight into a live CRM deal.
            spec = json.load(sys.stdin)
            deal_id = spec["deal_id"]
            entries = deal_ledger.load(deal_id)
            # Ledger records are a cache.  Always refresh OfferRow ids from the
            # live deal before a write: a failed earlier attempt may have added a
            # row, and calling /offerRow/None is never a recoverable operation.
            live_deal = api._call("GET", f"/deal/{deal_id}")["data"]
            live_rows_by_offer = {
                str((row.get("offer") or {}).get("id")): row
                for row in (live_deal.get("positions") or [])
                if (row.get("offer") or {}).get("id")
            }
            for cached in entries:
                live_row = live_rows_by_offer.get(str(cached.get("offer_id") or ""))
                if live_row:
                    cached["offer_row_id"] = live_row.get("id")
            by_offer_id = {e["offer_id"]: e for e in entries}
            by_name = {e["name"]: e for e in entries}
            overage_notices = []

            for u in spec.get("updates") or []:
                entry = by_offer_id.get(u["offer_id"])
                if not entry:
                    continue
                overage_qty, overage_material, overage_work = api._accumulate_position(
                    entry, u["qty_used"], u.get("material_cost_used") or 0,
                    u.get("work_cost_used") or 0, u.get("markup_pct"),
                )
                api.update_offer_cost(entry["offer_id"], cost_material=entry.get("cost_material"), cost_work=entry.get("cost_work"))
                if u.get("markup_pct") is not None and entry.get("offer_row_id"):
                    api.update_offer_row_price(entry["offer_row_id"], entry["sell_price"])
                entry["price_source"] = "supplier_invoice"
                entry["needs_review"] = False

                if overage_qty > 1e-9:
                    dop_name = DOP_PREFIX + entry["name"]
                    dop_entry = by_name.get(dop_name)
                    if dop_entry:
                        api._accumulate_position(
                            dop_entry, overage_qty, overage_material, overage_work,
                            u.get("markup_pct"), open_ended=True,
                        )
                        api.update_offer_cost(dop_entry["offer_id"], cost_material=dop_entry.get("cost_material"), cost_work=dop_entry.get("cost_work"))
                        api.update_offer_row_price(dop_entry["offer_row_id"], dop_entry["sell_price"], qty=dop_entry["qty"])
                        dop_entry["price_source"] = "supplier_invoice"
                        dop_entry["needs_review"] = False
                    else:
                        dop_entry = {
                            "offer_id": None, "offer_row_id": None, "name": dop_name,
                            "qty": 0, "sell_price": entry["sell_price"], "cost_material": None, "cost_work": None,
                            "consumed_qty": 0, "cumulative_cost_material": 0, "cumulative_cost_work": 0,
                            "price_source": "supplier_invoice", "needs_review": False, "matched_catalog_name": None,
                        }
                        api._accumulate_position(
                            dop_entry, overage_qty, overage_material, overage_work,
                            u.get("markup_pct"), open_ended=True,
                        )
                        offer_id = api.find_or_create_offer(
                            dop_name, dop_entry["sell_price"],
                            cost_material=dop_entry.get("cost_material"), cost_work=dop_entry.get("cost_work"),
                        )
                        api.add_position_to_deal(deal_id, offer_id, dop_entry["qty"], dop_entry["sell_price"])
                        dop_entry["offer_id"] = offer_id
                        # add_position_to_deal creates a cloned Offer in
                        # Megaplan. Resolve the newly created OfferRow now so
                        # a later update in the same request cannot target None.
                        refreshed = api._call("GET", f"/deal/{deal_id}")["data"]
                        for row in refreshed.get("positions") or []:
                            if str((row.get("offer") or {}).get("id") or "") == str(offer_id):
                                dop_entry["offer_id"] = (row.get("offer") or {}).get("id")
                                dop_entry["offer_row_id"] = row.get("id")
                                break
                        entries.append(dop_entry)
                        by_name[dop_name] = dop_entry
                    overage_notices.append(
                        f"«{entry['name']}»: расход превысил спецификацию ({entry['qty']}) на "
                        f"{overage_qty:.2f} — создана/пополнена позиция «{dop_name}»"
                    )

            for a in spec.get("additions") or []:
                offer_id = api.find_or_create_offer(
                    a["name"], a["sell_price"], cost_material=a.get("cost_material"), cost_work=a.get("cost_work"),
                )
                api.add_position_to_deal(deal_id, offer_id, a["qty"], a["sell_price"])
                entries.append({
                    "offer_id": offer_id, "name": a["name"], "qty": a["qty"],
                    "sell_price": a["sell_price"],
                    "cost_material": a.get("cost_material"), "cost_work": a.get("cost_work"),
                    "price_source": "supplier_invoice", "needs_review": False, "matched_catalog_name": None,
                })

            # Re-derive every entry's offer_id/offer_row_id by POSITION ORDER, not by
            # matching the old offer_id - Мегаплан clones each Offer referenced in a
            # deal's positions into a fresh catalog entry (see create_deal_from_spec's
            # docstring), so a brand new addition's freshly-created offer_id is never
            # the id the resulting OfferRow actually ends up pointing at either.
            deal = api._call("GET", f"/deal/{deal_id}")["data"]
            returned_positions = deal.get("positions") or []
            for entry, row in zip(entries, returned_positions):
                entry["offer_id"] = row["offer"]["id"]
                entry["offer_row_id"] = row["id"]
            deal_ledger.save(deal_id, entries)
            print(json.dumps({
                "ok": True, "id": deal_id, "url": api.deal_url(deal_id),
                "updated_count": len(spec.get("updates") or []), "added_count": len(spec.get("additions") or []),
                "overage_notices": overage_notices,
                "ledger": entries,
            }, ensure_ascii=False))
        elif cmd == "add-deal-item":
            # Explicit manager-driven addition to an existing deal.  Keep it
            # separate from supplier-invoice application: it has no invoice source,
            # must not be labelled as one in the ledger, and never fabricates a cost.
            spec = json.load(sys.stdin)
            deal_id = str(spec["deal_id"])
            item = spec.get("item") or {}
            name = str(item.get("name") or "").strip()
            try:
                qty = float(item.get("qty"))
                sell_price = float(item.get("unit_price"))
            except (TypeError, ValueError):
                raise ValueError("для позиции нужны числовые количество и цена")
            if not name or qty <= 0 or sell_price < 0:
                raise ValueError("некорректные данные добавляемой позиции")
            offer_id = api.find_or_create_offer(
                name, sell_price,
                cost_material=item.get("cost_material"),
                cost_work=item.get("cost_work"),
                unit_id=str(item.get("unit_id") or "1"),
            )
            api.add_position_to_deal(deal_id, offer_id, qty, sell_price)
            deal = api._call("GET", f"/deal/{deal_id}")["data"]
            entries = deal_ledger.load(deal_id)
            entries.append({
                "offer_id": offer_id, "name": name, "qty": qty,
                "sell_price": sell_price,
                "cost_material": item.get("cost_material"),
                "cost_work": item.get("cost_work"),
                "price_source": "manager_manual", "needs_review": False,
                "matched_catalog_name": name,
            })
            for entry, row in zip(entries, deal.get("positions") or []):
                entry["offer_id"] = (row.get("offer") or {}).get("id")
                entry["offer_row_id"] = row.get("id")
            deal_ledger.save(deal_id, entries)
            upsert_deal_browser_cache(deal)
            print(json.dumps({
                "ok": True, "id": deal_id, "url": api.deal_url(deal_id),
                "positions_count": len(deal.get("positions") or []), "ledger": entries,
            }, ensure_ascii=False))
        else:
            print("Unknown command:", cmd)
            sys.exit(1)
    except ValueError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)
    except MegaplanAPIError as e:
        print(json.dumps({"ok": False, "status": e.status, "body": e.body}, ensure_ascii=False))
        sys.exit(1)
