#!/usr/bin/env bash
set -euo pipefail

# Run only LocalStack-backed tests.
uv run pytest -q -m integration --cov=src --cov-report=term-missing
