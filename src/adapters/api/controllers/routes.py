from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from src.adapters.api.dependencies import get_route_jobs_service, get_routing_service
from src.adapters.api.schemas.routes import (
    EnqueueResponseSchema,
    GeoPointSchema,
    RouteJobStatusSchema,
    RouteLegSchema,
    RouteRequestSchema,
    RouteSchema,
    TransitLineSchema,
)
from src.app.services.multimodal_routing_service import MultimodalRoutingService
from src.app.services.route_jobs_service import RouteJobsService
from src.domain.models import GeoPoint

router = APIRouter(tags=["routes"])


def _route_to_schema(route) -> RouteSchema:
    return RouteSchema(
        origin=GeoPointSchema(lat=route.origin.lat, lon=route.origin.lon),
        destination=GeoPointSchema(
            lat=route.destination.lat, lon=route.destination.lon
        ),
        legs=[
            RouteLegSchema(
                mode=leg.mode.value,
                origin=GeoPointSchema(lat=leg.origin.lat, lon=leg.origin.lon),
                destination=GeoPointSchema(
                    lat=leg.destination.lat, lon=leg.destination.lon
                ),
                origin_name=getattr(leg, "origin_name", None),
                destination_name=getattr(leg, "destination_name", None),
                origin_stop_id=getattr(leg, "origin_stop_id", None),
                destination_stop_id=getattr(leg, "destination_stop_id", None),
                depart_at=getattr(leg, "depart_at", None),
                arrive_at=getattr(leg, "arrive_at", None),
                distance_m=leg.distance_m,
                duration_s=leg.duration_s,
                path=(
                    [GeoPointSchema(lat=p.lat, lon=p.lon) for p in leg.path]
                    if getattr(leg, "path", None)
                    else None
                ),
                line=(
                    TransitLineSchema(
                        route_id=leg.line.route_id,
                        short_name=leg.line.short_name,
                        long_name=leg.line.long_name,
                        color=leg.line.color,
                        text_color=leg.line.text_color,
                    )
                    if getattr(leg, "line", None)
                    else None
                ),
                trip_id=getattr(leg, "trip_id", None),
            )
            for leg in route.legs
        ],
        total_distance_m=route.total_distance_m,
        total_duration_s=route.total_duration_s,
    )


@router.post("/routes", response_model=RouteSchema)
def calculate_route(
    req: RouteRequestSchema,
    service: MultimodalRoutingService = Depends(get_routing_service),
) -> RouteSchema:
    origin = GeoPoint(lat=req.origin.lat, lon=req.origin.lon)
    destination = GeoPoint(lat=req.destination.lat, lon=req.destination.lon)
    depart_at = req.depart_at or datetime.now()
    route = service.calculate_route(
        origin=origin,
        destination=destination,
        depart_at=depart_at,
        preference=req.preference,
    )
    return _route_to_schema(route)


@router.post("/routes/async", response_model=EnqueueResponseSchema)
def enqueue_route(
    req: RouteRequestSchema,
    service: RouteJobsService = Depends(get_route_jobs_service),
) -> EnqueueResponseSchema:
    origin = GeoPoint(lat=req.origin.lat, lon=req.origin.lon)
    destination = GeoPoint(lat=req.destination.lat, lon=req.destination.lon)
    depart_at = req.depart_at or datetime.now()
    request_id = service.submit(
        origin=origin,
        destination=destination,
        depart_at=depart_at,
        preference=req.preference,
    )
    return EnqueueResponseSchema(request_id=request_id)


@router.get("/routes/jobs/{request_id}", response_model=RouteJobStatusSchema)
def get_route_job(
    request_id: str,
    service: RouteJobsService = Depends(get_route_jobs_service),
) -> RouteJobStatusSchema:
    job = service.get(request_id=request_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return RouteJobStatusSchema(**dict(job))
