# File Downloads Reference

## Pre-Download Confirmation (Required)

Before any file download begins — before any network request or file write — pause and present the following summary to the user and wait for explicit confirmation.

**Confirmation prompt (show all three items together):**

```
About to download [COURSE] files.

  Destination : /Users/you/Desktop/brightspace-downloads   (from config.download_dir)
  Layout      : course-first  →  downloads/ECE380/lectures/file.pdf
  On conflict : skip (existing files will not be overwritten)

Type a number to change a setting, or "confirm" / "yes" / "proceed" to start:
  1. Change destination path
  2. Change layout  (course-first | type-first)
  3. Change conflict policy  (skip | overwrite | rename)
```

Rules:
- **ALWAYS** show this prompt before any bulk download, even if the user has downloaded before.
- **DO NOT** start downloading until the user replies with "confirm", "yes", or "proceed" (case-insensitive).
- All three items (destination, layout, conflict policy) must appear in the **same** prompt — do not ask them as separate sequential questions.
- Defaults: destination = `config.download_dir`, layout = course-first, conflict = skip.
- If the user overrides destination or layout for this session, save the preference in memory but do not persist it back to `config.json` unless the user explicitly asks.

**Example tree preview** (include in the confirmation prompt when the course TOC is already known):

```
Will create:
  downloads/ECE380/lectures/lecture-01.pdf
  downloads/ECE380/lectures/lecture-02.pdf
  downloads/ECE380/labs/lab-01.pdf
  … (12 files total, 3 already exist — will be skipped)
```

## Folder Structure

```
downloads/<COURSE>/<TYPE>/filename.pdf
```

Download root is read from `config.json` → `download_dir`.

### Course Folder Names

Derived automatically from the enrollment `Name` field — never hardcoded:

```python
import re

def course_to_folder(name):
    """Convert enrollment name to a clean folder name.
    'ECE 380 (LEC 002)' -> 'ECE380'
    'ECE 380 Lab'       -> 'ECE380_Lab'
    'MATH 135 Online'   -> 'MATH135'
    'PSYCH 207 Online'  -> 'PSYCH207'
    """
    name = re.sub(r'\(.*?\)', '', name).strip()   # remove "(LEC 002)" etc.
    name = re.sub(r'\b(Online|Lecture|Section)\b', '', name, flags=re.I).strip()
    parts = name.split()
    if parts and parts[-1].lower() == "lab":
        return "".join(parts[:-1]) + "_Lab"
    return "".join(parts[:2]) if len(parts) >= 2 else parts[0]
```

### Type Classification (by D2L Module Title Keywords)

| Module keyword | Subfolder |
|---|---|
| lecture, slides, chapter | `lectures/` |
| lab, manual | `labs/` |
| tutorial, pss | `tutorials/` |
| assignment, hw, homework | `assignments/` |
| exam, midterm, final | `exams/` |
| solution | `solutions/` |
| course info, outline, schedule | `course_info/` |
| (unclassified) | `other/` |

## Skip Existing Files (Default)

```python
import os

def download_file(session, url, dest_path):
    if os.path.exists(dest_path):
        return "skipped"
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    resp = session.get(encode_url(url), stream=True)
    resp.raise_for_status()
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(8192):
            f.write(chunk)
    return "downloaded"
```

Always report both skip and download counts so the user knows existing files were preserved.

## Conflict Handling

Before downloading, scan the target directory:

```python
def scan_existing_files(download_root):
    existing = []
    for dirpath, _, filenames in os.walk(download_root):
        for fname in filenames:
            if fname == ".DS_Store":
                continue
            rel = os.path.relpath(os.path.join(dirpath, fname), download_root)
            existing.append(rel)
    return sorted(existing)
```

The conflict policy must be confirmed **upfront** as part of the Pre-Download Confirmation block (see above), not reactively after files are already found. The three options are:
- **Skip** (default) — preserve existing files
- **Overwrite** — replace with downloaded version
- **Rename** — save with suffix (e.g. `file_downloaded.pdf`)

**Personal notes protection**: Files matching `my-notes-*.md`, `annotated-*.md`, `personal-*.md`, or any file not matching known Brightspace download filenames must NEVER be overwritten — even if the user selects "overwrite" globally.

## Incremental Sync

Build the set of existing files first, compare against remote TOC, download only new files:

```python
def build_existing_set(download_root):
    existing = set()
    for dirpath, _, filenames in os.walk(download_root):
        for fname in filenames:
            if fname == ".DS_Store":
                continue
            rel = os.path.relpath(os.path.join(dirpath, fname), download_root)
            existing.add(rel)
    return existing
```

Match by relative path `<COURSE>/<TYPE>/filename`. If it exists locally, skip — the user may have annotated it.

## Custom Folder Structure

Two layout modes:

**Course-first (default):** `downloads/COURSE/TYPE/file`

**Type-first:** `downloads/TYPE/COURSE/file`

**Filename normalization** (optional): lowercase + hyphens

```python
import re

def normalize_filename(name):
    name = name.lower()
    name = re.sub(r'[^a-z0-9.\-]', '-', name)
    name = re.sub(r'-+', '-', name)
    return name.strip('-')
```

Layout preference is collected as part of the mandatory Pre-Download Confirmation block (see top of this file) — not as a separate question. It must appear alongside the destination path and conflict policy in one unified prompt before any download starts. Save preference for the session.

## Generate File Tree from Disk

Always use `find` — never reconstruct from logs:

```bash
find downloads -type f -not -name ".DS_Store" | sort
```

Or in Python:
```python
import subprocess
result = subprocess.run(
    ["find", "downloads", "-type", "f", "-not", "-name", ".DS_Store"],
    capture_output=True, text=True
)
files = sorted(result.stdout.strip().split("\n"))
```

Download stats JSON files can become stale after retry runs. Filesystem is the ground truth.
