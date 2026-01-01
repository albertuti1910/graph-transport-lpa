from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from src.domain.models import GeoPoint


class IMapProvider(ABC):
    """Port for fetching street network data."""

    @abstractmethod
    def get_street_graph(self, *, center: GeoPoint, dist_m: int) -> Any:
        """Return a street graph around a center point within a given distance."""
