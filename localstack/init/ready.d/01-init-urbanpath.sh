#!/usr/bin/env bash
set -euo pipefail

# LocalStack init script (runs when LocalStack is ready)
# Creates the resources needed for UrbanPath demo.

REGION="${AWS_DEFAULT_REGION:-eu-west-1}"

S3_GRAPHS_BUCKET="${S3_GRAPHS_BUCKET:-urbanpath-graphs}"
S3_STREET_BUCKET="${S3_STREET_BUCKET:-urbanpath-street-graphs}"

SQS_QUEUE_NAME="${SQS_QUEUE_NAME:-urbanpath-route-requests}"
DDB_TABLE_NAME="${DDB_TABLE_NAME:-urbanpath-route-results}"

awslocal s3 mb "s3://${S3_GRAPHS_BUCKET}" --region "$REGION" || true
awslocal s3 mb "s3://${S3_STREET_BUCKET}" --region "$REGION" || true

awslocal sqs create-queue --queue-name "$SQS_QUEUE_NAME" --region "$REGION" >/dev/null

# Create DynamoDB table if missing
if ! awslocal dynamodb describe-table --table-name "$DDB_TABLE_NAME" --region "$REGION" >/dev/null 2>&1; then
  awslocal dynamodb create-table \
    --table-name "$DDB_TABLE_NAME" \
    --billing-mode PAY_PER_REQUEST \
    --attribute-definitions AttributeName=request_id,AttributeType=S \
    --key-schema AttributeName=request_id,KeyType=HASH \
    --region "$REGION" >/dev/null
fi
