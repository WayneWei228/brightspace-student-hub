# Onboarding Reference

Before any task can run, two one-time setup steps must be completed by the user.
Run `check_setup.py` to detect the current state, then guide the user through
whichever steps are incomplete.

## Step 1 — Create the Chrome Profile

The skill uses a dedicated Chrome profile at:
```
~/Library/Application Support/Codex/LearnChromeProfile
```

**Check:** Does this directory exist?

If not, launch Chrome once with the profile flag to create it:
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/Library/Application Support/Codex/LearnChromeProfile"
```

Wait 3 seconds, then kill it. The directory and Default/Preferences file will exist.

**Verification:** `os.path.isdir(PROFILE_DIR)` returns True.

---

## Step 2 — Save Passwords in Chrome

The user must save their UWaterloo username and password in the Chrome profile's
password manager for each platform. AI never sees the credentials — Chrome fills
them automatically on login.

### Required platforms

| Platform | URL to visit |
|---|---|
| Learn (D2L) | `https://learn.uwaterloo.ca` |
| Crowdmark | `https://app.crowdmark.com/student` |

Piazza uses LTI from Learn and does not require a saved password.

### How to guide the user

Tell the user:

> "Please open Chrome and go to [URL]. When you see the login form, enter your
> UWaterloo username and password. Chrome will show a popup asking to save the
> password — click **Save**. Then come back."

Then wait. Poll `check_setup.py` every 10 seconds to detect when the password
is saved. Do not ask the user to confirm — detect it automatically.

**Verification:** Query `Default/Login Data` SQLite database:
```python
cur.execute("SELECT origin_url, username_value FROM logins")
# Check that a row exists for learn.uwaterloo.ca and app.crowdmark.com
```

---

## Step 3 — Disable Screen Lock for Password Filling

**This is a HARD BLOCKER. Do not proceed with any task until this is fixed.**

If "Use your screen lock when filling passwords" is enabled, Chrome requires
biometric/PIN confirmation before autofilling saved passwords. This completely
blocks headless automation — Chrome will not autofill without user interaction.

There is NO workaround. CDP cookie extraction does not help here because the
issue is Chrome refusing to autofill the password on the login page. The only
fix is to disable this setting.

### How to guide the user

Tell the user:

> "Please open Chrome and go to **chrome://password-manager/settings**. Turn OFF
> **Use your screen lock when filling passwords**. Then let me know."

**Important:** Chrome must be closed and reopened, OR the user must change the
setting in the currently running Chrome window. Writing to Preferences while
Chrome is running has no effect — Chrome overwrites it on exit.

**Verification:** Read `Default/Preferences` JSON:
```python
prefs["password_manager"]["biometric_authentication_filling"] == False
# (key absent also means disabled)
```

---

## Onboarding Flow (for the AI to follow)

```
run check_setup.py
│
├── profile_exists: FAIL
│   → "Run this command to create the profile: [command]"
│   → Wait 5s, re-check
│
├── saved_passwords: FAIL (missing: ["learn.uwaterloo.ca"])
│   → "Open Chrome (command below), go to learn.uwaterloo.ca, log in,
│      save password when prompted"
│   → Launch Chrome with profile, open the URL via browser-use
│   → Poll check_setup.py every 10s until password appears
│   → Repeat for each missing domain
│
├── screen_lock_disabled: FAIL
│   → "Go to chrome://password-manager/settings and turn off
│      'Use your screen lock when filling passwords'"
│   → Poll check_setup.py every 5s until biometric_authentication_filling = false
│
└── all_pass: TRUE → proceed to the requested task
```

## Cookie Refresh (after setup is complete)

When a platform API returns 401 or redirects to login:

1. Run `check_setup.py` to confirm passwords are still saved
2. Use browser-use to navigate to the platform URL in the LearnChromeProfile
3. Chrome auto-fills the saved password and submits
4. Wait for the auth cookie to appear (poll CDP `Network.getAllCookies`)
5. Re-export cookies and retry the original API call

**Success criteria for cookie refresh:**
- Learn: `d2lSessionVal` or `D2LSessionVal` cookie present for `learn.uwaterloo.ca`
- Crowdmark: `crowdmark_session` or equivalent auth cookie present for `app.crowdmark.com`
- Piazza: `session_id` present for `piazza.com`
