#!/usr/bin/env python3
"""
Thin client for the official Hogart / B2B Motion REST API (admin.b2b.hogart.ru/api/v1/).
Docs: https://future.hogart.ru/gotovye-reshenija/API.php ->
      https://export-enterprise.b2b.api.docs.3davinci.ru/ (OpenAPI/Swagger spec)
      https://b2bmotion.docs.apiary.io/ (same platform, generic docs)

This replaces the earlier Playwright/browser-based scraper (login.mjs, search_live.mjs,
export_section.mjs, get_photo.mjs) for everything those covered — real login, live price/stock,
and even better product photos (750px available directly, vs the 168px thumbnail the b2b.hogart.ru
website itself renders). Those .mjs scripts are kept only as a fallback for anything this API
doesn't expose.

Usage as a library:
    from hogart_api import HogartAPI
    api = HogartAPI()  # reads .env, caches token in token.json, re-logs in on 401
    items = api.search_products("AS25S2SF3FA-B")

Usage as a CLI:
    python3 hogart_api.py search "AS25S2SF3FA-B"
    python3 hogart_api.py product-scroll   # dumps the whole catalog (paginated via scrollId)
"""
import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, ".env")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")
API_BASE = "https://admin.b2b.hogart.ru/api/v1"
API_ORIGIN = "https://admin.b2b.hogart.ru"
# Hogart can keep accepting an old bearer token while silently returning a degraded
# pricing context (contractPrice=null and another active price type).  Do not wait for
# a 401: refresh the account session periodically so personal prices stay attached.
TOKEN_MAX_AGE_SECONDS = 12 * 60 * 60


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


class HogartAPIError(Exception):
    def __init__(self, status, body):
        self.status = status
        self.body = body
        super().__init__(f"Hogart API error {status}: {body}")


class HogartAPI:
    def __init__(self):
        env = load_env()
        self.phone = env["HOGART_PHONE"]
        self.password = env["HOGART_PASSWORD"]
        self.token_loaded_at = None
        self.token = self._load_cached_token()

    def _load_cached_token(self):
        if os.path.exists(TOKEN_FILE):
            token_age = time.time() - os.path.getmtime(TOKEN_FILE)
            if token_age < TOKEN_MAX_AGE_SECONDS:
                self.token_loaded_at = os.path.getmtime(TOKEN_FILE)
                with open(TOKEN_FILE, encoding="utf-8") as source:
                    return json.load(source)["token"]
        return None

    def _save_token(self, token):
        with open(TOKEN_FILE, "w") as f:
            json.dump({"token": token}, f)
        os.chmod(TOKEN_FILE, 0o600)

    def login(self):
        body = json.dumps({"phone": self.phone, "password": self.password}).encode()
        req = urllib.request.Request(
            f"{API_BASE}/user/login-new", data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
        if data.get("errorCode") != 0:
            raise HogartAPIError(400, data)
        self.token = data["token"]
        self._save_token(self.token)
        self.token_loaded_at = time.time()
        return self.token

    def _call(self, method, path, params=None, json_body=None, retry=True):
        if not self.token or not self.token_loaded_at or time.time() - self.token_loaded_at >= TOKEN_MAX_AGE_SECONDS:
            self.login()
        # Product/user methods live under /api/v1, while the documented supplier
        # order endpoint is /api/edi/orders.  Accept an absolute API path so orders
        # are not accidentally sent through the legacy /api/v1/order route, which
        # silently discarded valid composite catalog products.
        url = f"{API_ORIGIN}{path}" if path.startswith("/api/") else f"{API_BASE}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        body = json.dumps(json_body, ensure_ascii=False).encode() if json_body is not None else None
        headers = {"Authorization": f"Bearer {self.token}"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 401 and retry:
                self.login()
                return self._call(method, path, params, json_body=json_body, retry=False)
            body = e.read()
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = {"raw": body.decode("utf-8", "replace")}
            raise HogartAPIError(e.code, parsed)

    def search_products(self, keyword=None, group=None, instock=None, limit=None):
        params = {}
        if keyword:
            params["filters[keyword]"] = keyword
        if group:
            params["filters[group]"] = group
        if instock is not None:
            params["filters[instock]"] = "1" if instock else "0"
        if limit:
            params["filters[limit]"] = limit
        return self._call("GET", "/product", params)["items"]

    def get_product(self, id_or_article):
        return self._call("GET", f"/product/{urllib.parse.quote(id_or_article, safe='')}")

    def create_order(self, items, comment=None, delivery_point_id=None, pickup_point_id=None):
        """Create a Hogart order. A supplier invoice appears later as an order document."""
        payload = {"items": [
            {"productId": str(item["productId"]), "amount": item["amount"]}
            for item in items
        ], "clientApp": 6, "sourceType": "api"}
        if comment:
            payload["comment"] = comment
        if delivery_point_id is not None:
            payload["deliveryPointId"] = int(delivery_point_id)
        if pickup_point_id is not None:
            payload["pickupPointId"] = int(pickup_point_id)
        return self._call("POST", "/api/edi/orders", json_body=payload)

    def product_scroll_page(self, scroll_id=None, keyword=None, limit=200):
        params = {"filters[limit]": limit}
        if scroll_id:
            params["scrollId"] = scroll_id
        if keyword:
            params["filters[keyword]"] = keyword
        return self._call("GET", "/product-scroll", params)

    def iter_all_products(self, keyword=None, page_limit=200):
        """Generator over the whole catalog (or a keyword-filtered slice) via scroll pagination.
        NB: scroll sessions expire after ~1 minute of inactivity between requests (per Hogart docs)."""
        scroll_id = None
        while True:
            page = self.product_scroll_page(scroll_id=scroll_id, keyword=keyword, limit=page_limit)
            items = page.get("items", [])
            if not items:
                break
            for it in items:
                yield it
            scroll_id = page.get("scrollId")
            if not scroll_id:
                break


def image_url(product, size="750"):
    img = (product.get("image") or {}).get(size)
    if not img:
        return None
    return "https://admin.b2b.hogart.ru" + img


def _print(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    api = HogartAPI()
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    try:
        if cmd == "search":
            keyword = sys.argv[2] if len(sys.argv) > 2 else None
            _print(api.search_products(keyword=keyword))
        elif cmd == "product-scroll":
            keyword = sys.argv[2] if len(sys.argv) > 2 else None
            count = 0
            for _ in api.iter_all_products(keyword=keyword):
                count += 1
            print(f"total items: {count}")
        elif cmd == "login":
            print(api.login())
        else:
            print("Unknown command:", cmd)
            sys.exit(1)
    except HogartAPIError as e:
        print(json.dumps({"ok": False, "status": e.status, "body": e.body}, ensure_ascii=False, indent=2))
        sys.exit(1)
