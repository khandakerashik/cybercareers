# CyberCareers BD v5.4.0 — Scan now and live progress

This release adds a manual **Scan now** action and **Source-by-source progress**. The v5.2 source/detection repairs and v5.3 Archived Jobs, Applied Jobs and personal notes remain included.

## Upgrade the complete project

1. Preserve your existing `.env`, `config/users.json`, `.vault/`, `encrypted/`, collected data, customized feeds/ATS settings and `CC_MASTER_KEY` secret. Keep the same site address to retain access to browser-stored applications and notes.
2. Merge the complete package into the existing project root, including **`github-scan.js`**, `collector/github_progress.py`, updated frontend/collector/server/vault code and `.github/workflows/pages.yml`. Keep private configuration instead of sample files.
3. Locally, install `requirements.txt` and restart `python -m server.app`. For Pages, commit/push the code and run **Actions → Collect, encrypt & publish → Run workflow** once to publish the updated dashboard. Keep **Settings → Pages → Source** set to **GitHub Actions**.
4. Refresh the dashboard and confirm **v5.4.0**, **Scan now**, and **Source-by-source progress** are visible. The supplied workflow's push filter remains `main`; change that filter if your deployment branch is different. The manual scanner does not assume that your default branch is `main`.

No vault reset or new database is needed. Older installations should also read the [v5.2 configuration guide](UPGRADE_v5.2.md) and [v5.3 application/notes guide](UPGRADE_v5.3.md).

## Use the local scanner

```powershell
python -m pip install -r requirements.txt
python -m server.app
```

Open the printed address and choose **Scan now**. The browser uses the protected same-origin refresh endpoint. Keep the server running. Progress refreshes approximately every **two seconds**; provider schedules and request limits still apply.

An existing scan is followed. An uncertain request is checked before another is enabled. Stopping the server stops local collection; unfinished activity is identified as interrupted on restart.

## Connect GitHub Pages

1. Sign in to the published dashboard so it can decrypt your dataset and live progress.
2. Choose **Scan now** or **Connect scanner**. Confirm `owner/repository`. Updated Pages builds supply public repository/workflow/branch metadata automatically; otherwise enter the repository yourself.
3. Use the deployment branch, or leave **Branch** empty to discover the repository's default branch. The selected branch must contain the updated `pages.yml` workflow with `workflow_dispatch` enabled.
4. Enter a repository-authorized GitHub token and choose **Connect & scan**, or connect first and then choose **Scan now**.
5. Follow the run in the dashboard. **View GitHub run** opens its GitHub page. The workflow may spend time queued or preparing dependencies before any source update exists.

The token stays in this tab's memory and is sent directly to `api.github.com`. It is never saved in browser storage, site configuration or the dataset. Disconnect, sign-out and reload clear it. Disconnecting does not cancel a running workflow.

### Token permissions

| Task | Supported access |
| --- | --- |
| Start and monitor a workflow | A compatible token authorized for the repository with **Actions write** access. A fine-grained personal token can be restricted to the selected repository. |
| Read private live source details | A compatible GitHub App token with **Actions write + Checks read**, or a classic personal token with `repo` scope. The classic scope grants broader repository access. |
| Run without entering a token in this dashboard | Choose **Open GitHub Actions**, then **Collect, encrypt & publish → Run workflow**. Published results load after deployment; connecting is required for the dashboard's GitHub monitoring. |

GitHub documents fine-grained tokens for [workflow dispatch](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event), but its [Checks API](https://docs.github.com/en/rest/checks/runs#get-a-check-run) lists compatible App tokens and classic `repo` access for private repositories. A fine-grained token may start a scan while private live details remain unavailable; workflow status and the Actions link remain available.

## Read the source report

Open **Source-by-source progress**, search by employer/feed/source, or use **Checking now**, **Queued**, **Failed / limited**, or **Completed / deferred** filters.

| Displayed state | Meaning |
| --- | --- |
| Queued | Planned, with no reported source start yet. |
| Checking | The collector reported that this source started. Several can run concurrently. |
| Completed | This source attempt finished successfully; zero relevant jobs can be a valid result. |
| Limited | Some requested source coverage or extraction remained incomplete. |
| Failed | The source attempt reported a network, policy, access or parser failure. |
| Cached / deferred | No fresh check was required or the source was deliberately deferred. |
| Interrupted | The run ended before the source completed; it is not counted as a successful fetch. |

Rows show messages, **jobs / newly added jobs**, and duration from reported timestamps. Unknown values show **—**. Counts describe this collector's results; they do not establish exhaustive publisher coverage.

GitHub updates arrive approximately every **15 seconds**, subject to availability. Stale updates are labelled, with no simulated completion. **Sources checked · publishing** means collection finished but sealing/deployment continues. The previous completed-fetch timestamp stays visible during a new or failed attempt; published jobs refresh after deployment.

Repeated clicks cannot start parallel local collectors. An existing GitHub run is followed. If a dispatch response is lost, the dashboard monitors for that run instead of automatically sending another POST. Check the linked workflow before disconnecting/reconnecting to retry.

## How live progress stays private

The workflow grants its built-in token `checks: write` and passes it only to collection as `GH_PROGRESS_TOKEN`. A **CyberCareers live collection** check contains a generic summary and encrypted `CCLIVE1` output. Its fresh AES-256 key is wrapped for current vault users. Source details remain encrypted, with no master-key/CI recipient.

A separate worker publishes progress; permission failures or outages do not stop collection. Oversized updates explicitly indicate shortened details. The final source-health report remains available after publication. Browser and workflow tokens are separate credentials.

## Troubleshooting and validation

| Symptom | What to check |
| --- | --- |
| Cannot connect or start | Repository access, token expiry/permissions, selected branch and the updated `pages.yml`. Use **Open GitHub Actions** to inspect the workflow. |
| Workflow runs, source detail unavailable | Checks-read compatibility, workflow `checks: write`, the existing vault master key/users, and whether the collector step has started. |
| No source rows on an old report | Run one scan with v5.4. Historic snapshots have no fabricated lifecycle rows. |
| Progress stopped changing | Read the stale/error notice and actual GitHub run state. Rate-limited requests wait before polling again. |
| Jobs still show the previous collection | Wait for seal/build/deploy to finish; the dashboard distinguishes source completion from publication. |

This package was checked with offline regressions and synthetic Python-to-browser encryption interoperability. **No live repository was connected, dispatched or deployed during preparation.** See [VALIDATION.md](VALIDATION.md) for final test results and remaining environment limits.

**Developed by Khandaker Ashikul Hoque**
