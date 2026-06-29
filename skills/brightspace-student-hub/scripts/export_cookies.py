#!/usr/bin/env python3
"""Export cookies from Chrome CDP for the configured Brightspace instance.

By default exports ONLY `learn.uwaterloo.ca` (the configured Brightspace domain)
cookies, which is sufficient for all Learn API calls. Pass --include-sso to also
export Microsoft / institutional SSO cookies; this is rarely needed and was the
source of approval prompts in sandboxes, so it is opt-in.

Requires the `websocket-client` package for the CDP WebSocket call:
    pip3 install websocket-client
(If it is missing the script prints a clear error instead of a bare ImportError.)

CDP target fallback: a browser-level `/json/version` target has no
`webSocketDebuggerUrl`, so we look for an actual page target first and fall back
to `webSocketDebuggerUrl` on any target that exposes one. We also prefer a Learn
page target when one exists.
"""
import argparse
import os
import sys
import json

import requests

try:
    import websocket
except ImportError:
    print(
        "ERROR: this script needs the `websocket-client` package.\n"
        "Install it with:  pip3 install websocket-client",
        file=sys.stderr,
    )
    sys.exit(2)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CDP_BASE = "http://localhost:9222"


def pick_ws_target(tabs):
    """Choose a CDP target with a usable webSocketDebuggerUrl.

    CDP may expose only the browser-level websocket initially; that endpoint does
    not carry `webSocketDebuggerUrl`. We prefer a page target whose URL looks like
    the Brightspace instance, then any page target, then anything with a
    `webSocketDebuggerUrl`.
    """
    page_targets = [t for t in tabs if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
    if not page_targets:
        page_targets = [t for t in tabs if t.get("webSocketDebuggerUrl")]
    if not page_targets:
        raise RuntimeError(
            "No CDP target with a webSocketDebuggerUrl was found. Open a Learn page "
            "in the Chrome profile so a page target exists, then re-run."
        )
    learn_targets = [t for t in page_targets if "learn." in t.get("url", "") or "brightspace" in t.get("url", "")]
    return (learn_targets or page_targets)[0]["webSocketDebuggerUrl"]


def get_all_cookies():
    tabs = requests.get(f"{CDP_BASE}/json", timeout=5).json()
    ws_url = pick_ws_target(tabs)

    ws = websocket.create_connection(ws_url)
    ws.send(json.dumps({"id": 1, "method": "Network.getAllCookies", "params": {}}))
    response = json.loads(ws.recv())
    ws.close()

    cookies = response.get("result", {}).get("cookies", [])
    return cookies


def filter_cookies(cookies, domain_filter):
    return [c for c in cookies if domain_filter in c.get("domain", "")]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export Brightspace cookies from Chrome CDP.")
    parser.add_argument(
        "--include-sso",
        action="store_true",
        help="Also export Microsoft / institutional SSO cookies (default: Learn only).",
    )
    args = parser.parse_args()

    all_cookies = get_all_cookies()
    learn_cookies = filter_cookies(all_cookies, "learn.uwaterloo.ca")
    combined = list(learn_cookies)

    sso_count = 0
    if args.include_sso:
        ms_cookies = filter_cookies(all_cookies, "microsoft")
        combined += ms_cookies
        sso_count = len(ms_cookies)

    output_path = os.path.join(SCRIPT_DIR, "learn_cookies.json")
    with open(output_path, "w") as f:
        json.dump(combined, f, indent=2)

    if args.include_sso:
        print(f"Exported {len(combined)} cookies ({len(learn_cookies)} learn + {sso_count} microsoft SSO)")
    else:
        print(f"Exported {len(learn_cookies)} Learn cookies (use --include-sso to also export Microsoft SSO cookies)")