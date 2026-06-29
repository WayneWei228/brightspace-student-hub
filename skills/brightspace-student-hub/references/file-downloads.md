# File Downloads Reference

## Table of Contents
- [Pre-Download Confirmation (Required)](#pre-download-confirmation-required)
- [Folder Structure](#folder-structure)
- [Skip Existing Files (Default)](#skip-existing-files-default)
- [Conflict Handling](#conflict-handling)
- [Incremental Sync](#incremental-sync)
- [Custom Folder Structure](#custom-folder-structure)
- [Generate File Tree from Disk](#generate-file-tree-from-disk)

## Pre-Download Confirmation (Required)

The three settings this prompt asks for — destination, layout, conflict policy
— are **read from `SYNC_PREFERENCES.md`** if it exists (see
`references/sync-init.md` for how that file is generated). When a setting is
present in the md file, show it as the resolved value and do **not** re-ask it;
the user can still override for this download by picking a number. If
`SYNC_PREFERENCES.md` is missing entirely, run sync-init first.

Before any file download begins — before any network request or file write —
pause and present the following summary to the user and wait for explicit
confirmation.

**Confirmation prompt (show all settings together):**

```
About to download [COURSE] files.

  Destination : /Users/you/your-repo             (from SYNC_PREFERENCES.md)
  Layout      : course-first  →  ECE380/lectures/file.pdf
  On conflict : skip (existing files will not be overwritten)
  Protected   : 4 patterns + 2 explicit files will be skipped regardless of conflict policy
                (see USER_NOTED_FILES.md)

Type a number to change a setting for this download, or "confirm" / "yes" / "proceed" to start:
  1. Change destination path (this download only — edit SYNC_PREFERENCES.md to persist)
  2. Change layout  (course-first | type-first)
  3. Change conflict policy  (skip | overwrite | rename)
```

Rules:
- **ALWAYS** show this prompt before any bulk download, even if the user has downloaded before.
- **DO NOT** start downloading until the user replies with "confirm", "yes", or "proceed" (case-insensitive).
- All settings must appear in the **same** prompt — do not ask them as separate sequential questions.
- Resolve defaults by reading `SYNC_PREFERENCES.md` (destination → `## destination`, layout → `## layout`, conflict policy → `## conflict_policy`). If the file is absent, run sync-init first (see `references/sync-init.md`).
- If `SYNC_PREFERENCES.md## course_mapping` is present, use it to override the default `course_to_folder()` derivation for the named course.
- If the user overrides a setting for this download, save the preference in memory only — do not persist it back to the md file unless the user explicitly asks.

**Example tree preview** (include in the confirmation prompt when the course TOC is already known):

```
Will create:
  ECE380/lectures/lecture-01.pdf
  ECE380/lectures/lecture-02.pdf
  ECE380/labs/lab-01.pdf
  … (12 files total, 3 already exist — will be skipped)
```

## Folder Structure

```
downloads/<COURSE>/<TYPE>/filename.pdf
```

Download root is read from `SYNC_PREFERENCES.md` → `## destination` (which
defaults to the user's current folder). Falls back to `config.json` →
`download_dir` only if the md file is absent (in which case sync-init should
have run first).

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

**Personal notes protection**: Files matching the patterns in `USER_NOTED_FILES.md## patterns`, or listed under `USER_NOTED_FILES.md## explicit files`, must NEVER be overwritten — even if the user selects "overwrite" globally. If `USER_NOTED_FILES.md` is absent, fall back to the hardcoded defaults: `my-notes-*.md`, `annotated-*.md`, `personal-*.md`, and any file not matching known Brightspace download filenames. Run sync-init to populate the md file (see `references/sync-init.md`).

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
