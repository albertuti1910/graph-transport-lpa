locals {
  project = "urbanpath"
}

module "storage" {
  source = "./modules/storage"

  bucket_name   = "${local.project}-graphs"
  force_destroy = var.use_localstack

  tags = {
    Project = local.project
    Env     = var.use_localstack ? "local" : "aws"
  }
}

module "street_graph_cache" {
  source = "./modules/storage"

  bucket_name   = "${local.project}-street-graphs"
  force_destroy = var.use_localstack

  tags = {
    Project = local.project
    Env     = var.use_localstack ? "local" : "aws"
  }
}

module "messaging" {
  source = "./modules/messaging"

  queue_name = "${local.project}-route-requests"

  tags = {
    Project = local.project
    Env     = var.use_localstack ? "local" : "aws"
  }
}

module "database" {
  source = "./modules/database"

  table_name = "${local.project}-route-results"

  tags = {
    Project = local.project
    Env     = var.use_localstack ? "local" : "aws"
  }
}

module "compute" {
  source = "./modules/compute"
  count  = var.enable_compute && !var.use_localstack ? 1 : 0

  project = local.project

  aws_region          = var.aws_region
  app_sqs_queue_url   = module.messaging.queue_url
  app_ddb_table_name  = module.database.table_name
  street_graph_bucket = module.street_graph_cache.bucket_name

  osm_graph_s3_uri = var.osm_graph_s3_uri

  instance_type    = var.compute_instance_type
  image_tag        = var.compute_image_tag
  allow_http_cidr  = var.compute_allow_http_cidr
}

output "s3_bucket_name" {
  value = module.storage.bucket_name
}

output "street_graph_bucket_name" {
  value = module.street_graph_cache.bucket_name
}

output "sqs_queue_url" {
  value = module.messaging.queue_url
}

output "dynamodb_table_name" {
  value = module.database.table_name
}

output "compute_public_ip" {
  value       = try(module.compute[0].public_ip, null)
  description = "Public IPv4 of the EC2 instance (if enable_compute=true)."
}

output "compute_instance_id" {
  value       = try(module.compute[0].instance_id, null)
  description = "Instance id (if enable_compute=true)."
}

output "app_ecr_repository_url" {
  value       = try(module.compute[0].app_ecr_repository_url, null)
  description = "ECR repo URL for app image (if enable_compute=true)."
}

output "web_ecr_repository_url" {
  value       = try(module.compute[0].web_ecr_repository_url, null)
  description = "ECR repo URL for web image (if enable_compute=true)."
}
