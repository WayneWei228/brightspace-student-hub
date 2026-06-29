#!/usr/bin/env python3
"""
Fetch Crowdmark grades: Spring 2026 assignment-level scores and per-question instructor feedback.
Uses existing crowdmark_cookies.json.
"""

import os
import json
import requests
from datetime import datetime, timezone, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")
COOKIES_FILE = os.path.join(SCRIPT_DIR, "crowdmark_cookies.json")
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "crowdmark_grades_result.json")

EDT = timezone(timedelta(hours=-4))
BASE_URL = "https://app.crowdmark.com"


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {"term_filter": None}


def load_session():
    session = requests.Session()
    with open(COOKIES_FILE) as f:
        cookies = json.load(f)
    for c in cookies:
        session.cookies.set(c["name"], c["value"], domain=c.get("domain", ""))
    session.headers.update({
        "Accept": "application/vnd.api+json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    })
    return session


def utc_to_et(iso_str):
    if not iso_str:
        return None
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    return dt.astimezone(EDT).strftime("%Y-%m-%d %I:%M %p ET")


def fetch_assignments_with_includes(session):
    resp = session.get(f"{BASE_URL}/api/v2/student/assignments?include=course,exam-master")
    resp.raise_for_status()
    return resp.json()


def fetch_results(session, score_uuid):
    """Fetch per-question grades and instructor feedback via v1 API."""
    resp = session.get(f"{BASE_URL}/api/v1/student/results/{score_uuid}")
    if resp.status_code != 200:
        return None
    return resp.json()


def extract_feedback(results_data):
    """
    Extract CommentAnnotation feedback from JSON:API included array.
    Returns list of {text, points} dicts for all CommentAnnotation items.
    """
    if results_data is None:
        return []
    included = results_data.get("included", [])
    feedback = []
    for item in included:
        if item.get("type") == "annotations":
            attrs = item.get("attributes", {})
            if attrs.get("type") == "CommentAnnotation":
                text = attrs.get("metadata", {}).get("text", "").strip()
                pts = attrs.get("points", None)
                if pts is not None:
                    try:
                        pts = float(pts)
                    except (ValueError, TypeError):
                        pts = None
                if text:
                    feedback.append({"text": text, "points": pts})
    return feedback


def extract_evaluations(results_data):
    """
    Extract per-question evaluation points from JSON:API included array.
    Returns list of {id, points, state} dicts.
    """
    if results_data is None:
        return []
    included = results_data.get("included", [])
    evals = []
    for item in included:
        if item.get("type") == "evaluations":
            attrs = item.get("attributes", {})
            pts = attrs.get("points", None)
            if pts is not None:
                try:
                    pts = float(pts)
                except (ValueError, TypeError):
                    pts = None
            evals.append({
                "id": item["id"],
                "points": pts,
                "state": attrs.get("state", "")
            })
    return evals


def main():
    config = load_config()
    term_filter = config.get("term_filter")

    print("Loading Crowdmark session...")
    session = load_session()

    print("Fetching assignments (with course and exam-master includes)...")
    data = fetch_assignments_with_includes(session)

    # Build lookup maps
    em_map = {}
    course_map = {}
    for item in data.get("included", []):
        t = item.get("type")
        if t == "exam-masters":
            em_map[item["id"]] = item
        elif t == "courses":
            course_map[item["id"]] = item

    print(f"Total courses found: {len(course_map)}")

    # Process assignments — optionally filter by term
    results = []
    for a in data.get("data", []):
        em_id = a["relationships"]["exam-master"]["data"]["id"]
        em = em_map.get(em_id, {})
        em_attrs = em.get("attributes", {})

        # Get course from exam-master relationships
        em_course_data = em.get("relationships", {}).get("course", {}).get("data", {})
        course_id = em_course_data.get("id") if isinstance(em_course_data, dict) else None

        course_name = course_map.get(course_id, {}).get("attributes", {}).get("name", "Unknown")
        if term_filter and term_filter.lower() not in course_name.lower():
            continue
        title = em_attrs.get("title", "Unknown")
        total_pts = em_attrs.get("total-points", 0)
        try:
            total_pts = float(total_pts) if total_pts is not None else 0.0
        except (ValueError, TypeError):
            total_pts = 0.0

        a_attrs = a.get("attributes", {})
        norm_pts = a_attrs.get("normalized-points", 0)
        try:
            norm_pts = float(norm_pts) if norm_pts is not None else 0.0
        except (ValueError, TypeError):
            norm_pts = 0.0

        submitted_at = a_attrs.get("submitted-at")
        marks_sent_at = a_attrs.get("marks-sent-at")
        score_uuid = a_attrs.get("score-uuid", "nope")

        # Calculate score
        if total_pts > 0 and marks_sent_at is not None:
            score = round(norm_pts * total_pts, 2)
            percentage = round(norm_pts * 100, 1)
        else:
            score = None
            percentage = None

        # Determine status
        if submitted_at is None:
            status = "Not submitted"
        elif marks_sent_at is None:
            status = "Submitted, awaiting grade"
        else:
            status = "Graded"

        # Fetch detailed results for graded assignments
        feedback = []
        evaluations = []
        if status == "Graded" and score_uuid and score_uuid != "nope":
            print(f"  Fetching results for '{title}' (uuid: {score_uuid[:8]}...)...")
            results_data = fetch_results(session, score_uuid)
            feedback = extract_feedback(results_data)
            evaluations = extract_evaluations(results_data)
            print(f"    -> {len(evaluations)} evaluations, {len(feedback)} comment(s)")

        results.append({
            "course": course_name,
            "assignment": title,
            "score": score,
            "max_score": total_pts,
            "percentage": percentage,
            "status": status,
            "submitted_at": utc_to_et(submitted_at),
            "marks_sent_at": utc_to_et(marks_sent_at),
            "feedback": feedback,
            "evaluations": evaluations,
        })

    # Sort by course, then by a logical order
    # Define sort order for assignment names
    def sort_key(r):
        name = r["assignment"].lower()
        # Put "not submitted" and "awaiting" after graded
        status_order = {"Graded": 0, "Submitted, awaiting grade": 1, "Not submitted": 2}
        return (r["course"], status_order.get(r["status"], 3), name)

    results.sort(key=sort_key)

    # Save to file
    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2)

    filter_label = f" ({term_filter})" if term_filter else " (all terms)"
    print(f"\nSaved {len(results)} assignments{filter_label} to {OUTPUT_FILE}")

    # Print display summary
    print(f"\n=== CROWDMARK GRADES{filter_label.upper()} ===\n")
    current_course = None
    for r in results:
        if r["course"] != current_course:
            current_course = r["course"]
            print(f"\n[{current_course}]")

        score_str = f"{r['score']}/{r['max_score']} ({r['percentage']}%)" if r['score'] is not None else "N/A"
        print(f"  {r['assignment']}: {r['status']} | Score: {score_str}")

        if r["feedback"]:
            print(f"    Instructor feedback ({len(r['feedback'])} comment(s)):")
            for fb in r["feedback"]:
                pts_tag = f" [{fb['points']:+.1f} pts]" if fb["points"] is not None else ""
                print(f"      -{pts_tag} {fb['text']}")

    return results


if __name__ == "__main__":
    main()
