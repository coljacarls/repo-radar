"""Baut eine einzelne, offline lauffähige HTML-Datei: Template + CSS + JS + Daten inline."""

from __future__ import annotations

import html
import json
from pathlib import Path

ASSETS = Path(__file__).parent
# Reihenfolge ist relevant: app.js definiert den globalen Namensraum RR, die Views registrieren sich darin.
SCRIPTS = [
    "vendor/d3.v7.min.js",
    "app.js",
    "prompt.js",
    "views/overview.js",
    "views/hotspots.js",
    "views/deps.js",
    "views/coupling.js",
    "views/files.js",
    "detail.js",
]


def _inline_safe(text: str) -> str:
    return text.replace("</script", "<\\/script").replace("<!--", "<\\!--")


def build_report(data: dict, out: Path) -> None:
    template = (ASSETS / "template.html").read_text(encoding="utf-8")
    css = (ASSETS / "styles.css").read_text(encoding="utf-8")
    js = "\n;\n".join((ASSETS / s).read_text(encoding="utf-8") for s in SCRIPTS)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    page = (
        template.replace("/*__CSS__*/", css)
        .replace("__TITLE__", html.escape(f"repo-radar · {data['meta']['name']}"))
        .replace("__DATA__", _inline_safe(payload))
        .replace("/*__JS__*/", _inline_safe(js))
    )
    out.write_text(page, encoding="utf-8")
