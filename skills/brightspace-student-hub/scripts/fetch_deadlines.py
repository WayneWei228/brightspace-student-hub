#!/usr/bin/env python3
"""Fetch all deadlines (quizzes + dropbox) from D2L Brightspace for the next 14 days."""

import os
import sys
import requests
import json
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
COOKIES_FILE = os.path.join(SCRIPT_DIR, "learn_cookies.json")


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
                all_deadlines.append({
                    "course": course["name"],
                    "name": item["name"],
                    "due_date_local": local_time.strftime("%Y-%m-%d %I:%M %p %Z"),
                    "due_date_utc": item["end_date_utc"],
                    "type": item["type"],
                    "sort_key": dt.isoformat(),
                })

    all_deadlines.sort(key=lambda x: x["sort_key"])

    output_path = os.path.join(SCRIPT_DIR, "deadlines_result.json")
    with open(output_path, "w") as f:
        json.dump(all_deadlines, f, indent=2)

    print(f"Found {len(all_deadlines)} deadlines in the next 14 days")
    print(json.dumps(all_deadlines, indent=2))


if __name__ == "__main__":
    main()
