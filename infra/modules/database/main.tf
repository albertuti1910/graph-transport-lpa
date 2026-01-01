variable "table_name" {
  type        = string
  description = "DynamoDB table name for storing route job results."
}

variable "tags" {
  type        = map(string)
  description = "Tags to apply to resources."
  default     = {}
}

resource "aws_dynamodb_table" "route_results" {
  name         = var.table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "request_id"

  attribute {
    name = "request_id"
    type = "S"
  }

  tags = var.tags
}
