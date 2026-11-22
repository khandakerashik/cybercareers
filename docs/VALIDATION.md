# Validation — v5.3.0

## Automated checks completed

| Check | Result |
| --- | --- |
| Python regression suite | 297 passed |
| Application storage checks (dependency-free Node) | 89 assertions passed |
| Archive and application workspace DOM checks | 50 assertions passed |
| Frontend DOM and WebCrypto smoke checks | 18 assertions passed |
| Frontend JavaScript syntax | `app.js`, `auth.js` and `applications.js` passed Node syntax checks |
| GitHub workflow YAML | Parsed successfully |
| Original uploaded baseline suite | 115 tests passed before the repairs |

The regression cases cover genuine bilingual cybersecurity roles, event/training/news false positives, physical-security look-alikes, company boilerplate, PDF and structured multi-role identity, geographic restrictions, alert parsing/backlog, search pagination/budgets, source failure classification, malformed ATS responses, duplicate/deadline handling, atomic persistence, and interrupted/incomplete completion timestamps.

The frontend checks exercise rendered DOM content, BDT date/time formatting, completion state, source coverage, the job-details drawer, a clean local installation without data files, actual AES-GCM/PBKDF2 snapshot decryption and key rollover, and the reauthentication gate. They do not measure visual layout.

The v5.3 additions cover Bangladesh midnight and deadline extensions, explicit source closures, invalid/unknown dates, active/archive partitioning, mark-as-applied actions, notes and character limits, escaped note display, application retention after feed removal, account/site isolation, previous-account DOM clearing before network fetch, cross-tab changes and note conflicts, unsaved draft preservation across refreshes, browser quota errors, malformed storage protection, CSV escaping and safe static publication. The application module is also checked through the local server and encrypted Pages builder.

The test runner emitted one deprecation warning from the execution environment's installed `anyio` pytest plugin. It did not indicate a project test failure.

## Live source checks

These are the source observations carried forward from the v5.2 audit; v5.3 does not claim a new live source sweep.

- 151 employer sources were measured with permitted HTTP requests.
- 28 selected employers were rechecked after route/collector changes.
- The latest actual observation for each source is preserved in the included audit.
- Remaining limitations, scan settings and timestamps are documented in `SOURCE_AUDIT.md` and the full JSON report.
- No production job dataset was fabricated or replaced with test fixtures.

## Limits of verification

No authenticated LinkedIn-alert mailbox, Brave key or Jooble key was supplied. Those integrations were tested with representative email/JSON fixtures and mocked provider responses; their live account-specific configuration still needs a deployment run.

Real Chromium rendering could not start in this execution environment because a required browser socket operation was denied. The managed browser download was also unavailable. The renderer's concurrent-thread ownership and fallback behaviour are tested, but actual rendered career-page extraction and full visual browser QA are not claimed. GitHub Actions installs/enables the optional renderer by default, and source health exposes unreadable JavaScript pages.

External accessibility changes by time and network. A readable page is not proof that every job on a service was collected, and a zero-match result is not proof that an employer has no cybersecurity openings unless an explicit no-openings message was read.

## Reproduce checks

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
node --check app.js
node --check auth.js
node --check applications.js
node tests/applications_store.cjs
```

Optional DOM/crypto developer check (the application itself has no Node dependencies):

```powershell
npm install --no-save --ignore-scripts jsdom@26
node tests/frontend_smoke.cjs
node tests/frontend_workspace.cjs
```

Repeat source diagnostics separately in your deployment environment:

```powershell
python -m collector.diagnose --failed-only --limit 250 --output source-diagnostics.json
```

Diagnostics are separate from the deterministic test suite; tests never require production website reachability.
