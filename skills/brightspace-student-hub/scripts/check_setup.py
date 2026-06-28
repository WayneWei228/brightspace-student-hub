#!/usr/bin/env python3
"""
Check onboarding setup status for brightspace-student-hub skill.
Verifies:
  1. Chrome profile directory exists
  2. Chrome CDP is reachable on port 9222
  3. Saved passwords exist for the Brightspace instance
  4. Screen lock for password filling is disabled

On first run, also auto-discovers the Brightspace base_url from open Chrome
tabs and writes scripts/config.json if it doesn't exist.
"""

import os
import json
import sqlite3
import shutil
import requests
import tempfile

# ── Config ────────────────────────────────────────────────────────────────────

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPTS_DIR, "config.json")
CDP_BASE = "http://localhost:9222"

# Brightspace domains (for auto-discovery from open tabs)
BRIGHTSPACE_INDICATORS = [
    "/d2l/home",
    "/d2l/lms/",
    "brightspace.com",
]

# Known SSO subdomain patterns — check these if institution domain has no saved password
SSO_SUBDOMAIN_PATTERNS = ["adfs.", "sso.", "login.", "auth.", "idp.", "fed."]

# ── Load or bootstrap config ──────────────────────────────────────────────────

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

def get_profile_dir(config):
    return config.get("chrome_profile", os.path.expanduser(
        "~/Library/Application Support/Codex/LearnChromeProfile"
    ))

# ── Helpers ───────────────────────────────────────────────────────────────────

def check_profile_exists(config):
    profile_dir = get_profile_dir(config)
    exists = os.path.isdir(profile_dir)
    return {
        "step": "profile_exists",
        "pass": exists,
        "detail": profile_dir if exists else f"Directory not found: {profile_dir}",
    }

def check_cdp_reachable():
    try:
        requests.get(f"{CDP_BASE}/json", timeout=3).json()
        try:
            version = requests.get(f"{CDP_BASE}/json/version", timeout=3).json()
            user_data = version.get("userDataDir", "")
            if user_data:
                return {
                    "step": "cdp_reachable",
                    "pass": True,
                    "detail": f"CDP reachable, profile: {user_data}",
                    "user_data_dir": user_data,
                }
        except Exception:
            pass
        return {
            "step": "cdp_reachable",
            "pass": True,
            "detail": "CDP reachable on port 9222",
        }
    except Exception as e:
        return {
            "step": "cdp_reachable",
            "pass": False,
            "detail": f"CDP not reachable on port 9222: {e}",
        }

def discover_brightspace_url():
    """Find a Brightspace tab in CDP and extract base_url."""
    try:
        tabs = requests.get(f"{CDP_BASE}/json", timeout=3).json()
        for tab in tabs:
            url = tab.get("url", "")
            for indicator in BRIGHTSPACE_INDICATORS:
                if indicator in url:
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    return f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        pass
    return None

def get_institution_domain(config):
    base_url = config.get("base_url", "")
    if not base_url:
        return None
    from urllib.parse import urlparse
    return urlparse(base_url).netloc  # e.g. "learn.uwaterloo.ca"

def find_saved_passwords(profile_dir, domain):
    """Search Login Data and Login Data For Account for entries matching domain."""
    login_files = [
        os.path.join(profile_dir, "Default", "Login Data"),
        os.path.join(profile_dir, "Default", "Login Data For Account"),
    ]
    rows = []
    for login_file in login_files:
        if not os.path.exists(login_file):
            continue
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            shutil.copy2(login_file, tmp_path)
            conn = sqlite3.connect(tmp_path)
            cur = conn.cursor()
            cur.execute("SELECT origin_url, username_value FROM logins")
            rows.extend(cur.fetchall())
            conn.close()
        except Exception:
            pass
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    return rows

def check_saved_passwords(config):
    profile_dir = get_profile_dir(config)
    institution_domain = get_institution_domain(config)

    if not institution_domain:
        return {
            "step": "saved_passwords",
            "pass": False,
            "detail": "No base_url in config — run with a Brightspace tab open to auto-discover",
        }

    rows = find_saved_passwords(profile_dir, institution_domain)

    # Check institution domain itself + known SSO subdomains
    base_domain = ".".join(institution_domain.split(".")[-2:])  # e.g. "uwaterloo.ca"
    candidates = [institution_domain] + [
        f"{prefix}{base_domain}" for prefix in SSO_SUBDOMAIN_PATTERNS
    ]

    found = {}
    for url, username in rows:
        for candidate in candidates:
            if candidate in url and candidate not in found:
                found[candidate] = username

    if found:
        return {
            "step": "saved_passwords",
            "pass": True,
            "found": found,
            "missing": [],
            "detail": f"Saved for: {list(found.keys())}",
        }
    else:
        return {
            "step": "saved_passwords",
            "pass": False,
            "found": {},
            "missing": [institution_domain],
            "detail": f"No saved password found for {institution_domain} or its SSO domains",
        }

def check_screen_lock_disabled(config):
    profile_dir = get_profile_dir(config)
    prefs_file = os.path.join(profile_dir, "Default", "Preferences")

    if not os.path.exists(prefs_file):
        return {
            "step": "screen_lock_disabled",
            "pass": False,
            "detail": "Preferences file not found — open Chrome with the profile first",
        }

    with open(prefs_file) as f:
        prefs = json.load(f)

    pm = prefs.get("password_manager", {})
    lock_enabled = pm.get("biometric_authentication_filling", False)

    return {
        "step": "screen_lock_disabled",
        "pass": not lock_enabled,
        "biometric_lock": lock_enabled,
        "detail": (
            "Screen lock is DISABLED (good)"
            if not lock_enabled
            else "Screen lock is ENABLED — disable at chrome://password-manager/settings"
        ),
    }

# ── Auto-discover and update config ───────────────────────────────────────────

def maybe_update_config(config):
    """If base_url is missing, try to discover from open Chrome tabs."""
    changed = False

    if not config.get("base_url"):
        # Try to discover from open Chrome tabs first
        discovered = discover_brightspace_url()
        config["base_url"] = discovered or "https://learn.uwaterloo.ca"
        domain = config["base_url"].lower()
        if "uwaterloo" in domain or "utoronto" in domain or "mcmaster" in domain:
            config.setdefault("timezone", "America/Toronto")
        elif "ubc" in domain:
            config.setdefault("timezone", "America/Vancouver")
        else:
            config.setdefault("timezone", "UTC")
        changed = True

    if not config.get("chrome_profile"):
        config["chrome_profile"] = os.path.expanduser(
            "~/Library/Application Support/Codex/LearnChromeProfile"
        )
        changed = True

    config.setdefault("term_filter", None)
    config.setdefault("download_dir", os.path.expanduser("~/Desktop/brightspace-downloads"))
    config.setdefault("integrations", {"crowdmark": False, "piazza": False})

    if changed:
        save_config(config)

    return config

# ── Main ──────────────────────────────────────────────────────────────────────

def run_all_checks():
    config = load_config()
    config = maybe_update_config(config)

    results = [
        check_profile_exists(config),
        check_cdp_reachable(),
        check_saved_passwords(config),
        check_screen_lock_disabled(config),
    ]

    all_pass = all(r["pass"] for r in results)

    output = {
        "all_pass": all_pass,
        "config": {
            "base_url": config.get("base_url"),
            "institution": config.get("institution"),
            "timezone": config.get("timezone"),
            "integrations": config.get("integrations"),
        },
        "checks": results,
    }

    print(json.dumps(output, indent=2))
    return all_pass

if __name__ == "__main__":
    ok = run_all_checks()
    exit(0 if ok else 1)
