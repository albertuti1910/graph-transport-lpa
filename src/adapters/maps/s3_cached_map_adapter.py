from __future__ import annotations

import gzip
import os
import pickle
from dataclasses import dataclass
from typing import Any

from src.adapters.aws import s3_client
from src.app.ports.output import IMapProvider
from src.domain.models import GeoPoint


@dataclass(slots=True)
class S3CachedMapAdapter(IMapProvider):
    """Caches street graphs in S3.

    This is an adapter-level decorator around another IMapProvider.

    Env vars:
      - STREET_GRAPH_BUCKET (required)
      - STREET_GRAPH_PREFIX (default: street-graphs)
      - ENDPOINT_URL (preferred for LocalStack)
    """

    upstream: IMapProvider
    bucket: str | None = None
    prefix: str | None = None

    def _bucket(self) -> str:
        value = self.bucket or os.getenv("STREET_GRAPH_BUCKET")
        if not value:
            raise RuntimeError("Missing STREET_GRAPH_BUCKET")
        return value

    def _prefix(self) -> str:
        return (
            self.prefix or os.getenv("STREET_GRAPH_PREFIX") or "street-graphs"
        ).strip("/")

    def _key(
        self, *, center: GeoPoint, dist_m: int, network_type: str | None = None
    ) -> str:
        # Round coordinates to reduce key explosion.
        lat = round(center.lat, 4)
        lon = round(center.lon, 4)
        nt = (network_type or "walk").strip().lower()
        return f"{self._prefix()}/nt={nt}/dist={int(dist_m)}/center={lat}_{lon}.pkl.gz"

    def get_street_graph(self, *, center: GeoPoint, dist_m: int):
        s3 = s3_client()
        bucket = self._bucket()

        network_type = getattr(self.upstream, "network_type", None)
        key = self._key(center=center, dist_m=dist_m, network_type=network_type)

        try:
            obj = s3.get_object(Bucket=bucket, Key=key)
            body = obj["Body"].read()
            data = gzip.decompress(body)
            graph = pickle.loads(data)
            return self._normalize_graph(graph)
        except Exception:
            graph = self.upstream.get_street_graph(center=center, dist_m=dist_m)

            graph = self._normalize_graph(graph)
            payload = gzip.compress(pickle.dumps(graph))
            s3.put_object(Bucket=bucket, Key=key, Body=payload)
            return graph

    def _normalize_graph(self, graph: Any) -> Any:
        """Best-effort normalization of a street graph.

        Some serialized graphs (e.g. GraphML loaded with generic NetworkX loaders)
        may store numeric attributes like edge 'length' or node 'x'/'y' as strings.
        That breaks weighted shortest-path and can trigger straight-line fallbacks.

        We coerce common numeric attributes to floats in-place.
        """

        try:
            # Node coordinates
            if hasattr(graph, "nodes"):
                for n in graph.nodes:
                    data = graph.nodes[n]
                    if "x" in data:
                        try:
                            data["x"] = float(data["x"])
                        except Exception:
                            pass
                    if "y" in data:
                        try:
                            data["y"] = float(data["y"])
                        except Exception:
                            pass

            # Edge lengths
            if hasattr(graph, "edges"):
                # Support MultiGraphs and simple Graphs.
                try:
                    iterator = graph.edges(keys=True, data=True)  # type: ignore[attr-defined]
                    for _, _, _, data in iterator:
                        if "length" in data:
                            try:
                                data["length"] = float(data["length"])
                            except Exception:
                                pass
                except TypeError:
                    for _, _, data in graph.edges(data=True):
                        if "length" in data:
                            try:
                                data["length"] = float(data["length"])
                            except Exception:
                                pass
        except Exception:
            # Never fail routing due to cache normalization.
            return graph

        return graph
