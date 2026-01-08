from __future__ import annotations

import os
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import osmnx as ox

from src.adapters.aws import s3_client
from src.app.ports.output import IMapProvider
from src.domain.models import GeoPoint


@dataclass(slots=True)
class OSMnxMapAdapter(IMapProvider):
    """OSMnx-backed map provider."""

    network_type: str = "walk"

    _prebuilt_graph: Any | None = None

    def _configure_osmnx(self) -> None:
        # Make Overpass/OSM downloads cacheable across requests.
        ox.settings.use_cache = True
        ox.settings.log_console = False
        cache_folder = os.getenv("OSMNX_CACHE_FOLDER") or "data/osm_cache"
        ox.settings.cache_folder = cache_folder

    def _load_prebuilt_graph(self) -> Any | None:
        """Optionally load a prebuilt graph from disk to avoid downloading/building on demand.

        Env vars:
          - OSM_GRAPH_PATH: path to .graphml or .pkl/.pickle
        """

        if self._prebuilt_graph is not None:
            return self._prebuilt_graph

        path = (os.getenv("OSM_GRAPH_PATH") or "").strip()
        if not path:
            return None

        if path.lower().endswith(".graphml"):
            # Important: use OSMnx loader so node/edge attributes keep correct
            # numeric types (e.g. edge "length"), otherwise shortest-path can
            # fail and the app falls back to a straight-line walk.
            self._prebuilt_graph = ox.load_graphml(path)
            return self._prebuilt_graph

        if path.lower().endswith((".pkl", ".pickle")):
            with open(path, "rb") as fp:
                self._prebuilt_graph = pickle.load(fp)
            return self._prebuilt_graph

        raise RuntimeError(f"Unsupported OSM_GRAPH_PATH format: {path}")

    def _maybe_build_prebuilt_graph(self) -> None:
        """Build and persist a full-area graph once, then reuse it.

        Intended to avoid expensive OSM downloads/building per request.

        Env vars:
          - OSM_GRAPH_PATH: where to load/save the graph (.graphml or .pkl/.pickle)
                    - OSM_GRAPH_S3_URI: optional source (s3://bucket/key) to download the prebuilt file
          - OSM_GRAPH_AUTO_BUILD: if '1'/'true', build when file is missing (default: true when OSM_GRAPH_PATH is set)
          - OSM_PLACE: place string for OSMnx (e.g. 'Las Palmas de Gran Canaria, Canary Islands, Spain')
        """

        raw_path = (os.getenv("OSM_GRAPH_PATH") or "").strip()
        if not raw_path:
            return

        path = Path(raw_path)
        auto_raw = (os.getenv("OSM_GRAPH_AUTO_BUILD") or "").strip().lower()
        auto_build = auto_raw in {"1", "true", "yes", "on"} or auto_raw == ""

        if path.exists() or not auto_build:
            return

        place = (os.getenv("OSM_PLACE") or "").strip()
        if not place:
            raise RuntimeError(
                "OSM_GRAPH_PATH is set but file does not exist and OSM_PLACE is missing; "
                "set OSM_PLACE (or disable auto-build with OSM_GRAPH_AUTO_BUILD=0)."
            )

        path.parent.mkdir(parents=True, exist_ok=True)

        # Basic inter-process lock to avoid API+worker racing to build.
        lock_path = path.with_suffix(path.suffix + ".lock")
        with open(lock_path, "w", encoding="utf-8") as lock_fp:
            try:
                import fcntl

                fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX)
            except Exception:
                # If locking is unavailable, we still try best-effort.
                pass

            # Another process might have built it while we waited.
            if path.exists():
                return

            self._configure_osmnx()

            # Full-area graph (once). Uses the adapter network_type.
            graph = ox.graph_from_place(
                place, network_type=self.network_type, simplify=True
            )

            tmp = path.with_suffix(path.suffix + ".tmp")
            if path.name.lower().endswith(".graphml"):
                ox.save_graphml(graph, tmp)
            elif path.name.lower().endswith((".pkl", ".pickle")):
                with open(tmp, "wb") as fp:
                    pickle.dump(graph, fp)
            else:
                raise RuntimeError(f"Unsupported OSM_GRAPH_PATH format: {path}")

            os.replace(tmp, path)

    def _maybe_download_prebuilt_graph_from_s3(self) -> None:
        """Download a prebuilt graph artifact from S3 if configured.

        This is the preferred mode for AWS: store a fixed graph in S3 and download
        it on container start (fast), without ever rebuilding from Overpass.

        Env vars:
          - OSM_GRAPH_PATH: local file path (target)
          - OSM_GRAPH_S3_URI: s3://bucket/key (source)
        """

        raw_path = (os.getenv("OSM_GRAPH_PATH") or "").strip()
        raw_uri = (os.getenv("OSM_GRAPH_S3_URI") or "").strip()
        if not raw_path or not raw_uri:
            return

        path = Path(raw_path)
        if path.exists():
            return

        if not raw_uri.lower().startswith("s3://"):
            raise RuntimeError(
                f"Unsupported OSM_GRAPH_S3_URI (expected s3://...): {raw_uri}"
            )

        # Parse s3://bucket/key
        without = raw_uri[5:]
        parts = without.split("/", 1)
        bucket = parts[0].strip()
        key = parts[1].strip() if len(parts) > 1 else ""
        if not bucket or not key:
            raise RuntimeError(f"Invalid OSM_GRAPH_S3_URI: {raw_uri}")

        path.parent.mkdir(parents=True, exist_ok=True)

        lock_path = path.with_suffix(path.suffix + ".lock")
        with open(lock_path, "w", encoding="utf-8") as lock_fp:
            try:
                import fcntl

                fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX)
            except Exception:
                pass

            if path.exists():
                return

            s3 = s3_client()
            obj = s3.get_object(Bucket=bucket, Key=key)
            body = obj["Body"].read()

            tmp = path.with_suffix(path.suffix + ".tmp")
            with open(tmp, "wb") as fp:
                fp.write(body)
            os.replace(tmp, path)

    def get_street_graph(self, *, center: GeoPoint, dist_m: int) -> Any:
        self._configure_osmnx()

        self._maybe_download_prebuilt_graph_from_s3()

        self._maybe_build_prebuilt_graph()

        prebuilt = self._load_prebuilt_graph()
        if prebuilt is not None:
            return prebuilt

        # OSMnx uses (lat, lon)
        return ox.graph_from_point(
            (center.lat, center.lon), dist=int(dist_m), network_type=self.network_type
        )
