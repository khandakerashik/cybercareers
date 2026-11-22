# CyberCareers BD v5.4.1 — Repair failed publishing

> **Superseded for incomplete or older installations:** use [the v5.4.2 complete repair](UPGRADE_v5.4.2.md). The two-file procedure below assumes all v5.4 scanner code is already present. If `collector/github_progress.py` or `github-scan.js` is missing, updating only the workflow and backup helper will leave collection broken.

## What the supplied log shows

The failing step is **Commit encrypted state when the job list changed (durable backup)**. The local commit was created, but GitHub rejected its push with `main -> main (fetch first)`. The remote branch had changes absent from the runner's checkout. Because that optional backup step preceded the build and deployment and was allowed to fail the job, all subsequent publishing steps were skipped.

The cache reservation warning is separate. The old key used only `github.run_id`; GitHub retains that ID when an execution is rerun, and an existing cache cannot be overwritten. Reusing a key can therefore produce the displayed warning. The screenshot alone does not establish who changed the branch or whether the key was reused by a rerun or another writer. The Node `punycode` deprecation warning is also separate from the rejected push.

## Install the repair

For an existing v5.4 installation, the two functional repair files are:

- `.github/workflows/pages.yml` — replace the existing workflow.
- `vault/backup.py` — add this new module.

Merge the complete v5.4.1 package if you also want the updated version label, documentation and regression tests. Extract the ZIP before uploading files to GitHub; uploading a ZIP file into the repository does not update the files inside it. Keep your existing `.env`, `.vault/`, `config/users.json`, `encrypted/`, customized source settings and `CC_MASTER_KEY` secret.

1. Commit the updated workflow and backup module together to the deployment branch (`main` in the supplied screenshot).
2. The push can start a new **Collect, encrypt & publish** run automatically. If it does, follow that new execution.
3. Otherwise open **Actions → Collect, encrypt & publish → Run workflow**. Select the updated branch, keep **Run a collection scan before publishing** enabled, and start the workflow.
4. Open the **new run** and confirm the build, upload and Pages deployment steps complete.
5. Read **Back up encrypted state after successful deployment** and the run summary for the optional backup result.

Use a new run after updating the files. Clicking **Re-run failed jobs** on the old execution uses its original commit/ref and can run the old workflow again.

## What changed

The workflow now builds and deploys the ciphertext-only site before attempting a repository backup. A failure in that optional backup is reported without undoing or blocking a successful deployment. Collection, encryption, tests and deployment still report their own failures; a real interrupted collector is not hidden.

The backup fetches the latest remote branch and creates a separate temporary worktree. It copies only validated manifest-listed ciphertext and its keyring, preserving unrelated remote changes. If the remote encrypted snapshot or allowed-user configuration changed since the original checkout, it skips the stale backup rather than overwriting that state. If unrelated code advances during the push, the helper refetches and retries a bounded number of times. It never force-pushes, rebases the live build checkout, or merges individual encrypted blobs.

A missing backup is considered again after the next successful deployment. The helper compares the collected jobs' fingerprint to the repository backup, not only the restored cache; fresh encryption keys alone do not cause unnecessary hourly commits.

Cache keys have this structure:

```yaml
key: cc-v2-vault-${{ github.ref }}::${{ github.run_id }}-${{ github.run_attempt }}
restore-keys: 'cc-v2-vault-${{ github.ref }}::'
```

The ref delimiter prevents similarly named branches from sharing a prefix. On the default branch, a separate fallback can recover an old-format cache when no new-format cache matched. Cache reads and writes are optional; the committed encrypted snapshot remains a fallback when available.

## Expected outcomes

| Result | Meaning |
| --- | --- |
| Pages deployment succeeded; backup saved | Both the site and encrypted repository backup were updated. |
| Pages deployment succeeded; backup unchanged | The repository already has the same collected jobs. |
| Pages deployment succeeded; backup skipped | Newer vault/access state was preserved, or the run was not eligible for a branch backup. Read the summary. |
| Pages deployment succeeded; backup failed | The published site is available, but a repository/network/policy issue prevented this optional backup. The next successful run can retry. |
| Build, seal, collection or deployment failed | Inspect that step's own error; the current repair addresses the backup/cache errors in the supplied screenshot. |

Do not delete the encrypted dataset or reset the vault key to solve this push rejection. Branch protections and repository permissions are respected; the helper does not bypass them.

The repair is validated against temporary local Git repositories, including real rejected pushes and concurrent changes. It has not been pushed to or executed inside the user's live repository. See [VALIDATION.md](VALIDATION.md) for the recorded tests.

## References

- [GitHub: dealing with non-fast-forward errors](https://docs.github.com/en/get-started/using-git/dealing-with-non-fast-forward-errors)
- [GitHub Actions: run ID and run attempt](https://docs.github.com/en/actions/reference/workflows-and-actions/variables)
- [GitHub Actions: cache matching and immutability](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
- [GitHub Actions: reruns use the original commit and ref](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs)

**Developed by Khandaker Ashikul Hoque**
