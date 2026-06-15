#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export UV_CACHE_DIR="${UV_CACHE_DIR:-${TMPDIR:-/tmp}/interviewlg-uv-cache}"

run_python_checks() {
  local project="$1"
  echo "==> ${project}: ruff check"
  (cd "${ROOT_DIR}/${project}" && uv run ruff check src tests)

  if [[ "${CHECK_FORMAT:-0}" == "1" ]]; then
    echo "==> ${project}: ruff format --check"
    (cd "${ROOT_DIR}/${project}" && uv run ruff format --check src tests)
  fi

  echo "==> ${project}: pytest"
  (cd "${ROOT_DIR}/${project}" && uv run pytest)
}

run_web_checks() {
  echo "==> interview-agent/web: lint"
  (cd "${ROOT_DIR}/interview-agent/web" && npm run lint)

  if [[ "${CHECK_FORMAT:-0}" == "1" ]]; then
    echo "==> interview-agent/web: format check"
    (cd "${ROOT_DIR}/interview-agent/web" && npm run format:check)
  fi

  echo "==> interview-agent/web: build"
  (cd "${ROOT_DIR}/interview-agent/web" && npm run build)
}

run_python_checks "interview-agent"
run_python_checks "interview-vectordb"
run_python_checks "interview-tester"
run_web_checks

echo "All checks passed."
