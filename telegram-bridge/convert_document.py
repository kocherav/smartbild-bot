#!/usr/bin/env python3
"""
Converts a Word/Excel document (supplier invoices/КП often arrive as one of these, not
just PDF/photo) to plain Markdown text, so Claude's Read tool - which only natively
handles PDFs/images/notebooks, not binary Office XML formats - can actually read it.
Runs under ~/.report-venv (this project's dedicated venv for openpyxl-family deps,
system python3 is externally-managed/PEP-668) via markitdown[docx,xlsx,pptx].

Reads {"path": "..."} from stdin (never argv - see project memory on ARG_MAX). Writes
a sibling "<path>.md" file. Prints {"ok": true, "text_path": "..."} or
{"ok": false, "error": "..."}.
"""
import json
import sys

from markitdown import MarkItDown


def convert(path):
    md = MarkItDown()
    result = md.convert(path)
    text_path = path + ".md"
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(result.text_content)
    return text_path


if __name__ == "__main__":
    try:
        spec = json.load(sys.stdin)
        text_path = convert(spec["path"])
        print(json.dumps({"ok": True, "text_path": text_path}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)
