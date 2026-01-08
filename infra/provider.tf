terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

variable "use_localstack" {
  type        = bool
  description = "Whether to target LocalStack instead of AWS."
  default     = true
}

variable "aws_region" {
  type        = string
  description = "AWS region (also used for LocalStack)."
  default     = "eu-west-1"
}

variable "localstack_endpoint" {
  type        = string
  description = "Base URL for LocalStack (e.g. http://localhost:4566)."
  default     = "http://localhost:4566"
}

variable "enable_compute" {
  type        = bool
  description = "Whether to provision a cheap EC2-based runtime (ECR + EC2 + SSM) for AWS."
  default     = false
}

variable "compute_instance_type" {
  type        = string
  description = "EC2 instance type for the runtime (cost driver)."
  default     = "t3.micro"
}

variable "compute_image_tag" {
  type        = string
  description = "Docker image tag to deploy to the instance."
  default     = "latest"
}

variable "compute_allow_http_cidr" {
  type        = string
  description = "CIDR allowed to access the demo (port 80)."
  default     = "0.0.0.0/0"
}

variable "osm_graph_s3_uri" {
  type        = string
  description = "s3://bucket/key for the prebuilt OSM graph used in AWS runtime (set OSM_GRAPH_AUTO_BUILD=0)."
  default     = ""
}

provider "aws" {
  region = var.aws_region

  access_key = var.use_localstack ? "test" : null
  secret_key = var.use_localstack ? "test" : null

  s3_use_path_style           = var.use_localstack
  skip_credentials_validation = var.use_localstack
  skip_metadata_api_check     = var.use_localstack
  skip_requesting_account_id  = var.use_localstack

  endpoints {
    s3       = var.use_localstack ? var.localstack_endpoint : null
    sqs      = var.use_localstack ? var.localstack_endpoint : null
    dynamodb = var.use_localstack ? var.localstack_endpoint : null
  }
}
