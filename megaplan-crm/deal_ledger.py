#!/usr/bin/env python3
"""
Local per-deal cost/price ledger (2026-08-23, Phase 1b).

Why this exists: Megaplan's Offer/OfferRow entities have NO cost/purchase-price field
at all (confirmed via /api/v3/docs - Offer only has name/article/tax/price/unit/
quantity/description; OfferRow's "margin" is a markup value, not a cost basis).
Megaplan only ever sees the resulting sell `price`. So cost tracking - needed for the
tiered pricing pipeline (Megaplan catalog / Hogart / Daichi / Kemiks / unresolved) and
for filling in real cost later from supplier invoices - has to live here instead,
the same way Hogart's own contractPrice already stands in for cost on the Cliwell KP
side (see generate_kp.py).

One JSON file per deal at ledger/<deal_id>.json: a list of position records -
{"offer_id", "offer_row_id", "name", "qty", "sell_price", "cost_material" (None if
unknown - material/equipment cost, mirrors Мегаплан's own "Цена закупки" custom field),
"cost_work" (None if unknown - labour cost, mirrors "Себестоимость работ"),
"price_source" ("megaplan_catalog"|"hogart"|"daichi"|"kemiks"|"unresolved"|"user_stated"
|"supplier_invoice"), "needs_review" (bool - catalog match flagged for owner
confirmation, of BOTH the price and whatever cost came with it), "matched_catalog_name"
(only set when price_source == "megaplan_catalog")}. **Was a single "cost_price" field
until 2026-08-24** - split in two because a catalog-matched Offer can carry both real
material AND labour cost simultaneously (see project memory), and collapsing them into
one number silently dropped the labour figure.

**Gained three more fields same day** (see `megaplan_api.py`'s `_accumulate_position`
for the full story/math): `consumed_qty` (cumulative real-world quantity accounted for
via supplier invoices applied to this position so far - starts at/defaults to 0, NOT
the same as `qty`, which stays fixed at the original spec amount for a normal position),
`cumulative_cost_material`/`cumulative_cost_work` (running RUB totals accumulated across
however many invoices have touched this position - `cost_material`/`cost_work` are
always just `cumulative / divisor`, never written to directly by an invoice-apply call
anymore). A "ДОП <name>" overflow position (created automatically once `consumed_qty`
would exceed a normal position's `qty`) is open-ended - for those, `qty` itself grows
to match `consumed_qty` rather than staying fixed, so its cost is a plain weighted
average instead of a "spread over planned quantity" running average.

recent_deals.json is a flat append-only-ish index (capped, newest first) of
{"deal_id", "client_name", "created_at"} - used so "which of the last few deals does
this supplier invoice belong to" has something to list from without querying the whole
Megaplan account. Every deal-creating path (Phase 1's create-full-deal and Phase 1b's
create-deal-from-spec) should call record_deal() after a successful create.
"""
import json
import os
import time
import tempfile
from registry_transaction import transaction

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LEDGER_DIR = os.path.join(BASE_DIR, "ledger")
RECENT_DEALS_FILE = os.path.join(BASE_DIR, "recent_deals.json")
MAX_RECENT_DEALS = 20


def _ledger_path(deal_id):
    return os.path.join(LEDGER_DIR, f"{deal_id}.json")


def load(deal_id):
    path = _ledger_path(deal_id)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(deal_id, entries):
    # Monetary basis is part of the data, not a formatting guess.  All normal
    # catalogue/API values are unit prices; historical or imported line totals
    # must be explicitly marked ``line_total`` before saving (or placed in the
    # audited override registry).  This makes a later report incapable of
    # silently multiplying an ambiguous value twice.
    for entry in entries:
        entry.setdefault("cost_material_basis", "unit")
        entry.setdefault("cost_work_basis", "unit")
    os.makedirs(LEDGER_DIR, exist_ok=True)
    atomic_json(_ledger_path(deal_id),entries)


def atomic_json(path,value):
    fd,temporary=tempfile.mkstemp(prefix='.ledger-',dir=os.path.dirname(path))
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as target:
            json.dump(value,target,ensure_ascii=False,indent=2,allow_nan=False)
            target.flush(); os.fsync(target.fileno())
        # mkstemp starts at 0600 and masks the directory's dashboard read ACL.
        # Preserve existing access and enable inherited read access (no world access).
        mode=(os.stat(path).st_mode & 0o770) if os.path.exists(path) else 0o640
        os.chmod(temporary,mode | 0o040)
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


@transaction(lambda:RECENT_DEALS_FILE)
def record_deal(deal_id, client_name):
    """Append this deal to the recent-deals index (newest first, capped)."""
    deals = []
    if os.path.exists(RECENT_DEALS_FILE):
        with open(RECENT_DEALS_FILE, encoding="utf-8") as f:
            deals = json.load(f)
    deals = [d for d in deals if d["deal_id"] != deal_id]
    deals.insert(0, {"deal_id": deal_id, "client_name": client_name, "created_at": time.time()})
    deals = deals[:MAX_RECENT_DEALS]
    atomic_json(RECENT_DEALS_FILE,deals)


def list_recent_deals(n=5):
    if not os.path.exists(RECENT_DEALS_FILE):
        return []
    with open(RECENT_DEALS_FILE, encoding="utf-8") as f:
        deals = json.load(f)
    return deals[:n]


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else None
    if cmd == "list-recent":
        print(json.dumps(list_recent_deals(), ensure_ascii=False))
    elif cmd == "show":
        # Single line, no indent - matches the compact-JSON convention every CLI in this
        # project uses. 2026-08-24: this used to pretty-print with indent=2, and every
        # caller (bridge.py's fetch_deal_ledger) parses only the LAST line of stdout
        # (the standard pattern here for one-line JSON output) - for indented output
        # that's just a bare "]", which is not valid JSON on its own. So this command
        # was 100% broken for any non-empty ledger, not merely flaky - confirmed via a
        # real incident where the bridge silently treated a real 19-position deal as
        # having zero positions and duplicated two of them. `show` is still fine to run
        # interactively (`python3 deal_ledger.py show <id> | python3 -m json.tool` if you
        # want it pretty for a human).
        print(json.dumps(load(sys.argv[2]), ensure_ascii=False))
    else:
        print(__doc__)
