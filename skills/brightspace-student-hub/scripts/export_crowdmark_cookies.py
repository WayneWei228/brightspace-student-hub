#!/usr/bin/env python3
"""Export Crowdmark cookies from Chrome CDP for app.crowdmark.com."""

import os
import requests
import json
import websocket

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

CDP_BASE = "http://localhost:9222"

def get_cookies():
    # Get available tabs
    tabs = requests.get(f"{CDP_BASE}/json").json()
    if not tabs:
        print("ERROR: No Chrome tabs found")
        return None

    ws_url = tabs[0]["webSocketDebuggerUrl"]
    ws = websocket.create_connection(ws_url)

    # Get all cookies
    ws.send(json.dumps({"id": 1, "method": "Network.getAllCookies"}))
    result = json.loads(ws.recv())
    ws.close()

    all_cookies = result.get("result", {}).get("cookies", [])

    # Filter for crowdmark domain
    crowdmark_cookies = [c for c in all_cookies if "crowdmark" in c.get("domain", "")]

    return crowdmark_cookies

def main():
    try:
        cookies = get_cookies()
        if cookies:
            output_path = os.path.join(SCRIPT_DIR, "crowdmark_cookies.json")
            with open(output_path, "w") as f:
                json.dump(cookies, f, indent=2)
            print(f"Exported {len(cookies)} Crowdmark cookies")
        else:
            print("No Crowdmark cookies found in Chrome")
    except Exception as e:
        print(f"ERROR: Could not connect to Chrome CDP: {e}")

if __name__ == "__main__":
    main()
