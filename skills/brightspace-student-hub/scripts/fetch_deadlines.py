#!/usr/bin/env python3
"""Fetch all deadlines (quizzes + dropbox) from D2L Brightspace for the next 14 days.

When config.integrations.piazza is true and piazza_cookies.json exists, also scans
recent Piazza feed posts for deadline-mentioning keywords and appends those results.
Each result is labelled with a "source" field so callers can distinguish origin.
"""

import os
import sys
import re
import base64
import requests
import json
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
COOKIES_FILE = os.path.join(SCRIPT_DIR, "learn_cookies.json")
PIAZZA_COOKIES_FILE = os.path.join(SCRIPT_DIR, "piazza_cookies.json")

# Keywords that suggest a Piazza post mentions a deadline
DEADLINE_KEYWORDS = re.compile(
    r"\bdue\b|\bdeadline\b|\bsubmit\b|\bsubmission\b|\bdue date\b|\bsubmit by\b",
    re.IGNORECASE,
)


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {"base_url": "https://learn.uwaterloo.ca", "timezone": "America/Toronto", "term_filter": None}


def utc_to_local(iso_str, tz_name):
    if not iso_str:
        return None
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    return dt.astimezone(ZoneInfo(tz_name))


def load_session():
    session = requests.Session()
    with open(COOKIES_FILE) as f:
        for c in json.load(f):
            session.cookies.set(c["name"], c["value"], domain=c.get("domain", ""))
    return session


def get_active_courses(session, config):
    base = config["base_url"]
    resp = session.get(
        f"{base}/d2l/api/lp/1.26/enrollments/myenrollments/?orgUnitTypeId=3&isActive=1"
    )
    if resp.status_code != 200:
        print(f"ERROR: Failed to fetch enrollments ({resp.status_code})", file=sys.stderr)
        sys.exit(1)
    items = resp.json().get("Items", [])
    term = config.get("term_filter")
    if term:
        items = [i for i in items if term in i["OrgUnit"]["Name"]]
    return [{"id": i["OrgUnit"]["Id"], "name": i["OrgUnit"]["Name"]} for i in items]


def fetch_quizzes(session, base_url, org_unit_id):
    url = f"{base_url}/d2l/api/le/1.53/{org_unit_id}/quizzes/?pageSize=100"
    resp = session.get(url)
    if resp.status_code != 200:
        return []
    data = resp.json()
    items = data.get("Objects", data) if isinstance(data, dict) else data
    results = []
    for q in items:
        end_date = q.get("EndDate")
        if end_date:
            results.append({"name": q.get("Name", "Unknown Quiz"), "end_date_utc": end_date, "type": "Quiz"})
    return results


def fetch_dropbox(session, base_url, org_unit_id):
    url = f"{base_url}/d2l/api/le/1.53/{org_unit_id}/dropbox/folders/"
    resp = session.get(url)
    if resp.status_code != 200:
        return []
    results = []
    for folder in resp.json():
        end_date = folder.get("DueDate") or folder.get("EndDate")
        if end_date:
            results.append({"name": folder.get("Name", "Unknown Assignment"), "end_date_utc": end_date, "type": "Assignment"})
    return results


# ---------------------------------------------------------------------------
# Piazza helpers
# ---------------------------------------------------------------------------

def piazza_api(session_id, method, params):
    """Make an authenticated request to the Piazza RPC API."""
    try:
        resp = requests.post(
            f"https://piazza.com/logic/api?method={method}",
            json={"method": method, "params": params},
            headers={
                "CSRF-Token": session_id,
                "Content-Type": "application/json",
            },
            cookies={"session_id": session_id},
            timeout=15,
        )
        return resp.json()
    except Exception as exc:
        print(f"WARNING: Piazza API call {method} failed: {exc}", file=sys.stderr)
        return {}


def get_nids(cookie_file):
    """Decode the piazza_session JWT and return the list of enrolled network IDs."""
    with open(cookie_file) as f:
        cookies = json.load(f)
    jwt = next((c["value"] for c in cookies if c["name"] == "piazza_session"), None)
    if not jwt:
        return []
    payload = jwt.split(".")[1]
    payload += "=" * (4 - len(payload) % 4)
    return json.loads(base64.b64decode(payload)).get("nids", [])


def get_piazza_session_id(cookie_file):
    """Return the session_id cookie value from piazza_cookies.json."""
    with open(cookie_file) as f:
        cookies = json.load(f)
    return next((c["value"] for c in cookies if c["name"] == "session_id"), None)


