output "queue_url" {
  value = aws_sqs_queue.route_requests.url
}

output "queue_arn" {
  value = aws_sqs_queue.route_requests.arn
}
