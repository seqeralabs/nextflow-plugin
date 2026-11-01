#!/usr/bin/env bash
# Stop hook: run `nextflow lint` once, after Claude finishes responding.
# Idle unless NEXTFLOW_LINT_HOOK=1 or $CLAUDE_PROJECT_DIR/.claude/nextflow-lint-hook exists.
# Lints uncommitted .nf and .config files. A follow-up stop in the same turn exits without linting again.
set -euo pipefail

input=$(cat)

project=${CLAUDE_PROJECT_DIR:-$(pwd)}
if [[ ${NEXTFLOW_LINT_HOOK:-} != 1 && ! -f ${project}/.claude/nextflow-lint-hook ]]; then
  exit 0
fi

if command -v jq >/dev/null 2>&1; then
  stop_hook_active=$(printf '%s' "$input" | jq -r 'if .stop_hook_active == true then "true" else "false" end' 2>/dev/null || printf 'false')
else
  stop_hook_active=false
  if printf '%s' "$input" | grep -Eq '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
    stop_hook_active=true
  fi
fi
if [[ $stop_hook_active == true ]]; then
  exit 0
fi

command -v nextflow >/dev/null 2>&1 || exit 0
command -v git >/dev/null 2>&1 || exit 0
git -C "$project" rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

root=$(git -C "$project" rev-parse --show-toplevel)
if ! status=$(git -C "$root" status --porcelain --untracked-files=all); then
  exit 0
fi

files=()
while IFS= read -r line; do
  [[ -n $line ]] || continue
  path=${line:3}
  path=${path#* -> }
  # git quotes paths that contain spaces: "new dir/b.nf"
  if [[ $path == \"*\" ]]; then
    path=${path#\"}
    path=${path%\"}
  fi
  case "$path" in
    *.nf | *.config)
      if [[ -f "$root/$path" ]]; then
        files+=("$root/$path")
      fi
      ;;
  esac
done <<< "$status"

[[ ${#files[@]} -gt 0 ]] || exit 0

log=$(mktemp "${TMPDIR:-/tmp}/nextflow-lint.XXXXXX")
trap 'rm -f "$log"' EXIT

cd "$root"
if output=$(nextflow -q -log "$log" lint -o concise "${files[@]}" 2>&1); then
  exit 0
fi

{
  echo "nextflow lint reported issues in uncommitted .nf/.config files:"
  printf '%s\n' "$output"
  echo
  echo "Fix the lint issues above."
} >&2
exit 2
