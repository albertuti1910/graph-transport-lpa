from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class GeoPointSchema(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)


class TransitLineSchema(BaseModel):
    route_id: str | None = None
    short_name: str | None = None
    long_name: str | None = None
    color: str | None = None
    text_color: str | None = None


class RouteLegSchema(BaseModel):
    mode: Literal["walk", "bus"]
    origin: GeoPointSchema
    destination: GeoPointSchema
    origin_name: str | None = None
    destination_name: str | None = None
    origin_stop_id: str | None = None
    destination_stop_id: str | None = None
    depart_at: datetime | None = None
    arrive_at: datetime | None = None
    distance_m: float | None = None
    duration_s: float | None = None
    path: list[GeoPointSchema] | None = None
    line: TransitLineSchema | None = None
    trip_id: str | None = None


class RouteSchema(BaseModel):
    origin: GeoPointSchema
    destination: GeoPointSchema
    legs: list[RouteLegSchema] = []

    total_distance_m: float | None = None
    total_duration_s: float | None = None


class RouteRequestSchema(BaseModel):
    origin: GeoPointSchema
    destination: GeoPointSchema
    depart_at: datetime | None = None
    preference: Literal["fastest", "least_walking"] = "fastest"


class EnqueueResponseSchema(BaseModel):
    request_id: str


class RouteJobStatusSchema(BaseModel):
    request_id: str
    status: str | None = None
    created_at_ms: int | None = None
    updated_at_ms: int | None = None
    payload: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