def fetch_piazza_deadlines(cookie_file):
    """Scan recent Piazza feed posts across all enrolled networks for deadline keywords.

    Returns a list of dicts compatible with the Learn deadline shape, with
    source set to "Piazza (post title)".
    """
    session_id = get_piazza_session_id(cookie_file)
    if not session_id:
        print("WARNING: No session_id in piazza_cookies.json — skipping Piazza scan", file=sys.stderr)
        return []

    nids = get_nids(cookie_file)
    if not nids:
        print("WARNING: No network IDs found in piazza_session JWT — skipping Piazza scan", file=sys.stderr)
        return []

    results = []
    for nid in nids:
        # Get course name for labelling
        info_resp = piazza_api(session_id, "network.get_info", {"nid": nid})
        course_name = (
            info_resp.get("result", {}).get("name")
            or info_resp.get("result", {}).get("num")
            or nid
        )

        feed_resp = piazza_api(session_id, "network.get_my_feed", {
            "nid": nid,
            "limit": 50,
            "offset": 0,
        })
        posts = feed_resp.get("result", {}).get("feed", [])

        for post in posts:
            subject = post.get("subject", "")
            if DEADLINE_KEYWORDS.search(subject):
                results.append({
                    "course": course_name,
                    "name": subject,
                    "due_date_local": post.get("t", ""),
                    "due_date_utc": post.get("t", ""),
                    "type": "Piazza Post",
                    "source": f"Piazza ({subject[:60]})",
                    "sort_key": post.get("t", ""),
                })

    return results


# ---------------------------------------------------------------------------
# Deduplication helper
# ---------------------------------------------------------------------------

def _norm(s):
    """Lowercase and strip non-alphanumeric chars for fuzzy comparison."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def deduplicate(deadlines):
    """Remove near-duplicate entries sharing the same course + normalised name."""
    seen = set()
    unique = []
    for d in deadlines:
        key = (_norm(d.get("course", "")), _norm(d.get("name", "")))
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique


def main():
    config = load_config()
    tz_name = config.get("timezone", "UTC")
    base_url = config["base_url"]

    session = load_session()
    courses = get_active_courses(session, config)
    print(f"Found {len(courses)} active courses", file=sys.stderr)

    now_utc = datetime.now(timezone.utc)
    cutoff_utc = now_utc + timedelta(days=14)
    all_deadlines = []

    for course in courses:
        for item in fetch_quizzes(session, base_url, course["id"]) + fetch_dropbox(session, base_url, course["id"]):
            dt = datetime.fromisoformat(item["end_date_utc"].replace("Z", "+00:00"))
            if now_utc <= dt <= cutoff_utc:
                local_time = dt.astimezone(ZoneInfo(tz_name))
                item_type = item["type"]
                all_deadlines.append({
                    "course": course["name"],
                    "name": item["name"],
                    "due_date_local": local_time.strftime("%Y-%m-%d %I:%M %p %Z"),
                    "due_date_utc": item["end_date_utc"],
                    "type": item_type,
                    "source": f"Learn ({item_type.lower()})",
                    "sort_key": dt.isoformat(),
                })

    # Optionally scan Piazza feeds for deadline-mentioning posts
    if config.get("integrations", {}).get("piazza") and os.path.exists(PIAZZA_COOKIES_FILE):
        print("Piazza integration enabled — scanning feeds for deadline keywords...", file=sys.stderr)
        piazza_deadlines = fetch_piazza_deadlines(PIAZZA_COOKIES_FILE)
        print(f"Found {len(piazza_deadlines)} deadline-related Piazza post(s)", file=sys.stderr)
        all_deadlines.extend(piazza_deadlines)
    else:
        if config.get("integrations", {}).get("piazza") and not os.path.exists(PIAZZA_COOKIES_FILE):
            print("WARNING: Piazza integration enabled but piazza_cookies.json not found — skipping", file=sys.stderr)

    all_deadlines = deduplicate(all_deadlines)
    all_deadlines.sort(key=lambda x: x["sort_key"])

    output_path = os.path.join(SCRIPT_DIR, "deadlines_result.json")
    with open(output_path, "w") as f:
        json.dump(all_deadlines, f, indent=2)

    print(f"Found {len(all_deadlines)} deadlines in the next 14 days")
    print(json.dumps(all_deadlines, indent=2))


if __name__ == "__main__":
    main()
