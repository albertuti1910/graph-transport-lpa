# Repo hygiene (qué sobra / qué falta)

Este documento resume el estado del repositorio y qué piezas son “core” vs placeholders/legacy.

## Core (usado hoy)

- API FastAPI: `src/main.py` + `src/adapters/api/**`
- Worker async: `src/worker.py`
- Routing multimodal: `src/app/services/multimodal_routing_service.py`
- Adaptadores runtime:
  - GTFS local: `src/adapters/persistence/local_gtfs_repository.py`
  - SQS/DynamoDB (async): `src/adapters/messaging/sqs_queue_adapter.py`, `src/adapters/persistence/dynamodb_route_result_repository.py`
  - Street graph OSM: `src/adapters/maps/osmnx_map_adapter.py` (+ cache: `src/adapters/maps/s3_cached_map_adapter.py`)
- Demo web (Leaflet + Nginx): `web/` + `docker-compose.demo.yml`
- LocalStack init (crea buckets/cola/tabla): `localstack/init/**`
- Infra base Terraform (S3/SQS/DynamoDB): `infra/`

## Placeholder / carpetas vacías detectadas

Estas carpetas están vacías hoy y no afectan al runtime:

- `src/app/dtos/`
- `src/app/ports/input/`
- `src/common/`
- `tests/e2e/`
- `tests/load/data/`
- `infra/envs/dev/`, `infra/envs/prod/`
- `infra/modules/compute/`, `infra/modules/networking/`

Recomendación: o bien eliminarlas, o dejar un README pequeño explicando que son scaffolding del curso.

## Legacy (probable código no usado)

Hay un “camino antiguo” basado en `IGraphRepository` que no se usa en la demo actual (multimodal + OSM+GTFS):

- `src/app/services/routing_service.py`
- `src/app/ports/output/graph_repository.py`
- `src/adapters/persistence/s3_graph_repository.py`

Recomendación: si ya no vas a usar el enfoque de “grafo único”, puedes borrarlo para reducir confusión.
Si quieres mantenerlo, conviene documentarlo como legacy y no re-exportarlo desde `src/app/ports/output/__init__.py`.

## Infra vs demo

- La demo (`docker-compose.demo.yml`) levanta TODO local (LocalStack + API + worker + web).
- Terraform (`infra/`) hoy solo cubre recursos “managed” (S3/SQS/DynamoDB).
- Para un deploy real faltan módulos de compute/networking (hoy están vacíos).

## Chequeos rápidos

- Carpetas vacías:
  - `find . -type d -empty`
- Módulos legacy referenciados:
  - `grep -RIn 'IGraphRepository|S3GraphRepository|routing_service' src`
