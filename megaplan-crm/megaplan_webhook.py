#!/usr/bin/env python3
"""
Webhook receiver for the "Отправить в ТГ" button the owner configures inside
Megaplan's own workflow/automation editor for the "Продажа с монтажом" program.

Why this exists (2026-08-22): the earlier design auto-notified Telegram the instant an
invoice was created in Megaplan - owner rejected that ("нет, так плохо"), because an
invoice is often edited after generation and before it's actually ready to send. The
new design is owner-driven: they add a custom trigger/button in Megaplan's automation
UI (Настройки → Схемы сделок → «Продажа с монтажом» → Автоматизация/Регламенты) named
"Отправить в ТГ", configured to fire an outgoing webhook/HTTP request at this
endpoint when clicked - Megaplan's public docs and third-party integration write-ups
describe this as a real, supported action type ("отправить webhook" / "интеграция с
внешними сервисами"), but the exact field name Megaplan sends the entity id under
could not be confirmed visually (no working browser tool in this environment to
inspect the account's actual automation UI) - see ACCEPTED_ID_PARAMS below for the
defensive multi-name handling this uses as a result, and check the request log if the
first real trigger doesn't work as expected.

Listens on 127.0.0.1 only - reached from the internet via Caddy reverse-proxying
https://claude.smartbild.su/megaplan-webhook/* here (see /etc/caddy/Caddyfile).

Auth: a shared secret (MEGAPLAN_WEBHOOK_SECRET in .env) must be present as either a
query param (?secret=...) or JSON body field - this endpoint is internet-reachable and
would otherwise let anyone spam the owner's Telegram or probe for invoice data.

Accepts either an invoice id directly, or a deal id (in which case it sends the most
recently created invoice on that deal - covers the case where the button lives on the
deal/process rather than on the invoice itself).
"""
import json
import hmac
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from megaplan_api import MegaplanAPI, MegaplanAPIError
import megaplan_transport

LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 8095
LOG_PREFIX = "[megaplan-webhook]"
ACCEPTED_ID_PARAMS = ("invoiceId", "invoice_id", "id", "dealId", "deal_id")
MAX_PDF_BYTES = 20 * 1024 * 1024


def load_env(path):
    env = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


