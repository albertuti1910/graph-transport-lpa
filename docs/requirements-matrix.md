# Matriz de requisitos (enunciado → evidencia en el repo)

Este documento mapea el enunciado del trabajo a **dónde se cumple** dentro del proyecto.

## Enunciado → dónde se cumple

| Requisito del enunciado | Evidencia / dónde verlo |
|---|---|
| Proyecto práctico (individual o en pareja) usando computación en la nube | Repositorio completo + demo local y opción AWS descritas en [README.md](../README.md) |
| Programar en Python/Java/otro lenguaje | Implementación en **Python 3.12** (API + worker) en `src/` y tests en `tests/` |
| Uso de AWS o LocalStack como entorno simulado | LocalStack en `docker-compose.demo.yml` / `docker-compose.yml`; AWS real vía Terraform en `infra/` |
| Uso de servicios AWS (ejemplos: EC2, S3, Lambda, …) o su alternativa en LocalStack | **S3 + SQS + DynamoDB** (AWS/LocalStack) + opción **EC2** (AWS) en `infra/modules/compute` |
| Configuración de recursos en la nube | Terraform: `infra/main.tf` + módulos `infra/modules/*` + `terraform validate` (ver [infra/README.md](../infra/README.md)) |
| Buenas prácticas de diseño arquitectónico | Arquitectura hexagonal (Ports & Adapters): `src/app` + `src/domain` + `src/adapters` (ver [docs/architecture.md](architecture.md)) |
| Documentación desde frameworks de arquitecturas empresariales (niveles aplicación y tecnología) | Documento por niveles en [docs/architecture.md](architecture.md) |
| Entendimiento claro de estructura tecnológica y de aplicación | Estructura del repo en [docs/repo-hygiene.md](repo-hygiene.md) + diagrama/flujo en [docs/architecture.md](architecture.md) |
| Demostración del sistema (funciona) | Demo web local (`docker-compose.demo.yml`) y deploy AWS barato (`scripts/aws_deploy.sh`) descritos en [README.md](../README.md) |
