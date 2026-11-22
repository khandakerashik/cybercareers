# Upgrade to CyberCareers BD v5.2.0

This package updates the existing Python collector and static dashboard. It does not require a new repository or a new vault key.

## Existing GitHub Pages installation

1. Keep your existing `config/users.json`, `encrypted/`, `.vault/` and private configuration. The upload package contains no replacement user list, passwords or collected production data.
2. Extract the ZIP and merge its contents into the **root of the existing repository**, replacing matching code/configuration files. Include `.github/workflows/pages.yml`; do not put the entire package inside another folder.
3. Commit the changed files. The repaired workflow now responds to collector/source changes as well as frontend changes. It runs the tests, restores encrypted state, collects, encrypts and publishes.
4. In **Actions → Collect, encrypt & publish**, you can also choose **Run workflow**, with collection enabled, for an immediate run.
5. After the run, sign in to the dashboard. Check **Last completed fetch**, **Last attempt**, **Next planned check**, and **Source health**. All displayed collection timestamps are Bangladesh time (BDT).

Keep the existing `CC_MASTER_KEY` repository secret. Do not run vault initialization again merely to upgrade. If the installation still has the old separate refresh/deploy workflows described in the previous README, remove those obsolete workflows so only this collection/publish workflow writes the dataset.

The workflow remains scheduled for minute 12 of every hour (`12 * * * *`, UTC). This is also minute 12 in Bangladesh. GitHub scheduling is best effort. An ordinary collector exception preserves the earlier completion time and can publish the failed-attempt status. A runner termination or whole-job timeout cannot publish a new snapshot; the older timestamp and stale-snapshot message remain the evidence.

### JavaScript career sites

GitHub Actions installs Playwright/Chromium and enables rendering by default in v5.2. Set repository variable `RENDER_JS=0` to disable it. Rendering respects the same approved-host and robots checks and does not solve access challenges.

The source audit in this package used HTTP only because this execution environment could not start Chromium. The thread-ownership fix is covered by regression tests; real rendered extraction must be checked in the deployment environment.

## LinkedIn collection setup

LinkedIn is discovered through subscribed alerts and an optional licensed search index. Configuring one does not configure the other.

| Setting | GitHub location | Purpose |
| --- | --- | --- |
| `ALERT_IMAP_USER` | Actions secret | Dedicated job-alert mailbox username |
| `ALERT_IMAP_PASSWORD` | Actions secret | Mailbox app password or appropriate IMAP credential |
| `ALERT_IMAP_HOST` | Actions variable | Defaults to `imap.gmail.com`; set your mailbox provider's IMAP host if different |
| `ALERT_IMAP_FOLDER` | Actions variable | Folder/label containing job alerts; defaults to `INBOX` |
| `ALERT_LOOKBACK_DAYS` | Actions variable | Defaults to 21; bounded to 1–90 |
| `ALERT_MAX_MESSAGES` | Actions variable | Defaults to 500 unseen messages per run; new alerts are prioritised while an older backlog also progresses |
| `BRAVE_API_KEY` | Actions secret | Enables search-index discovery of LinkedIn and other postings |

Create daily LinkedIn alerts for relevant roles and locations. The discovery page includes direct search links for 18 LinkedIn role/location families, including information security, cybersecurity, SOC, penetration testing, AppSec, network/cloud security, IT audit, GRC, DevSecOps, CISO and worldwide/APAC remote searches. Review location and eligibility before enabling each alert.

LinkedIn's official documentation describes daily or weekly alert delivery, with up to 20 active alerts. Polling the mailbox hourly does not make upstream alert delivery hourly. Search indexes can omit or delay postings. Neither channel guarantees all LinkedIn jobs.

### Search request budgets

The defaults retain a conservative request budget; they are application limits, not a statement that a provider plan is free.

