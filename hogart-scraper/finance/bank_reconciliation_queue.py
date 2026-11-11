"""Cross-process request/receipt protocol for supplier payment reconciliation.

The daily finance user owns the request.  The Telegram bridge owns receipts and
the procurement registry, so neither process has to create locks in the other
process' data directory.
"""
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path


REQUEST_PATH = Path(__file__).resolve().parent / "data/bank_reconciliation_request.json"
RECEIPT_PATH = Path(__file__).resolve().parents[2] / "telegram-bridge/bank_reconciliation_receipts.json"


def _read(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    # Request and receipt are an intentional read-only boundary between two
    # service users.  Writes still remain confined to each owner's directory.
    os.chmod(temporary, 0o644)
    os.replace(temporary, path)


def request_id(bank_registry):
    """Tie one request to the exact projected bank-registry version."""
    payload = Path(bank_registry).read_bytes()
    return "bank-reconcile:" + hashlib.sha256(payload).hexdigest()


def enqueue(bank_registry, request_path=REQUEST_PATH, receipt_path=RECEIPT_PATH):
    ident = request_id(bank_registry)
    current = _read(request_path, {})
    if current.get("id") != ident:
        _write(request_path, {
            "id": ident,
            "action": "reconcile_bank",
            "bank_registry_sha256": ident.split(":", 1)[1],
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        })
    receipt = _read(receipt_path, {}).get("receipts", {}).get(ident)
    return {"request_id": ident, "state": (receipt or {}).get("state", "queued"),
            "receipt": receipt}


def pending(request_path=REQUEST_PATH, receipt_path=RECEIPT_PATH):
    request = _read(request_path, {})
    if not request or request.get("action") != "reconcile_bank":
        return None
    receipt = _read(receipt_path, {}).get("receipts", {}).get(request.get("id"))
    if receipt and receipt.get("state") == "completed":
        return None
    return request


def save_receipt(request, state, result=None, error=None, receipt_path=RECEIPT_PATH):
    """Bridge-owned atomic update; lock is created only beside bridge data."""
    receipt_path = Path(receipt_path)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = receipt_path.with_suffix(receipt_path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = _read(receipt_path, {"schema_version": 1, "receipts": {}})
        previous = data.setdefault("receipts", {}).get(request["id"], {})
        receipt = {
            "request_id": request["id"], "state": state,
            "attempts": int(previous.get("attempts") or 0) + 1,
            "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        if result is not None:
            receipt["result"] = result
        if error:
            receipt["error"] = str(error)[:1500]
        data["receipts"][request["id"]] = receipt
        # The current request plus a small audit tail is enough; transaction_id
        # remains the business idempotency key in procurement_registry.json.
        ordered = sorted(data["receipts"].items(), key=lambda item: item[1].get("updated_at", ""))[-50:]
        data["receipts"] = dict(ordered)
        _write(receipt_path, data)
        return receipt
