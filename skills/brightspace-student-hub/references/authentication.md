# Authentication Reference

## Chrome CDP Setup

All platforms use cookies extracted from a running Chrome instance via CDP.

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="{chrome_profile from config.json}"
```

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
- `session_id` — used as `CSRF-Token` header in all API calls
- `piazza_session` — JWT whose `nids` field lists all enrolled Piazza networks

```python
import base64, json

def get_network_ids(cookie_file):
    with open(cookie_file) as f:
        cookies = json.load(f)
    jwt = next(c["value"] for c in cookies if c["name"] == "piazza_session")
    payload = jwt.split(".")[1]
    payload += "=" * (4 - len(payload) % 4)
    return json.loads(base64.b64decode(payload)).get("nids", [])
```

## Cookie Refresh

When any API returns 401:

1. Re-navigate Chrome to the platform URL — Chrome auto-fills saved password
2. Wait for auth cookie to appear in CDP (poll `Network.getAllCookies` every 2s, max 30s)
3. Re-export cookies and retry the original request
