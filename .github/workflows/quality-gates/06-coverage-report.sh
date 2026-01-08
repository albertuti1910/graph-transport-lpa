#!/usr/bin/env bash
set -euo pipefail

# Print and enforce coverage once, after all test suites have run.
# Uses configuration from pyproject.toml ([tool.coverage.*]).

if [[ ! -f .coverage ]]; then
  echo "No .coverage data file found. Ensure tests ran with --cov."
  exit 1
fi

uv run coverage report -m --fail-under=70
