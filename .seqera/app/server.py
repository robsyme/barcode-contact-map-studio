#!/usr/bin/env python3
"""Serve the Barcode Contact Map viewer over .bcm bundles found in mounted data.

Routes
  /                  landing page: one card per sample (a directory holding .bcm files)
  /viewer/...        the static viewer (index.html, guide.html)
  /data/...          read-only files under BCM_DATA_ROOT (bundles, MultiQC reports)
  /api/samples       the same listing as JSON

Nothing is copied: bundles are read straight from the mount on each request.
Standard library only.
"""

import html
import json
import os
import re
import sys
import threading
import time
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

APP_DIR = Path(__file__).resolve().parent
VIEWER_DIR = APP_DIR / "viewer"
DATA_ROOT = Path(os.environ.get("BCM_DATA_ROOT", "/workspace/data"))
MAX_DEPTH = int(os.environ.get("BCM_SCAN_DEPTH", "6"))
MAX_DIRS = int(os.environ.get("BCM_SCAN_MAX_DIRS", "5000"))
SCAN_TTL = float(os.environ.get("BCM_SCAN_TTL", "30"))
SKIP_DIRS = {"work", ".git", ".nextflow", "node_modules", "__pycache__"}
REPORT_NAMES = {"multiqc_report.html"}

_cache = {"at": 0.0, "value": None}
_lock = threading.Lock()


def natural_key(text):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", text)]


def scan():
    """Walk DATA_ROOT and return ({dir: [bundle names]}, [report paths], truncated)."""
    samples, reports, seen, truncated = {}, [], 0, False
    if not DATA_ROOT.is_dir():
        return samples, reports, truncated
    root_depth = len(DATA_ROOT.parts)
    for current, dirs, files in os.walk(DATA_ROOT):
        seen += 1
        if seen > MAX_DIRS:
            truncated = True
            break
        depth = len(Path(current).parts) - root_depth
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        if depth >= MAX_DEPTH:
            dirs[:] = []
        rel = Path(current).relative_to(DATA_ROOT).as_posix()
        bundles = sorted((f for f in files if f.endswith(".bcm")), key=natural_key)
        if bundles:
            samples[rel] = bundles
        for f in files:
            if f in REPORT_NAMES:
                reports.append(f if rel == "." else f"{rel}/{f}")
    return samples, reports, truncated


def cached_scan():
    with _lock:
        now = time.monotonic()
        if _cache["value"] is None or now - _cache["at"] > SCAN_TTL:
            _cache["value"] = scan()
            _cache["at"] = now
        return _cache["value"]


def url_path(rel):
    return "/".join(quote(part) for part in rel.split("/") if part not in ("", "."))


