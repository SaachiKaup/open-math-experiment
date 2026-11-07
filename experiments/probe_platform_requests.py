"""Read-only tests of platform requests observed in the app or verified by the user.

Uses OPENMATHOS_PLATFORM_KEY, never the browser's session token. Requires curl.
Run: python3 probe_platform_requests.py
Each run saves separate, private result files under results/platform-api-probes/.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
BASE = "https://os.openmathmodel.org/v1/"
TEAM = "o-50527b20-c6c7-42da-b3f8-ec68cea3e143"
PROJECT = "p-dcc90014024d4a86960f01367a637d5a"
SESSION = "consider-the-standard-simplicial-5sta"
OPERATIONS = ("orgs", "org_projects", "models", "model_catalog", "recent_chats", "feature_gates",
              "project_sessions", "session_history", "open")


def load_key():
    environment_key = os.environ.get("OPENMATHOS_PLATFORM_KEY", "").strip()
    file_key = ""
    dotenv = ROOT / ".env"
    if dotenv.exists():
        for line in dotenv.read_text().splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip().removeprefix("export ").strip() == "OPENMATHOS_PLATFORM_KEY":
                file_key = value.strip().strip("\"'")
    key = environment_key or file_key
    if not key:
        raise ValueError("Set OPENMATHOS_PLATFORM_KEY in the environment or workspace .env.")
    if "\r" in key or "\n" in key:
        raise ValueError("The platform key must be a single line.")
    if key.startswith("nuc_sess_"):
        raise ValueError("This is a browser session token. Use your dedicated platform key instead.")
    return key, {
        "credential_source": "environment" if environment_key else ".env",
        "environment_and_dotenv_differ": bool(environment_key and file_key and environment_key != file_key),
    }


def cases(team, project, session):
    return [
        ("orgs", "orgs", {}, "application/json"),
        # Verified call site: platform-DoK3UpfL.js projects() -> org_projects,
        # pagination helper supplies limit=50; web-settings adds team from org scope.
        ("org_projects", "org_projects", {"limit": 50, "team": team}, "application/json"),
        ("models", "models", {}, "application/json"),
        ("model_catalog_json", "model_catalog", {}, "application/json"),
        ("model_catalog_browser_accept", "model_catalog", {}, "*/*"),
        ("recent_chats", "recent_chats", {"limit": 10, "team": team}, "*/*"),
        ("feature_gates", "feature_gates", {}, "*/*"),
        ("project_sessions", "project_sessions",
         {"limit": 50, "include_hidden": True, "project": project, "team": team}, "*/*"),
        ("session_history", "session_history",
         {"session": session, "limit": 200, "project": project, "team": team}, "*/*"),
    ]


def perform(operation, body, accept, key):
    # Headers go through stdin, not process arguments. No browser cookies, redirects,
    # TLS bypass, or retries. Only the fixed origin and captured operation names are used.
    try:
        result = subprocess.run(
            ["curl", "--disable", "--silent", "--show-error", "--max-time", "30",
             "--proto", "=https", "--request", "POST", "--header", "@-",
             "--header", "Content-Type: application/json", "--data-raw", json.dumps(body),
             "--write-out", "\n%{http_code}", BASE + operation],
            input=f"Authorization: Bearer {key}\nAccept: {accept}\n",
            capture_output=True, text=True, timeout=35,
        )
    except FileNotFoundError:
        return {"transport_error": "curl was not found"}, None
    except subprocess.TimeoutExpired:
        return {"transport_error": "Request timed out; no retry attempted"}, None
    if result.returncode:
        return {"transport_error": result.stderr.strip().replace(key, "[REDACTED]")}, None
    text, separator, status = result.stdout.rpartition("\n")
    if not separator or not status.isdigit():
        return {"transport_error": "curl returned no HTTP status"}, None
    row = {"http_status": int(status)}
    text = text.replace(key, "[REDACTED]")
    try:
        response = json.loads(text)
    except ValueError:
        row["response_format"] = "non-JSON"
        row["response_characters"] = len(text)
        return row, {"raw_text": text}
    if isinstance(response, dict):
        row["response_keys"] = list(response)
        row["list_counts"] = {name: len(value) for name, value in response.items() if isinstance(value, list)}
        if "error" in response:
            row["error"] = response["error"]
        if "code" in response:
            row["code"] = response["code"]
        if operation == "open":
            row["runtime"] = {name: response[name] for name in
                              ("state", "stage", "version", "ipc_version", "environment")
                              if name in response}
            row["ticket_returned"] = isinstance(response.get("ticket"), str)
    row["successful_json_response"] = 200 <= int(status) < 300
    return row, response


def save_json(path, data, key):
    text = json.dumps(data, indent=2, ensure_ascii=False).replace(key, "[REDACTED]")
    with path.open("x", encoding="utf-8") as file:
        path.chmod(0o600)
        file.write(text + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--team", default=TEAM)
    parser.add_argument("--project", default=PROJECT)
    parser.add_argument("--session", default=SESSION)
    parser.add_argument("--operation", choices=OPERATIONS, action="append", help="Only test this operation; repeatable")
    args = parser.parse_args()
    try:
        key, metadata = load_key()
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + "\n")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder = ROOT / "results" / "platform-api-probes" / stamp
    folder.mkdir(mode=0o700, parents=True)
    selected = [case for case in cases(args.team, args.project, args.session)
                if not args.operation or case[1] in args.operation]
    if args.operation and "open" in args.operation:
        # Exact browser contract from platform-DoK3UpfL.js / web-CduHP5yX.js.
        # Optional only: no VM wake or agent execution; ticket stays in private output.
        selected.append(("runtime_open_no_wake", "open", {
            "team": args.team, "version": "0.52.0", "ipc_version": 6,
            "ticket": True, "wake": False,
        }, "application/json"))
    report = {"created_at_utc": stamp, **metadata, "results": [], "skipped": []}
    print(json.dumps(metadata), flush=True)
    failure = False
    for index, (label, operation, body, accept) in enumerate(selected):
        details, response = perform(operation, body, accept, key)
        row = {"case": label, "method": "POST", "operation": operation,
               "request_body": body, "accept": accept, **details}
        report["results"].append(row)
        print(json.dumps({k: v for k, v in row.items() if k != "request_body"}, ensure_ascii=False), flush=True)
        if response is not None:
            save_json(folder / (label + ".json"), response, key)
        if "transport_error" in row:
            report["skipped"] = [case[0] for case in selected[index + 1:]]
            print("Transport failed; remaining cases are untested, not API failures.", flush=True)
            failure = True
            break
        if not row.get("successful_json_response", False):
            failure = True
    save_json(folder / "summary.json", report, key)
    print(f"Private results: {folder}")
    return 1 if failure else 0


if __name__ == "__main__":
    sys.exit(main())
