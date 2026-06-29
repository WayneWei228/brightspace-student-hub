#!/usr/bin/env python3
"""Scan the workspace root for sync-init suggestions.

The agent calls this BEFORE asking the user the 4 init questions, so each
question can be pre-filled with a sensible default instead of being a blank
form. Output is JSON on stdout:

{
  "workspace_root": "/path/to/repo",
  "destination_suggestion": "/path/to/repo",
  "existing_download_dirs": ["downloads/", "brightspace-downloads/"],
  "layout_suggestion": "course-first",
  "existing_structure_hint": "course-first | type-first | empty | mixed",
  "potential_protected_files": [
    {"path": "notes/foo.md",       "reason": "markdown file"},
    {"path": "ECE327/lec-03-mine.pdf", "reason": "name matches personal pattern"},
    ...
  ],
  "protected_patterns_default": ["my-notes-*.md", "annotated-*.md", "annotated-*.pdf", "*-personal.*"]
}

Default destination is the directory the user is currently working in
(workspace_root). This matches the discussion: "默认的下载地址是用户当前打开的folder".

Usage:
    python3 scripts/scan_workspace.py                # scan cwd
    python3 scripts/scan_workspace.py /some/path      # scan a specific root
"""
import os
import re
import sys
import json
import argparse


# Personal-note / annotated-file heuristics. Biased toward false positives —
# it's cheaper to let the user uncheck a wrongly-flagged file than to miss one
# the user actually cares about.
PERSONAL_NAME_RE = re.compile(
    r"(note|annotated|personal|mine|my_|手写|标注|笔记)",
    re.IGNORECASE,
)

# Filenames typical of Brightspace course downloads — used to AVOID flagging
# them as personal (they're clearly replaceable remote content).
TYPICAL_REMOTE_RE = re.compile(
    r"(lecture[-_ ]?\d|lab[-_ ]?\d|tutorial[-_ ]?\d|assignment[-_ ]?\d|"
    r"solution[-_ ]?\d|exam[-_ ]?\d|midterm|final|syllabus|outline|"
    r"chapter[-_ ]?\d|slides[-_ ]?\d)",
    re.IGNORECASE,
)

MAX_SCAN_FILES = 5000  # safety cap so we don't walk a giant workspace forever


def safe_walk(root):
    """Yield (dirpath, filenames) up to a sane cap, skipping .git/node_modules."""
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root):
        # prune heavy / irrelevant dirs
        dirnames[:] = [d for d in dirnames if d not in
                       {".git", "node_modules", "__pycache__", ".venv", "venv",
                        "Library", ".Trash", ".cache"}]
        yield dirpath, filenames
        seen += len(filenames)
        if seen > MAX_SCAN_FILES:
            return


def detect_layout(root):
    """Infer course-first vs type-first from existing folder structure.

    Returns ("course-first"|"type-first"|"empty"|"mixed", hint).
    """
    top = [d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))
           and not d.startswith(".")]
    if not top:
        return ("empty", "no existing course/type folders")

    # course-first: top-level dirs look like course codes (ECE327, MATH135...)
    course_like = [d for d in top if re.match(r"^[A-Z]{2,5}\s?\d{2,4}", d)
                   or re.match(r"^[A-Z]{2,5}\d{2,4}", d)]
    # type-first: top-level dirs are lectures/labs/tutorials/...
    type_like = [d for d in top if d.lower() in
                 {"lectures", "labs", "tutorials", "assignments", "exams",
                  "solutions", "course_info", "other"} and any(
                      os.path.isdir(os.path.join(root, d, sub))
                      for d in [d] for sub in os.listdir(os.path.join(root, d))
                  )]

    if course_like and not type_like:
        return ("course-first", f"existing course dirs: {course_like[:3]}")
    if type_like and not course_like:
        return ("type-first", f"existing type dirs: {type_like[:3]}")
    if not course_like and not type_like:
        return ("empty", "top-level dirs don't look like course or type")
    return ("mixed", "both course-like and type-like top-level dirs found")


def find_potential_protected(root):
    """Find files the user might not want overwritten.

    Heuristics (biased toward listing more, let user uncheck):
      - any .md / .txt file (could be notes)
      - any file whose name matches personal pattern (note/annotated/mine/...)
        AND does NOT match typical remote pattern (lecture-NN etc.)
    Returns list of {path (relative), reason}.
    """
    results = []
    for dirpath, filenames in safe_walk(root):
        for fname in filenames:
            if fname.startswith("."):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fname), root)

            # Explicit personal/labelling intent wins over content-theme match.
            # A file named "my-notes-lecture-03.md" IS the user's notes even
            # though "lecture-03" looks like a remote download pattern.
            if PERSONAL_NAME_RE.search(fname):
                results.append({"path": rel, "reason": "name matches personal pattern"})
                continue

            # markdown / text files are likely notes (skip obvious remote stuff
            # like "lecture-NN.md" that Brightspace might ship)
            ext = os.path.splitext(fname)[1].lower()
            if ext in {".md", ".txt", ".markdown"} and not TYPICAL_REMOTE_RE.search(fname):
                results.append({"path": rel, "reason": "markdown/text file"})

    # cap + sort for a clean presentation to the agent
    results.sort(key=lambda r: r["path"])
    return results[:300]


def main():
    parser = argparse.ArgumentParser(description="Scan workspace for sync-init suggestions.")
    parser.add_argument("workspace_root", nargs="?", default=os.getcwd(),
                        help="Workspace root to scan (default: cwd)")
    args = parser.parse_args()

    root = os.path.abspath(args.workspace_root)
    if not os.path.isdir(root):
        print(json.dumps({"error": f"not a directory: {root}"}))
        sys.exit(1)

    layout, layout_hint = detect_layout(root)

    output = {
        "workspace_root": root,
        "destination_suggestion": root,  # default = user's current folder (per discussion)
        "existing_download_dirs": [
            d for d in os.listdir(root)
            if os.path.isdir(os.path.join(root, d)) and "download" in d.lower()
        ],
        "layout_suggestion": layout if layout in ("course-first", "type-first") else "course-first",
        "existing_structure_hint": layout_hint,
        "potential_protected_files": find_potential_protected(root),
        "protected_patterns_default": [
            "my-notes-*.md", "annotated-*.md", "annotated-*.pdf", "*-personal.*"
        ],
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()