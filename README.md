# UrbanPath (graph-transport-lpa)

Proyecto de cálculo de rutas multimodal (caminar + guagua/GTFS) para Las Palmas de Gran Canaria, usando AWS o LocalStack.

## Requisitos del trabajo y cómo se cubre

- **Uso de nube (AWS o LocalStack):** se usan **S3 + SQS + DynamoDB** (y LocalStack para desarrollo/CI).
- **Documentación de arquitectura empresarial:** ver [docs/architecture.md](docs/architecture.md).
- **Matriz de requisitos del enunciado:** ver [docs/requirements-matrix.md](docs/requirements-matrix.md).
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
docker compose --profile demo up --build
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

Variables usadas en `docker-compose.yml` (perfil `demo`):

- `OSM_GRAPH_PATH=/app/osm_prebuilt/lpa_walk.graphml`
- `OSM_GRAPH_AUTO_BUILD=1`
- `OSM_PLACE=Las Palmas de Gran Canaria, Canary Islands, Spain`

Si quieres forzar regeneración, borra el volumen y reinicia el stack:

```bash
docker compose --profile demo down
docker volume rm graph-transport-lpa_osm-prebuilt graph-transport-lpa_osm-cache
docker compose --profile demo up -d --build
```

Para inspeccionar el volumen:

```bash
docker compose --profile demo exec api sh -lc 'ls -lah /app/osm_prebuilt'
```

### AWS: usar un grafo fijo en S3 (sin reconstruir)

Para un sandbox AWS es recomendable guardar el grafo preconstruido como artefacto y **solo descargarlo**:

1) Genera una vez el fichero (local o en una máquina de build) y súbelo a S3.
2) En el runtime (ECS/EC2), configura:

- `OSM_GRAPH_PATH=/app/osm_prebuilt/lpa_walk.graphml`
- `OSM_GRAPH_S3_URI=s3://<bucket>/<key>`
- `OSM_GRAPH_AUTO_BUILD=0` (para garantizar que nunca se reconstruye desde Overpass)

Con eso, al arrancar el contenedor se descarga el fichero si falta y luego solo se carga.

### AWS: deploy automático (EC2 + ECR + SSM)

Para un despliegue mínimo el repo incluye una opción en la que **todo corre en una sola EC2** (web + api + worker), con imágenes en ECR y gestión por SSM (sin SSH).

Requisito: tener un grafo prebuilt en S3 (no se construye en runtime).

1) Sube el grafo prebuilt a S3 (ejemplo):

```bash
aws s3 cp ./lpa_walk.graphml s3://<bucket>/<key>
```

2) Despliega (Terraform + build/push + restart):

```bash
export AWS_REGION=eu-west-1
export IMAGE_TAG=latest
export OSM_GRAPH_S3_URI=s3://<bucket>/<key>
chmod +x ./scripts/aws_deploy.sh
./scripts/aws_deploy.sh
```

3) Obtén la IP pública:

```bash
cd infra
terraform output -raw compute_public_ip
```

4) Abre la demo en:

- `http://<ip>/`

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
- `docker-compose.yml` por defecto levanta solo LocalStack (útil para CI/tests).
- Para demo local usa el perfil `demo` (levanta LocalStack + API + worker + web).
- `docker-compose.aws.yml` se usa para runtime en AWS (sin LocalStack).
- Para más detalle de infra, ver [infra/README.md](infra/README.md).

## Sandbox AWS (mínimo viable)

Este repo deja lista la **infra base** (S3/SQS/DynamoDB) vía Terraform y una opción opcional de runtime en EC2 (ver sección anterior y [infra/README.md](infra/README.md)).

## Teardown y costes

### LocalStack / demo local

Parar contenedores:

```bash
docker compose --profile demo down
```

Borrar volúmenes (borra cachés del grafo OSM y el prebuilt):

```bash
docker volume rm graph-transport-lpa_osm-prebuilt graph-transport-lpa_osm-cache
```

### AWS

Cost drivers principales:

- **EC2** (si `enable_compute=true`): es lo que más cuesta de forma continua.
- **S3/SQS/DynamoDB**: normalmente bajo coste en sandbox (más “pay per use”).

Apagar y evitar costes:

```bash
cd infra
terraform destroy -auto-approve -var="use_localstack=false" -var="aws_region=eu-west-1" -var="enable_compute=true"
```

## Autores
+ Alberto Rivero Monzón
+ Mariana Bordes Bueno

Este proyecto fue realizado para la asignatura de "Tecnologías de Servicios para Ciencia de Datos" del Grado en Ingeniería y Ciencia de Datos de la Universidad de Las Palmas de Gran Canaria (ULPGC).
