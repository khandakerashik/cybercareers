# CyberCareers BD v5.3.0 — Archives and application notes

This release builds on v5.2.0. Source repairs, detection, LinkedIn discovery and hourly completion reporting remain included. The new sections are **Archived Jobs** and **Applied Jobs**.

## Upgrade an existing installation

1. Preserve your existing `.env`, `config/users.json`, `.vault/`, `encrypted/`, collected data and `CC_MASTER_KEY` secret.
2. Merge the complete ZIP contents into the root of the existing project, replacing matching code files. Include the new **`applications.js`**, updated `app.js`, `index.html`, `styles.css`, server/vault code and `.github/workflows/pages.yml`. Do not place the package inside an extra parent folder.
3. For GitHub Pages, commit and push the update, then run **Actions → Collect, encrypt & publish** if an immediate collection is wanted. The existing hourly schedule continues. For a local installation, restart `python -m server.app`.
4. Refresh the dashboard. The sidebar should show **Applied Jobs** and **Archived Jobs**, and the footer version should be **v5.3.0**. A hard refresh may help a browser that has cached the old HTML.

There is no new API key, database or vault initialization step. See [the v5.2 guide](UPGRADE_v5.2.md) for optional LinkedIn/mailbox configuration and general deployment details.

## Archived Jobs

| Listing evidence | Dashboard behaviour |
| --- | --- |
| Known application deadline before today in Bangladesh | Removed from active feeds and shown in Archived Jobs |
| Deadline is today | Stays active through the current Bangladesh day |
| Future deadline | Active, unless the source explicitly marks the role closed |
| Explicit closed or expired source status | Archived; a valid updated deadline can override a stale derived expiry, while explicit closure requires a fresh source update |
| Old publication date with no known deadline | Remains an older, unverified lead; age alone does not prove closure |
| Invalid or missing deadline | Treated as unknown, not automatically expired |

The archive includes Bangladesh and international listings retained in the dataset. Search by title/employer/skill, filter by region, sort by deadline/company/fit, or select **Saved jobs only**. Expired saved jobs can also be reached from the shortlist's archived count.

The frontend re-evaluates expiry when the Bangladesh date changes, so an already-open dashboard does not need to wait for another collector run. Date-only deadlines are inclusive through the end of that date. Timestamp deadlines are classified by their Bangladesh calendar day; this feature does not promise exact closing-hour precision. Check the original listing if an employer specifies a closing time.

Publisher retention rules still apply. For example, expired Himalayas listings are removed from the collected feed rather than republished in the archive. A user's compact application reference and notes are maintained separately.

## Mark a job as applied

1. Submit the application through the employer's original application process.
2. Choose **Mark as applied** on its job card or in the details panel.
3. The job appears in **Applied Jobs** with the date recorded in Bangladesh time.
4. Enter a short note, then choose **Save note**.

Example notes:

- `Applied through the company portal. Used CV v3. Follow up next Thursday.`
- `Referral submitted. Technical interview on 3 December; revise API security cases.`

Notes are plain text and can contain up to **1,000 characters**, including line breaks. Choose **Add note** or **Edit note** from Applied Jobs to reopen the editor. A saved note is searchable alongside the job title and employer. The character counter and save status show whether the latest edit was saved.

**Mark as applied records your own action; it does not send an application.** Removing the applied mark removes the local record and note after confirmation; it does not withdraw an employer application.

## What survives collection and refresh

- Applied records remain in Applied Jobs after their deadline passes.
- When the same listing is still collected, the view uses its current deadline and source information.
- When a listing is no longer collected, the view uses a compact saved reference and labels that it is no longer in the feed. Notes remain editable.
- Repeated marking of the same posting preserves the original application date and note.
- Distinct posting IDs and roles sharing a circular are not collapsed into a single application.
- Unsaved note drafts survive dashboard data refreshes in the open tab. Choose **Save note** before leaving the page; unsaved drafts are not durable browser records.
- Changes from another tab refresh the view. If the same note changed elsewhere while you were editing, the UI asks before replacing it with your draft.

## Where your records are kept

Applied records and notes are stored **in this browser**, scoped to the site's base URL and the signed-in account. Local installations without sign-in use one local browser scope. They are not uploaded to GitHub, sent to employers or added to the shared collector dataset.

This is browser persistence, not automatic account synchronization. Another device/browser/profile or a different site URL has separate records. Clearing site data removes the records, and private browsing may discard them when the private session closes. Browser storage is not encrypted by the dataset vault; account scoping separates the normal application views rather than providing device-level encryption.

Choose **Export applications** to download a CSV with titles, employers, application dates, deadlines, current/recorded listing status, notes and source links. The export includes all your current application records, even when a search filter is active. CSV cells are escaped for commas, line breaks, quotation marks and spreadsheet-formula prefixes. Treat the downloaded CSV as your personal record. This version does not include CSV import or cross-device synchronization.

If browser storage is blocked, full or malformed, the interface reports the problem and does not claim the change was saved. Existing malformed data is not silently replaced. Account switching clears the previous user's application notes before another dataset fetch, including when the fetch fails.

## Verification

See [VALIDATION.md](VALIDATION.md) for the current test results and environment limits. The application needs no Node dependency at runtime; optional DOM tests use jsdom only during development.

## Official references checked

- [Schema.org validThrough](https://schema.org/validThrough): the end of a posting's validity is separate from its publication date.
- [MDN localStorage](https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage): origin-scoped persistence across sessions and private-browsing behaviour.
- [MDN Using the Web Storage API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Storage_API/Using_the_Web_Storage_API): availability and storage failure handling.
