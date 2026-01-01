#!/usr/bin/env bash
set -euo pipefail

uv run pytest -q -m "not integration and not e2e and not load" --cov=src --cov-report=term-missing
