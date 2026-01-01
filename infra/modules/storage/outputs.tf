output "bucket_name" {
  value = aws_s3_bucket.graphs.bucket
}

output "bucket_arn" {
  value = aws_s3_bucket.graphs.arn
}
