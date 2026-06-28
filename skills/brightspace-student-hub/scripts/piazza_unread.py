#!/usr/bin/env python3
"""
Check all Piazza courses for unread posts.
Source: SKILL.md - Piazza API section
Uses: network.get_my_feed unseen_items field for unread count.
All 21 enrolled networks discovered via user.status API.
"""
import requests
import json
from datetime import datetime, timezone, timedelta

PIAZZA_BASE = "https://piazza.com"
EDT = timezone(timedelta(hours=-4))
COOKIES_FILE = "os.path.join(os.path.dirname(os.path.abspath(__file__)))/piazza_cookies.json"
OUTPUT_FILE = "os.path.join(os.path.dirname(os.path.abspath(__file__)))/piazza_unread_final.json"


def load_piazza_session():
    """Load session_id and all piazza.com cookies."""
    with open(COOKIES_FILE) as f:
        cookies_list = json.load(f)
    session_id = None
    cookie_dict = {}
    for c in cookies_list:
        if "piazza.com" in c.get("domain", ""):
            cookie_dict[c["name"]] = c["value"]
            if c["name"] == "session_id":
                session_id = c["value"]
    if not session_id:
        raise ValueError("session_id not found in piazza_cookies.json")
    return session_id, cookie_dict


def piazza_api(session_id, cookie_dict, method, params):
    """Call Piazza RPC API per SKILL.md Critical Authentication Requirements."""
    resp = requests.post(
        f"{PIAZZA_BASE}/logic/api?method={method}",
        json={"method": method, "params": params},
        headers={
            "CSRF-Token": session_id,
            "Content-Type": "application/json",
        },
        cookies=cookie_dict,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_all_networks(session_id, cookie_dict):
    """Get all enrolled networks with their names via user.status."""
    resp = piazza_api(session_id, cookie_dict, "user.status", {})
    if resp.get("error"):
        raise ValueError(f"user.status error: {resp['error']}")
    networks = resp["result"]["networks"]
    result = []
    for n in networks:
        nid = n.get("id") or n.get("nid") or n.get("_id")
        name = n.get("name", "Unknown")
        course_num = n.get("course_number", "")
        term = n.get("term", "")
        if nid:
            result.append({
                "nid": nid,
                "name": name,
                "course_number": course_num,
                "term": term,
            })
    return result


def get_unread_count(session_id, cookie_dict, nid):
    """
    Get unread post count for a network using network.get_my_feed.
    Per SKILL.md: 'unseen_items' field is the authoritative unread indicator.
    """
    resp = piazza_api(session_id, cookie_dict, "network.get_my_feed", {
        "nid": nid,
        "limit": 1,
        "offset": 0,
    })
    if resp.get("error"):
        return None, f"API error: {resp['error']}"
    result = resp.get("result", {})
    if result is None:
        return None, "Null result"
    # unseen_items at top level = total unread for this network
    unseen = result.get("unseen_items", 0)
    return unseen, None


def main():
    print("Loading Piazza cookies...")
    session_id, cookie_dict = load_piazza_session()

    print("Getting all enrolled networks...")
    networks = get_all_networks(session_id, cookie_dict)
    print(f"Found {len(networks)} networks")

    results = []
    for n in networks:
        nid = n["nid"]
        display_name = f"{n['course_number']} - {n['name']}" if n["course_number"] else n["name"]
        print(f"  Checking {display_name} ({nid})...", end=" ", flush=True)

        unread, error = get_unread_count(session_id, cookie_dict, nid)
        if error:
            print(f"ERROR: {error}")
            results.append({
                "nid": nid,
                "course_number": n["course_number"],
                "name": n["name"],
                "term": n["term"],
                "unread": None,
                "error": error,
            })
        else:
            print(f"unread={unread}")
            results.append({
                "nid": nid,
                "course_number": n["course_number"],
                "name": n["name"],
                "term": n["term"],
                "unread": unread,
                "error": None,
            })

    # Save results
    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved to {OUTPUT_FILE}")

    # Print summary table
    print("\n=== Unread Post Summary ===")
    has_unread = [r for r in results if r["unread"] and r["unread"] > 0]
    no_unread = [r for r in results if r["unread"] == 0]
    errors = [r for r in results if r["error"]]

    if has_unread:
        print("\nCourses with unread posts:")
        for r in sorted(has_unread, key=lambda x: -x["unread"]):
            course_label = f"{r['course_number']} - {r['name']}" if r["course_number"] else r["name"]
            print(f"  {course_label} ({r['term']}): {r['unread']} unread")
    else:
        print("\nNo courses have unread posts.")

    print(f"\nAll read ({len(no_unread)} courses), unread in {len(has_unread)} courses, errors: {len(errors)}")

    return results


if __name__ == "__main__":
    main()
