#!/usr/bin/env bash
set -euo pipefail

# Run only LocalStack-backed tests.
uv run pytest -q -m integration \
	--cov=src \
	--cov-append \
	--cov-report=xml:.coverage-integration.xml \
	--cov-fail-under=0
