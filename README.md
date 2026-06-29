# Brightspace Student Hub

Brightspace Student Hub is a plugin for coding agents that gives students unified access to D2L Brightspace (Learn), Crowdmark, and Piazza — without logging in manually each time.

It packages a skill that uses cookie-based Python scripts to fetch announcements, deadlines, grades, course files, and Piazza posts from any authenticated Chrome session.

## Quickstart

Give your agent Brightspace Student Hub: [Claude Code](#claude-code), [Codex](#codex).

## How It Works

Course information is scattered across Brightspace (announcements, deadlines, files), Crowdmark (graded assignments, per-question feedback), and Piazza (Q&A, instructor answers). This plugin gives your agent one unified workflow:

1. `brightspace-student-hub` runs a setup check, discovers your enrolled courses dynamically from the Brightspace enrollment API, and routes requests to the right platform.
2. Cookies are extracted once from a running Chrome session via CDP and reused across all API calls — no browser automation needed for data retrieval.
3. Optional integrations (Crowdmark, Piazza) are enabled per-institution in `config.json`.

The skill avoids course-specific hardcoding. Courses are discovered from the logged-in account, and the Brightspace base URL defaults to `learn.uwaterloo.ca` but works for any institution.

## Requirements

- Python 3 with: `requests`, `websocket-client`, `zoneinfo`
- `browser-use` CLI for Chrome automation during login
- Chrome installed with a dedicated profile for the skill
- macOS (Chrome profile path currently macOS-specific)

Install or verify `browser-use` before first use:

```bash
curl -fsSL https://browser-use.com/cli/install.sh | bash
browser-use doctor
```

## Installation

Installation differs by harness. If you use both Claude Code and Codex, install separately for each.

### Claude Code

This repository includes a Claude Code plugin manifest at `.claude-plugin/plugin.json`.

Register the marketplace:

```bash
/plugin marketplace add WayneWei228/brightspace-student-hub
```

Install the plugin:

```bash
/plugin install brightspace-student-hub
```

Validate locally from a clone:

```bash
claude plugin validate .
```

### Codex

This repository includes a Codex plugin manifest at `.codex-plugin/plugin.json`.

Install from GitHub:

```bash
npx codex-marketplace add WayneWei228/brightspace-student-hub --plugin
```

Validate a local clone:

```bash
python3 /path/to/plugin-creator/scripts/validate_plugin.py .
```

## First-Time Setup

The skill guides you through setup automatically. Two one-time steps are required:

1. **Save your university password in Chrome** — navigate to your institution's login page in the dedicated Chrome profile and save the password when Chrome prompts.
2. **Disable "Use screen lock when filling passwords"** — go to `chrome://password-manager/settings` and turn off this toggle. This is required for Chrome to autofill passwords without user interaction.

Run the setup check at any time to see current status:

```bash
python3 skills/brightspace-student-hub/scripts/check_setup.py
```

Output shows pass/fail for: Chrome profile exists, CDP reachable, password saved, screen lock disabled.

## The Basic Workflow

1. **Setup check** — `check_setup.py` verifies the environment and writes `config.json` on first run.
2. **Login** — `browser-use` navigates Chrome to the platform; Chrome autofills the saved password.
3. **Cookie extraction** — CDP `Network.getAllCookies` exports session cookies to `scripts/`.
4. **Course discovery** — enrollment API returns all active courses for the current term; no hardcoded IDs.
5. **Data fetch** — Python scripts call Brightspace, Crowdmark, and Piazza APIs directly.
6. **Output** — results displayed with timestamps converted to the configured local timezone.

If a cookie expires mid-session, the skill refreshes it automatically and retries.

## What's Inside

### Skills

- **brightspace-student-hub** — unified access to Brightspace (announcements, deadlines, file downloads), Crowdmark (grades, per-question feedback), and Piazza (search, unread counts, weekly summary).

### Scripts

- `check_setup.py` — environment setup detector; auto-discovers `base_url` from open Chrome tabs; writes `config.json`
- `export_cookies.py` — CDP cookie extractor for Brightspace
- `export_crowdmark_cookies.py` — CDP cookie extractor for Crowdmark
- `fetch_announcements.py` — latest announcements across all enrolled courses
- `fetch_deadlines.py` — quizzes and dropbox deadlines within a configurable window
- `fetch_crowdmark_grades.py` — assignment scores and per-question instructor annotations
- `piazza_unread.py` — unread post counts for all enrolled Piazza networks
- `search_piazza_ece380.py` — keyword search within a Piazza course feed
- `weekly_summary.py` — cross-platform digest: deadlines + Crowdmark pending + Piazza unread
- `download_ece380.py` — course file download with folder classification and conflict handling

### References

- `authentication.md` — Chrome CDP setup, cookie extraction, SSO domain detection, cookie refresh
- `learn-api.md` — Brightspace REST API endpoints and course discovery pattern
- `crowdmark-api.md` — Crowdmark v2/v1 endpoints, submission status logic, annotation handling
- `piazza-api.md` — Piazza RPC API auth (Referer header, method param), feed and content endpoints
- `file-downloads.md` — folder structure, conflict handling, incremental sync, custom layouts
- `onboarding.md` — step-by-step first-time setup guide with verification criteria

## config.json

Generated automatically on first run. Edit to configure your institution:

```json
{
  "base_url": "https://learn.uwaterloo.ca",
  "timezone": "America/Toronto",
  "term_filter": "Spring 2026",
  "chrome_profile": "/Users/you/Library/Application Support/Codex/LearnChromeProfile",
  "download_dir": "/Users/you/Desktop/brightspace-downloads",
  "integrations": {
    "crowdmark": true,
    "piazza": true
  }
}
```

Set `term_filter` to `null` to get all active courses. Set `crowdmark` and `piazza` to `false` if your institution does not use these platforms.

## Privacy

Course data stays local:

- Do not commit cookie files (`*_cookies.json`) — they contain live session tokens.
- Do not commit `config.json` — it contains your Chrome profile path.
- Do not commit downloaded course materials.
- Do not commit result JSON files containing grades, announcements, or post content.

The `.gitignore` in this repository excludes all of the above.

## Repository Layout

```text
brightspace-student-hub/
├── .claude-plugin/
│   └── plugin.json
├── .codex-plugin/
│   └── plugin.json
├── skills/
│   └── brightspace-student-hub/
│       ├── SKILL.md
│       ├── references/
│       │   ├── authentication.md
│       │   ├── crowdmark-api.md
│       │   ├── file-downloads.md
│       │   ├── learn-api.md
│       │   ├── onboarding.md
│       │   └── piazza-api.md
│       └── scripts/
│           ├── check_setup.py
│           ├── download_ece380.py
│           ├── export_cookies.py
│           ├── export_crowdmark_cookies.py
│           ├── fetch_announcements.py
│           ├── fetch_crowdmark_grades.py
│           ├── fetch_deadlines.py
│           ├── piazza_unread.py
│           ├── search_piazza_ece380.py
│           └── weekly_summary.py
├── .gitignore
├── README.md
└── LICENSE
```

## Development Checks

Run before publishing:

```bash
python3 /path/to/plugin-creator/scripts/validate_plugin.py .
python3 -m py_compile skills/brightspace-student-hub/scripts/check_setup.py
```

Scan for sensitive or environment-specific content:

```bash
rg -n "(/Users/|C:\\\\Users\\\\|/home/|_cookies\.json|config\.json|password|secret|token)" skills/
rg -n "\\b[0-9]{7}\\b" skills/
```

Review any matches manually. Seven-digit numbers can be real Brightspace org-unit IDs.

## Contributing

1. Fork or branch the repository.
2. Keep workflows general — no course-specific hardcoding as the default path.
3. New institutions should work via `config.json` changes, not code changes.
4. Validate the plugin and skills before opening a PR.

## Updating

Reinstall using the same command you used to install. This pulls the latest version.

**Claude Code:**

```
/plugin install brightspace-student-hub
```

**Codex:**

```bash
npx codex-marketplace add WayneWei228/brightspace-student-hub --plugin
```

## License

MIT License — see `LICENSE` for details.
