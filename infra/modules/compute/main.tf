data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}

data "aws_region" "current" {}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

locals {
  name_prefix  = var.project
  account_id   = data.aws_caller_identity.current.account_id
  ecr_registry = "${local.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com"

  # Optional: bucket that hosts the prebuilt OSM graph artifact (s3://bucket/key)
  osm_graph_bucket = var.osm_graph_s3_uri != "" ? split("/", replace(var.osm_graph_s3_uri, "s3://", ""))[0] : null
}

resource "aws_key_pair" "debug" {
  key_name   = "urbanpath-debug-key"
  public_key = file("${path.module}/debug_key.pub")
}

resource "aws_ecr_repository" "app" {
  name = "${local.name_prefix}-app"

  image_scanning_configuration {
    scan_on_push = false
  }
}

resource "aws_ecr_repository" "web" {
  name = "${local.name_prefix}-web"

  image_scanning_configuration {
    scan_on_push = false
  }
}

resource "aws_security_group" "http" {
  name        = "${local.name_prefix}-http"
  description = "HTTP access to UrbanPath web"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = [var.allow_http_cidr]
  }

  ingress {
    description = "SSH Debugging"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

data "aws_iam_policy_document" "assume_ec2" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "instance" {
  name               = "${local.name_prefix}-instance"
  assume_role_policy = data.aws_iam_policy_document.assume_ec2.json
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "instance_inline" {
  statement {
    sid = "EcrPull"
    actions = [
      "ecr:GetAuthorizationToken",
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer"
    ]
    resources = ["*"]
  }

  statement {
    sid = "Sqs"
    actions = [
      "sqs:SendMessage",
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl"
    ]
    resources = ["*"]
  }

  statement {
    sid = "Ddb"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DescribeTable"
    ]
    resources = ["*"]
  }

  statement {
    sid = "S3Buckets"
    actions = [
      "s3:ListBucket"
    ]
    resources = [
      "arn:${data.aws_partition.current.partition}:s3:::${var.street_graph_bucket}"
    ]
  }

  dynamic "statement" {
    for_each = local.osm_graph_bucket != null ? [local.osm_graph_bucket] : []
    content {
      sid = "S3OsmGraphBucket"
      actions = [
        "s3:ListBucket"
      ]
      resources = [
        "arn:${data.aws_partition.current.partition}:s3:::${statement.value}"
      ]
    }
  }

  statement {
    sid = "S3Objects"
    actions = [
      "s3:GetObject",
      "s3:PutObject"
    ]
    resources = [
      "arn:${data.aws_partition.current.partition}:s3:::${var.street_graph_bucket}/*"
    ]
  }

  dynamic "statement" {
    for_each = local.osm_graph_bucket != null ? [local.osm_graph_bucket] : []
    content {
      sid = "S3OsmGraphObjects"
      actions = [
        "s3:GetObject"
      ]
      resources = [
        "arn:${data.aws_partition.current.partition}:s3:::${statement.value}/*"
      ]
    }
  }
}

resource "aws_iam_role_policy" "instance_inline" {
  name   = "${local.name_prefix}-instance-inline"
  role   = aws_iam_role.instance.id
  policy = data.aws_iam_policy_document.instance_inline.json
}

resource "aws_iam_instance_profile" "instance" {
  name = "${local.name_prefix}-instance"
  role = aws_iam_role.instance.name
}

# Amazon Linux 2023 (x86_64)
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_instance" "urbanpath" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  subnet_id              = tolist(data.aws_subnets.default.ids)[0]
  vpc_security_group_ids = [aws_security_group.http.id]
  key_name               = aws_key_pair.debug.key_name
  iam_instance_profile   = aws_iam_instance_profile.instance.name
  # Public IPv4 is provided via the Elastic IP below.
  associate_public_ip_address = true

  root_block_device {
    volume_size = 20    # Increase from 8GB to 20GB
    volume_type = "gp3" # General Purpose SSD
  }

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    aws_region          = var.aws_region
    ecr_registry        = local.ecr_registry
    app_image           = "${local.ecr_registry}/${aws_ecr_repository.app.name}:${var.image_tag}"
    web_image           = "${local.ecr_registry}/${aws_ecr_repository.web.name}:${var.image_tag}"
    sqs_queue_url       = var.app_sqs_queue_url
    ddb_table           = var.app_ddb_table_name
    street_graph_bucket = var.street_graph_bucket
    osm_graph_s3_uri    = var.osm_graph_s3_uri
  })

  tags = {
    Name    = "${local.name_prefix}-compute"
    Project = var.project
  }
}

# Stable public IPv4 without ALB.
# Managed by Terraform so it is released on `terraform destroy`.
resource "aws_eip" "urbanpath" {
  domain = "vpc"

  tags = {
    Name    = "${local.name_prefix}-eip"
    Project = var.project
  }
}

resource "aws_eip_association" "urbanpath" {
  allocation_id = aws_eip.urbanpath.id
  instance_id   = aws_instance.urbanpath.id
}
