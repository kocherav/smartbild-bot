#!/usr/bin/env python3
import argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--secret", required=True, help="64 hex router_secret")
parser.add_argument("--cert-check", choices=["yes", "no"], default="no")
parser.add_argument("--input", default="sbkb-scripts.rsc.in")
parser.add_argument("--output", default="sbkb-scripts.rendered.rsc")
args = parser.parse_args()

secret = args.secret.strip()
if len(secret) != 64 or any(c not in "0123456789abcdefABCDEF" for c in secret):
    raise SystemExit("router_secret must be exactly 64 hex characters")

src = Path(args.input).read_text(encoding="utf-8")
out = src.replace("__ROUTER_SECRET__", secret).replace("__CERT_CHECK__", args.cert_check)
if "__ROUTER_SECRET__" in out or "__CERT_CHECK__" in out:
    raise SystemExit("template placeholder remains")
Path(args.output).write_text(out, encoding="utf-8")
print(args.output)
