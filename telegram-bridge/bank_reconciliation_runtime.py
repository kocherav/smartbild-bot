"""Execute finance reconciliation requests as the procurement-registry owner."""
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
FINANCE = BASE.parent / "hogart-scraper/finance"
sys.path.insert(0, str(FINANCE))
import bank_reconciliation_queue as queue


def poll(run, request_path=queue.REQUEST_PATH, receipt_path=queue.RECEIPT_PATH):
    request = queue.pending(request_path, receipt_path)
    if not request:
        return None
    try:
        result = run({"action": "reconcile_bank"})
        if not result.get("ok"):
            raise RuntimeError(result.get("error") or "сверка завершилась без квитанции успеха")
        receipt = queue.save_receipt(request, "completed", result=result,
                                     receipt_path=receipt_path)
        return {"ok": True, "request": request, "receipt": receipt}
    except Exception as exc:
        receipt = queue.save_receipt(request, "error", error=f"{type(exc).__name__}: {exc}",
                                     receipt_path=receipt_path)
        return {"ok": False, "request": request, "receipt": receipt,
                "error": receipt["error"], "notify_owner": receipt["attempts"] == 1}
