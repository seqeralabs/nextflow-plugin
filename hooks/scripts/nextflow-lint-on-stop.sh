#!/usr/bin/env bash
# Stop hook: lint uncommitted .nf and .config files once, when the agent
# finishes a turn. Idle unless NXF_LINT_ON_STOP is 1, true, or yes. Skips
# when nextflow is missing, the directory is not a git checkout, or no
# matching file changed. A Stop that is already a continuation of this hook
# exits without linting, so a failing run does not start Nextflow again.
set -euo pipefail

case "${NXF_LINT_ON_STOP:-}" in
  1|true|TRUE|yes|YES) ;;
  *) exit 0 ;;
esac

input="$(cat || true)"
# Match compact or pretty-printed JSON. Avoid grep -q under pipefail: a large
# payload can SIGPIPE the writer and hide a real match.
active_pattern='"stop_hook_active"[[:space:]]*:[[:space:]]*true'
if [[ "$input" =~ $active_pattern ]]; then
  exit 0
fi

command -v nextflow >/dev/null 2>&1 || exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

root="$(git rev-parse --show-toplevel)"
files=()
while IFS= read -r path; do
  [ -n "$path" ] || continue
  case "$path" in
    *.nf|*.config) ;;
    *) continue ;;
  esac
  abs="${root}/${path}"
  [ -f "$abs" ] || continue
  files+=("$abs")
done < <(
  {
    git -C "$root" diff --name-only --diff-filter=ACMR
    git -C "$root" diff --name-only --cached --diff-filter=ACMR
    git -C "$root" ls-files --others --exclude-standard
  } | LC_ALL=C sort -u
)

[ "${#files[@]}" -eq 0 ] && exit 0

if output="$(nextflow lint "${files[@]}" 2>&1)"; then
  exit 0
fi

{
  echo "nextflow lint found issues in uncommitted .nf/.config files:"
  echo "$output"
  echo
  echo "Fix the lint errors above."
} >&2
exit 2
