from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import boto3
from botocore.client import BaseClient

if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBClient
    from mypy_boto3_s3 import S3Client
    from mypy_boto3_sqs import SQSClient
else:
    DynamoDBClient = BaseClient  # type: ignore[misc,assignment]
    S3Client = BaseClient  # type: ignore[misc,assignment]
    SQSClient = BaseClient  # type: ignore[misc,assignment]


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True, slots=True)
class AwsRuntimeConfig:
    use_localstack: bool
    region: str
    endpoint_url: str | None

    @staticmethod
    def from_env() -> "AwsRuntimeConfig":
        endpoint_url = os.getenv("ENDPOINT_URL")
        if endpoint_url is not None:
            endpoint_url = endpoint_url.strip() or None

        return AwsRuntimeConfig(
            use_localstack=_env_bool("USE_LOCALSTACK", False),
            region=os.getenv("AWS_REGION", "eu-west-1"),
            endpoint_url=endpoint_url,
        )

    def resolved_endpoint_url(self) -> str | None:
        """Return the endpoint URL to use for boto3.

        Priority:
          1) ENDPOINT_URL (explicit override; preferred for LocalStack)
          2) LOCALSTACK_ENDPOINT_URL if USE_LOCALSTACK is enabled (legacy)
          3) None (AWS real)
        """

        if self.endpoint_url:
            return self.endpoint_url
        if self.use_localstack:
            return os.getenv("LOCALSTACK_ENDPOINT_URL", "http://localhost:4566")
        return None


def boto3_client(service: str) -> BaseClient:
    cfg = AwsRuntimeConfig.from_env()

    endpoint_url = cfg.resolved_endpoint_url()

    session = boto3.session.Session(region_name=cfg.region)
    return cast(
        BaseClient, cast(Any, session).client(service, endpoint_url=endpoint_url)
    )


def s3_client() -> S3Client:
    cfg = AwsRuntimeConfig.from_env()
    endpoint_url = cfg.resolved_endpoint_url()
    session = boto3.session.Session(region_name=cfg.region)
    return session.client("s3", endpoint_url=endpoint_url)


def sqs_client() -> SQSClient:
    cfg = AwsRuntimeConfig.from_env()
    endpoint_url = cfg.resolved_endpoint_url()
    session = boto3.session.Session(region_name=cfg.region)
    return session.client("sqs", endpoint_url=endpoint_url)


def dynamodb_client() -> DynamoDBClient:
    cfg = AwsRuntimeConfig.from_env()
    endpoint_url = cfg.resolved_endpoint_url()
    session = boto3.session.Session(region_name=cfg.region)
    return session.client("dynamodb", endpoint_url=endpoint_url)
