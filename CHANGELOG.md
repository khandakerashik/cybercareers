# Changelog

## 5.4.2 — 2026-11-22

- Repair incomplete scanner installations by delivering all application modules and integration files together in an existing-installation repair package.
- Add an inline file inventory before dependency installation and scanner compatibility checks before collection. Missing modules and frontend assets produce an actionable `Incomplete release upload` error instead of a hidden startup failure.
- Run collection through a private-output CI entry point. Keep raw output and exception messages out of public Actions logs while reporting a safe failure category and repository code location.
- Keep genuine collector failures visible; preserve the existing deployment-before-optional-backup behavior and attempt-specific cache keys.
- Add regressions for missing Python/JavaScript files, mixed scanner interfaces and private-output handling.
- Explain the inspected run's missing `collector/github_progress.py` and `github-scan.js`, and replace the earlier two-file upgrade assumption with complete repair instructions.

## 5.4.1 — 2026-11-22

- Repair publishing that stopped at the encrypted-state backup when the remote branch advanced after checkout (`fetch first` / non-fast-forward rejection).
- Deploy Pages before attempting the optional repository backup; failed backups and cache operations are non-blocking and remain visible as warnings.
- Back up through a temporary worktree based on the latest remote branch, using ordinary pushes with bounded retries. Keep the build checkout intact and skip incompatible concurrent vault or user-configuration changes.
- Commit only validated keyring/ciphertext files as one snapshot; never merge encrypted blobs or force-push remote history.
- Compare the collected job fingerprint with the repository backup so a missed backup can be retried even when the next scan adds no new jobs.
- Include the full ref, run ID and run attempt in cache keys; use an isolated same-ref restore prefix and a default-branch-only migration from the prior cache format.
- Add real local-Git concurrency regressions and a publishing repair guide explaining why an updated workflow needs a fresh run.

## 5.4.0 — 2026-11-22

- Add Scan now for the local collector and GitHub Pages, with connection management and a direct GitHub Actions alternative.
- Keep browser GitHub credentials in tab memory only; clear them on disconnect, account change, sign-out and reload.
- Discover the repository default branch when none is specified; validate repository/workflow/run identity and distinguish workflow attempts sharing a commit.
- Follow an existing active scan, suppress repeated requests, and reconcile uncertain workflow dispatches before allowing another request.
- Add source-by-source queued, running, success, partial, failed, skipped and interrupted status, search/state filters, job/new-job counts, actual start/finish times and durations.
- Refresh local progress approximately every two seconds and publish encrypted GitHub progress approximately every 15 seconds without blocking source collection.
- Add the CCLIVE1 Checks publisher with a fresh run key, current-user key wrapping, context-bound encryption, bounded payloads and explicit truncation metadata.
- Give the workflow Checks write permission and pass its progress token only to the collection step; publish public repository/workflow/branch metadata without credentials.
- Preserve previous completion and published jobs during collection, API outages and failed attempts; distinguish collection completion from subsequent Pages publication.
- Keep optional progress failures separate from collector success, and retain an interrupted scan's evidence after process restart.
- Ship the GitHub scanner module through both servers/builders and add offline lifecycle, protocol, credential, dispatch, DOM and encryption-interoperability checks. No live repository dispatch or deployment was performed for this release.

## 5.3.0 — 2026-11-22

- Add dedicated Archived Jobs with search, region and saved-only filters, sorting, counters and progressive loading; remove expired-listing toggles from the active feeds.
- Keep deadline-today jobs active through the Bangladesh day; archive expired/closed jobs, preserve unknown-deadline older leads, and reopen records after a genuine deadline extension.
- Normalize timestamp deadlines to the Bangladesh calendar date without changing original publication dates.
- Add Applied Jobs, Mark as applied actions, applied dates, short editable notes, search/status filters and CSV export.
- Persist minimal application references separately from collected listings, so notes remain available after expiry or removal from the feed.
- Scope application records to the site and signed-in browser account; clear previous-account notes before loading another account, including during network failures.
- Preserve unsaved drafts and cursor position across refreshes; detect conflicting note edits from another tab and report storage failures without pretending a save succeeded.
- Preserve distinct posting IDs/shared-page roles and recover matching applications after harmless collector-ID changes.
- Ship the application module through the local server and Pages builder; keep personal exports and stray files out of published artifacts.
- Add archive, application-storage, privacy and frontend regressions.

## 5.2.0 — 2026-11-22

- Separate vacancy evidence from cybersecurity relevance; reject event/training/news/list pages and ambiguous physical-security or company-boilerplate matches.
- Revalidate historical data with recoverable rejection reasons; preserve genuine archives and low-confidence historical leads.
- Correct generic bank-title, short PDF-title, multi-role circular and shared-listing parsing.
- Retain distinct LinkedIn requisitions, preserve job identifier query parameters, and make duplicate merging respect source trust, observation dates and incompatible deadlines.
- Support complete alert-card metadata, plain-text emails, tracking wrappers, exact portal domains, staged IMAP UID checkpoints, and a fresh/backlog split.
- Add bounded resumable search pagination, query-family expansion, request quotas and provider cooldowns; protect API credentials across redirects.
- Require correct country-specific Jooble host configuration; stop relabelling foreign roles as Bangladesh jobs.
- Repair 16 employer-published routes; improve redirect resolution, job-card discovery, sitemap handling, fair follow-up budgets and source classifications.
- Continue bounded Workday/SmartRecruiters pagination and reject malformed ATS responses.
- Use one owner thread for Playwright and support an explicitly configured/system Chromium executable.
- Persist truthful last-completed and last-successful timestamps, duration and run state; display BDT timestamps, schedule status and stale data.
- Automatically refresh encrypted snapshots; repair reauthentication, transient reload recovery and first-run local loading.
- Include source audit, upgrade instructions, regression tests and optional DOM/WebCrypto checks.
