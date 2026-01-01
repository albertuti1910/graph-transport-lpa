output "table_name" {
  value = aws_dynamodb_table.route_results.name
}

output "table_arn" {
  value = aws_dynamodb_table.route_results.arn
}
