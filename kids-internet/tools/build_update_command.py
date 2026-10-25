#!/usr/bin/env python3
"""Build the one-file updater from vps/app.py and the MikroTik templates.

    python3 kids-internet/tools/build_update_command.py
"""
import base64
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
app = (ROOT / "vps" / "app.py").read_bytes()
version = re.search(rb'^VERSION = "([^"]+)"', app, re.M).group(1).decode()
rsc_new = (ROOT / "mikrotik" / "sbkb-scripts.rsc.in").read_bytes()
rsc_old = (ROOT / "mikrotik" / "rollback" / "sbkb-scripts-2.0.0.rsc.in").read_bytes()

out = (ROOT / "tools" / "update.command.in").read_text(encoding="utf-8")
for key, value in {
    "@@VERSION@@": version,
    "@@APP_B64@@": base64.b64encode(app).decode(),
    "@@APP_SHA256@@": hashlib.sha256(app).hexdigest(),
    "@@RSC_NEW_B64@@": base64.b64encode(rsc_new).decode(),
    "@@RSC_OLD_B64@@": base64.b64encode(rsc_old).decode(),
}.items():
    out = out.replace(key, value)
assert "@@" not in out

target = ROOT / f"SmartBild_KidsBot_Update_{version}.command"
target.write_text(out, encoding="utf-8")
target.chmod(0o755)
print(target)