def sample_entries():
    samples, reports, truncated = cached_scan()
    names = [Path(rel).name if rel != "." else DATA_ROOT.name for rel in samples]
    entries = []
    for rel, bundles in sorted(samples.items(), key=lambda kv: natural_key(kv[0])):
        name = Path(rel).name if rel != "." else DATA_ROOT.name
        # Two directories with the same name (say a test run beside the real one)
        # are told apart by their full path.
        label = name if names.count(name) == 1 else rel
        base = url_path(rel)
        prefix = f"../data/{base}/" if base else "../data/"
        query = "&".join("src=" + quote(prefix + quote(b), safe="/.:~-_%") for b in bundles)
        size = 0
        for b in bundles:
            try:
                size += (DATA_ROOT / rel / b).stat().st_size
            except OSError:
                pass
        entries.append(
            {
                "label": label,
                "path": rel,
                "bundles": bundles,
                "bytes": size,
                "href": f"viewer/index.html?{query}",
            }
        )
    return entries, reports, truncated


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Barcode Contact Map</title>
<style>
  :root {{ color-scheme: light dark; --fg: #1b1f24; --muted: #5c6670; --line: #d7dce1; --bg: #fff; --card: #f6f8fa; --accent: #1a66d6; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --fg: #e6e9ec; --muted: #9aa4ae; --line: #2f363d; --bg: #14171a; --card: #1c2126; --accent: #6aa5ff; }} }}
  body {{ margin: 0; background: var(--bg); color: var(--fg); font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }}
  main {{ max-width: 980px; margin: 0 auto; padding: 32px 16px 48px; }}
  h1 {{ font-size: 24px; margin: 0 0 4px; }}
  h2 {{ font-size: 16px; margin: 32px 0 12px; }}
  p {{ margin: 0 0 12px; color: var(--muted); }}
  code {{ font: 13px ui-monospace, SFMono-Regular, Menlo, monospace; }}
  a {{ color: var(--accent); }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }}
  .card {{ display: block; padding: 14px 16px; border: 1px solid var(--line); border-radius: 8px; background: var(--card); text-decoration: none; color: inherit; }}
  .card:hover {{ border-color: var(--accent); }}
  .card strong {{ display: block; font-size: 16px; color: var(--accent); }}
  .card span {{ display: block; color: var(--muted); font-size: 13px; overflow-wrap: anywhere; }}
  ul {{ padding-left: 20px; margin: 0; }}
  .warn {{ border-left: 3px solid #c9822b; padding-left: 10px; }}
</style>
</head>
<body>
<main>
<h1>Barcode Contact Map</h1>
<p>Linked-read barcode co-occurrence maps, read in place from <code>{root}</code>. Pick a sample to open all of its chromosomes in the viewer.</p>
{body}
<h2>Help</h2>
<p><a href="viewer/guide.html">How to read the map, and the input format</a>. <a href="viewer/index.html">Open the viewer with no data</a> to load bundles from your own computer.</p>
</main>
</body>
</html>
"""


def human(n):
    for unit in ("B", "kB", "MB", "GB"):
        if n < 1000 or unit == "GB":
            return f"{n:.0f} {unit}" if unit in ("B", "kB") else f"{n:.1f} {unit}"
        n /= 1000


def landing_page():
    entries, reports, truncated = sample_entries()
    parts = []
    if entries:
        parts.append(f"<h2>Samples ({len(entries)})</h2><div class=\"grid\">")
        for e in entries:
            chroms = ", ".join(b[:-4] for b in e["bundles"])
            if len(e["bundles"]) > 10:
                chroms = f"{e['bundles'][0][:-4]} to {e['bundles'][-1][:-4]}"
            parts.append(
                f"<a class=\"card\" href=\"{html.escape(e['href'])}\">"
                f"<strong>{html.escape(e['label'])}</strong>"
                f"<span>{len(e['bundles'])} chromosomes, {human(e['bytes'])}: {html.escape(chroms)}</span>"
                f"<span><code>{html.escape(e['path'])}</code></span></a>"
            )
        parts.append("</div>")
    else:
        parts.append(
            f"<h2>No bundles found</h2><p class=\"warn\">No <code>.bcm</code> files under "
            f"<code>{html.escape(str(DATA_ROOT))}</code>. Mount the pipeline's output folder "
            "as data when you add the Studio, then reload this page.</p>"
        )
    if reports:
        parts.append("<h2>Pipeline QC</h2><ul>")
        for r in sorted(reports, key=natural_key):
            parts.append(f"<li><a href=\"data/{url_path(r)}\">{html.escape(r)}</a></li>")
        parts.append("</ul>")
    if truncated:
        parts.append(
            f"<p class=\"warn\">The scan stopped after {MAX_DIRS} folders. Mount a narrower folder to see everything.</p>"
        )
    return PAGE.format(root=html.escape(str(DATA_ROOT)), body="\n".join(parts))


class Handler(SimpleHTTPRequestHandler):
    server_version = "bcm-studio"
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".bcm": "application/octet-stream"}

    def translate_path(self, path):
        """Map /viewer/... and /data/... to their roots; anything else is not a file."""
        clean = unquote(urlsplit(path).path)
        parts = [p for p in clean.split("/") if p not in ("", ".")]
        if not parts or ".." in parts:
            return str(APP_DIR / "__missing__")
        if parts[0] == "viewer":
            base = VIEWER_DIR
        elif parts[0] == "data":
            base = DATA_ROOT
        else:
            return str(APP_DIR / "__missing__")
        return str(base.joinpath(*parts[1:]))

    def send_text(self, body, content_type):
        data = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def route(self):
        path = urlsplit(self.path).path
        if path in ("/", "/index.html"):
            self.send_text(landing_page(), "text/html; charset=utf-8")
            return True
        if path == "/api/samples":
            entries, reports, truncated = sample_entries()
            self.send_text(
                json.dumps({"root": str(DATA_ROOT), "samples": entries, "reports": reports, "truncated": truncated}),
                "application/json",
            )
            return True
        if path == "/healthz":
            self.send_text("ok\n", "text/plain")
            return True
        return False

    def do_GET(self):
        if not self.route():
            super().do_GET()

    def do_HEAD(self):
        if not self.route():
            super().do_HEAD()

    def list_directory(self, path):
        self.send_error(HTTPStatus.NOT_FOUND, "No directory listings")
        return None

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.log_date_time_string(), fmt % args))


def main():
    port = int(os.environ.get("CONNECT_TOOL_PORT") or os.environ.get("PORT") or "8080")
    server = ThreadingHTTPServer(("0.0.0.0", port), partial(Handler))
    print(f"Serving viewer on port {port}; data root {DATA_ROOT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
