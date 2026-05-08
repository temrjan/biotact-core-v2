#!/usr/bin/env bash
# Phase 0 smoke: small RAG eval run to verify the pipeline is wired and
# safety redirects still work. Skips the LLM faithfulness judge to keep
# runtime under ~30s. Used by /verify.
#
# Exit codes:
#   0 — pipeline OK, no safety regressions
#   1 — at least one case errored or a safety case failed to redirect
#   2 — no matching cases (config/path issue)

set -euo pipefail

cd "$(dirname "$0")/.."

exec python3 scripts/run_eval.py --limit 5 --no-judge --lang ru "$@"
