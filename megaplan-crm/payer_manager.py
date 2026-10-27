#!/usr/bin/env python3
"""Create/reuse a client's payer and attach it to an existing Megaplan deal.

The command accepts JSON on stdin and prints one JSON object on stdout:

    {"deal_id":"887", "payer": {"name":"...", "inn":"...", ...}}

It is intentionally a separate, deterministic write path.  The Telegram model only
extracts fields and asks for confirmation; validation, duplicate prevention and both
Megaplan writes happen here.
"""
import json
import re
import sys

from megaplan_api import MegaplanAPI
from payer_signatory_store import save_signatory as save_signatory_profile


TEXT_FIELDS = (
    "name", "inn", "kpp", "ogrn", "legalAddress", "address",
    "currentAccount", "bank", "bik", "correspondentAccount", "okpo",
)
DIGIT_FIELDS = {
    "inn": {10, 12}, "kpp": {9}, "ogrn": {13, 15}, "currentAccount": {20},
    "bik": {9}, "correspondentAccount": {20}, "okpo": {8, 10},
}
DIRECTOR_FIELD = "Category715CustomFieldFioRukovoditelya"


def digits(value):
    return re.sub(r"\D", "", str(value or ""))


def is_full_person_name(value):
    parts = re.findall(r"[A-Za-zА-Яа-яЁё-]+", str(value or ""))
    return len(parts) >= 3 and all(len(part.replace("-", "")) > 1 for part in parts)


def valid_inn(value):
    value = digits(value)
    if len(value) == 10:
        weights = (2, 4, 10, 3, 5, 9, 4, 6, 8)
        return sum(int(n) * w for n, w in zip(value, weights)) % 11 % 10 == int(value[9])
    if len(value) == 12:
        w11 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
        w12 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
        return (sum(int(n) * w for n, w in zip(value, w11)) % 11 % 10 == int(value[10])
                and sum(int(n) * w for n, w in zip(value, w12)) % 11 % 10 == int(value[11]))
    return False


def normalize(raw):
    if not isinstance(raw, dict):
        raise ValueError("реквизиты плательщика должны быть объектом")
    payer = {key: str(raw.get(key) or "").strip() for key in TEXT_FIELDS}
    for key in DIGIT_FIELDS:
        payer[key] = digits(payer[key])
    payer["director"] = str(raw.get("director") or "").strip()
    if not payer["name"]:
        raise ValueError("не указано наименование плательщика")
    if not payer["inn"]:
        raise ValueError("не указан ИНН плательщика")
    if not valid_inn(payer["inn"]):
        raise ValueError("ИНН не прошёл проверку контрольных цифр")
    for key, lengths in DIGIT_FIELDS.items():
        value = payer[key]
        if value and len(value) not in lengths:
            expected = " или ".join(map(str, sorted(lengths)))
            raise ValueError(f"поле {key} должно содержать {expected} цифр")
    return payer


def payer_matches(existing, payer):
    """INN identifies a taxpayer; an account distinguishes multiple bank records."""
    if digits(existing.get("inn")) != payer["inn"]:
        return False
    old_account = digits(existing.get("currentAccount"))
    return not old_account or not payer["currentAccount"] or old_account == payer["currentAccount"]


def contractor_name(item):
    return (item.get("name") or " ".join(filter(None, [item.get("firstName"), item.get("lastName")]))).strip()


def resolve_contractor(api, spec, deal_id):
    if deal_id:
        deal = api._call("GET", f"/deal/{deal_id}")["data"]
        contractor = deal.get("contractor") or {}
        if not contractor.get("id"):
            raise ValueError("у сделки не указан клиент, плательщика не к чему привязать")
        return contractor, deal
    if spec.get("client_id"):
        content_type = spec.get("client_type") or "ContractorCompany"
        if content_type not in ("ContractorCompany", "ContractorHuman"):
            raise ValueError("неверный тип клиента")
        return {"contentType": content_type, "id": str(spec["client_id"]), "name": spec.get("client_name") or ""}, None
    name = str(spec.get("client_name") or "").strip()
    if not name:
        raise ValueError("не указан клиент или сделка")
    matches = {}
    for endpoint in ("/contractorCompany/search", "/contractorHuman/search"):
        for item in api._call("GET", endpoint, params={"q": name}).get("data") or []:
            if contractor_name(item).casefold() == name.casefold():
                matches[(str(item.get("id")), item.get("contentType"))] = item
    if not matches:
        raise ValueError(f"клиент «{name}» не найден в Мегаплане")
    unique_ids = {key[0] for key in matches}
    if len(unique_ids) > 1:
        raise ValueError(f"найдено несколько клиентов с именем «{name}»; укажите ID клиента или сделку")
    return next(iter(matches.values())), None


