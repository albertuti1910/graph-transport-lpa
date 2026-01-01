from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping


class IRouteResultRepository(ABC):
    """Port for persisting async routing job status/results."""

    @abstractmethod
    def put_pending(self, *, request_id: str, payload: Mapping[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def put_success(self, *, request_id: str, result: Mapping[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def put_error(self, *, request_id: str, error: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def get(self, *, request_id: str) -> Mapping[str, Any] | None:
        raise NotImplementedError
