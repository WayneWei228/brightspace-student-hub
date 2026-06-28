#!/usr/bin/env python3
"""Export cookies from Chrome CDP for learn.uwaterloo.ca"""
import requests
import json
import websocket

CDP_BASE = "http://localhost:9222"

def get_all_cookies():
    tabs = requests.get(f"{CDP_BASE}/json").json()
    ws_url = tabs[0]["webSocketDebuggerUrl"]

    ws = websocket.create_connection(ws_url)
    ws.send(json.dumps({"id": 1, "method": "Network.getAllCookies", "params": {}}))
    response = json.loads(ws.recv())
    ws.close()

    cookies = response.get("result", {}).get("cookies", [])
    return cookies

def filter_cookies(cookies, domain_filter):
    return [c for c in cookies if domain_filter in c.get("domain", "")]

if __name__ == "__main__":
    all_cookies = get_all_cookies()

    # Learn cookies
    learn_cookies = filter_cookies(all_cookies, "learn.uwaterloo.ca")
    # Also include microsoft auth cookies needed for SSO
    ms_cookies = filter_cookies(all_cookies, "microsoft")
    combined = learn_cookies + ms_cookies

    # Save all cookies for learn
    with open("os.path.join(os.path.dirname(os.path.abspath(__file__)))/learn_cookies.json", "w") as f:
        json.dump(combined, f, indent=2)

    print(f"Exported {len(combined)} cookies for Learn ({len(learn_cookies)} learn + {len(ms_cookies)} microsoft)")