def apply(spec, api=None):
    api = api or MegaplanAPI()
    if spec.get("action") == "list_deal_payers":
        deal_id = digits(spec.get("deal_id"))
        if not deal_id:
            raise ValueError("нужен номер сделки")
        contractor, deal = resolve_contractor(api, spec, deal_id)
        contractor_type = contractor.get("contentType")
        full = api._call("GET", f"/{contractor_type[0].lower() + contractor_type[1:]}/{contractor['id']}")["data"]
        selected_id = str((deal.get("payer") or {}).get("id") or "")
        payers = [{"id": str(item.get("id")), "name": item.get("name") or "", "inn": digits(item.get("inn")),
                   "selected": str(item.get("id")) == selected_id}
                  for item in (full.get("payers") or []) if item.get("id")]
        return {"ok": True, "deal_id": deal_id, "client_id": str(contractor.get("id")),
                "client_name": contractor_name(contractor), "payers": payers}
    if spec.get("action") in ("save_director", "save_signatory"):
        deal_id = digits(spec.get("deal_id"))
        director = str(spec.get("director") or "").strip()
        if not deal_id or not director:
            raise ValueError("для сохранения руководителя нужны сделка и ФИО")
        if not is_full_person_name(director):
            raise ValueError("ФИО подписанта должно содержать фамилию, имя и отчество")
        deal = api._call("GET", f"/deal/{deal_id}")["data"]
        payer_entity = deal.get("payer") or {}
        if not payer_entity.get("id"):
            raise ValueError("в сделке не выбран плательщик")
        api._call("POST", f"/payer/{payer_entity['id']}", json_body={
            "contentType": "Payer", DIRECTOR_FIELD: director,
        })
        if spec.get("action") == "save_signatory":
            save_signatory_profile(
                payer_entity["id"], director,
                spec.get("position"), spec.get("authority"),
            )
        return {"ok": True, "deal_id": deal_id, "payer_id": str(payer_entity["id"]),
                "payer_name": payer_entity.get("name") or "", "director": director,
                "saved": True}
    deal_id = digits(spec.get("deal_id"))
    linking_existing = bool(spec.get("payer_id") or spec.get("payer_name"))
    payer = None if linking_existing else normalize(spec.get("payer"))
    contractor, _deal = resolve_contractor(api, spec, deal_id)
    contractor_id = contractor.get("id")
    contractor_type = contractor.get("contentType")
    if not contractor_id or contractor_type not in ("ContractorCompany", "ContractorHuman"):
        raise ValueError("у сделки не указан клиент, плательщика не к чему привязать")

    full_contractor = api._call("GET", f"/{contractor_type[0].lower() + contractor_type[1:]}/{contractor_id}")["data"]
    # Link an already-created payer by its exact id or name. It must belong to the
    # deal's own client; this prevents cross-client assignment by a guessed id.
    if linking_existing:
        if not deal_id:
            raise ValueError("для привязки существующего плательщика нужна сделка")
        wanted_id = str(spec.get("payer_id") or "")
        wanted_name = str(spec.get("payer_name") or "").strip().casefold()
        candidates = [item for item in full_contractor.get("payers") or []
                      if (wanted_id and str(item.get("id")) == wanted_id)
                      or (wanted_name and str(item.get("name") or "").strip().casefold() == wanted_name)]
        if len(candidates) != 1:
            raise ValueError("плательщик не найден у клиента сделки или найден неоднозначно")
        payer_entity = candidates[0]
        api._call("POST", f"/deal/{deal_id}", json_body={
            "contentType": "Deal", "payer": {"contentType": "Payer", "id": str(payer_entity["id"])},
        })
        return {
            "ok": True, "deal_id": deal_id, "payer_id": str(payer_entity["id"]),
            "payer_name": payer_entity.get("name") or "", "client_id": str(contractor_id),
            "client_name": contractor_name(contractor), "created": False, "attached": True,
            "deal_url": api.deal_url(deal_id),
        }

    existing = next((item for item in full_contractor.get("payers") or [] if payer_matches(item, payer)), None)
    created = False
    if existing:
        payer_entity = existing
    else:
        payload = {
            "contentType": "Payer", "type": "Legal",
            "country": {"contentType": "Country", "id": "RU"},
            "contractor": {"contentType": contractor_type, "id": str(contractor_id)},
            **{key: value for key, value in payer.items() if key != "director" and value},
        }
        # The generic Payer schema lists OKPO, but this account's RU/Legal field map
        # rejects it on create. Keep it out rather than failing the whole card.
        payload.pop("okpo", None)
        if payer["director"]:
            payload[DIRECTOR_FIELD] = payer["director"]
        # `/payer` is read-only in API v3; creation is scoped to the client.
        payer_entity = api._call(
            "POST", f"/{contractor_type[0].lower() + contractor_type[1:]}/{contractor_id}/payers",
            json_body=payload,
        )["data"]
        created = True

    # A requisites card can arrive after this payer already exists. Update the
    # canonical Megaplan field instead of silently discarding a new director name.
    if payer["director"] and not created and str(payer_entity.get(DIRECTOR_FIELD) or "").strip() != payer["director"]:
        api._call("POST", f"/payer/{payer_entity['id']}", json_body={
            "contentType": "Payer", DIRECTOR_FIELD: payer["director"],
        })
        payer_entity[DIRECTOR_FIELD] = payer["director"]

    if deal_id:
        api._call("POST", f"/deal/{deal_id}", json_body={
            "contentType": "Deal",
            "payer": {"contentType": "Payer", "id": str(payer_entity["id"])},
        })
    return {
        "ok": True, "deal_id": deal_id or None, "payer_id": str(payer_entity["id"]),
        "payer_name": payer_entity.get("name") or payer["name"],
        "client_id": str(contractor_id), "client_name": contractor_name(contractor),
        "created": created, "attached": bool(deal_id),
        "director": str(payer_entity.get(DIRECTOR_FIELD) or payer.get("director") or "").strip(),
        "deal_url": api.deal_url(deal_id) if deal_id else None,
    }


def main():
    try:
        spec = json.load(sys.stdin)
        print(json.dumps(apply(spec), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
