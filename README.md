# CyberCareers BD v5 — Private Cybersecurity Job Intelligence

An hourly job radar for cybersecurity and information security roles in Bangladesh, plus international remote roles open to Bangladesh-based applicants. You can run it locally, or publish it to **GitHub Pages behind a login**: only you and the people you allow can sign in, and the published data is encrypted.

> A posting in the dashboard is a lead. Always confirm the vacancy, deadline and eligibility on the original posting.

---

## What's new in v5

### Detection
| Area | v4.2 | v5 |
| --- | --- | --- |
| Relevance | Substring keywords, so "mechan**isms**" and "cred**it audit**" matched while "Network Security Engineer" did not | Weighted bilingual engine (`collector/relevance.py`) with word boundaries, physical-security/AML/credit negatives, IT-context checks for ambiguous "Security Manager" titles, and description evidence for generic bank titles ("Senior Principal Officer … Information Security Division"). Every job gets a `relevance_score` and `matched_terms`. |
| robots.txt | Python's parser: first-match only, no wildcards, so `Disallow: /` + `Allow: /careers/` wrongly blocked careers pages; robots 403 counted as a failure | RFC 9309 matcher (`collector/robots.py`): longest match wins, `*`/`$` wildcards, 4xx = no restrictions, 5xx/network = disallow, and `Crawl-delay` is honoured |
| ATS providers | Greenhouse, Lever, Ashby (links only) | **+ Workday, Workable, SmartRecruiters, Recruitee, BambooHR, Personio, Breezy, Lever EU**, found from links, iframes, script embeds and career-page redirects |
| Remote roles from ATS boards | Dropped unless located in Bangladesh | Kept on *International* when explicitly worldwide or APAC (e.g. "Home based – Worldwide") |
| Dates | English formats only | Bangla digits and month names, ordinals and DD-MM-YYYY; deadlines found in body text ("আবেদনের শেষ তারিখ", "Apply before …"); Bangla experience requirements |
| Structured data | JSON-LD | JSON-LD (tolerant parsing) **+ microdata**, salary from `baseSalary` |
| Crawl | Sequential; ~100 of 150 employers per hour, rotated | **Parallel** (8 workers in CI, still ≥1.5 s per host). Every employer is checked every hour, with listing pagination, sitemap indexes and more PDF circulars |
| JS-only career sites | Missed | Optional rendering (`RENDER_JS=1`) through Playwright, after the robots check |
| Duplicates | URL only | Same role found through an alert, search or aggregator **and** on the official page is merged, with an "Also listed on" link list |

### New sources
* **Free feeds:** We Work Remotely (RSS) and Working Nomads, in addition to Himalayas, Remotive, Remote OK and Jobicy.
* **LinkedIn / Bdjobs / Indeed / Glassdoor via your own job-alert emails.** See below; this is the biggest gain for Bangladesh.
* **Optional licensed APIs:** Brave Search (site-scoped LinkedIn/Bdjobs queries) and Jooble (aggregator with Bangladesh coverage).
* **Your own RSS/Atom feeds** (`data/custom_feeds.json`), e.g. Google Alerts for "সাইবার নিরাপত্তা নিয়োগ".
* Seeded global remote employers in `data/ats.json`: GitLab, Canonical, Cloudflare, Mozilla and Wikimedia.

### What it deliberately does not do
It does not ignore robots.txt, solve CAPTCHAs, spoof browsers or log into portals. LinkedIn and Bdjobs prohibit automated collection, and getting around that risks IP bans and account bans. The alert-email and search-API routes below reach those listings legitimately.

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

**Security notes:** whoever has the published keyring can try to guess passwords offline, so use long passphrases (PBKDF2 makes each guess slow, but cannot save a weak password). In a public repository the code, `sources.json` and the Actions logs are visible, but the collected jobs are not. The workflow discards collector output for that reason. A private repository needs a paid plan for Pages, but the vault is designed to be safe either way.

### How the workflow handles state
`.github/workflows/pages.yml` does: restore `encrypted/` (hourly cache) → `vault unseal` (decrypt state inside the runner) → collect → test → `vault seal` (fresh key) → cache → **commit `encrypted/` only when the job list changed** (a durable backup without hourly commits) → `vault build-site` → deploy. Plaintext never touches the repository or Pages.

---

## LinkedIn & Bdjobs coverage through job-alert emails

1. Use a dedicated Gmail address, and turn on 2-Step Verification and an **App password**.
2. Create job alerts with that address. On LinkedIn, try "information security", "cyber security", "SOC", "penetration testing" and "IT audit" for Bangladesh, sent daily. Do the same on Bdjobs, Indeed and Glassdoor.
3. Add the Actions secrets `ALERT_IMAP_USER` and `ALERT_IMAP_PASSWORD`. Optional variables: `ALERT_IMAP_HOST`, `ALERT_IMAP_FOLDER`.

The collector reads those emails over IMAP in read-only mode and never marks them as read. It keeps only cybersecurity roles and links to the original posting. The platform pages themselves are never fetched.

## Optional keys (all free tiers)
| Secret | What it adds |
| --- | --- |
| `BRAVE_API_KEY` | Site-scoped search over LinkedIn and Bdjobs postings, plus Bangla circular queries. 2 queries per hour by default (`BRAVE_QUERIES_PER_RUN`), which fits the free monthly quota. |
| `JOOBLE_API_KEY` | Bangladesh listings aggregated from many boards (`JOOBLE_QUERIES_PER_RUN`, default 3). |
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
| `config/users.json` | Allowed users (salts and ciphertext only) |
| `encrypted/` | Published encrypted dataset and keyring |

**Developed by Khandaker Ashikul Hoque**
