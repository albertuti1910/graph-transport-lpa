from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from src.adapters.api.schemas.routes import GeoPointSchema


class TransitRouteSchema(BaseModel):
    route_id: str
    short_name: str | None = None
    long_name: str | None = None
    color: str | None = None
    text_color: str | None = None


class RouteShapeSchema(BaseModel):
    route_id: str
    points: list[GeoPointSchema]


class VehicleSchema(BaseModel):
    vehicle_id: str | None = None
    trip_id: str | None = None
    route_id: str | None = None
    lat: float
    lon: float
    bearing: float | None = None
    speed_mps: float | None = None
    timestamp: datetime | None = None
    stop_id: str | None = None


class VehiclesResponseSchema(BaseModel):
    fetched_at: datetime
    is_cached: bool
    vehicles: list[VehicleSchema]
