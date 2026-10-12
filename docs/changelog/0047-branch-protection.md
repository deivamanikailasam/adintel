# 0047 — Nobody changes the main code line alone

**In one sentence:** the rules for changing the main branch — a reviewed pull request, the code owner's
approval and every CI check green — are now written as files in the repository and applied with one
command.

## What changed

- `.github/rulesets/default-branch.json` — on the default branch: changes only through pull requests; 1
  approval including the code owner; approvals dismissed on new pushes; the last push must be approved by
  someone else; review threads resolved; all nine CI jobs required and up to date with the base; linear
  history; no force-push, no deletion. Repository admins may bypass the review count only *through* a PR
  (needed while the team is one person).
- `.github/rulesets/release-tags.json` — `v*` tags cannot be moved or deleted (releases are immutable).
- `scripts/apply_repo_rules.sh <owner/repo> [--dry-run]` — creates or updates the rulesets via the GitHub
  API and sets squash-only merges, branch auto-delete, secret scanning and push protection.
- `tests/unit/test_repo_rules.py` — fails if a CI job is added without becoming a required check (or the
  reverse).

**To activate:** a repository admin runs `scripts/apply_repo_rules.sh deivamanikailasam/adintel` once
(it changes repository settings, so it is deliberately not run automatically).

## Why it matters (layman's terms)

Two-person rule for the vault: no one — not even the owner — can quietly push a change to the code that
moves client money. Every change is seen by a second pair of eyes and passes every automatic check first,
and once a release is labelled, the label can't be moved to different code.
