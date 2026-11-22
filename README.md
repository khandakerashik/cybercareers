# CyberCareers BD v5.4.1

An hourly job radar for cybersecurity and information security roles in Bangladesh, plus international remote roles open to Bangladesh-based applicants. You can run it locally, or publish it to **GitHub Pages behind a login**: only you and the people you allow can sign in, and the published data is encrypted.

> A posting in the dashboard is a lead. Always confirm the vacancy, deadline and eligibility on the original posting.

---

## v5.4.1 — Publishing recovery

**If Actions fails at the encrypted-state commit with `fetch first`, use the [publishing repair guide](docs/UPGRADE_v5.4.1.md).** The workflow now deploys the site before attempting its optional repository backup. The backup works from the latest remote branch in a separate worktree, preserves concurrent changes, retries ordinary push races, and reports a warning when it cannot safely save. A failed backup no longer blocks Pages deployment.

Encrypted-state cache keys now include the full ref, run ID and run attempt. Re-running a workflow writes a new cache entry instead of colliding with an immutable entry from the previous attempt. Restore is scoped to the same ref; the default branch can migrate its older cache on the first upgraded run. Cache outages remain non-blocking.

After merging this update, start a **new workflow run on the updated branch**. Re-running an older failed execution keeps its original commit and may still use the old workflow.

## v5.4.0 — Scan now and live source progress

**Start here: [v5.4 upgrade and scanner guide](docs/UPGRADE_v5.4.md).** This release keeps the source repairs, detection, hourly completion reporting, Archived Jobs and Applied Jobs from v5.2/v5.3.

| Feature | Behaviour |
| --- | --- |
| Scan now locally | Starts the existing local collector through its protected same-origin endpoint. A running scan is followed instead of starting a second collector. |
| Scan now on GitHub Pages | Connect the repository's workflow using a token held only in the current tab's memory. The browser sends requests directly to GitHub; the token is cleared on disconnect, sign-out or reload. **Open GitHub Actions** provides an alternative way to run the workflow. |
| Source-by-source progress | Shows queued, checking, completed, limited, failed, cached/deferred and interrupted states, with source messages, jobs/new-job counts and measured durations. Search and state filters help locate a particular source. |
| Actual updates | Local progress refreshes approximately every two seconds; encrypted GitHub progress updates approximately every 15 seconds. Missing updates remain unknown or stale; a progress animation never substitutes for a reported result. |
| Completion and recovery | The previous completed fetch stays visible during a new or interrupted attempt. On Pages, source collection and publication are shown separately; updated jobs load after publication. Uncertain dispatches are monitored before another request is allowed. |

