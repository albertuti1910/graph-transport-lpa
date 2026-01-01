from __future__ import annotations

import os
import pickle
import tempfile
from dataclasses import dataclass
from typing import Any, Iterable

import networkx as nx

from src.adapters.aws import s3_client
from src.app.ports.output import IGraphRepository
from src.domain.exceptions import NoPathFound
from src.domain.models import GeoPoint, Route, RouteLeg, TravelMode


@dataclass(slots=True)
class S3GraphRepository(IGraphRepository):
    """Graph repository backed by S3.

    Env vars:
      - S3_BUCKET: bucket name
      - S3_GRAPH_KEY: object key (e.g. graphs/lpa.graphml)
      - GRAPH_FORMAT: graphml|pickle (default: graphml)
            - ENDPOINT_URL: preferred LocalStack endpoint (e.g. http://localhost:4566)
            - USE_LOCALSTACK: 1|true to enable LocalStack (legacy toggle)
            - LOCALSTACK_ENDPOINT_URL: fallback endpoint if USE_LOCALSTACK is set (legacy)
      - AWS_REGION: defaults to eu-west-1

    Notes:
      - pickle loading is only safe for trusted inputs.
    """

    bucket: str | None = None
    key: str | None = None

    _graph: Any | None = None

    def _bucket(self) -> str:
        value = self.bucket or os.getenv("S3_BUCKET")
        if not value:
            raise RuntimeError("Missing S3_BUCKET")
        return value

    def _key(self) -> str:
        value = self.key or os.getenv("S3_GRAPH_KEY")
        if not value:
            raise RuntimeError("Missing S3_GRAPH_KEY")
        return value

    def load_graph(self) -> Any:
        if self._graph is not None:
            return self._graph

        s3 = s3_client()
        bucket = self._bucket()
        key = self._key()

        obj = s3.get_object(Bucket=bucket, Key=key)
        body = obj["Body"].read()

        graph_format = (
            (os.getenv("GRAPH_FORMAT", "graphml") or "graphml").strip().lower()
        )
        if graph_format == "pickle":
            self._graph = pickle.loads(body)
            return self._graph

        if graph_format != "graphml":
            raise RuntimeError(f"Unsupported GRAPH_FORMAT: {graph_format}")

        # networkx.read_graphml expects a path or file-like; safest is a temp file.
        with tempfile.NamedTemporaryFile(suffix=".graphml") as fp:
            fp.write(body)
            fp.flush()
            self._graph = nx.read_graphml(fp.name)
            return self._graph

    def find_path(self, origin: GeoPoint, destination: GeoPoint) -> Route:
        graph = self.load_graph()

        try:
            origin_node = self._nearest_node(graph, origin)
            dest_node = self._nearest_node(graph, destination)

            path_nodes = nx.shortest_path(
                graph, origin_node, dest_node, weight="length"
            )
            distance_m = self._path_distance_m(graph, path_nodes)

            leg = RouteLeg(
                mode=TravelMode.WALK,
                origin=origin,
                destination=destination,
                distance_m=distance_m,
                duration_s=None,
                stops=(),
            )
            return Route(origin=origin, destination=destination, legs=(leg,))
        except (nx.NetworkXNoPath, nx.NodeNotFound) as exc:
            raise NoPathFound(str(exc)) from exc

    def _nearest_node(self, graph: Any, point: GeoPoint) -> Any:
        try:
            import osmnx as ox  # type: ignore

            return ox.distance.nearest_nodes(graph, X=point.lon, Y=point.lat)
        except Exception:
            pass

        # OSMnx-style nodes have x=lon, y=lat attributes; GraphML may store them as strings.
        best_node: Any | None = None
        best_d2 = float("inf")

        for node_id, data in self._iter_nodes(graph):
            x = data.get("x")
            y = data.get("y")
            if x is None or y is None:
                continue
            try:
                lon = float(x)
                lat = float(y)
            except (TypeError, ValueError):
                continue

            d_lat = lat - point.lat
            d_lon = lon - point.lon
            d2 = d_lat * d_lat + d_lon * d_lon
            if d2 < best_d2:
                best_d2 = d2
                best_node = node_id

        if best_node is None:
            raise NoPathFound("Graph contains no georeferenced nodes (missing x/y)")
        return best_node

    def _iter_nodes(self, graph: Any) -> Iterable[tuple[Any, dict[str, Any]]]:
        if hasattr(graph, "nodes"):
            return ((n, dict(graph.nodes[n])) for n in graph.nodes)
        raise RuntimeError("Unsupported graph type")

    def _path_distance_m(self, graph: Any, path_nodes: list[Any]) -> float | None:
        total = 0.0
        for u, v in zip(path_nodes, path_nodes[1:]):
            edge_data = graph.get_edge_data(u, v)
            if not edge_data:
                continue

            # MultiDiGraph: edge_data is keyed by edge key.
            if isinstance(edge_data, dict) and all(
                isinstance(val, dict) for val in edge_data.values()
            ):
                candidates = list(edge_data.values())
            elif isinstance(edge_data, dict):
                candidates = [edge_data]
            else:
                candidates = []

            lengths = []
            for e in candidates:
                val = e.get("length")
                if val is None:
                    continue
                try:
                    lengths.append(float(val))
                except (TypeError, ValueError):
                    pass

            if lengths:
                total += min(lengths)

        return total
