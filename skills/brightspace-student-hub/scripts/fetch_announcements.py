#!/usr/bin/env python3
"""Fetch latest announcements from all active courses on D2L Brightspace."""
import os
import sys
import requests
import json
import re
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from html.parser import HTMLParser

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
COOKIES_FILE = os.path.join(SCRIPT_DIR, "learn_cookies.json")


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {"base_url": "https://learn.uwaterloo.ca", "timezone": "America/Toronto", "term_filter": None}


class HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []

    def handle_data(self, data):
        self.text.append(data)

    def get_text(self):
        return " ".join(self.text).strip()


def strip_html(html_str):
    if not html_str:
        return ""
    stripper = HTMLStripper()
    stripper.feed(html_str)
    return stripper.get_text()


def get_first_sentences(text, n=2):
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    result = " ".join(sentences[:n])
    if len(result) > 300:
        result = result[:297] + "..."
    return result


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


def fetch_announcements(session, base_url, org_unit_id):
    url = f"{base_url}/d2l/api/le/1.53/{org_unit_id}/news/"
    resp = session.get(url)
    if resp.status_code != 200:
        return []
    data = resp.json()
    if isinstance(data, list):
        return data
    return data.get("Items", data.get("items", []))


def main():
    config = load_config()
    tz_name = config.get("timezone", "UTC")
    base_url = config["base_url"]

    session = load_session()
    courses = get_active_courses(session, config)
    print(f"Found {len(courses)} active courses", file=sys.stderr)

    all_announcements = []
    for course in courses:
        items = fetch_announcements(session, base_url, course["id"])
        for item in items:
            title = item.get("Title", "")
            body_html = item.get("Body", {}).get("Html", "") if isinstance(item.get("Body"), dict) else ""
            start_date = item.get("StartDate", "")
            body_text = strip_html(body_html)
            preview = get_first_sentences(body_text, 2)
            local_time = utc_to_local(start_date, tz_name) if start_date else None
            all_announcements.append({
                "course": course["name"],
                "title": title,
                "date_utc": start_date,
                "date_local": local_time.strftime("%Y-%m-%d %I:%M %p %Z") if local_time else "N/A",
                "preview": preview,
            })

    all_announcements.sort(key=lambda x: x["date_utc"] or "", reverse=True)

    output_path = os.path.join(SCRIPT_DIR, "announcements_result.json")
    with open(output_path, "w") as f:
        json.dump(all_announcements, f, indent=2)

    print(f"Total announcements: {len(all_announcements)}")
    for a in all_announcements:
        print(f"[{a['date_local']}] {a['course']}")
        print(f"  Title: {a['title']}")
        print(f"  Preview: {a['preview']}")
        print()


if __name__ == "__main__":
    main()
