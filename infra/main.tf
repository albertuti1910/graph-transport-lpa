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
