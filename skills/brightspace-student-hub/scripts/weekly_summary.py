#!/usr/bin/env python3
"""
Weekly Summary Script
Source: SKILL.md - Cross-Platform Weekly Summary section
Pulls:
  1. Learn deadlines this week (quizzes + dropbox)
  2. Crowdmark pending items (not submitted due this week, submitted awaiting grade)
  3. Piazza courses with unread instructor answers

Cookies: reused from prior tasks (learn_cookies.json, crowdmark_cookies.json, piazza_cookies.json)
"""

import requests
import json
import base64
from datetime import datetime, timezone, timedelta

SCRIPTS_DIR = "os.path.join(os.path.dirname(os.path.abspath(__file__)))"
EDT = timezone(timedelta(hours=-4))

# "This week" = today through end of Sunday
now_utc = datetime.now(timezone.utc)
now_et = now_utc.astimezone(EDT)
week_start_et = now_et.replace(hour=0, minute=0, second=0, microsecond=0)
# Today is Sunday June 28 — end of week is Saturday July 4 (Mon=0...Sun=6)
# "this week" = today (Sun Jun 28) through Sat Jul 4
days_until_saturday = (5 - now_et.weekday()) % 7
if days_until_saturday == 0:
    days_until_saturday = 7
week_end_et = week_start_et + timedelta(days=days_until_saturday, hours=23, minutes=59, seconds=59)

week_start_utc = week_start_et.astimezone(timezone.utc)
week_end_utc = week_end_et.astimezone(timezone.utc)

print(f"Weekly window (ET): {week_start_et.strftime('%Y-%m-%d %H:%M')} to {week_end_et.strftime('%Y-%m-%d %H:%M')}")
print()

# ==========================================
# Section 1: Learn Deadlines This Week
# ==========================================

LEARN_BASE = "https://learn.uwaterloo.ca"


def load_learn_session():
    session = requests.Session()
    with open(f"{SCRIPTS_DIR}/learn_cookies.json") as f:
        for c in json.load(f):
            session.cookies.set(c["name"], c["value"], domain=c.get("domain", ""))
    return session


learn_session = load_learn_session()

# Discover active courses dynamically
enroll_resp = learn_session.get(f"{LEARN_BASE}/d2l/api/lp/1.26/enrollments/myenrollments/?orgUnitTypeId=3&isActive=1")
enroll_items = enroll_resp.json().get("Items", [])
current_terms = ["Spring 2026", "Summer 2026"]
courses = []
for i in enroll_items:
    name = i["OrgUnit"]["Name"]
    if any(term in name for term in current_terms):
        courses.append({"id": i["OrgUnit"]["Id"], "name": name})

print(f"  Discovered {len(courses)} active courses for Spring/Summer 2026")

weekly_deadlines = []

for course in courses:
    org_id = course["id"]
    course_name = course["name"]

    # Quizzes
    try:
        r = learn_session.get(f"{LEARN_BASE}/d2l/api/le/1.53/{org_id}/quizzes/?pageSize=100", timeout=30)
        if r.status_code == 200:
            data = r.json()
            items = data.get("Objects", []) if isinstance(data, dict) else data
            for q in items:
                end_date = q.get("EndDate")
                if end_date:
                    end_utc = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                    if week_start_utc <= end_utc <= week_end_utc:
                        weekly_deadlines.append({
                            "course": course_name,
                            "name": q.get("Name", "Unknown"),
                            "due_et": end_utc.astimezone(EDT).strftime("%a %b %d, %I:%M %p EDT"),
                            "type": "Quiz",
                            "_dt": end_utc
                        })
    except Exception as e:
        print(f"  [WARN] Quiz fetch failed for {course_name}: {e}")

    # Dropbox (Assignments)
    try:
        r = learn_session.get(f"{LEARN_BASE}/d2l/api/le/1.53/{org_id}/dropbox/folders/", timeout=30)
        if r.status_code == 200:
            data = r.json()
            items = data if isinstance(data, list) else data.get("Objects", [])
            for d in items:
                end_date = d.get("EndDate")
                if end_date:
                    end_utc = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                    if week_start_utc <= end_utc <= week_end_utc:
                        weekly_deadlines.append({
                            "course": course_name,
                            "name": d.get("Name", "Unknown"),
                            "due_et": end_utc.astimezone(EDT).strftime("%a %b %d, %I:%M %p EDT"),
                            "type": "Assignment",
                            "_dt": end_utc
                        })
    except Exception as e:
        print(f"  [WARN] Dropbox fetch failed for {course_name}: {e}")

