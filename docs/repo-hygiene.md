# Estructura del repositorio

Este documento describe cómo está organizado el proyecto **según el código actual**.

## Piezas principales

- API FastAPI: `src/main.py` + `src/adapters/api/**`
- Worker de jobs: `src/worker.py`
- Casos de uso:
  - `MultimodalRoutingService` (ruta síncrona): `src/app/services/multimodal_routing_service.py`
  - `RouteJobsService` (submit + polling async): `src/app/services/route_jobs_service.py`
- Adaptadores (Ports & Adapters):
  - GTFS local: `src/adapters/persistence/local_gtfs_repository.py`
  - SQS: `src/adapters/messaging/sqs_queue_adapter.py`
  - DynamoDB: `src/adapters/persistence/dynamodb_route_result_repository.py`
  - OSM street graph (OSMnx): `src/adapters/maps/osmnx_map_adapter.py`
  - Caché de grafos OSM en S3: `src/adapters/maps/s3_cached_map_adapter.py`

## Documentación

- Arquitectura (niveles aplicación y tecnología): `docs/architecture.md`
- Matriz de requisitos (enunciado → evidencia): `docs/requirements-matrix.md`

## Entornos

- Demo local (UI + backend + worker + LocalStack): `docker-compose.yml` (perfil `demo`) + `web/`
- LocalStack “solo infra” (útil para CI/integración): `docker-compose.yml` (sin perfil)
- Infra como código (S3/SQS/DynamoDB): `infra/`
- Deploy AWS (build/push + restart vía SSM): `scripts/aws_deploy.sh`
- Compose de referencia para AWS (sin LocalStack): `docker-compose.aws.yml`

## Chequeos rápidos

- Test suite:
  - `uv run pytest -q`
- Validación Terraform (sin backend):
  - `cd infra && terraform init -backend=false && terraform validate`
