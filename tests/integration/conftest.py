from __future__ import annotations

import os
import urllib.request

import pytest


def _localstack_healthy(endpoint_url: str) -> bool:
    url = endpoint_url.rstrip("/") + "/_localstack/health"
    try:
        with urllib.request.urlopen(url, timeout=1.5) as resp:  # nosec B310
            return 200 <= resp.status < 300
    except Exception:
        return False


@pytest.fixture(scope="session", autouse=True)
def localstack_env() -> None:
    """Set sane defaults so boto3 can talk to LocalStack in integration tests."""

    os.environ.setdefault("USE_LOCALSTACK", "true")
    os.environ.setdefault("ENDPOINT_URL", "http://localhost:4566")
    # Backwards compatible name (used by some scripts/older code).
    os.environ.setdefault(
        "LOCALSTACK_ENDPOINT_URL",
        os.environ.get("ENDPOINT_URL", "http://localhost:4566"),
    )
    os.environ.setdefault("AWS_REGION", "eu-west-1")

    # boto3 requires some credentials to be present, even for LocalStack.
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")


@pytest.fixture(scope="session")
def require_localstack(localstack_env: None) -> str:
    endpoint_url = os.environ.get(
        "ENDPOINT_URL",
        os.environ.get("LOCALSTACK_ENDPOINT_URL", "http://localhost:4566"),
    )
    if not _localstack_healthy(endpoint_url):
        msg = f"LocalStack not reachable at {endpoint_url}"

        # In CI we want this to be a hard failure, because the workflow is
        # expected to start LocalStack.
        if (
            os.getenv("CI")
            or os.getenv("GITHUB_ACTIONS")
            or os.getenv("REQUIRE_LOCALSTACK")
        ):
            pytest.fail(msg, pytrace=False)

        pytest.skip(f"{msg}; skipping integration tests")
    return endpoint_url
