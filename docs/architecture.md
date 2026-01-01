# UrbanPath — Documentación de arquitectura (Aplicación y Tecnología)

Esta documentación está orientada a “frameworks de arquitecturas empresariales” (visión por capas):

- **Nivel Aplicación**: componentes lógicos, responsabilidades, contratos.
- **Nivel Tecnología**: infraestructura, runtime, servicios cloud (AWS/LocalStack) y despliegue.

## Nivel Aplicación

### Objetivo

Calcular rutas multimodales combinando:
- **Caminar** por red viaria (OSM) y
- **Transporte público** (GTFS de guaguas), dependiente de hora (`depart_at`).

### Estilo

- **Arquitectura Hexagonal** (Ports & Adapters)
  - Dominio puro: sin dependencias de infraestructura.
  - Casos de uso orquestan puertos.
  - Adaptadores implementan puertos (AWS, mapas, API).

### Componentes principales

- **API (FastAPI)**
  - Expone endpoints de cálculo síncrono y asíncrono.

- **Servicios de aplicación**
  - `MultimodalRoutingService`: orquesta repositorio GTFS + proveedor de mapa.
  - `RouteJobsService`: patrón job asíncrono (submit + get).

- **Dominio**
  - Modelos: `GeoPoint`, `Route`, `RouteLeg`, `Stop`, etc.
  - Algoritmos: CSA (Connection Scan Algorithm) para earliest arrival.

### Flujos

**Síncrono**
1) API recibe `origin/destination/depart_at/preference`
2) `MultimodalRoutingService.calculate_route`
3) Devuelve `Route` (legs walk/bus)

**Asíncrono**
1) API recibe request
2) `RouteJobsService.submit`:
   - guarda `PENDING` en DynamoDB
   - publica mensaje en SQS con `request_id`
3) Worker consume SQS, calcula ruta y actualiza DynamoDB (`SUCCESS`/`ERROR`)
4) API permite polling por `request_id`

## Nivel Tecnología

### Runtime

- Python 3.12
- Gestión de dependencias: `uv`
- Contenedores: Docker

### Servicios cloud (AWS / LocalStack)

- **S3**
  - bucket de artefactos/grafos
  - bucket de caché de grafos OSM (`STREET_GRAPH_BUCKET`)

- **SQS**
  - cola de jobs de routing (`SQS_QUEUE_URL`)

- **DynamoDB**
  - tabla de resultados de jobs (`DDB_TABLE`) con clave `request_id`

### Entorno simulado

- LocalStack para desarrollo local y CI.
- Configuración preferente de boto3: `ENDPOINT_URL`.

### Infra como código

- Terraform en [infra/](../infra)
  - módulos: `storage` (S3), `messaging` (SQS), `database` (DynamoDB)
  - provider preparado para LocalStack (endpoints por servicio)

### Demo web

- SPA estática (Leaflet + OSM tiles) para probar UrbanPath de forma “tipo maps”.
- Reverse proxy Nginx para evitar problemas de CORS y exponer `/api/*`.

## Riesgos / Limitaciones (MVP)

- La web dibuja una línea directa (no geometría real de la ruta), porque el backend no expone polyline/shape todavía.
- Routing transit es un MVP (CSA) y la integración walk+bus está simplificada.
