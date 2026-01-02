from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from src.app.ports.output import IRealtimeVehicleProvider
from src.domain.models.realtime import RealtimeVehicle


@dataclass(slots=True)
class HttpGtfsRealtimeVehicleProvider(IRealtimeVehicleProvider):
    """Fetches GTFS-Realtime VehiclePositions feed over HTTP.

    Env vars:
      - GTFS_RT_VEHICLE_POSITIONS_URL: URL to a GTFS-RT VehiclePositions feed
      - GTFS_RT_HEADERS: optional headers, as 'Key:Value;Key2:Value2'
      - GTFS_RT_TIMEOUT_S: request timeout (default 10)
      - GTFS_RT_CACHE_TTL_S: in-process cache TTL seconds (default 25)

    Notes:
      - If URL is not configured, returns an empty list.
      - Cache is per-process and shared across requests.
    """

    url: str | None = None
    headers_raw: str | None = None
    timeout_s: float = 10.0
    cache_ttl_s: float = 25.0

    # In-process cache
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    _cached_at_monotonic: float = 0.0
    _cached_vehicles: tuple[RealtimeVehicle, ...] = ()

    def __post_init__(self) -> None:
        if self.url is None:
            self.url = os.getenv("GTFS_RT_VEHICLE_POSITIONS_URL")
        if self.headers_raw is None:
            self.headers_raw = os.getenv("GTFS_RT_HEADERS")
        if os.getenv("GTFS_RT_TIMEOUT_S"):
            self.timeout_s = float(os.environ["GTFS_RT_TIMEOUT_S"])
        if os.getenv("GTFS_RT_CACHE_TTL_S"):
            self.cache_ttl_s = float(os.environ["GTFS_RT_CACHE_TTL_S"])

    def _headers(self) -> dict[str, str]:
        raw = (self.headers_raw or "").strip()
        if not raw:
            return {}
        headers: dict[str, str] = {}
        for part in raw.split(";"):
            part = part.strip()
            if not part:
                continue
            if ":" not in part:
                continue
            k, v = part.split(":", 1)
            k = k.strip()
            v = v.strip()
            if k:
                headers[k] = v
        return headers

    async def list_vehicles(self) -> tuple[RealtimeVehicle, ...]:
        if not self.url:
            return ()

        async with self._lock:
            now_mono = time.monotonic()
            if (
                self._cached_vehicles
                and (now_mono - self._cached_at_monotonic) < self.cache_ttl_s
            ):
                return self._cached_vehicles

            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                resp = await client.get(self.url, headers=self._headers())
                resp.raise_for_status()
                content = resp.content

            vehicles = _parse_gtfs_rt_vehicle_positions(content)

            self._cached_at_monotonic = time.monotonic()
            self._cached_vehicles = vehicles
            return vehicles


def _parse_gtfs_rt_vehicle_positions(content: bytes) -> tuple[RealtimeVehicle, ...]:
    # Import lazily so the app can still start without the dependency in dev.
    try:
        from google.transit import gtfs_realtime_pb2  # type: ignore
    except Exception:
        return ()

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(content)

    out: list[RealtimeVehicle] = []

    for ent in feed.entity:
        if not ent.HasField("vehicle"):
            continue

        v = ent.vehicle
        if not v.HasField("position"):
            continue

        pos = v.position
        lat = float(pos.latitude)
        lon = float(pos.longitude)

        trip_id = None
        route_id = None
        if v.HasField("trip"):
            trip_id = v.trip.trip_id or None
            route_id = v.trip.route_id or None

        vehicle_id = None
        if v.HasField("vehicle"):
            vehicle_id = v.vehicle.id or None

        bearing = float(pos.bearing) if pos.HasField("bearing") else None
        speed = float(pos.speed) if pos.HasField("speed") else None

        timestamp = None
        if v.HasField("timestamp") and int(v.timestamp) > 0:
            timestamp = datetime.fromtimestamp(int(v.timestamp), tz=timezone.utc)

        stop_id = v.stop_id or None

        out.append(
            RealtimeVehicle(
                vehicle_id=vehicle_id,
                trip_id=trip_id,
                route_id=route_id,
                lat=lat,
                lon=lon,
                bearing=bearing,
                speed_mps=speed,
                timestamp=timestamp,
                stop_id=stop_id,
            )
        )

    return tuple(out)
