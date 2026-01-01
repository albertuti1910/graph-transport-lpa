from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path

from src.app.ports.output import IGtfsRepository
from src.domain.models import GeoPoint, Stop
from src.domain.models.gtfs import GtfsFeed


def _parse_gtfs_time_to_seconds(raw: str) -> int:
    # GTFS time can be HH:MM:SS with HH possibly > 24.
    hh, mm, ss = raw.strip().split(":")
    return int(hh) * 3600 + int(mm) * 60 + int(ss)


@dataclass(slots=True)
class LocalGtfsRepository(IGtfsRepository):
    """Loads a GTFS feed from a directory of .txt files.

    Env vars:
      - GTFS_PATH: path to directory containing stops.txt, stop_times.txt, trips.txt
    """

    base_path: str | Path | None = None

    def _base(self) -> Path:
        value = self.base_path or os.getenv("GTFS_PATH") or "data/gtfs"
        return Path(value)

    def load_feed(self) -> GtfsFeed:
        base = self._base()

        # Optional metadata.
        from src.domain.models.gtfs import GtfsRoute, GtfsTrip

        routes_by_id: dict[str, GtfsRoute] = {}
        routes_path = base / "routes.txt"
        if routes_path.exists():
            with routes_path.open("r", encoding="utf-8", newline="") as fp:
                reader = csv.DictReader(fp)
                for row in reader:
                    route_id = (row.get("route_id") or "").strip()
                    if not route_id:
                        continue
                    routes_by_id[route_id] = GtfsRoute(
                        route_id=route_id,
                        short_name=(row.get("route_short_name") or "").strip() or None,
                        long_name=(row.get("route_long_name") or "").strip() or None,
                        color=(row.get("route_color") or "").strip() or None,
                        text_color=(row.get("route_text_color") or "").strip() or None,
                    )

        trips_by_id: dict[str, GtfsTrip] = {}
        trips_path = base / "trips.txt"
        if trips_path.exists():
            with trips_path.open("r", encoding="utf-8", newline="") as fp:
                reader = csv.DictReader(fp)
                for row in reader:
                    trip_id = (row.get("trip_id") or "").strip()
                    if not trip_id:
                        continue
                    trips_by_id[trip_id] = GtfsTrip(
                        trip_id=trip_id,
                        route_id=(row.get("route_id") or "").strip() or None,
                        shape_id=(row.get("shape_id") or "").strip() or None,
                    )

        shapes_by_id: dict[str, tuple[GeoPoint, ...]] = {}
        shapes_path = base / "shapes.txt"
        if shapes_path.exists():
            tmp: dict[str, list[tuple[int, GeoPoint]]] = {}
            with shapes_path.open("r", encoding="utf-8", newline="") as fp:
                reader = csv.DictReader(fp)
                for row in reader:
                    shape_id = (row.get("shape_id") or "").strip()
                    if not shape_id:
                        continue
                    try:
                        seq = int(row.get("shape_pt_sequence") or 0)
                        lat = float(row["shape_pt_lat"])
                        lon = float(row["shape_pt_lon"])
                    except (TypeError, ValueError, KeyError):
                        continue
                    tmp.setdefault(shape_id, []).append(
                        (seq, GeoPoint(lat=lat, lon=lon))
                    )

            for shape_id, pts in tmp.items():
                pts.sort(key=lambda x: x[0])
                shapes_by_id[shape_id] = tuple(p for _, p in pts)

        stops_by_id: dict[str, Stop] = {}
        with (base / "stops.txt").open("r", encoding="utf-8", newline="") as fp:
            reader = csv.DictReader(fp)
            for row in reader:
                stop_id = (row.get("stop_id") or "").strip()
                if not stop_id:
                    continue
                name = (row.get("stop_name") or stop_id).strip()
                lat = float(row["stop_lat"])
                lon = float(row["stop_lon"])
                stops_by_id[stop_id] = Stop(
                    id=stop_id, name=name, location=GeoPoint(lat=lat, lon=lon)
                )

        # Build stop_times per trip with ordering.
        stop_times_by_trip: dict[str, list[tuple[int, str, int, int]]] = {}
        with (base / "stop_times.txt").open("r", encoding="utf-8", newline="") as fp:
            reader = csv.DictReader(fp)
            for row in reader:
                trip_id = (row.get("trip_id") or "").strip()
                stop_id = (row.get("stop_id") or "").strip()
                if not trip_id or not stop_id:
                    continue

                seq = int(row.get("stop_sequence") or 0)
                arr_s = _parse_gtfs_time_to_seconds(row["arrival_time"])
                dep_s = _parse_gtfs_time_to_seconds(row["departure_time"])

                stop_times_by_trip.setdefault(trip_id, []).append(
                    (seq, stop_id, dep_s, arr_s)
                )

        # Connections: consecutive stop_times within each trip.
        from src.domain.models.gtfs import Connection

        connections: list[Connection] = []
        for trip_id, entries in stop_times_by_trip.items():
            entries.sort(key=lambda x: x[0])
            for (_, a_stop, a_dep, _), (_, b_stop, _, b_arr) in zip(
                entries, entries[1:]
            ):
                if a_stop not in stops_by_id or b_stop not in stops_by_id:
                    continue
                connections.append(
                    Connection(
                        dep_stop_id=a_stop,
                        arr_stop_id=b_stop,
                        dep_time_s=int(a_dep),
                        arr_time_s=int(b_arr),
                        trip_id=trip_id,
                    )
                )

        connections.sort(key=lambda c: (c.dep_time_s, c.arr_time_s))

        return GtfsFeed(
            stops_by_id=stops_by_id,
            connections=tuple(connections),
            routes_by_id=routes_by_id,
            trips_by_id=trips_by_id,
            shapes_by_id=shapes_by_id,
        )
