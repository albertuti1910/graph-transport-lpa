from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from src.adapters.api.dependencies import get_realtime_view_service
from src.adapters.api.schemas.realtime import (
    RouteShapeSchema,
    RouteShapesSchema,
    StopSchema,
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


@router.get("/routes/{route_id}/shape", response_model=RouteShapesSchema)
def get_route_shape(
    route_id: str,
    service: RealtimeViewService = Depends(get_realtime_view_service),
) -> RouteShapesSchema:
    shapes = service.route_shapes(route_id=route_id, max_shapes=2)
    return RouteShapesSchema(
        route_id=route_id,
        shapes=[
            RouteShapeSchema(
                shape_id=shape_id,
                points=[GeoPointSchema(lat=p.lat, lon=p.lon) for p in pts],
            )
            for (shape_id, pts) in shapes
        ],
    )


@router.get("/routes/{route_id}/stops", response_model=list[StopSchema])
def get_route_stops(
    route_id: str,
    service: RealtimeViewService = Depends(get_realtime_view_service),
) -> list[StopSchema]:
    stops = service.route_stops(route_id=route_id)
    return [
        StopSchema(
            stop_id=sid,
            name=name,
            location=GeoPointSchema(lat=loc.lat, lon=loc.lon),
        )
        for (sid, name, loc) in stops
    ]


@router.get("/vehicles", response_model=VehiclesResponseSchema)
async def list_vehicles(
    route_id: list[str] = Query(default=[]),
    service: RealtimeViewService = Depends(get_realtime_view_service),
) -> VehiclesResponseSchema:
    route_ids = set(route_id) or None
    vehicles = await service.list_vehicles(route_ids=route_ids)

    fetched_at = datetime.now(tz=timezone.utc)
    return VehiclesResponseSchema(
        fetched_at=fetched_at,
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
