# Brightspace (D2L) API Reference

## Table of Contents
- [API Version Matrix](#api-version-matrix)
- [Get Enrolled Courses (Always Call First)](#get-enrolled-courses-always-call-first)
- [Get Announcements](#get-announcements)
- [Get Deadlines](#get-deadlines)
- [Get Content TOC (root modules)](#get-content-toc-root-modules)
- [Get Module Structure](#get-module-structure)
- [Download a File](#download-a-file)
- [Multi-Source Deadline Aggregation](#multi-source-deadline-aggregation)
- [Timezone Conversion](#timezone-conversion)

Base URL: read from `scripts/config.json` → `base_url`. Works for any Brightspace instance (UWaterloo, UofT, McMaster, etc.).

## API Version Matrix

| Use case | Endpoint prefix |
|---|---|
| Enrollments | `/d2l/api/lp/1.26/` |
| Announcements, quizzes, dropbox, calendar | `/d2l/api/le/1.53/` |
| Content TOC, module structure | `/d2l/api/le/1.53/` |

> **Do not use `/d2l/api/le/1.75/{orgUnitId}/content/toc/`** — it returns `404` on
> current UWaterloo Learn (tested with API versions 1.53, 1.75, 1.26). Use
> `/content/root/` under the same version as the rest of the LE calls
> (`/d2l/api/le/1.53/`) instead.

## Get Enrolled Courses (Always Call First)

```
GET {base_url}/d2l/api/lp/1.26/enrollments/myenrollments/?orgUnitTypeId=3&isActive=1
```

Never hardcode course IDs — fetch dynamically at the start of every task.

```python
def get_active_courses(session, config):
    resp = session.get(
        f"{config['base_url']}/d2l/api/lp/1.26/enrollments/myenrollments/"
        "?orgUnitTypeId=3&isActive=1"
    )
    items = resp.json().get("Items", [])
    term = config.get("term_filter")
    if term:
        items = [i for i in items if term in i["OrgUnit"]["Name"]]
    return [{"id": i["OrgUnit"]["Id"], "name": i["OrgUnit"]["Name"]} for i in items]
```

Set `term_filter` in `config.json` to filter by term name (e.g. "Spring 2026", "Fall 2025"). Set to `null` for all active courses.

## Get Announcements

```
GET {base_url}/d2l/api/le/1.53/{orgUnitId}/news/
```

Response: `{ "Items": [...] }`

Each item:
- `Title` — announcement title
- `Body.Html` — full HTML body (strip tags for preview)
- `StartDate` — ISO 8601 UTC

Iterate all courses from `get_active_courses()`, merge results, sort by `StartDate` descending.

## Get Deadlines

Query three endpoints per course. Convert UTC → local timezone before displaying.

**Quizzes:**
```
GET {base_url}/d2l/api/le/1.53/{orgUnitId}/quizzes/?pageSize=100
```
Fields: `Name`, `EndDate`

**Dropbox (assignments):**
```
GET {base_url}/d2l/api/le/1.53/{orgUnitId}/dropbox/folders/
```
Fields: `Name`, `EndDate`

**Calendar events:**
```
GET {base_url}/d2l/api/le/1.53/{orgUnitId}/calendar/myeventiterators/?startDateTime=...&endDateTime=...&eventTypeId=1
```
Note: EventType=1 meaning varies per course — verify before relying on it.

## Get Content TOC (root modules)

```
GET {base_url}/d2l/api/le/1.53/{orgUnitId}/content/root/
```

> The `content/toc/` endpoint (any version) returns `404` on current UWaterloo
> Learn. Use `content/root/` instead. This is a **list of root module objects**,
> not an object with a `Modules[]` key.

Response is a **JSON array** of root module objects. Each root module has a
`Structure` key listing its direct children. Walk the tree by recursing into
child modules via `content/modules/{moduleId}/structure/`.

```python
def get_content_tree(session, base_url, org_unit_id):
    resp = session.get(f"{base_url}/d2l/api/le/1.53/{org_unit_id}/content/root/")
    data = resp.json()  # list
    all_items = []
    for root_mod in data:
        all_items.extend(root_mod.get("Structure", []))
    return all_items
```

Each item in `Structure`:
- `Title` — display name
- `Type` — `0` = module, `1` = topic
- `Url` — `/content/enforced/...` relative path when the topic is downloadable
- `TopicType` / `TypeIdentifier` — `d2l_file`, `lti_link`, `d2l_video`, `dropbox`, `quiz` (for topics)
- `FileSize` — bytes (may be 0 for some files)

Only `d2l_file` topics (Type=1, downloadable `Url`) are directly downloadable.

## Get Module Structure

```
GET {base_url}/d2l/api/le/1.53/{orgUnitId}/content/modules/{moduleId}/structure/
```

## Download a File

```
GET {base_url}{topic.Url}
```

Use Brightspace session cookies. Stream the response.

**URL encoding:** D2L URLs sometimes contain raw spaces. Encode the path component:

```python
from urllib.parse import urlparse, quote, urlunparse

def encode_url(url):
    parsed = urlparse(url)
    return urlunparse(parsed._replace(path=quote(parsed.path, safe="/")))
```

## Multi-Source Deadline Aggregation

When fetching deadlines, always query Learn first, then optionally extend with Piazza.

**Algorithm:**

1. Always query Learn quizzes (`/quizzes/?pageSize=100`) and dropbox (`/dropbox/folders/`) for every enrolled course.
2. Label each Learn result with `source`: `"Learn (quiz)"` or `"Learn (dropbox)"`.
3. Check `config.integrations.piazza`:
   - If `true` and `piazza_cookies.json` exists: load the file, discover enrolled network IDs via the `user.status` API (the `piazza_session` JWT no longer carries `nids`), then call `network.get_my_feed` (limit 50) per network.
   - For each feed post whose **subject OR body snippet** (`content_snipet`) matches deadline keywords — `due`, `deadline`, `submit`, `submission`, `submit by`, `due date` — add it to results with `source` set to `"Piazza (<post subject>)"`. Scanning the body is required because instructors frequently put the due date in the body of a post whose title has no deadline keyword.
4. Deduplicate the combined list by `(normalised course name, normalised assignment name)` to avoid showing the same deadline twice when both Learn and Piazza mention it.
5. Sort final list by `sort_key` (ISO UTC timestamp).

**Keyword pattern (case-insensitive):**
```
\bdue\b | \bdeadline\b | \bsubmit\b | \bsubmission\b | \bdue date\b | \bsubmit by\b
```

**Result shape (every item):**
```json
{
  "course":         "ECE 380 — Digital Circuits",
  "name":           "Lab 3 submission",
  "due_date_local": "2026-07-04 11:59 PM EDT",
  "due_date_utc":   "2026-07-05T03:59:00Z",
  "type":           "Assignment",
  "source":         "Learn (dropbox)",
  "sort_key":       "2026-07-05T03:59:00+00:00"
}
```

`source` is always present — callers use it to distinguish origin and apply per-source display formatting.

## Timezone Conversion

Read timezone from `config.json` → `timezone` (e.g. `"America/Toronto"`, `"America/Vancouver"`).

```python
from datetime import datetime
from zoneinfo import ZoneInfo

def utc_to_local(iso_str, tz_name):
    if not iso_str:
        return None
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    return dt.astimezone(ZoneInfo(tz_name))
```

Default to `"UTC"` if `timezone` is missing from config. Never hardcode `UTC-4` or EDT.
