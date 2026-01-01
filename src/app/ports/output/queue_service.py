from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping


class IQueueService(ABC):
    """Messaging port for async route calculation requests."""

    @abstractmethod
    def publish_request(self, message: Mapping[str, Any]) -> str:
        """Publish a request message and return its provider message id."""

    @abstractmethod
    def consume_request(
        self, *, max_messages: int = 1, wait_time_s: int = 10
    ) -> list[Mapping[str, Any]]:
        """Consume up to N messages and return decoded message bodies."""