To trigger a workflow, a repository-authorized token needs **Actions write** access. Private live source details additionally need a compatible GitHub App token with **Checks read**, or a classic personal access token with `repo` scope. A fine-grained personal token can trigger scans even when it cannot read Checks; workflow status and the GitHub Actions link remain available. See the [permission choices and setup steps](docs/UPGRADE_v5.4.md#connect-github-pages).

The updated workflow publishes only encrypted progress in a custom check using its own `checks: write` permission. Optional progress-publication failures do not stop collection. No live repository was connected, dispatched or deployed while preparing this package; see [validation](docs/VALIDATION.md) for the completed offline checks.

## v5.3.0 — Archived Jobs and Applied Jobs

**Start here: [v5.3 upgrade and usage guide](docs/UPGRADE_v5.3.md).** Merge the complete package into the existing project, preserving your vault key, users, private configuration and collected data.

| Feature | Behaviour |
| --- | --- |
| Archived Jobs | Past-deadline and explicitly closed/expired listings have a dedicated section with search, region, sort and saved-only filters. Active Bangladesh and International pages exclude them. |
| Deadline handling | Uses Bangladesh calendar dates. A deadline today stays active through that day. An older posting without a known deadline stays unverified; publication age alone does not archive it. A fresh deadline extension can reopen a previously expired role. |
| Applied Jobs | Choose **Mark as applied** on a job card or details panel. The application date and a compact job reference are retained independently of future collection runs. |
| Short notes | Add or edit a plain-text note of up to 1,000 characters. Choose **Save note**; unsaved edits survive a dashboard refresh. |
| Personal history | Applied records remain available after a deadline passes or the listing disappears from the feed. Notes and application records are stored per site and signed-in account in this browser. They do not automatically sync between devices. |
| Export and removal | Export applications and notes as CSV, or remove an applied mark and its note. Marking/removing a record does not submit or withdraw an application with the employer. |

Application records are saved in browser storage rather than the shared collector dataset. Keep an exported copy before clearing browser data. The new `applications.js` file must be included when updating the site; the local server and Pages builder both support it.

## v5.2.0 repair release

**Start here: [Upgrade instructions](docs/UPGRADE_v5.2.md).** Keep your existing vault key, user configuration and collected data when merging this package into an existing installation.

| Area | Repair |
| --- | --- |
| False-positive events | Independent vacancy evidence rejects workshops, courses, news, advice, service pages and multi-job search pages. Cybersecurity relevance is assessed separately. |
| Existing records | Clear false positives are rechecked and retained with rejection reasons in a recoverable local review file. Plausible historic leads remain unverified rather than disappearing. |
| Missing vacancies | Preserves distinct LinkedIn requisition IDs, multiple roles in one PDF, multiple structured roles sharing a page, short titles such as SOC Analyst, and generic bank titles supported by security duties. |
| Source reliability | Repairs 16 employer routes, uses redirect-aware links and declared sitemaps, follows bounded pagination, improves ATS handling, and distinguishes inaccessible/partial/empty recruiting content. |
| LinkedIn alerts and search | Better HTML/plain-text alert parsing, persistent mail backlog, 26 search families, resumable search pagination, request budgets and exact posting identity. Coverage remains partial and visible. |
| Fetch status | Full completion time in BDT, run duration, failed/limited/cached counts, scheduler-aware next check, preserved previous completion on failure, and automatic published-snapshot refresh. |
| Dates and geography | Receipt/update dates stay separate from publication dates; expired alerts cannot expire newer official roles; explicit foreign eligibility takes precedence over company geography. |

**Measured audit:** 151 employer sources were checked, followed by 28 targeted rechecks. Latest per-source observations are 53 readable, 66 limited and 32 blocked/unavailable. These combined observations used HTTP only and do not certify exhaustive job retrieval. See [the audit and its limits](docs/SOURCE_AUDIT.md), [machine-readable observations](docs/source-audit-2026-11-22.json), and [validation](docs/VALIDATION.md).

The catalogue also contains 36 manual-link/restricted/directory entries and six publisher feeds. A catalogue link is not an automatic collector. Mailbox/API credentials must be configured before those optional channels can fetch anything.

## Earlier v5 features

### Detection

| Area | v4.2 | v5 |
| --- | --- | --- |
| Relevance | Substring keywords, so "mechan**isms**" and "cred**it audit**" matched while "Network Security Engineer" did not | Weighted bilingual engine (`collector/relevance.py`) with word boundaries, physical-security/AML/credit negatives, IT-context checks for ambiguous "Security Manager" titles, and description evidence for generic bank titles ("Senior Principal Officer … Information Security Division"). Every job gets a `relevance_score` and `matched_terms`. |
| robots.txt | Python's parser: first-match only, no wildcards, so `Disallow: /` + `Allow: /careers/` wrongly blocked careers pages; robots 403 counted as a failure | RFC 9309 matcher (`collector/robots.py`): longest match wins, `*`/`$` wildcards, 4xx = no restrictions, 5xx/network = disallow, and `Crawl-delay` is honoured |
| ATS providers | Greenhouse, Lever, Ashby (links only) | **+ Workday, Workable, SmartRecruiters, Recruitee, BambooHR, Personio, Breezy, Lever EU**, found from links, iframes, script embeds and career-page redirects |
| Remote roles from ATS boards | Dropped unless located in Bangladesh | Kept on *International* when explicitly worldwide or APAC (e.g. "Home based – Worldwide") |
| Dates | English formats only | Bangla digits and month names, ordinals and DD-MM-YYYY; deadlines found in body text ("আবেদনের শেষ তারিখ", "Apply before …"); Bangla experience requirements |
| Structured data | JSON-LD | JSON-LD (tolerant parsing) **+ microdata**, salary from `baseSalary` |
| Crawl | Sequential; ~100 of 150 employers per hour, rotated | **Parallel** (8 workers in CI, still ≥1.5 s per host). Every eligible employer can be scheduled each hour, with bounded listing pagination, sitemap discovery and PDF circulars; actual coverage is reported |
| JS-only career sites | Missed | Optional rendering (`RENDER_JS=1`) through Playwright, after the robots check |
| Duplicates | URL only | Same role found through an alert, search or aggregator **and** on the official page is merged, with an "Also listed on" link list |

### Source channels

* **Free feeds:** We Work Remotely (RSS) and Working Nomads, in addition to Himalayas, Remotive, Remote OK and Jobicy.
* **LinkedIn / Bdjobs / Indeed / Glassdoor via your own job-alert emails.** See below; this is the biggest gain for Bangladesh.
* **Optional licensed APIs:** Brave Search (site-scoped LinkedIn/Bdjobs queries) and Jooble (country-specific coverage that must match the configured key).
* **Your own RSS/Atom feeds** (`data/custom_feeds.json`), e.g. Google Alerts for "সাইবার নিরাপত্তা নিয়োগ".
* Seeded global remote employers in `data/ats.json`: GitLab, Canonical, Cloudflare, Mozilla and Wikimedia.

### What it deliberately does not do

It does not ignore robots.txt, solve CAPTCHAs, spoof browsers or log into portals. Restricted portals are not fetched directly. The supported alert-email and licensed search-API routes provide partial discovery of those postings.

---

## Publish privately on GitHub Pages (login required)

GitHub Pages is static hosting, so a login form on its own would not protect anything: the JSON files would still be downloadable. v5 therefore publishes **only ciphertext**:

* Each hourly run encrypts every data file with a fresh **AES-256-GCM** data key.
* That key is wrapped separately for each allowed user, using a key derived from their password (**PBKDF2-SHA256, 600,000 iterations**).
* The browser derives the key from the username and password, unwraps the data key and decrypts the files locally. No password and no plaintext is ever sent anywhere.
* Removing a user locks them out at the next hourly publish, even if their browser kept a session.
* The site sends `noindex` and serves a `robots.txt` that disallows everything.

### One-time setup

```powershell
python -m pip install -r requirements.txt
python -m vault init                      # prints CC_MASTER_KEY, keep a private backup
python -m vault user add ashik            # prompts for a password (min 12 chars, use a passphrase)
python -m vault user add colleague1
python -m vault seal                      # encrypt your current data/ into encrypted/
python -m vault verify ashik              # optional: test the login exactly like the browser does
```
Then on GitHub:
1. **Settings → Secrets and variables → Actions → New repository secret:** `CC_MASTER_KEY` = the value printed by `vault init`.
2. **Settings → Pages → Source: GitHub Actions.**
3. Commit and push: `config/users.json`, `encrypted/`, and the code. **Never commit `.vault/`**; it is git-ignored.
4. **Actions → "Collect, encrypt & publish" → Run workflow.** After that it runs hourly.

> **Upgrading an existing repo:** v4 committed plaintext `data/jobs.json` and related files. Run
> `git rm --cached data/jobs.json data/status.json data/source_health.json data/progress.json data/feed_state.json data/ats_discovered.json`,
> delete the old `refresh-data.yml` and `deploy-pages.yml` workflows (v5 replaces them with `pages.yml`), and consider purging the old files from history or starting a fresh repository. Old commits stay public.

### Managing access

```powershell
python -m vault user add <name>       # allow someone
python -m vault user passwd <name>    # change a password
python -m vault user remove <name>    # revoke
python -m vault user list
```
Commit `config/users.json` and push; the workflow republishes within minutes. It holds only salts and ciphertext. Usernames are stored encrypted, and the keyring identifies users by a hash.

**Security notes:** whoever has the published keyring can try to guess passwords offline, so use long passphrases (PBKDF2 makes each guess slow, but cannot save a weak password). In a public repository the code, `sources.json` and the Actions logs are visible, but the collected jobs are not. The workflow discards collector output for that reason. Private-repository Pages availability depends on your GitHub plan. The vault protects the published dataset independently of repository visibility.

### How the workflow handles state

`.github/workflows/pages.yml` does: install/test code → restore `encrypted/` (hourly cache) → `vault unseal` (decrypt state inside the runner) → collect with optional encrypted live progress → `vault seal` (fresh key) → cache → `vault build-site` → deploy → **attempt an encrypted repository backup when the saved job fingerprint differs**. The backup uses a separate worktree and cannot block deployment. Plaintext collected data never touches the repository or Pages. The site build includes public repository/workflow/branch metadata for the scanner, never a GitHub token or vault secret.

The supplied workflow's push trigger still names `main`. Adjust that filter if your deployment branch differs. The scanner uses the configured branch or discovers the repository's default branch when the branch field is empty.

---

## LinkedIn & Bdjobs coverage through job-alert emails

1. Use a dedicated Gmail address, and turn on 2-Step Verification and an **App password**.
2. Create job alerts with that address. On LinkedIn, try "information security", "cyber security", "SOC", "penetration testing" and "IT audit" for Bangladesh, sent daily. Do the same on Bdjobs, Indeed and Glassdoor.
3. Add the Actions secrets `ALERT_IMAP_USER` and `ALERT_IMAP_PASSWORD`. Optional variables: `ALERT_IMAP_HOST`, `ALERT_IMAP_FOLDER`.

The collector reads those emails over IMAP in read-only mode and never marks them as read. It keeps only cybersecurity roles and links to the original posting. The platform pages themselves are never fetched.

## Optional licensed API keys

| Secret | What it adds |
| --- | --- |
| `BRAVE_API_KEY` | Site-scoped search over LinkedIn and Bdjobs postings, plus Bangla circular queries. Defaults to two requests per run with a 1,500-request application monthly cap; check your own provider plan. Pagination resumes across runs. |
| `JOOBLE_API_KEY` | Country-specific aggregator discovery; also requires the provider-issued regional `JOOBLE_API_HOST`. The US endpoint is not a Bangladesh source. |
| Variable `RENDER_JS=1` | Installs Chromium in CI and renders JavaScript-only career pages. |

## Google Alerts / custom feeds

Create a Google Alert, choose **Deliver to: RSS feed**, and add the feed URL to `data/custom_feeds.json` (see `custom_feeds.example.json`). Feed items are kept only if they look like a vacancy **and** pass the relevance engine.

## Adding ATS boards manually

If an employer uses an ATS that isn't linked from its site, add it to `data/ats.json`. `ats.example.json` shows the token format for each provider, e.g. Workday is `tenant|wd3|SiteName`.

---

## Run locally (no login)

```powershell
python -m pip install -r requirements.txt
python -m server.app                       # http://127.0.0.1:8000/  (scans now, then hourly)
python -m server.app --no-refresh-on-start --refresh-every-hours 0
python -m collector.collect                # one scan from the command line
python -m collector.diagnose --failed-only --limit 30
python -m pytest -q
```
Optional settings are in `.env.example`. Local mode reads plaintext `data/*.json`, which is git-ignored. To import jobs from an older install: `python -m collector.import_existing "C:\old\data\jobs.json"`.

## Project map

| Path | Purpose |
| --- | --- |
| `collector/collect.py` | Pipeline, employer crawl, parsing, deduplication, region routing |
| `collector/telemetry.py` | Durable scan lifecycle, per-source results and completion history |
| `collector/github_progress.py` | Optional encrypted GitHub Checks progress publisher and collector CLI wrapper |
| `vault/backup.py` | Optional encrypted repository backup after deployment, with concurrent-change checks and bounded push retries |
| `collector/relevance.py` | Weighted English and Bangla cybersecurity relevance engine |
| `collector/robots.py` | RFC 9309 robots.txt matcher |
| `collector/textmine.py` | Bangla/English dates, deadlines, experience and city extraction |
| `collector/ats.py` | Workday, Workable, SmartRecruiters, Recruitee, BambooHR, Personio and Breezy, plus board discovery |
| `collector/free_feeds.py` | Himalayas, Remotive, Remote OK, Jobicy, We Work Remotely, Working Nomads |
| `collector/email_alerts.py` | IMAP reader for job-alert emails you subscribed to |
| `collector/search_apis.py` | Optional Brave Search and Jooble |
| `collector/custom_feeds.py` | Your RSS/Atom feeds (Google Alerts) |
| `collector/render.py` | Optional Playwright rendering for JavaScript-only career pages |
| `vault/` | Encryption, user management and static site builder (`python -m vault`) |
| `auth.js` | Browser login gate and WebCrypto decryption |
| `applications.js` | Private browser application records and notes |
| `github-scan.js` | GitHub workflow requests and live progress lookup; token retained only in memory |
| `config/users.json` | Allowed users (salts and ciphertext only) |
| `encrypted/` | Published encrypted dataset and keyring |

**Developed by Khandaker Ashikul Hoque**
