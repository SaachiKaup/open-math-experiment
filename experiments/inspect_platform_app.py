"""Download public app JavaScript to locate platform API call sites.

No API key, browser session, or cookies are read or sent. This fetches static files
only; it does not call platform operations or start agent work.
"""

from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urljoin, urlsplit

ORIGIN = "https://os.openmathmodel.org"
ENTRY = ORIGIN + "/app/"
ROOT = Path(__file__).resolve().parent
MAX_FILES = 64
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_BYTES = 8 * 1024 * 1024


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and attrs.get("src"):
            self.references.append(attrs["src"])
        if tag == "link" and attrs.get("rel") == "modulepreload" and attrs.get("href"):
            self.references.append(attrs["href"])


def asset_url(base, reference):
    # Vite's dependency map uses app-root-relative "assets/..." paths, while
    # real imports use module-relative "./chunk.js" paths.
    url = urljoin(ENTRY if reference.startswith("assets/") else base, reference)
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc != "os.openmathmodel.org"
            or not parsed.path.endswith((".js", ".mjs"))):
        return None
    return url.split("#", 1)[0]


def javascript_references(base, text):
    references = re.findall(r'''["'`]([^"'`\s]+\.(?:js|mjs)(?:\?[^"'`\s]*)?)["'`]''', text)
    return [url for ref in references if (url := asset_url(base, ref))]


def download(url):
    result = subprocess.run(
        ["curl", "--disable", "--silent", "--show-error", "--max-time", "25",
         "--max-filesize", str(MAX_BYTES), "--proto", "=https",
         "--write-out", "\n%{http_code}", url],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip() or f"curl failed ({result.returncode})")
    body, _, status = result.stdout.rpartition("\n")
    if status != "200":
        raise ValueError(f"HTTP {status}; redirects are not followed")
    if len(body.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Static resource exceeded the download limit")
    return body


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder = ROOT / "results" / "platform-app" / stamp
    folder.mkdir(parents=True, mode=0o700)
    report = {"entry": ENTRY, "credentials_used": False, "files": [], "errors": []}
    pending = [ENTRY]
    seen = set()
    total_bytes = 0
    while pending and len(seen) < MAX_FILES:
        url = pending.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            text = download(url)
        except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
            report["errors"].append({"url": url, "error": str(exc)})
            print(f"Could not fetch {url}: {exc}", flush=True)
            if url == ENTRY:
                break
            continue
        suffix = ".html" if url == ENTRY else ".js"
        total_bytes += len(text.encode("utf-8"))
        if total_bytes > MAX_TOTAL_BYTES:
            report["errors"].append({"url": url, "error": "Total download limit reached"})
            break
        name = f"{len(report['files']):02d}" + suffix
        (folder / name).write_text(text, encoding="utf-8")
        candidates = sorted(set(re.findall(
            r'''["'`]((?:(?:session|chat|project|file|files|org)_[a-z0-9_]+)|orgs|models|model_catalog|feature_gates)["'`]''', text
        )))
        direct_paths = sorted(set(re.findall(r"/v1/[A-Za-z0-9_./-]+", text)))
        report["files"].append({"url": url, "file": name, "characters": len(text),
                                "candidate_operations": candidates, "literal_api_paths": direct_paths})
        print(f"Saved {name}: {url} ({len(text)} characters)", flush=True)
        if candidates:
            print("Candidate operation strings: " + ", ".join(candidates), flush=True)
        if url == ENTRY:
            parser = Scripts()
            parser.feed(text)
            pending.extend(resolved for ref in parser.references if (resolved := asset_url(url, ref)))
        pending.extend(javascript_references(url, text))
    report["remaining_assets"] = sorted(set(pending) - seen)
    report["downloaded_bytes"] = total_bytes
    report["limit_reached"] = bool(report["remaining_assets"] and len(seen) >= MAX_FILES)
    (folder / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Results: {folder}")
    if not report["files"]:
        return 1
    print("Operation strings are clues; inspect their call sites to establish request schemas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
