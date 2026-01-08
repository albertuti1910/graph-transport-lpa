#!/usr/bin/env bash
set -euo pipefail

# Cheap+automatic AWS deploy:
# - Terraform creates S3/SQS/DDB + optional EC2 runtime + ECR repos.
# - This script builds & pushes app+web images to ECR.
# - Then it triggers a restart on the EC2 instance via SSM to pull latest.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INFRA_DIR="$ROOT_DIR/infra"
IMAGE_TAG="${IMAGE_TAG:-latest}"
AWS_REGION="${AWS_REGION:-eu-west-1}"
OSM_GRAPH_S3_URI="${OSM_GRAPH_S3_URI:-}"

# Optional overrides
COMPUTE_INSTANCE_TYPE="${COMPUTE_INSTANCE_TYPE:-}"
COMPUTE_ALLOW_HTTP_CIDR="${COMPUTE_ALLOW_HTTP_CIDR:-}"

require() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

require terraform
require aws
require docker

echo "[preflight] Checking AWS credentials"
if ! aws sts get-caller-identity >/dev/null 2>&1; then
  echo "AWS credentials are not valid (expired/invalid/missing)." >&2
  echo "Fix this first, then re-run this script." >&2
  echo "Quick checks:" >&2
  echo "  aws configure list" >&2
  echo "  aws sts get-caller-identity" >&2
  echo "Common fixes:" >&2
  echo "- If you use AWS SSO: run 'aws sso login' (and ensure AWS_PROFILE is set)." >&2
  echo "- If you use temporary session credentials: refresh access key + secret + session token." >&2
  echo "- If you use long-lived IAM user keys: remove any 'aws_session_token' from ~/.aws/credentials." >&2
  exit 1
fi

if [[ -z "$OSM_GRAPH_S3_URI" ]]; then
  echo "Missing OSM_GRAPH_S3_URI (required). Example: s3://my-bucket/lpa_walk.graphml" >&2
  exit 1
fi

pushd "$INFRA_DIR" >/dev/null

echo "[1/4] Applying Terraform (AWS)"
terraform init
terraform apply -auto-approve \
  -var="use_localstack=false" \
  -var="aws_region=$AWS_REGION" \
  -var="enable_compute=true" \
  -var="compute_image_tag=$IMAGE_TAG" \
  -var="osm_graph_s3_uri=$OSM_GRAPH_S3_URI" \
  ${COMPUTE_INSTANCE_TYPE:+-var="compute_instance_type=$COMPUTE_INSTANCE_TYPE"} \
  ${COMPUTE_ALLOW_HTTP_CIDR:+-var="compute_allow_http_cidr=$COMPUTE_ALLOW_HTTP_CIDR"}

APP_ECR_URL="$(terraform output -raw app_ecr_repository_url)"
WEB_ECR_URL="$(terraform output -raw web_ecr_repository_url)"
INSTANCE_ID="$(terraform output -raw compute_instance_id)"

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ECR_REGISTRY="$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

popd >/dev/null

echo "[2/4] Logging into ECR ($ECR_REGISTRY)"
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"

echo "[3/4] Building & pushing images ($IMAGE_TAG)"
(
  cd "$ROOT_DIR"
  docker build -t "$APP_ECR_URL:$IMAGE_TAG" .
  docker push "$APP_ECR_URL:$IMAGE_TAG"

  docker build -t "$WEB_ECR_URL:$IMAGE_TAG" -f web/Dockerfile web
  docker push "$WEB_ECR_URL:$IMAGE_TAG"
)


echo "[4/4] Restarting service on EC2 via SSM ($INSTANCE_ID)"

echo "Waiting for EC2 Status Checks..."
aws ec2 wait instance-status-ok --instance-ids "$INSTANCE_ID" --region "$AWS_REGION"

echo "Waiting for SSM Agent to come online..."
while true; do
  STATUS=$(aws ssm describe-instance-information \
    --filters "Key=InstanceIds,Values=$INSTANCE_ID" \
    --query "InstanceInformationList[0].PingStatus" \
    --region "$AWS_REGION" \
    --output text)

  if [[ "$STATUS" == "Online" ]]; then
    echo "Instance is Online in SSM!"
    break
  fi

  echo "SSM Status: ${STATUS:-Offline}. Retrying in 5 seconds..."
  sleep 5
done

aws ssm send-command \
  --region "$AWS_REGION" \
  --instance-ids "$INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --comment "urbanpath: pull latest images and restart" \
  --parameters commands='[
    "set -euo pipefail",
    "if systemctl list-unit-files | grep -qE \"^urbanpath\\.service\"; then sudo systemctl restart urbanpath.service; exit 0; fi",
    "echo \"urbanpath.service not found; attempting direct docker compose up\"",
    "if [ -x /usr/local/bin/urbanpath-update.sh ]; then sudo /usr/local/bin/urbanpath-update.sh; exit 0; fi",
    "echo \"/usr/local/bin/urbanpath-update.sh not found. Debug info:\"",
    "ls -la /opt/urbanpath || true",
    "cloud-init status --long || true",
    "journalctl -u cloud-init -b --no-pager | tail -n 200 || true",
    "tail -n 200 /var/log/cloud-init-output.log || true"
  ]' \
  --output text >/dev/null

echo "Done. It can take ~1-2 minutes for SSM/containers to settle."

echo "Next: check the public IP with:"
echo "  cd infra && terraform output -raw compute_public_ip"