| Variable | Default | Meaning |
| --- | ---: | --- |
| `BRAVE_QUERIES_PER_RUN` | 2 | Query families considered per run |
| `BRAVE_PAGES_PER_QUERY` | 2 | Maximum pages for a query before rotating |
| `BRAVE_MAX_REQUESTS_PER_RUN` | 2 | Hard request cap per run |
| `BRAVE_MONTHLY_REQUEST_LIMIT` | 1500 | Application-enforced monthly cap |
| `BRAVE_FRESHNESS` | Empty | No mandatory one-month index-date filter |

There are 26 search query families, including 18 LinkedIn families. At two requests per run, visiting every family takes at least 13 hourly runs, and pagination or errors may lengthen that cycle. Requests and continuation state are saved between runs. Increase budgets only within your actual API plan if you want a shorter sweep. An hourly fetch timestamp means that the scheduled run finished, not that the whole search index or all LinkedIn jobs were retrieved.

Jooble is optional. When supplying `JOOBLE_API_KEY`, also supply `JOOBLE_API_HOST`, using the exact regional host associated with that key. The application no longer assumes a US `jooble.org` key provides Bangladesh listings. Confirm that the provider supports your target country. Defaults are three query families, three pages/query, four requests/run, and 96 requests/day. Missing regional configuration is reported as a configuration error.

## Existing local installation

Merge the package into the existing project folder and preserve your `.env`, local data and vault credentials.

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
python -m server.app
```

Open `http://127.0.0.1:8000/`. The server starts a collection and, by default, repeats it hourly while the process remains running. A clean installation can display an empty dashboard while the first collection is underway; it refreshes automatically when data becomes available.

For optional local JavaScript rendering:

```powershell
python -m pip install playwright
python -m playwright install chromium
```

Set `RENDER_JS=1` in `.env`, then restart the server. `CHROMIUM_EXECUTABLE_PATH` can select an existing installed Chromium executable. The included `.env.example` documents all supported settings; inline comments are now parsed correctly.

One-off collection and diagnostics:

```powershell
python -m collector.collect
python -m collector.diagnose --failed-only --limit 250 --output source-diagnostics.json
```

A one-off CLI run does not start an hourly scheduler. Diagnostics do not overwrite job data or collection history.

## What happens to old false positives

At the next collection, stored records are rechecked. Clear event, training, advice, listing-page and unrelated-role false positives are removed from the dashboard. Rejected records and reasons are retained in `data/rejected_jobs.json` for local review, up to 1,000 records. This file is excluded from the local web server's public paths and is encrypted with collector state for GitHub publishing. Copies of rejected historical rows are saved before incremental job writes so interruption does not silently lose the review evidence.

Plausible older employer leads with limited original evidence remain explicitly unverified. Real vacancy archives and original posting dates are retained. Receipt dates and search/provider updates are not presented as publication dates.

## How to interpret the status

| Display | Meaning |
| --- | --- |
| Last completed fetch | Most recent run that processed every scheduled target; a run can complete with source issues |
| Completed with source issues | Scheduled processing finished, but at least one source failed or had limited extraction |
| Interrupted / failed | The attempt failed; the prior completed-fetch timestamp is retained |
| Some targets not processed | The planned sweep did not finish; completion time does not advance |
| Cached / deferred | A provider was not due or is cooling down; this is not a fresh successful fetch |
| Limited source | The reachable page did not yield a complete usable recruiting view |
| Directory / manual-link source | A catalogue/search link without a direct automatic collector |
| Next planned check | Scheduler estimate, not a promise of collection or deployment completion |

## Official references

- [LinkedIn job alerts](https://www.linkedin.com/help/linkedin/answer/a511279/job-alerts-on-linkedin?lang=en)
- [LinkedIn Job Posting API overview](https://learn.microsoft.com/en-us/linkedin/talent/job-postings/api/overview?view=li-lts-2026-03)
- [Brave Web Search API](https://api-dashboard.search.brave.com/api-reference/web/search/get)
- [Jooble REST API documentation](https://help.jooble.org/en/support/solutions/articles/60001448238-rest-api-documentation)
- [GitHub scheduled workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
