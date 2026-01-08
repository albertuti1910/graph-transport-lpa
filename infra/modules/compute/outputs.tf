output "app_ecr_repository_url" {
  value       = aws_ecr_repository.app.repository_url
  description = "ECR repository URL for the UrbanPath app image."
}

output "web_ecr_repository_url" {
  value       = aws_ecr_repository.web.repository_url
  description = "ECR repository URL for the UrbanPath web image."
}

output "instance_id" {
  value       = aws_instance.urbanpath.id
  description = "EC2 instance id running the stack."
}

output "public_ip" {
  value       = aws_eip.urbanpath.public_ip
  description = "Elastic IP (stable public IPv4; HTTP on port 80)."
}
