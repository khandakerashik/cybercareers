# Validation — v5.4.2

## Automated checks completed

| Check | Result |
| --- | --- |
| Python regression suite | 371 passed |
| Incomplete-upload and compatibility guard regressions (included in Python total) | 11 passed against the actual inline workflow checks |
| Private CI output regressions (included in Python total) | 19 passed with synthetic subprocess packages |
| Publishing backup regressions (included in Python total) | 11 passed, using real temporary local Git remotes |
| GitHub scanner and live encryption checks (dependency-free Node) | 111 assertions passed |
| Manual scan and per-source progress DOM checks | 115 assertions passed |
| Application storage checks (dependency-free Node) | 89 assertions passed |
| Archive and application workspace DOM checks | 50 assertions passed |
| Frontend DOM and WebCrypto smoke checks | 18 assertions passed |
| Frontend JavaScript syntax | `app.js`, `auth.js`, `applications.js` and `github-scan.js` passed Node syntax checks |
| GitHub workflow YAML | Parsed successfully; release guards, safe collector entry point, attempt-specific cache keys, same-ref restore scope and deployment-before-backup failure gates verified |
| Original uploaded baseline suite | 115 tests passed before the repairs |

The regression cases cover genuine bilingual cybersecurity roles, event/training/news false positives, physical-security look-alikes, company boilerplate, PDF and structured multi-role identity, geographic restrictions, alert parsing/backlog, search pagination/budgets, source failure classification, malformed ATS responses, duplicate/deadline handling, atomic persistence, and interrupted/incomplete completion timestamps.

The frontend checks exercise rendered DOM content, BDT date/time formatting, completion state, source coverage, the job-details drawer, a clean local installation without data files, actual AES-GCM/PBKDF2 snapshot decryption and key rollover, and the reauthentication gate. They do not measure visual layout.

The v5.3 additions cover Bangladesh midnight and deadline extensions, explicit source closures, invalid/unknown dates, active/archive partitioning, mark-as-applied actions, notes and character limits, escaped note display, application retention after feed removal, account/site isolation, previous-account DOM clearing before network fetch, cross-tab changes and note conflicts, unsaved draft preservation across refreshes, browser quota errors, malformed storage protection, CSV escaping and safe static publication. The application module is also checked through the local server and encrypted Pages builder.

The v5.4 collector checks cover actual source starts and finishes, queued work, concurrent active sources, duplicate completion, cached/deferred work without fabricated starts, independent status snapshots, callback failure isolation, interrupted rows and a single worker under concurrent local scan requests.

The GitHub checks cover validated repository/default-branch/workflow/run identities, existing queued/running scans, one-shot dispatch with both current and legacy responses, lost-response reconciliation, rate limits, cancellation of pending connections, private token handling, Checks permission failure, repeated attempts on one commit, payload limits and context-bound live decryption. Publisher tests cover fresh run keys, per-user wrapping, no CI recipient, encrypted-only output, coalescing while HTTP is blocked, timed finalization and optional failure isolation. A separate synthetic Python publisher envelope was successfully decrypted through the actual browser authentication module using WebCrypto; this is cross-language interoperability, not a live GitHub test.

The manual-scan DOM checks cover local and Pages controls, parallel source rows, search/state filters, escaped source messages, found/new counts, cached durations, preserved completion timestamps, local request uncertainty and rejection, missing Checks permissions, rate-limit delays, interrupted workflow display, publication refresh, and token clearing on disconnect, sign-out, account changes, page exit and cancelled connection setup. Delayed-response regressions check that old polls cannot replace a newly requested scan, local polling remains a single chain, and authoritative controller failure status survives a stale on-disk progress file.

The v5.4.1 publishing repair is checked with real temporary local Git repositories and bare remotes. These tests reproduce branch movement and rejected pushes without contacting GitHub. They verify that unrelated remote code is preserved, the publishing checkout stays intact, concurrently updated encrypted state/user configuration is protected, push retries remain bounded, only valid ciphertext is committed, and a previously missed backup can be retried despite an unchanged cache. Workflow structure is checked separately because a local Git test does not execute GitHub's hosted Actions service.

