from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.models.realtime import RealtimeVehicle


class IRealtimeVehicleProvider(ABC):
    """Port for obtaining realtime vehicle positions (e.g., via GTFS-Realtime)."""

    @abstractmethod
    async def list_vehicles(self) -> tuple[RealtimeVehicle, ...]:
        raise NotImplementedError
