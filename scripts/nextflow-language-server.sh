#!/usr/bin/env bash
#
# Optional launcher for the Nextflow language server (.lsp.json).
# Skills do not call this script. They validate with `nextflow lint`.
#
# Resolution order:
#   1. nextflow-lsp on PATH (standalone release bundle)
#   2. nlsp on PATH
#   3. java -jar "$NEXTFLOW_LSP_JAR" (Java 17+)
#
# https://github.com/nextflow-io/language-server

set -euo pipefail

log() { echo "nextflow-language-server: $*" >&2; }

if command -v nextflow-lsp >/dev/null 2>&1; then
  exec nextflow-lsp "$@"
fi

if command -v nlsp >/dev/null 2>&1; then
  exec nlsp "$@"
fi

jar="${NEXTFLOW_LSP_JAR:-}"
if [ -n "$jar" ]; then
  if [ ! -f "$jar" ]; then
    log "NEXTFLOW_LSP_JAR is not a file: $jar"
    exit 1
  fi
  if ! command -v java >/dev/null 2>&1; then
    log "Java 17+ is required to run $jar"
    exit 1
  fi
  exec java -jar "$jar" "$@"
fi

log "language server not installed; live diagnostics are skipped."
log "Install nextflow-lsp or set NEXTFLOW_LSP_JAR. Skills still use nextflow lint."
exit 1
