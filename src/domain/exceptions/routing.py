class RoutingError(Exception):
    """Base exception for route calculation failures."""


class NoPathFound(RoutingError):
    """Raised when no feasible path exists for the given request."""
