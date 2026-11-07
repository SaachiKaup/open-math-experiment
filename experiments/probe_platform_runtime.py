"""Verify platform-key access to the VM and list project files without changing them.

Uses the protocol observed in the downloaded Open Math OS 0.52.0 app:
POST /v1/open -> WSS /v1/runtime/{environment}?ticket=... -> binary JSON lines.
Does not wake the VM, start agents, submit messages, or write remote files.
"""

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
import ssl
import sys
import time
from urllib.parse import urlencode

from probe_platform_requests import ROOT, TEAM, load_key, perform

PROJECT = "p-acd94c16e21a4059ba4d3acbaba02af1"
VERSION = "0.52.0"
IPC_VERSION = 6
SUBPROTOCOL = "agent-vm-runtime-v1"
MAX_LINE = 8454144


class Runtime:
    def __init__(self, socket):
        self.socket = socket
        self.sequence = 0
        self.buffer = bytearray()

    def write(self, message):
        encoded = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        for offset in range(0, len(encoded), 65536):
            self.socket.send(encoded[offset:offset + 65536])

    def call(self, operation, **payload):
        self.sequence += 1
        request_id = self.sequence
        self.write({"op": operation, **payload, "id": request_id})
        deadline = time.monotonic() + 30
        while True:
            while b"\n" in self.buffer:
                line, _, tail = self.buffer.partition(b"\n")
                self.buffer = bytearray(tail)
                if len(line) > MAX_LINE:
                    raise ValueError("The runtime returned an oversized JSON line.")
                answer = json.loads(line)
                if not isinstance(answer, dict) or answer.get("id") != request_id:
                    continue
                if "ok" in answer:
                    return answer["ok"]
                error = answer.get("error", {})
                raise ValueError(f"{operation}: {error}")
            if len(self.buffer) > MAX_LINE:
                raise ValueError("The runtime returned an oversized JSON line.")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"{operation} timed out; no retry attempted.")
            frame = self.socket.recv(timeout=remaining)
            if not isinstance(frame, bytes):
                raise ValueError("The server ended the binary runtime session.")
            self.buffer.extend(frame)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--team", default=TEAM)
    parser.add_argument("--project", default=PROJECT, help="Runtime project name, not the pp- publication ID")
    parser.add_argument("--path", default="", help="Project-relative directory to list")
    args = parser.parse_args()
    key = ticket = ""
    report = {"team": args.team, "project": args.project, "path": args.path,
              "wake_requested": False, "agents_started": False, "remote_files_changed": False}
    success = False
    try:
        key, metadata = load_key()
        report.update(metadata)
        details, opened = perform("open", {
            "team": args.team, "version": VERSION, "ipc_version": IPC_VERSION,
            "ticket": True, "wake": False,
        }, "application/json", key)
        report["open"] = details
        if "transport_error" in details:
            raise ValueError(details["transport_error"])
        if details.get("http_status") != 200 or not isinstance(opened, dict):
            raise ValueError(f"Runtime open failed: HTTP {details.get('http_status')}; {opened}")
        ticket = opened.get("ticket", "")
        if opened.get("state") != "ready":
            raise ValueError(f"VM state is {opened.get('state')!r}; this probe does not wake or prepare it.")
        environment = opened.get("environment", "")
        bundle = opened.get("bundle_sha256", "")
        if (not isinstance(environment, str) or not re.fullmatch(r"avm-[0-9a-f-]{36}", environment)
                or opened.get("version") != VERSION or opened.get("ipc_version") != IPC_VERSION
                or not isinstance(bundle, str) or not re.fullmatch(r"[0-9a-f]{64}", bundle)
                or opened.get("programs_root") != f"/opt/nucleus/runtimes/{bundle}/bin"):
            raise ValueError("VM runtime selection differs from the downloaded app contract; refresh app sources.")
        if not isinstance(ticket, str) or not re.fullmatch(r"[\x21-\x7e]{1,1024}", ticket):
            raise ValueError("The server did not return a valid runtime ticket.")
        try:
            import certifi
            from websockets.sync.client import connect
        except ImportError:
            raise ValueError("Install runtime dependencies: python3 -m pip install -r requirements-platform.txt") from None

        # A dedicated silent logger prevents credentials in binary auth frames or the
        # ticket URL from entering websockets debug logs. TLS verification stays on.
        logger = logging.Logger("openmath-private-runtime", level=logging.CRITICAL + 1)
        logger.addHandler(logging.NullHandler())
        logger.propagate = False
        tls = ssl.create_default_context(cafile=certifi.where())
        uri = f"wss://os.openmathmodel.org/v1/runtime/{environment}?" + urlencode({"ticket": ticket})
        with connect(uri, ssl=tls, origin="https://os.openmathmodel.org",
                     subprotocols=[SUBPROTOCOL], proxy=None, compression=None,
                     open_timeout=15, close_timeout=3, max_size=MAX_LINE, logger=logger) as socket:
            if socket.subprotocol != SUBPROTOCOL:
                raise ValueError("The server selected an unexpected WebSocket protocol.")
            runtime = Runtime(socket)
            runtime.write({"nucleus_key": key})
            report["whoami"] = runtime.call("whoami")
            print("Platform key authenticated to the VM runtime.", flush=True)
            projects = []
            after = None
            cursors = set()
            for _ in range(100):
                page = runtime.call("projects.list", **({"after": after} if after else {}))
                if not isinstance(page, dict) or not isinstance(page.get("projects"), list):
                    raise ValueError("Unexpected projects.list response.")
                projects.extend(page["projects"])
                after = page.get("next")
                if after is None:
                    break
                if not isinstance(after, str) or after in cursors:
                    raise ValueError("Invalid or repeated project cursor.")
                cursors.add(after)
            else:
                raise ValueError("Project pagination exceeded the probe limit.")
            report["projects"] = projects
            selected = next((p for p in projects if p.get("name") == args.project), None)
            if selected is None or not isinstance(selected.get("dir"), str):
                raise ValueError("Requested project was not returned with a directory ID.")
            print(f"Found target project among {len(projects)} runtime projects.", flush=True)
            files = runtime.call("files.list", dir=selected["dir"], path=args.path)
            if not isinstance(files, dict) or not isinstance(files.get("entries"), list):
                raise ValueError("Unexpected files.list response.")
            report["files"] = files
            print(f"Listed {len(files['entries'])} project entries; more pages: {files.get('next') is not None}.", flush=True)
            success = True
    except Exception as error:
        report["error"] = str(error)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder = ROOT / "results" / "platform-runtime" / stamp
    folder.mkdir(parents=True, mode=0o700)
    serialized = json.dumps(report, indent=2, ensure_ascii=False)
    for secret in (key, ticket):
        if isinstance(secret, str) and secret:
            serialized = serialized.replace(secret, "[REDACTED]")
    destination = folder / "report.json"
    with destination.open("x", encoding="utf-8") as output:
        destination.chmod(0o600)
        output.write(serialized + "\n")
    if not success:
        message = report.get("error", "Runtime probe did not finish.")
        for secret in (key, ticket):
            if isinstance(secret, str) and secret:
                message = message.replace(secret, "[REDACTED]")
        print("Probe failed: " + message, file=sys.stderr)
    print(f"Private report: {destination}")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
