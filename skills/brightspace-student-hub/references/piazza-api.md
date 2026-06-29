# Piazza API Reference

Base URL: `https://piazza.com`
RPC endpoint: `/logic/api`

## Table of Contents
- [Critical Authentication](#critical-authentication)
- [Get Network IDs](#get-network-ids)
- [Get Course Feed](#get-course-feed)
- [Check for Instructor Answer (Without Full Fetch)](#check-for-instructor-answer-without-full-fetch)
- [Get Post Content](#get-post-content)
- [Get Unread Count](#get-unread-count)

## Critical Authentication

Piazza validates requests as browser-originated via the `Referer` header. A
`CSRF-Token` header is **not** required and passing `session_id` as the CSRF
token causes `{"error": "Please authenticate", "error_codes": [1]}` errors.

Requirements (all mandatory):

1. URL: `?method={method_name}` as query parameter
2. Body: `"params"` key — NOT `"kwargs"`
3. Headers: `Referer: https://piazza.com/` and a desktop `User-Agent`
4. Cookies: the **full** `piazza.com` cookie jar (not just `session_id`)

```python
import requests, json

def piazza_api(session_id, cookie_dict, method, params):
    return requests.post(
        f"https://piazza.com/logic/api?method={method}",
        json={"method": method, "params": params},
        headers={
            "Content-Type": "application/json",
            "Referer": "https://piazza.com/",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/126.0 Safari/537.36",
        },
        cookies=cookie_dict,
    ).json()
```

If you get "Please authenticate" or "Request not valid": verify the Referer
header is set and the full cookie jar is being sent, then re-export cookies.

## Get Network IDs

The `piazza_session` JWT **does not** carry a `nids` field on current accounts
(it decodes to `[]`), so decoding the JWT silently skips every network. Discover
enrolled networks authoritatively via the `user.status` API instead:

```python
def get_nids(session_id, cookie_dict):
    resp = piazza_api(session_id, cookie_dict, "user.status", {})
    if resp.get("error"):
        return []
    networks = resp.get("result", {}).get("networks", [])
    nids = [n.get("id") or n.get("nid") or n.get("_id") for n in networks]
    return [n for n in nids if n]
```

Each network object also has `name`, `course_number`, and `term` — useful for
labelling without an extra `network.get_info` call.

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
