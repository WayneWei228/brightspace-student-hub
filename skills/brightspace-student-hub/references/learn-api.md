# Brightspace (D2L) API Reference

Base URL: read from `scripts/config.json` → `base_url`. Works for any Brightspace instance (UWaterloo, UofT, McMaster, etc.).

## API Version Matrix

| Use case | Endpoint prefix |
|---|---|
| Enrollments | `/d2l/api/lp/1.26/` |
| Announcements, quizzes, dropbox, calendar | `/d2l/api/le/1.53/` |
| Content TOC, module structure | `/d2l/api/le/1.75/` |

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

## Get Content TOC

```
GET {base_url}/d2l/api/le/1.75/{orgUnitId}/content/toc/
```

Returns nested structure: `Modules[]` (each has `Title`, `Modules[]`, `Topics[]`)

Each topic has:
- `Title` — display name
- `TypeIdentifier` — `d2l_file`, `lti_link`, `d2l_video`, `dropbox`, `quiz`
- `Url` — `/content/enforced/...` path (only for `d2l_file`)
- `FileSize` — bytes (may be 0 for some files)

Only `d2l_file` topics are directly downloadable.

## Get Module Structure

```
GET {base_url}/d2l/api/le/1.75/{orgUnitId}/content/modules/{moduleId}/structure/
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
