# CyberCareers BD v5.4.2 — Complete scanner repair

## Confirmed cause in the inspected repository

The public summary for [run #424](https://github.com/khandakerashik/cybercareers/actions/runs/45049472526), started on 22 November 2026 at 23:26 Bangladesh time, reports a failed collection step and the final `Collection was interrupted` error.

Its [executed workflow](https://github.com/khandakerashik/cybercareers/actions/runs/45049472526/workflow) calls `python -m collector.github_progress`. However, the [collector directory at that exact commit](https://github.com/khandakerashik/cybercareers/tree/9f8746f30f5c06f74d95440f5fd31936c783d86c/collector) does not contain `github_progress.py`. The same commit's file tree is also missing the root `github-scan.js` module. Python cannot start the requested module when its source file is absent.

The earlier v5.4.1 instructions for replacing only the workflow and backup helper assumed the full v5.4 scanner release was already installed. That assumption did not hold for this repository. Re-uploading only those two files does not restore the missing scanner components.

The latest workflow includes the previous Git push/cache repair. The current failure occurs in collection. Raw collector output was discarded, which hid Python's useful startup error from the workflow summary.

## What this package contains

`CyberCareers-BD-v5.4.2-repair.zip` is for the existing installation. It contains all application Python and frontend code, tests, static assets, the workflow and documentation. Extract it before uploading; a ZIP committed as one repository file does not install its contents.

The package does not contain `config.js`, `config/users.json`, `data/`, `encrypted/`, `.env` or `.vault/`. The existing installation supplies those files. Merge/overwrite the included code paths without deleting the repository's other files. Keep the existing `CC_MASTER_KEY` and other repository secrets.

The repaired code includes the detection/source improvements, Archived Jobs, Applied Jobs and notes, last completed fetch time, Scan now and encrypted live source progress. The GitHub scanner requires the compatible frontend, collector, telemetry, server and vault code together; adding one missing file alone is not a complete upgrade.

## Apply the repair through GitHub

1. Download and extract the repair ZIP. Open the extracted folder: `README.md`, `index.html`, `github-scan.js`, `collector/`, `server/`, `vault/`, `tests/`, `assets/`, `docs/` and `.github/` should be directly inside it.
2. In `khandakerashik/cybercareers`, choose **Add file → Upload files** from the repository root. Upload the extracted contents while retaining their paths. Choose a new branch such as `repair-complete-scanner` so the complete update can reach `main` together. Upload the contents, not an extra enclosing `CyberCareers-BD-v5.4.2-repair/` directory.
3. Include `.github/workflows/pages.yml`. If your file picker hides `.github`, enable hidden files. If the uploader still omits it, open the repository's existing `.github/workflows/pages.yml` on the repair branch, use its edit control, replace its complete content with the packaged file and commit to that same repair branch.
4. Before merging, confirm these files are present at their exact paths: `collector/ci.py`, `collector/github_progress.py`, `collector/telemetry.py`, `github-scan.js`, `vault/backup.py`, `tests/test_v542_ci.py`, and `tests/test_v542_release_preflight.py`. The rest of the included code must also be uploaded. Check the diff for unintended changes to account/configuration/data files; this package supplies none of those paths.
5. Merge the completed repair branch into `main`. The workflow's push trigger starts a fresh run. Alternatively, open **Actions → Collect, encrypt & publish → Run workflow**, select `main`, and leave **Run a collection scan before publishing** enabled.

GitHub supports folder uploads and up to 100 files per upload. The repair archive stays below that limit. The official [upload instructions](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository) and [manual workflow instructions](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow) describe those controls.

## Verify the new run

Use the new execution created from the repaired commit. The existing failed run is historical evidence and will remain red.

| Check | Expected result |
| --- | --- |
| Check complete release upload | Passes before dependency installation. If a required file is missing, it names the public code path and stops early. |
| Check release compatibility | Passes after dependencies are installed, before decrypting or collecting production data. It checks the collector/telemetry interfaces and scanner asset integration. |
| Collect cybersecurity vacancies | Runs `python -m collector.ci`. A normal completion prints a generic success message; private collection output stays suppressed. |
| Build/upload/deploy | Publishes the encrypted dataset after collection and sealing. |
| Back up encrypted state after successful deployment | Remains optional and runs after deployment. A cache or backup warning alone does not fail publishing. |
| Dashboard | Shows v5.4.2 after reload. A completed scan advances the last completed fetch time. A failed scan preserves the earlier completion time. |

The early checks do not fetch jobs or access vault keys. A missing file or incompatible scanner component is a release-installation error, not a successful empty scan.

The safe collection entry point suppresses collector prints, logging and inherited stdout/stderr. On a Python error it reports a restricted error category and, when available, a known repository Python file and line. It does not print raw exception messages, job titles, response bodies, local variables or credentials. A genuine failure retains a nonzero exit status; it is not relabeled as success.

## If a different error remains

Open the **first failing step** in the new run. Share its step name and safe error annotation. A missing-file preflight error identifies the upload path to correct. A collector error now includes a safe code location. The final interruption message summarizes the failed collection; it is not the underlying exception.

This repair restores the scanner's executable files and reports installation errors clearly. Individual sources can still be unavailable, rate-limited or restricted; the dashboard reports those results separately. Optional alert-mailbox and licensed API integrations still require their existing account-specific configuration.

## Validation and deployment status

See [VALIDATION.md](VALIDATION.md) for the offline tests and limits of verification. The public repository was inspected read-only. No repository commit, live scan, secret change or deployment was performed from this workspace. Production verification happens after the complete repair is uploaded and the new workflow finishes.

Developed by Khandaker Ashikul Hoque.
