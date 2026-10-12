#!/usr/bin/env bash
# Apply the repository rulesets in .github/rulesets/ (branch protection as code). Idempotent: an existing
# ruleset with the same name is updated in place. Needs the GitHub CLI authenticated as a repository admin.
#
#   scripts/apply_repo_rules.sh deivamanikailasam/adintel
#   scripts/apply_repo_rules.sh deivamanikailasam/adintel --dry-run
set -euo pipefail
REPO="${1:?usage: scripts/apply_repo_rules.sh <owner/repo> [--dry-run]}"
DRY="${2:-}"
cd "$(dirname "$0")/.."
existing=$(gh api "repos/$REPO/rulesets" --paginate -q '.[] | "\(.name)\t\(.id)"' || true)
for f in .github/rulesets/*.json; do
  name=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["name"])' "$f")
  id=$(printf '%s\n' "$existing" | awk -F'\t' -v n="$name" '$1==n{print $2}')
  if [ -n "$DRY" ]; then echo "would $( [ -n "$id" ] && echo update "#$id" || echo create ) $name"; continue; fi
  if [ -n "$id" ]; then
    gh api -X PUT "repos/$REPO/rulesets/$id" --input "$f" >/dev/null && echo "updated $name (#$id)"
  else
    gh api -X POST "repos/$REPO/rulesets" --input "$f" >/dev/null && echo "created $name"
  fi
done
# Repository settings that rulesets don't cover
[ -n "$DRY" ] || gh api -X PATCH "repos/$REPO" \
  -F delete_branch_on_merge=true -F allow_merge_commit=false -F allow_squash_merge=true -F allow_rebase_merge=false \
  -F 'security_and_analysis[secret_scanning][status]=enabled' \
  -F 'security_and_analysis[secret_scanning_push_protection][status]=enabled' >/dev/null && echo "repository settings applied"