The backup helper runs in the supplied Ubuntu Actions workflow. Its local Git integration tests require a POSIX host and Git; they are skipped on Windows or when Git is unavailable. This does not prevent running the dashboard locally on Windows.

The v5.4.2 release checks execute the actual inline workflow code against temporary complete and incomplete releases. They cover missing collector/CI/JavaScript files, older collector and telemetry interfaces, stale server/vault asset lists, fixed-label import failures and suppression of buffered native/Python output. They verify that checking an installation does not run collection or access a vault key. Configuration and collected-data files are not required by the code inventory.

The new CI-entrypoint tests run synthetic subprocess packages. They cover import/syntax failures, argument forwarding, prints, logging, raw descriptor writes, child-process output, buffered C output, exception chains, arbitrary exception names/filenames, numeric and string SystemExit values, interrupts, and stream/descriptor restoration. Error categories and code locations remain public; the sentinel private data never appears. These runner-specific tests require POSIX and are skipped on Windows.

The missing-module condition observed in the public repository was reproduced separately: Python exited with status 1 when `collector.github_progress` was absent. Both inline guards also passed against the complete repaired working tree. These checks establish code-installation behavior; they do not constitute a production workflow run.

The test runner emitted one deprecation warning from the execution environment's installed `anyio` pytest plugin. It did not indicate a project test failure.

## Live source checks

These are the source observations carried forward from the v5.2 audit; v5.4.2 does not claim a new live source sweep.

- 151 employer sources were measured with permitted HTTP requests.
- 28 selected employers were rechecked after route/collector changes.
- The latest actual observation for each source is preserved in the included audit.
- Remaining limitations, scan settings and timestamps are documented in `SOURCE_AUDIT.md` and the full JSON report.
- No production job dataset was fabricated or replaced with test fixtures.

## Limits of verification

The public GitHub run summary, executed workflow and exact-commit repository tree were inspected read-only. Run #424 calls `collector.github_progress`, but commit `9f8746f30f5c06f74d95440f5fd31936c783d86c` lacks that file and also lacks `github-scan.js`. The detailed Actions logs required sign-in, and the collection command discarded its output. The missing file itself establishes the startup defect; no unseen traceback is claimed. See `UPGRADE_v5.4.2.md` for the evidence links.

No authenticated repository access or token was supplied. No live workflow dispatch, Checks write, repository update or Pages deployment was performed. The delivered package still needs to be merged and published in the existing installation. Its archive preserves configuration/state by omitting those paths. Several older catalogue tests read the installation's public source/query configuration and expect the supplied catalogue, so those checks are not independent of arbitrary user configuration changes; they never fetch production websites.

No authenticated LinkedIn-alert mailbox, Brave key or Jooble key was supplied. Those integrations were tested with representative email/JSON fixtures and mocked provider responses; their live account-specific configuration still needs a deployment run.

The earlier local Chromium rendering attempt could not start because a required browser socket operation was denied, and its managed browser download was unavailable. The renderer's concurrent-thread ownership and fallback behaviour are tested, but actual rendered career-page extraction and full visual dashboard QA are not claimed. Public GitHub pages were inspected in the cloud browser for this repair. GitHub Actions installs/enables the optional renderer by default, and source health exposes unreadable JavaScript pages.

External accessibility changes by time and network. A readable page is not proof that every job on a service was collected, and a zero-match result is not proof that an employer has no cybersecurity openings unless an explicit no-openings message was read.

## Reproduce checks

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
node --check app.js
node --check auth.js
node --check applications.js
node --check github-scan.js
node tests/applications_store.cjs
node tests/github_scan.cjs
```

Optional DOM/crypto developer check (the application itself has no Node dependencies):

```powershell
npm install --no-save --ignore-scripts jsdom@26
node tests/frontend_smoke.cjs
node tests/frontend_workspace.cjs
node tests/frontend_scan.cjs
```

Repeat source diagnostics separately in your deployment environment:

```powershell
python -m collector.diagnose --failed-only --limit 250 --output source-diagnostics.json
```

Diagnostics are separate from the deterministic test suite; tests never require production website reachability.
