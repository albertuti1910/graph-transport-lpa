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

provider "aws" {
  region = var.aws_region

  access_key = var.use_localstack ? "test" : null
  secret_key = var.use_localstack ? "test" : null

  s3_use_path_style           = var.use_localstack
  skip_credentials_validation = var.use_localstack
  skip_metadata_api_check     = var.use_localstack
  skip_requesting_account_id  = var.use_localstack

  endpoints {
    s3  = var.use_localstack ? var.localstack_endpoint : null
    sqs = var.use_localstack ? var.localstack_endpoint : null
    dynamodb = var.use_localstack ? var.localstack_endpoint : null
  }
}
