from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from src.adapters.api.dependencies import get_realtime_view_service
from src.adapters.api.schemas.realtime import (
    RouteShapeSchema,
    TransitRouteSchema,
    VehicleSchema,
    VehiclesResponseSchema,
)
from src.adapters.api.schemas.routes import GeoPointSchema
from src.app.services.realtime_view_service import RealtimeViewService

router = APIRouter(prefix="/realtime", tags=["realtime"])


@router.get("/routes", response_model=list[TransitRouteSchema])
def list_routes(
    service: RealtimeViewService = Depends(get_realtime_view_service),
) -> list[TransitRouteSchema]:
    return [
        TransitRouteSchema(
            route_id=r.route_id,
            short_name=r.short_name,
            long_name=r.long_name,
            color=r.color,
            text_color=r.text_color,
        )
        for r in service.list_routes()
    ]


@router.get("/routes/{route_id}/shape", response_model=RouteShapeSchema)
def get_route_shape(
    route_id: str,
    service: RealtimeViewService = Depends(get_realtime_view_service),
) -> RouteShapeSchema:
    pts = service.route_shape(route_id=route_id)
    return RouteShapeSchema(
        route_id=route_id,
        points=[GeoPointSchema(lat=p.lat, lon=p.lon) for p in pts],
    )


@router.get("/vehicles", response_model=VehiclesResponseSchema)
async def list_vehicles(
    route_id: list[str] | None = Query(default=None),
    service: RealtimeViewService = Depends(get_realtime_view_service),
) -> VehiclesResponseSchema:
    route_ids = set(route_id) if route_id else None

    # Best-effort cache hint: if the provider is configured with caching, this will reduce upstream calls.
    # We don't know if the response was cached, so we expose `is_cached` as false by default.
    vehicles = await service.list_vehicles(route_ids=route_ids)

    return VehiclesResponseSchema(
        fetched_at=datetime.now(timezone.utc),
        is_cached=False,
        vehicles=[
            VehicleSchema(
                vehicle_id=v.vehicle_id,
                trip_id=v.trip_id,
                route_id=v.route_id,
                lat=v.lat,
                lon=v.lon,
                bearing=v.bearing,
                speed_mps=v.speed_mps,
                timestamp=v.timestamp,
                stop_id=v.stop_id,
            )
            for v in vehicles
        ],
    )
