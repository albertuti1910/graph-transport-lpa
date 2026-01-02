variable "project" {
  type        = string
  description = "Project name/prefix used for resource naming."
}

variable "aws_region" {
  type        = string
  description = "AWS region."
}

variable "app_sqs_queue_url" {
  type        = string
  description = "SQS queue URL used by the API/worker."
}

variable "app_ddb_table_name" {
  type        = string
  description = "DynamoDB table name used by the API/worker."
}

variable "street_graph_bucket" {
  type        = string
  description = "S3 bucket name used for street graph cache."
}

variable "osm_graph_s3_uri" {
  type        = string
  description = "s3://bucket/key for the prebuilt OSM graph (GraphML)."
}

variable "instance_type" {
  type        = string
  description = "EC2 instance type (cost driver)."
  default     = "t3.micro"
}

variable "image_tag" {
  type        = string
  description = "Docker image tag to deploy (e.g. latest, v1)."
  default     = "latest"
}

variable "allow_http_cidr" {
  type        = string
  description = "CIDR allowed to access port 80."
  default     = "0.0.0.0/0"
}
