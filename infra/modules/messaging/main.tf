variable "queue_name" {
  type        = string
  description = "SQS queue name for route calculation requests."
}

variable "tags" {
  type        = map(string)
  description = "Tags to apply to resources."
  default     = {}
}

resource "aws_sqs_queue" "route_requests" {
  name = var.queue_name

  # Free-tier friendly settings (defaults are already conservative)
  visibility_timeout_seconds = 30
  message_retention_seconds  = 86400

  tags = var.tags
}
