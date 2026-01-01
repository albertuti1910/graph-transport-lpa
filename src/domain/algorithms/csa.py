from __future__ import annotations

from dataclasses import dataclass

from src.domain.models.gtfs import Connection, GtfsFeed


@dataclass(frozen=True, slots=True)
class CsaResult:
    arrival_time_s_by_stop: dict[str, int]
    prev_by_stop: dict[str, Connection]


def earliest_arrival(
    feed: GtfsFeed, *, initial_time_s_by_stop: dict[str, int]
) -> CsaResult:
    """Compute earliest arrival times using a basic Connection Scan Algorithm.

    This implementation assumes:
        - connections are in service-day seconds and sorted by dep_time_s
        - transfers at the same stop have zero transfer time (MVP)
        - calendar/service validity filtering is handled upstream (MVP: not filtered)
    """

    arrival: dict[str, int] = dict(initial_time_s_by_stop)
    prev: dict[str, Connection] = {}

    def _get_arrival(stop_id: str) -> int:
        return arrival.get(stop_id, 2**31 - 1)

    for c in feed.connections:
        if _get_arrival(c.dep_stop_id) <= c.dep_time_s and c.arr_time_s < _get_arrival(
            c.arr_stop_id
        ):
            arrival[c.arr_stop_id] = c.arr_time_s
            prev[c.arr_stop_id] = c

    return CsaResult(arrival_time_s_by_stop=arrival, prev_by_stop=prev)


def reconstruct_connections(
    result: CsaResult, *, dest_stop_id: str
) -> list[Connection]:
    """Reconstruct the used connections ending at dest_stop_id."""

    out: list[Connection] = []
    cur = dest_stop_id
    while cur in result.prev_by_stop:
        c = result.prev_by_stop[cur]
        out.append(c)
        cur = c.dep_stop_id
    out.reverse()
    return out
