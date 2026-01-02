# Infra (Terraform)

Este directorio define la **infra base** para UrbanPath.

## Qué está implementado

En `infra/main.tf` se crean (en AWS o LocalStack):

- 2 buckets S3:
  - `${project}-graphs`
  - `${project}-street-graphs`
- 1 cola SQS:
  - `${project}-route-requests`
- 1 tabla DynamoDB:
  - `${project}-route-results`

Módulos implementados:

- `infra/modules/storage`
- `infra/modules/messaging`
- `infra/modules/database`
- `infra/modules/compute` (runtime en EC2 + ECR + SSM)

## Alcance

Esta carpeta cubre **recursos gestionados** (S3/SQS/DynamoDB) y, de forma opcional, un runtime basado en una única instancia EC2.

No se crea VPC/ALB: se usa la VPC por defecto y se expone HTTP (puerto 80) directamente en la instancia.

## Relación con la demo

La demo local usa `docker-compose.demo.yml` + LocalStack y crea recursos vía scripts de init.
Terraform sirve para validar “infra as code” y preparar un sandbox AWS real.

## Próximos pasos para un deploy real

Según el servicio objetivo (ECS/EC2/Kubernetes), normalmente harías:

- networking (VPC/subnets/SG)
- compute (ECS service + task definitions para `api` y `worker`)
- exposición (ALB/API Gateway) y/o hosting estático para `web`
- IAM roles y policy mínima
- artifact del grafo OSM prebuilt en S3 + env vars (`OSM_GRAPH_S3_URI`, `OSM_GRAPH_AUTO_BUILD=0`)

## Deploy AWS automático (EC2 + Docker Compose)

Este repo incluye un camino mínimo para desplegar el stack (web + api + worker) en **una sola EC2**:

- ECR para imágenes `urbanpath-app` y `urbanpath-web`
- EC2 Amazon Linux 2023 con:
  - Docker + Compose plugin
  - SSM (sin SSH)
  - un servicio systemd (`urbanpath.service`) que hace `docker compose pull && up -d`

Variables Terraform:

- `use_localstack=false`
- `enable_compute=true`
- `osm_graph_s3_uri=s3://<bucket>/<key>` (recomendado: grafo prebuilt fijo)
- opcional: `compute_instance_type` (default `t3.micro`)

Script de despliegue (build + push + restart):

```bash
export AWS_REGION=eu-west-1
export IMAGE_TAG=latest
export OSM_GRAPH_S3_URI=s3://<bucket>/<key>
./scripts/aws_deploy.sh
```

## Teardown y costes (AWS)

Cost drivers principales:

- **EC2**: coste fijo mientras la instancia esté encendida (principal driver).
- **EBS**: volumen de la instancia (normalmente pequeño, pero existe).
- **S3/SQS/DynamoDB**: coste por uso (habitualmente bajo en sandbox).

Para evitar costes, destruye lo creado por Terraform:

```bash
terraform destroy -auto-approve \
  -var="use_localstack=false" \
  -var="aws_region=eu-west-1" \
  -var="enable_compute=true"
```
