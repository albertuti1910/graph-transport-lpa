from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from src.domain.models import GeoPoint, Route


class IGraphRepository(ABC):
    """Persistence port for loading and querying route graphs."""

    @abstractmethod
    def load_graph(self) -> Any:
        """Load the graph into memory and return a handle/reference."""

    @abstractmethod
    def find_path(self, origin: GeoPoint, destination: GeoPoint) -> Route:
        """Compute a route between two points using the loaded graph."""
