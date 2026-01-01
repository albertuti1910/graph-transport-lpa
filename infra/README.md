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

## Qué es placeholder

Estos módulos/envs están vacíos hoy:

- `infra/modules/compute`
- `infra/modules/networking`
- `infra/envs/dev`
- `infra/envs/prod`

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