weekly_deadlines.sort(key=lambda x: x["_dt"])
for d in weekly_deadlines:
    del d["_dt"]

print(f"\n=== Section 1: Learn Deadlines This Week ({len(weekly_deadlines)} found) ===")
for d in weekly_deadlines:
    print(f"  [{d['course']}] {d['name']} — due {d['due_et']} ({d['type']})")
if not weekly_deadlines:
    print("  (none this week)")
print()

# ==========================================
# Section 2: Crowdmark Pending Items
# ==========================================


def load_crowdmark_session():
    session = requests.Session()
    with open(f"{SCRIPTS_DIR}/crowdmark_cookies.json") as f:
        for c in json.load(f):
            session.cookies.set(c["name"], c["value"], domain=c.get("domain", ""))
    session.headers.update({"Accept": "application/vnd.api+json"})
    return session


cm_session = load_crowdmark_session()

try:
    r = cm_session.get(
        "https://app.crowdmark.com/api/v2/student/assignments?include=course,exam-master",
        timeout=30
    )
    r.raise_for_status()
    cm_data = r.json()
except Exception as e:
    print(f"  [ERROR] Crowdmark fetch failed: {e}")
    cm_data = {"data": [], "included": []}

# Build maps from included objects
course_map = {}
em_map = {}
for item in cm_data.get("included", []):
    if item.get("type") == "courses":
        attrs = item.get("attributes", {})
        course_map[item["id"]] = attrs.get("name", f"Course {item['id']}")
    elif item.get("type") == "exam-masters":
        attrs = item.get("attributes", {})
        em_map[item["id"]] = {
            "title": attrs.get("title", "Unknown"),
            "total_points": attrs.get("total-points", 0)
        }

pending_crowdmark = []
awaiting_grade = []

for assignment in cm_data.get("data", []):
    attrs = assignment.get("attributes", {})
    submitted_at = attrs.get("submitted-at")
    marks_sent_at = attrs.get("marks-sent-at")
    due_raw = attrs.get("due")

    em_rel = assignment.get("relationships", {}).get("exam-master", {}).get("data", {})
    em_id = em_rel.get("id", "") if em_rel else ""
    em_info = em_map.get(em_id, {"title": "Unknown", "total_points": 0})
    name = em_info["title"]
    total_pts = em_info["total_points"]

    course_rel = assignment.get("relationships", {}).get("course", {}).get("data", {})
    course_id = course_rel.get("id", "") if course_rel else ""
    course_name = course_map.get(course_id, f"Course {course_id}")

    due_et_str = None
    due_utc = None
    if due_raw:
        due_utc = datetime.fromisoformat(due_raw.replace("Z", "+00:00"))
        due_et_str = due_utc.astimezone(EDT).strftime("%a %b %d, %I:%M %p EDT")

    # Submitted, awaiting grade — Spring 2026 courses
    if submitted_at is not None and marks_sent_at is None and "2026" in course_name:
        submitted_utc = datetime.fromisoformat(submitted_at.replace("Z", "+00:00"))
        awaiting_grade.append({
            "course": course_name,
            "name": name,
            "submitted": submitted_utc.astimezone(EDT).strftime("%Y-%m-%d %I:%M %p EDT"),
            "max_points": total_pts,
            "due": due_et_str,
        })

    # Not submitted + due this week (any course)
    elif submitted_at is None and due_utc and week_start_utc <= due_utc <= week_end_utc:
        pending_crowdmark.append({
            "course": course_name,
            "name": name,
            "due": due_et_str,
            "max_points": total_pts,
        })

print(f"=== Section 2: Crowdmark Pending Items ===")
print(f"  NOT submitted, due this week ({len(pending_crowdmark)}):")
for p in sorted(pending_crowdmark, key=lambda x: x.get("due", "")):
    print(f"    [{p['course']}] {p['name']} — due {p['due']} (/{p['max_points']} pts)")
if not pending_crowdmark:
    print("    (none due this week)")

print(f"  Submitted, awaiting grade — Spring 2026 ({len(awaiting_grade)}):")
for a in sorted(awaiting_grade, key=lambda x: x["submitted"]):
    print(f"    [{a['course']}] {a['name']} — submitted {a['submitted']} (/{a['max_points']} pts)")
if not awaiting_grade:
    print("    (none)")
print()