MEGAPLAN_ENV = load_env(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
TELEGRAM_ENV = load_env(os.path.expanduser("~/telegram-bridge/.env"))
WEBHOOK_SECRET = MEGAPLAN_ENV["MEGAPLAN_WEBHOOK_SECRET"]

_api_lock = threading.Lock()
_api = None


def get_api():
    global _api
    with _api_lock:
        if _api is None:
            _api = MegaplanAPI()
        return _api


def find_invoice(params):
    """Resolve either an invoice id or a deal id (whichever the webhook sent) to a
    full Invoice object. If given a deal id, picks the most recently created invoice
    linked to that deal (highest id)."""
    api = get_api()

    invoice_id = params.get("invoiceId") or params.get("invoice_id")
    if invoice_id:
        return api._call("GET", f"/invoice/{invoice_id}")["data"]

    deal_id = params.get("dealId") or params.get("deal_id") or params.get("id")
    if not deal_id:
        raise ValueError("no invoiceId/dealId/id in request")

    deal = api._call("GET", f"/deal/{deal_id}", params={"fields": ["invoices"]})["data"]
    invoices = deal.get("invoices") or []
    if not invoices:
        raise ValueError(f"deal {deal_id} has no invoices")
    latest = max(invoices, key=lambda x: int(x["id"]))
    return api._call("GET", f"/invoice/{latest['id']}")["data"]


def invoice_pdf(invoice):
    from invoice_pdf_versions import approved_pdf
    return approved_pdf(invoice) or download_pdf(invoice['publicDownloadLink'])


def download_pdf(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with megaplan_transport.urlopen(req, timeout=30) as resp:
        data = resp.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES:
        raise ValueError("invoice PDF too large")
    fd, path = tempfile.mkstemp(suffix=".pdf", prefix="megaplan-invoice-")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return path


def format_invoice_date(invoice_date):
    """invoiceDate is a Megaplan DateOnly object with a 0-indexed month."""
    if not invoice_date:
        return None
    try:
        return "%02d.%02d.%04d" % (invoice_date["day"], invoice_date["month"] + 1, invoice_date["year"])
    except (KeyError, TypeError):
        return None


def invoice_filename(invoice):
    number = invoice.get("number") or invoice.get("id")
    date_str = format_invoice_date(invoice.get("invoiceDate"))
    name = f"Счет №{number} от {date_str}" if date_str else f"Счет №{number}"
    return name.replace("/", "-").replace(";", "-") + ".pdf"


def invoice_caption(invoice):
    deal = invoice.get("deal") or {}
    client = deal.get("shortDescription") or (invoice.get("payer") or {}).get("name") or "?"
    amount = (invoice.get("sum") or {}).get("value")
    return f"Счёт № {invoice.get('number')} — {client}" + (f" — {amount} руб." if amount else "")


def send_telegram_document(path, caption, filename):
    import subprocess
    cmd = [
        "curl", "-s", "-X", "POST",
        f"https://api.telegram.org/bot{TELEGRAM_ENV['TELEGRAM_BOT_TOKEN']}/sendDocument",
        "-F", f"chat_id={TELEGRAM_ENV['TELEGRAM_CHAT_ID']}",
        "-F", f"document=@{path};filename={filename}",
        "-F", f"caption={caption[:1024]}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    resp = json.loads(result.stdout or "{}")
    return bool(resp.get("ok"))


class BoundedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, *args, **kwargs):
        self.slots = threading.BoundedSemaphore(16)
        super().__init__(*args, **kwargs)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, fmt, *args):
        # BaseHTTPRequestHandler includes the complete URL (and secret) in args.
        # Log neither the URL nor arbitrary request fields.
        status = args[1] if len(args) > 1 and str(args[1]).isdigit() else "-"
        print(f"{LOG_PREFIX} response status={status}", file=sys.stderr)

    def _params(self):
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("unsupported request encoding")
        if len(self.path) > 8192:
            raise ValueError("request URL too long")
        parsed = urllib.parse.urlparse(self.path)
        params = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query, max_num_fields=32).items()}
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) > 1:
            raise ValueError("ambiguous request length")
        length = int(lengths[0]) if lengths else 0
        if length < 0 or length > 65536:
            raise ValueError("request body too large or invalid")
        if length:
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError("incomplete request body")
            try:
                values = json.loads(body)
            except json.JSONDecodeError:
                if "application/json" in self.headers.get("Content-Type", ""):
                    raise ValueError("invalid JSON")
                values = {k: v[0] for k, v in urllib.parse.parse_qs(body.decode(), max_num_fields=32).items()}
            if not isinstance(values, dict) or len(values) > 32:
                raise ValueError("expected a small JSON object")
            params.update(values)
        return params

    def _respond(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(body, ensure_ascii=False).encode())

    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def _handle(self):
        if not urllib.parse.urlparse(self.path).path.rstrip("/").endswith("/send-invoice"):
            self._respond(404, {"ok": False, "error": "not found"})
            return

        try:
            params = self._params()
        except (ValueError, UnicodeError, TimeoutError):
            self._respond(400, {"ok": False, "error": "invalid request"})
            return

        supplied = params.get("secret")
        if not WEBHOOK_SECRET or not isinstance(supplied, str) or not hmac.compare_digest(supplied.encode(), WEBHOOK_SECRET.encode()):
            self._respond(403, {"ok": False, "error": "bad secret"})
            return

        try:
            invoice = find_invoice(params)
            pdf_path = invoice_pdf(invoice)
            caption = invoice_caption(invoice)
            ok = send_telegram_document(pdf_path, caption, invoice_filename(invoice))
            os.remove(pdf_path)
            if ok:
                self._respond(200, {"ok": True})
            else:
                self._respond(502, {"ok": False, "error": "telegram send failed"})
        except (MegaplanAPIError, ValueError, urllib.error.URLError) as e:
            print(f"{LOG_PREFIX} error: {e}", file=sys.stderr)
            self._respond(400, {"ok": False, "error": "request failed"})
        except Exception as e:
            print(f"{LOG_PREFIX} unexpected error: {e}", file=sys.stderr)
            self._respond(500, {"ok": False, "error": "internal error"})


def fetch_invoice_pdf_cli():
    """CLI mode for telegram-bridge's "/счет <id>" / "/сделка <id>" commands (2026-08-22) -
    reuses the exact same find_invoice/download_pdf/invoice_filename logic as the webhook
    handler above, just invoked directly instead of over HTTP. Reads {"invoiceId": ...} or
    {"dealId": ...} from stdin, prints {"ok": true, "path", "filename", "caption"} or
    {"ok": false, "error"} to stdout - bridge.py shells out to this (stdin JSON, never argv,
    per the ARG_MAX lesson - see project memory)."""
    params = json.load(sys.stdin)
    try:
        invoice = find_invoice(params)
        pdf_path = invoice_pdf(invoice)
        print(json.dumps({
            "ok": True, "path": pdf_path,
            "filename": invoice_filename(invoice), "caption": invoice_caption(invoice),
        }, ensure_ascii=False))
    except (MegaplanAPIError, ValueError, urllib.error.URLError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"internal error: {e}"}, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "fetch-invoice-pdf":
        fetch_invoice_pdf_cli()
    else:
        server = BoundedHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
        print(f"{LOG_PREFIX} listening on {LISTEN_HOST}:{LISTEN_PORT}")
        server.serve_forever()
