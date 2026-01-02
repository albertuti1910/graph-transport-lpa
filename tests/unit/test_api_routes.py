from __future__ import annotations

from datetime import datetime

import httpx
import pytest

from src.adapters.api.dependencies import get_route_jobs_service, get_routing_service
from src.domain.models import GeoPoint, Route, RouteLeg, TravelMode
from src.main import app


class _FakeMultimodalRoutingService:
    def calculate_route(
        self,
        *,
        origin: GeoPoint,
        destination: GeoPoint,
        depart_at: datetime,
        preference: str,
    ) -> Route:
        leg = RouteLeg(
            mode=TravelMode.WALK,
            origin=origin,
            destination=destination,
            distance_m=123.0,
            duration_s=456.0,
            stops=(),
        )
        return Route(origin=origin, destination=destination, legs=(leg,))

    def enqueue_route_request(
        self,
        *,
        origin: GeoPoint,
        destination: GeoPoint,
        depart_at: datetime,
        preference: str,
    ) -> str:
        raise AssertionError("Should not be called in API tests")


class _FakeJobsService:
    def submit(
        self,
        *,
        origin: GeoPoint,
        destination: GeoPoint,
        depart_at: datetime,
        preference: str,
    ) -> str:
        raise RuntimeError("Queue service not configured")


@pytest.mark.unit
@pytest.mark.anyio
async def test_post_routes_returns_route() -> None:
    def _override():
        return _FakeMultimodalRoutingService()

    app.dependency_overrides[get_routing_service] = _override

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/routes",
            json={
                "origin": {"lat": 28.12, "lon": -15.43},
                "destination": {"lat": 28.121, "lon": -15.431},
            },
        )

    app.dependency_overrides.clear()

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total_distance_m"] == 123.0
    assert payload["total_duration_s"] == 456.0
    assert payload["legs"][0]["mode"] == "walk"


@pytest.mark.unit
@pytest.mark.anyio
async def test_post_routes_async_requires_queue_configured() -> None:
    def _override():
        return _FakeJobsService()

    app.dependency_overrides[get_route_jobs_service] = _override

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/routes/async",
            json={
                "origin": {"lat": 28.12, "lon": -15.43},
                "destination": {"lat": 28.121, "lon": -15.431},
            },
        )

    app.dependency_overrides.clear()

    # Service raises RuntimeError; FastAPI converts to 500 by default.
    assert resp.status_code == 500


@pytest.mark.unit
@pytest.mark.anyio
async def test_post_routes_async_returns_request_id_when_configured() -> None:
    class _OkJobsService:
        def submit(
            self,
            *,
            origin: GeoPoint,
            destination: GeoPoint,
            depart_at: datetime,
            preference: str,
        ) -> str:
            return "req-123"

        def get(self, *, request_id: str):
            raise AssertionError("Not used")

    def _override():
        return _OkJobsService()

    app.dependency_overrides[get_route_jobs_service] = _override

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/routes/async",
            json={
                "origin": {"lat": 28.12, "lon": -15.43},
                "destination": {"lat": 28.121, "lon": -15.431},
            },
        )

    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["request_id"] == "req-123"