# ==========================================
# Section 3: Piazza Courses with Unread Instructor Answers
# ==========================================


def load_piazza_cookies():
    with open(f"{SCRIPTS_DIR}/piazza_cookies.json") as f:
        cookies_list = json.load(f)
    cookie_dict = {}
    session_id = None
    for c in cookies_list:
        if "piazza.com" in c.get("domain", ""):
            cookie_dict[c["name"]] = c["value"]
            if c["name"] == "session_id":
                session_id = c["value"]
    return session_id, cookie_dict


def piazza_api(session_id, cookie_dict, method, params):
    resp = requests.post(
        f"https://piazza.com/logic/api?method={method}",
        json={"method": method, "params": params},
        headers={
            "CSRF-Token": session_id,
            "Content-Type": "application/json",
        },
        cookies=cookie_dict,
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()


session_id, piazza_cookies = load_piazza_cookies()
print(f"  Piazza: loaded {len(piazza_cookies)} cookies, session_id={'yes' if session_id else 'NO'}")

status_resp = piazza_api(session_id, piazza_cookies, "user.status", {})
all_networks = status_resp.get("result", {}).get("networks", [])
print(f"  Found {len(all_networks)} Piazza networks total")

# Filter to Spring/Summer 2026
spring_2026_networks = []
for n in all_networks:
    term = n.get("term", "")
    if "2026" in term:
        spring_2026_networks.append({
            "nid": n.get("id") or n.get("nid") or n.get("_id"),
            "name": n.get("name", "Unknown"),
            "term": term,
            "course_number": n.get("course_number", "")
        })

print(f"  Spring/Summer 2026 networks: {len(spring_2026_networks)}")
print()

courses_with_unread_instructor = []

for network in spring_2026_networks:
    nid = network["nid"]
    course_label = f"{network['course_number']} - {network['name']}" if network["course_number"] else network["name"]

    try:
        feed_resp = piazza_api(session_id, piazza_cookies, "network.get_my_feed", {
            "nid": nid,
            "limit": 50,
            "offset": 0
        })
        feed_result = feed_resp.get("result", {})
        feed_items = feed_result.get("feed", [])
        unseen_total = feed_result.get("unseen_items", 0)

        unread_with_instructor = []
        for item in feed_items:
            item_unseen = item.get("unseen_items", 0)
            if item_unseen > 0:
                has_i_answer = any(
                    event.get("n") == "i_answer"
                    for event in item.get("log", [])
                )
                if has_i_answer:
                    unread_with_instructor.append({
                        "nr": item.get("nr"),
                        "subject": item.get("subject", "No title"),
                        "unseen_items": item_unseen
                    })

        if unread_with_instructor:
            courses_with_unread_instructor.append({
                "nid": nid,
                "course": course_label,
                "term": network["term"],
                "unread_instructor_posts": unread_with_instructor,
                "count": len(unread_with_instructor),
                "total_unseen": unseen_total
            })
        print(f"    {course_label}: total_unread={unseen_total}, unread_with_instructor_answer={len(unread_with_instructor)}")

    except Exception as e:
        print(f"  [WARN] Feed fetch failed for {nid} ({course_label}): {e}")

print()
print(f"=== Section 3: Piazza Courses with Unread Instructor Answers ===")
if courses_with_unread_instructor:
    for c in courses_with_unread_instructor:
        print(f"  [{c['course']}] {c['count']} unread post(s) with instructor answers:")
        for p in c["unread_instructor_posts"]:
            print(f"    - @{p['nr']}: {p['subject']}")
else:
    print("  No courses have unread posts with instructor answers.")
print()

# ==========================================
# Save Results
# ==========================================

results = {
    "generated_at_et": now_et.strftime("%Y-%m-%d %I:%M %p EDT"),
    "week_window": {
        "start_et": week_start_et.strftime("%Y-%m-%d %H:%M EDT"),
        "end_et": week_end_et.strftime("%Y-%m-%d %H:%M EDT"),
    },
    "learn_deadlines_this_week": weekly_deadlines,
    "crowdmark_not_submitted_this_week": pending_crowdmark,
    "crowdmark_awaiting_grade_spring2026": awaiting_grade,
    "piazza_unread_instructor_answers": courses_with_unread_instructor,
}

with open(f"{SCRIPTS_DIR}/weekly_summary_result.json", "w") as f:
    json.dump(results, f, indent=2)

print("Results saved to scripts/weekly_summary_result.json")
