# Git Governance & Recovery Runbook

**Why this exists:** Workstream A was fully implemented, tested, and reviewed — then
its branch was deleted from origin **unmerged**. It survived only as a dangling object
in a single local clone and was nearly lost permanently. Root cause: origin was the
single source of truth, and one deletion there meant total loss. No PR, tag, or mirror
held a copy. This document defines the controls that make that failure impossible to
repeat, and the procedure to recover if work is ever lost again.

## Controls (defense in depth)

### Tier 1 — Prevent (GitHub)
- **Branch protection on `main` and `dev`:** PR required, status checks strict
  (`lint-and-test`), **force-push blocked, deletion blocked**, admins included,
  0 required approvals (solo-maintainer friendly — CI + CodeRabbit/Antigravity/Aikido + in-window
  Opus are the gates).
- **Merge-only branch deletion:** repo setting "Automatically delete head branches"
  is enabled — it fires *only on merge*, never on close. Feature branches are never
  deleted while their work is unmerged.
- **Draft PR on first push:** the moment a workstream branch is pushed, open a (draft)
  PR. GitHub retains a PR's head commits even after the branch is deleted — this single
  habit would have prevented the A loss.

### Tier 2 — Recover (insurance)
- **Nightly off-GitHub mirror on the always-on gateway** (paths below are relative to
  the gateway service account's home directory):
  - Script: `~/git-backups/hermia-backup.sh`
  - Cron: `0 3 * * *` (nightly 03:00)
  - **Non-pruning** bare mirror at `~/git-backups/hermia.git` — refs deleted
    on origin are **retained** here.
  - Immutable dated `git bundle` snapshots in `~/git-backups/bundles/`
    (`--all`, 30-day retention). Each bundle is a complete point-in-time backup that
    origin deletion or force-push cannot touch.
- **Milestone tags:** annotated `ws-<x>-reviewed-<date>` tags pin reviewed work. Tags
  are not pruned and survive branch deletion.

### Tier 3 — Detect (tripwire)
- **`docs/WORKSTREAMS.md`** lists every active branch + PR + tag. A vanished branch is
  immediately obvious, and the manifest names its PR/tag for recovery.

### Tier 4 — Discipline
- PR-only into `dev`/`main` (enforced by Tier 1). Never delete a branch until its PR
  reads **Merged**. Never rely on a single clone's remote-tracking refs as the only
  copy of a branch — push it, and let the Tier 2 mirror/bundles and milestone tags hold
  the backups. (`git fetch --prune` only removes stale `refs/remotes/*` tracking refs,
  not local branches — but a branch that lives *only* as a tracking ref disappears with it.)

## Recovery procedures

### A branch was deleted on origin
1. **From its PR (fastest):** the PR retains the commits. `gh pr checkout <n>` or fetch
   the PR head: `git fetch origin pull/<n>/head:recover/<name>`.
2. **From a milestone tag:** `git fetch origin tag ws-<x>-reviewed-<date>` then
   `git branch recover/<name> ws-<x>-reviewed-<date>`. (The `tag` keyword creates the
   local tag ref; a bare `refs/tags/<x>` fetch only populates `FETCH_HEAD`.)
3. **From the gateway mirror** (retains deleted refs):
   ```bash
   git fetch "gateway:git-backups/hermia.git" \
     '+refs/heads/<name>:recover/<name>'
   ```
4. **From a dated bundle** (worst case, full snapshot):
   ```bash
   scp gateway:~/git-backups/bundles/hermia-<stamp>.bundle /tmp/
   git bundle list-heads /tmp/hermia-<stamp>.bundle      # inspect refs
   git fetch /tmp/hermia-<stamp>.bundle '+refs/heads/<name>:recover/<name>'
   ```

### A commit is "lost" locally (detached/amended)
- `git reflog` and `git fsck --lost-found` find dangling commits before GC removes them.

## Verifying the backup is healthy
```bash
ssh gateway 'tail -3 ~/git-backups/backup.log; \
  ls -t ~/git-backups/bundles | head -1'
```
Most recent bundle should be < 24h old. If stale, run the script manually and check cron.
