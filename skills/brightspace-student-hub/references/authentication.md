# Authentication Reference

## Table of Contents
- [Chrome CDP Setup](#chrome-cdp-setup)
- [Cookie Extraction](#cookie-extraction)
- [Loading Cookies into requests.Session](#loading-cookies-into-requestssession)
- [Brightspace Login](#brightspace-login)
- [SSO Domain Detection](#sso-domain-detection)
- [Crowdmark Login *(UWaterloo / if integration enabled)*](#crowdmark-login-uwaterloo--if-integration-enabled)
- [Piazza Login *(UWaterloo / if integration enabled)*](#piazza-login-uwaterloo--if-integration-enabled)
- [Cookie Refresh](#cookie-refresh)

## Chrome CDP Setup

All platforms use cookies extracted from a running Chrome instance via CDP.

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="{chrome_profile from config.json}" \
  --remote-allow-origins='*' \
  --no-first-run \
  --no-default-browser-check
```

`--remote-allow-origins='*'` is required — without it, WebSocket connections to
CDP are rejected with `403 Forbidden` (`WebSocketBadStatusException`).

Profile path is stored in `config.json` → `chrome_profile`. Set during onboarding.

## Cookie Extraction

```python
import requests, json, websocket

CDP_BASE = "http://localhost:9222"

def get_all_cookies():
    tabs = requests.get(f"{CDP_BASE}/json").json()
    ws_url = tabs[0]["webSocketDebuggerUrl"]
    ws = websocket.create_connection(ws_url)
    ws.send(json.dumps({"id": 1, "method": "Network.getAllCookies"}))
    result = json.loads(ws.recv())
    ws.close()
    return result["result"]["cookies"]

def export_cookies_for_domain(domain_filter, output_file):
    all_cookies = get_all_cookies()
    filtered = [c for c in all_cookies if domain_filter in c.get("domain", "")]
    with open(output_file, "w") as f:
        json.dump(filtered, f, indent=2)
    return len(filtered)
```

## Loading Cookies into requests.Session

```python
def load_session(cookie_file):
    session = requests.Session()
    with open(cookie_file) as f:
        for c in json.load(f):
            session.cookies.set(c["name"], c["value"], domain=c.get("domain", ""))
    return session
```

## Brightspace Login

1. Read `base_url` from `config.json` (e.g. `https://learn.uwaterloo.ca`)
2. Extract the domain (e.g. `learn.uwaterloo.ca`)
3. Navigate Chrome to `{base_url}` — SSO or login page loads
4. Chrome auto-fills saved password and submits (requires saved password in Chrome profile)
5. Export cookies filtered by the Brightspace domain
6. Output: `scripts/learn_cookies.json`

**Detect auth cookie success:** look for any of these in the exported cookies:
- `d2lSessionVal` or `D2LSessionVal`
- `d2l_sessionId`
- `d2lSecureSessionVal`

If none present after login, cookies are not valid — retry or prompt user.

## SSO Domain Detection

Different institutions use different SSO providers. The saved password domain in Chrome's Login Data may differ from the Brightspace URL:

| Institution | Brightspace URL | SSO/saved password domain |
|---|---|---|
| UWaterloo | learn.uwaterloo.ca | adfs.uwaterloo.ca |
| Generic | {base_url} | {base_url} (direct login) |

`check_setup.py` auto-detects the saved password domain by searching both `Login Data` and `Login Data For Account` for any entry whose `origin_url` contains the institution's domain or a known SSO subdomain.

## Crowdmark Login *(UWaterloo / if integration enabled)*

1. Navigate Chrome to `https://app.crowdmark.com/student`
2. Select institution from school dropdown — SSO auto-completes
3. Export cookies filtered by `crowdmark.com`
4. Output: `scripts/crowdmark_cookies.json`

## Piazza Login *(UWaterloo / if integration enabled)*

Piazza has no direct login — uses LTI handshake from Brightspace:

1. Find a topic with `TypeIdentifier: lti_link` pointing to Piazza in any course TOC
2. POST the LTI form to `https://piazza.com/connect` via CDP data URI injection
3. Chrome follows redirect and sets `session_id` cookie
4. Export cookies filtered by `piazza.com`
5. Output: `scripts/piazza_cookies.json`

Key cookies:
- `session_id` — primary auth cookie (sent in the piazza.com cookie jar)
- `piazza_session` — JWT (does **not** carry `nids` on current accounts; use the `user.status` API instead)

```python
import requests, json

def get_network_ids(session_id, cookie_dict):
    resp = requests.post(
        "https://piazza.com/logic/api?method=user.status",
        json={"method": "user.status", "params": {}},
        headers={
            "Content-Type": "application/json",
            "Referer": "https://piazza.com/",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/126.0 Safari/537.36",
        },
        cookies=cookie_dict,
    ).json()
    networks = resp.get("result", {}).get("networks", [])
    return [n.get("id") or n.get("nid") or n.get("_id") for n in networks]
```

## Cookie Refresh

When any API returns 401:

1. Re-navigate Chrome to the platform URL — Chrome auto-fills saved password
2. Wait for auth cookie to appear in CDP (poll `Network.getAllCookies` every 2s, max 30s)
3. Re-export cookies and retry the original request
