variable "bucket_name" {
  type        = string
  description = "S3 bucket name for storing graphs/artifacts."
}

variable "force_destroy" {
  type        = bool
  description = "Whether to allow bucket deletion even if it contains objects (useful for LocalStack/dev)."
  default     = false
}

variable "tags" {
  type        = map(string)
  description = "Tags to apply to resources."
  default     = {}
}

resource "aws_s3_bucket" "graphs" {
  bucket        = var.bucket_name
  force_destroy = var.force_destroy
  tags          = var.tags
}

# Cost-conscious defaults: no versioning, no replication, no logging.
