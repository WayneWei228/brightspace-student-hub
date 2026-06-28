# Piazza API Reference

Base URL: `https://piazza.com`
RPC endpoint: `/logic/api`

## Critical Authentication

Discovered via CDP network interception. All three requirements are mandatory:

1. Header: `CSRF-Token: {session_id_value}` — NOT `X-CSRFToken`
2. URL: `?method={method_name}` as query parameter
3. Body: `"params"` key — NOT `"kwargs"`

```python
import requests, json

def piazza_api(session_id, method, params):
    return requests.post(
        f"https://piazza.com/logic/api?method={method}",
        json={"method": method, "params": params},
        headers={
            "CSRF-Token": session_id,
            "Content-Type": "application/json",
        },
        cookies={"session_id": session_id}
    ).json()
```

If you get "Request not valid": check all three auth requirements above, then re-export cookies.

## Get Network IDs

All enrolled Piazza networks are in the `nids` field of the `piazza_session` JWT. The count varies by user — extract dynamically, never hardcode network IDs.

```python
import base64, json

def get_nids(cookie_file):
    with open(cookie_file) as f:
        cookies = json.load(f)
    jwt = next(c["value"] for c in cookies if c["name"] == "piazza_session")
    payload = jwt.split(".")[1]
    payload += "=" * (4 - len(payload) % 4)
    return json.loads(base64.b64decode(payload)).get("nids", [])
```

To find the network ID for a specific course, call `network.get_my_feed` for each `nid` and match by the network name in the response, or use `network.get_info` to retrieve the course name.

## Get Course Feed

```python
result = piazza_api(session_id, "network.get_my_feed", {
    "nid": network_id,
    "limit": 100,
    "offset": 0
})
posts = result["result"]["feed"]
```

Each feed item:
- `nr` — post number (use as `cid` in `content.get`)
- `subject` — post title
- `t` — creation timestamp
- `log[]` — events; `n` field = `"create"`, `"i_answer"`, `"s_answer"`, `"followup"`
- `unseen_items` — unread indicator (> 0 means unread)

## Check for Instructor Answer (Without Full Fetch)

```python
def has_instructor_answer(feed_item):
    return any(e.get("n") == "i_answer" for e in feed_item.get("log", []))
```

Use this to avoid `content.get` calls on older posts (which can fail with "Request not valid").

## Get Post Content

```python
result = piazza_api(session_id, "content.get", {
    "cid": str(post_nr),
    "nid": network_id
})
post = result["result"]
```

`post["children"]` contains answers:
- `type == "i_answer"` → instructor answer; text in `history[0]["content"]`
- `type == "s_answer"` → student answer
- `type == "followup"` → discussion

## Get Unread Count

```python
result = piazza_api(session_id, "network.get_my_feed", {
    "nid": network_id,
    "limit": 1,
    "offset": 0
})
unread = result["result"]["feed_count"]
```
