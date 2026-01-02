from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class RealtimeVehicle:
    vehicle_id: str | None
    trip_id: str | None
    route_id: str | None
    lat: float
    lon: float
    bearing: float | None = None
    speed_mps: float | None = None
    timestamp: datetime | None = None
    stop_id: str | None = None
