from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.models.gtfs import GtfsFeed


class IGtfsRepository(ABC):
    """Port for loading GTFS data into an in-memory feed."""

    @abstractmethod
    def load_feed(self) -> GtfsFeed:
        raise NotImplementedError
