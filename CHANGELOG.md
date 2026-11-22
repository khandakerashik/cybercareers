# Changelog

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
