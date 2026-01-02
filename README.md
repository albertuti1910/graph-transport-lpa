# UrbanPath (graph-transport-lpa)

Proyecto de curso: cálculo de rutas multimodal (caminar + guagua/GTFS) para Las Palmas de Gran Canaria, usando AWS o LocalStack.

## Qué pide el profesor y cómo se cubre

- **Uso de nube (AWS o LocalStack):** se usan **S3 + SQS + DynamoDB** (y LocalStack para desarrollo/CI).
- **Programación y buenas prácticas:** Python 3.12, `uv`, tests, lint/typecheck, arquitectura hexagonal.
- **Documentación (niveles aplicación y tecnología):** ver [docs/architecture.md](docs/architecture.md).
- **Configuración de recursos cloud:** Terraform en [infra/](infra/), módulos para S3/SQS/DynamoDB.

## Arquitectura (resumen)

- **Dominio**: modelos + algoritmos (CSA para GTFS, utilidades geo).
- **Aplicación (casos de uso)**:
  - `MultimodalRoutingService`: calcula ruta síncrona.
  - `RouteJobsService`: encola job (SQS) y registra estado (DynamoDB).
- **Adaptadores**:
  - API FastAPI.
  - S3 cache (`S3CachedMapAdapter`) para grafos OSM.
  - SQS para colas.
  - DynamoDB para resultados de jobs.

## Endpoints

- `POST /routes`: calcula ruta en el acto.
- `POST /routes/async`: encola cálculo y devuelve `request_id`.
- `GET /routes/jobs/{request_id}`: consulta estado y resultado.
- `GET /health`

## Demo local (tipo “Google Maps”)

Requisitos: Docker + Docker Compose.

1) Levanta stack completo (LocalStack + API + worker + web):

```bash
docker compose -f docker-compose.demo.yml up --build
```

2) Abre la web demo:

- http://localhost:8080

3) Flujo async:

- Click en el mapa para origen y destino
- `Calcular async` → copia el `request_id`
- `Consultar` hasta ver `SUCCESS`

Notas:
- LocalStack se configura por `ENDPOINT_URL` (prioritario).
- Los recursos (bucket/cola/tabla) se crean automáticamente vía `localstack/init/ready.d/01-init-urbanpath.sh`.

### Acelerar el cálculo (grafo OSM preconstruido)

Construir el grafo OSM (walking) es lo que más tarda en “cold start”. La demo está configurada para:

- Generar un grafo completo de Las Palmas **una sola vez**.
- Reutilizar ese mismo grafo en siguientes arranques (mucho más rápido).

En la demo actual, el fichero prebuilt se guarda en un **volumen Docker nombrado** (`osm-prebuilt`), no en `./data/`.

Variables usadas en `docker-compose.demo.yml`:

- `OSM_GRAPH_PATH=/app/osm_prebuilt/lpa_walk.graphml`
- `OSM_GRAPH_AUTO_BUILD=1`
- `OSM_PLACE=Las Palmas de Gran Canaria, Canary Islands, Spain`

Si quieres forzar regeneración, borra el volumen y reinicia el stack:

```bash
docker compose -f docker-compose.demo.yml down
docker volume rm graph-transport-lpa_osm-prebuilt graph-transport-lpa_osm-cache
docker compose -f docker-compose.demo.yml up -d --build
```

Nota: si tu proyecto de Compose no se llama `graph-transport-lpa`, lista los volúmenes con `docker volume ls | grep osm-prebuilt` y borra el que corresponda.

Para inspeccionar el volumen:

```bash
docker compose -f docker-compose.demo.yml exec api sh -lc 'ls -lah /app/osm_prebuilt'
```

### AWS: usar un grafo fijo en S3 (sin reconstruir)

Para un sandbox AWS es recomendable guardar el grafo preconstruido como artefacto y **solo descargarlo**:

1) Genera una vez el fichero (local o en una máquina de build) y súbelo a S3.
2) En el runtime (ECS/EC2), configura:

- `OSM_GRAPH_PATH=/app/osm_prebuilt/lpa_walk.graphml`
- `OSM_GRAPH_S3_URI=s3://<bucket>/<key>`
- `OSM_GRAPH_AUTO_BUILD=0` (para garantizar que nunca se reconstruye desde Overpass)

Con eso, al arrancar el contenedor se descarga el fichero si falta y luego solo se carga.

## Desarrollo (sin Docker)

- Instala dependencias:

```bash
uv sync --group dev
```

- Tests y calidad:

```bash
uv run ruff check .
uv run mypy src
uv run pytest
```

## Terraform

- Validación local:

```bash
cd infra
terraform init -backend=false
terraform validate
```

Outputs esperados:
- `s3_bucket_name`
- `street_graph_bucket_name`
- `sqs_queue_url`
- `dynamodb_table_name`

Notas:
- `docker-compose.yml` levanta solo LocalStack (útil para CI/tests).
- `docker-compose.demo.yml` levanta el stack completo (LocalStack + API + worker + web).
- Para más detalle de infra, ver [infra/README.md](infra/README.md).

## Mantenimiento del repo

Checklist de higiene del repo: [docs/repo-hygiene.md](docs/repo-hygiene.md)

## Sandbox AWS (mínimo viable)

Este repo deja lista la **infra base** (S3/SQS/DynamoDB) vía Terraform. Para desplegar API/worker y la web en AWS hay varias opciones (ECS/EC2).

Si quieres que lo dejemos automatizado (ECS + ALB + S3 estático), dime qué restricción de coste/servicio te pone el profesor y lo implemento.
