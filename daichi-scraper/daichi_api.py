#!/usr/bin/env python3
"""
Thin client for the official Daichi Business B2B API.
Docs (as given by the site's own /personal/api/ page, owner-authorized partner):
  GET https://api.daichi.ru/b2b/<version>/<method>?<params>
Auth is a plain access-token query/path param — no session, no cookies, no browser.

Usage as a library:
    from daichi_api import DaichiAPI
    api = DaichiAPI()  # reads .env in this directory
    stores = api.get_stores()
    products = api.get_products(store_id="default")

Usage as a CLI (for quick checks / the telegram bridge's fixed-script pattern):
    python3 daichi_api.py stores
    python3 daichi_api.py products <store_id> [name_filter]
    python3 daichi_api.py sections
    python3 daichi_api.py productparams [name_filter]
"""
import json
import os
import sys
import urllib.request
import urllib.parse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, ".env")
API_BASE = "https://api.daichi.ru/b2b"


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


class DaichiAPIError(Exception):
    def __init__(self, status, body):
        self.status = status
        self.body = body
        super().__init__(f"Daichi API error {status}: {body}")


class DaichiAPI:
    def __init__(self, access_token=None, version=None):
        env = load_env()
        self.access_token = access_token or env.get("DAICHI_ACCESS_TOKEN", "access-demo")
        self.version = version or env.get("DAICHI_API_VERSION", "v1")

    def _call(self, method_path, params=None):
        params = dict(params or {})
        params["access-token"] = self.access_token
        url = f"{API_BASE}/{self.version}/{method_path.strip('/')}/?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
        except urllib.error.HTTPError as e:
            body = e.read()
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = {"raw": body.decode("utf-8", "replace")}
            raise DaichiAPIError(e.code, parsed)
        return json.loads(body)

    def get_stores(self):
        return self._call("stores/get")["Result"]

    def get_sections(self):
        return self._call("sections/get")["Result"]

    def get_products(self, store_id="default", name_filter=None, xml_id_filter=None):
        params = {"store-id": store_id}
        if name_filter:
            params["filter[NAME]"] = name_filter
        if xml_id_filter:
            params["filter[XML_ID]"] = xml_id_filter
        return self._call("products/get", params)["Result"]

    def get_productparams(self, name_filter=None, xml_id_filter=None, page=None, page_size=None, show_empty=False):
        params = {}
        if name_filter:
            params["filter[NAME]"] = name_filter
        if xml_id_filter:
            params["filter[XML_ID]"] = xml_id_filter
        if page_size:
            params["page-size"] = page_size
        if page:
            params["page"] = page
        if show_empty:
            params["show-empty-params"] = "true"
        return self._call("productparams/get", params)["Result"]


def _print(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    api = DaichiAPI()
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    try:
        if cmd == "stores":
            _print(api.get_stores())
        elif cmd == "sections":
            _print(api.get_sections())
        elif cmd == "products":
            store_id = sys.argv[2] if len(sys.argv) > 2 else "default"
            name_filter = sys.argv[3] if len(sys.argv) > 3 else None
            _print(api.get_products(store_id=store_id, name_filter=name_filter))
        elif cmd == "productparams":
            name_filter = sys.argv[2] if len(sys.argv) > 2 else None
            _print(api.get_productparams(name_filter=name_filter, page_size=5 if not name_filter else None))
        else:
            print("Unknown command:", cmd)
            sys.exit(1)
    except DaichiAPIError as e:
        print(json.dumps({"ok": False, "status": e.status, "body": e.body}, ensure_ascii=False, indent=2))
        sys.exit(1)
