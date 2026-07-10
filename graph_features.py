"""
Graph topology and Node2Vec embedding features for link prediction.

Computes structural features for object-object pairs using the heterogeneous
MET knowledge graph (object nodes connected to attribute hub nodes).

Topology features treat shared hub neighbors as "common neighbors" — e.g.
two objects sharing the same artist hub count as having that hub in common.
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np

# Try to import Node2Vec from node2vec package; fallback if unavailable.
try:
    from node2vec import Node2Vec
    HAS_NODE2VEC = True
except ImportError:
    HAS_NODE2VEC = False

logger = logging.getLogger(__name__)

OBJECT_NODE_PREFIX = "obj:"

TOPOLOGY_FEATURE_NAMES: list[str] = [
    "common_neighbors",
    "jaccard",
    "adamic_adar",
    "preferential_attachment",
]

NODE2VEC_FEATURE_NAME = "node2vec_similarity"

GRAPH_FEATURE_NAMES: list[str] = TOPOLOGY_FEATURE_NAMES + [NODE2VEC_FEATURE_NAME]

DEFAULT_NODE2VEC_CACHE = Path("cache/node2vec_embeddings.pkl")

DEFAULT_NODE2VEC_PARAMS: dict[str, Any] = {
    "dimensions": 64,
    "walk_length": 30,
    "num_walks": 200,
    "workers": -1,
    "p": 1,
    "q": 1,
    "window": 10,
    "min_count": 1,
    "sg": 1,
}


def object_node_id(object_id: int | str) -> str:
    """Convert an Object ID to its graph node identifier."""
    return f"{OBJECT_NODE_PREFIX}{object_id}"


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors; returns 0.0 on zero-norm inputs."""
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def load_graph(graph_path: str | Path) -> nx.Graph:
    """Load a NetworkX graph from a GraphML file."""
    graph = nx.read_graphml(graph_path)
    logger.info(
        "Loaded graph with %d nodes and %d edges",
        graph.number_of_nodes(),
        graph.number_of_edges(),
    )
    return graph


# Hub types that are used in 05_build_graph.py to SAMPLE the ground-truth
# positive pairs (see PAIR_SAMPLING_HUB_TYPES there). If a positive pair
# (A, B) exists, it is because A and B share one of these hubs -- so that
# hub is guaranteed to show up as a "common neighbor" of A and B in the
# graph. Counting it towards common_neighbors/jaccard/adamic_adar/
# preferential_attachment leaks the exact mechanism that produced the
# label into the features, which is the same problem the module docstring
# in 06_link_prediction.py explicitly tried to avoid for the raw
# "shared_artist"/"shared_tag" columns. These hub types must therefore be
# excluded from the topology-feature neighbor sets, not just from the
# explicit feature columns.
LEAKY_HUB_TYPES = {"has_artist", "has_tag"}


class GraphTopologyIndex:
    """Precomputed neighbor sets and degrees for fast topology feature lookup.

    Only object nodes (``node_type == "object"``) are indexed. Neighbors are
    typically attribute hub nodes (artist, tag, department, etc.), but any
    hub type in ``excluded_hub_types`` is dropped from the neighbor sets
    before any feature is computed -- see ``LEAKY_HUB_TYPES`` above for why.
    """

    def __init__(
        self,
        graph: nx.Graph,
        excluded_hub_types: frozenset[str] | set[str] = LEAKY_HUB_TYPES,
    ) -> None:
        self.excluded_hub_types = frozenset(excluded_hub_types)
        self._neighbors: dict[str, frozenset[str]] = {}
        self._degrees: dict[str, int] = {}
        self._hub_degrees: dict[str, int] = {}

        for node, attrs in graph.nodes(data=True):
            if attrs.get("node_type") == "hub":
                self._hub_degrees[node] = graph.degree(node)

        excluded_hub_nodes = 0
        for node, attrs in graph.nodes(data=True):
            if attrs.get("node_type") != "object":
                continue
            raw_neighbors = list(graph.neighbors(node))
            neighbors = frozenset(
                n for n in raw_neighbors
                if graph.nodes[n].get("hub_type") not in self.excluded_hub_types
            )
            excluded_hub_nodes += len(raw_neighbors) - len(neighbors)
            self._neighbors[node] = neighbors
            self._degrees[node] = len(neighbors)

        logger.info(
            "Indexed %d object nodes for topology features "
            "(excluded hub types: %s; %d object-hub edges dropped from "
            "neighbor sets to avoid leaking the pair-sampling signal)",
            len(self._neighbors), sorted(self.excluded_hub_types), excluded_hub_nodes,
        )

    def _node_key(self, object_id: int | str) -> str:
        return object_node_id(object_id)

    def compute_features(self, source_id: int | str, target_id: int | str) -> dict[str, float]:
        """Compute all topology features for an object pair.

        Returns zeros when either node is absent from the graph (no exception).
        """
        u = self._node_key(source_id)
        v = self._node_key(target_id)

        if u not in self._neighbors or v not in self._neighbors:
            return {name: 0.0 for name in TOPOLOGY_FEATURE_NAMES}

        neighbors_u = self._neighbors[u]
        neighbors_v = self._neighbors[v]
        common = neighbors_u & neighbors_v
        common_count = len(common)

        union_size = len(neighbors_u | neighbors_v)
        jaccard = common_count / union_size if union_size > 0 else 0.0

        adamic_adar = 0.0
        for hub in common:
            hub_degree = self._hub_degrees.get(hub, 0)
            if hub_degree > 1:
                adamic_adar += 1.0 / np.log(hub_degree)

        preferential_attachment = float(self._degrees[u] * self._degrees[v])

        return {
            "common_neighbors": float(common_count),
            "jaccard": float(jaccard),
            "adamic_adar": float(adamic_adar),
            "preferential_attachment": preferential_attachment,
        }


class Node2VecEmbeddings:
    """Train or load cached Node2Vec embeddings for all graph nodes.

    Embeddings are persisted to ``cache/node2vec_embeddings.pkl`` so that
    subsequent pipeline runs skip re-training.
    """

    def __init__(
        self,
        graph: nx.Graph,
        cache_path: str | Path | None = None,
        excluded_hub_types: frozenset[str] | set[str] | None = LEAKY_HUB_TYPES,
        **override_params: Any,
    ) -> None:
        self.excluded_hub_types = frozenset(excluded_hub_types) if excluded_hub_types else frozenset()

        base_cache_path = Path(cache_path) if cache_path else DEFAULT_NODE2VEC_CACHE
        if self.excluded_hub_types:
            # Deliberately a DIFFERENT filename than base_cache_path. Node2Vec
            # trained on the full graph (including has_artist/has_tag hubs)
            # encodes the exact same label-generating signal that
            # GraphTopologyIndex was fixed to exclude -- two objects sharing
            # an artist hub will always random-walk into each other and end
            # up with high node2vec_similarity, regardless of real semantic
            # relatedness. Using a distinct cache filename means an old,
            # leaky cache is never silently reused; a fresh, non-leaky
            # embedding set is trained instead.
            self.cache_path = base_cache_path.with_name(
                base_cache_path.stem + "_filtered" + base_cache_path.suffix
            )
        else:
            self.cache_path = base_cache_path

        self.graph = self._build_training_graph(graph)
        self.params = {**DEFAULT_NODE2VEC_PARAMS, **override_params}
        self._embeddings: dict[str, np.ndarray] = {}
        self._load_or_train()

    def _build_training_graph(self, graph: nx.Graph) -> nx.Graph:
        """Return a copy of `graph` with leaky hub nodes removed entirely,
        so Node2Vec random walks can never traverse a has_artist/has_tag
        hub. Object nodes and non-leaky hubs (department, culture, etc.)
        are kept, so legitimate structural signal is preserved."""
        if not self.excluded_hub_types:
            return graph

        leaky_nodes = [
            node for node, attrs in graph.nodes(data=True)
            if attrs.get("node_type") == "hub" and attrs.get("hub_type") in self.excluded_hub_types
        ]
        filtered = graph.copy()
        filtered.remove_nodes_from(leaky_nodes)
        logger.info(
            "Node2Vec training graph: removed %d leaky hub nodes (%s) -- "
            "%d nodes remain (was %d)",
            len(leaky_nodes), sorted(self.excluded_hub_types),
            filtered.number_of_nodes(), graph.number_of_nodes(),
        )
        return filtered

    def _load_or_train(self) -> None:
        if self.cache_path.exists():
            logger.info("Loading cached Node2Vec...")
            with self.cache_path.open("rb") as handle:
                self._embeddings = pickle.load(handle)
            logger.info("Loaded %d cached Node2Vec embeddings from %s", len(self._embeddings), self.cache_path)
            return

        self.cache_path.parent.mkdir(parents=True, exist_ok=True)

        if HAS_NODE2VEC:
            logger.info("Training Node2Vec...")
            n2v_init_keys = {"dimensions", "walk_length", "num_walks", "workers", "p", "q"}
            fit_keys = {"window", "min_count", "sg"}

            try:
                node2vec = Node2Vec(
                    self.graph,
                    **{k: self.params[k] for k in n2v_init_keys},
                )
                model = node2vec.fit(**{k: self.params[k] for k in fit_keys})

                for node in self.graph.nodes():
                    node_key = str(node)
                    try:
                        self._embeddings[node_key] = np.array(model.wv[node_key], dtype=np.float64)
                    except KeyError:
                        # Node may not appear in random walks; skip silently.
                        continue

                with self.cache_path.open("wb") as handle:
                    pickle.dump(self._embeddings, handle)
                logger.info(
                    "Trained and saved %d Node2Vec embeddings to %s",
                    len(self._embeddings),
                    self.cache_path,
                )
                return
            except Exception as e:
                logger.warning("Node2Vec training failed: %s. Falling back to SVD spectral embeddings.", e)

        # Fallback implementation if node2vec or gensim are not available or fail
        logger.info("node2vec or gensim is not available or failed. Computing SVD structural graph embeddings as fallback...")
        try:
            import scipy.sparse as sp
            from scipy.sparse.linalg import svds

            nodes = list(self.graph.nodes())
            node_to_idx = {node: i for i, node in enumerate(nodes)}

            # Build sparse adjacency matrix
            row_indices = []
            col_indices = []
            data = []
            for u, v in self.graph.edges():
                ui, vi = node_to_idx[u], node_to_idx[v]
                row_indices.extend([ui, vi])
                col_indices.extend([vi, ui])
                data.extend([1.0, 1.0])

            n = len(nodes)
            if n < 2:
                for node in nodes:
                    self._embeddings[str(node)] = np.zeros(64)
            else:
                adj = sp.csc_matrix((data, (row_indices, col_indices)), shape=(n, n), dtype=np.float64)
                k = min(64, n - 2)
                if k <= 0:
                    k = 1
                u_mat, s_mat, vt_mat = svds(adj, k=k)
                embeddings_matrix = u_mat * np.sqrt(s_mat)

                for node in self.graph.nodes():
                    idx = node_to_idx[node]
                    vec = embeddings_matrix[idx]
                    if len(vec) < 64:
                        vec = np.pad(vec, (0, 64 - len(vec)))
                    self._embeddings[str(node)] = vec

            with self.cache_path.open("wb") as handle:
                pickle.dump(self._embeddings, handle)
            logger.info(
                "Computed and cached %d SVD-based structural embeddings to %s",
                len(self._embeddings),
                self.cache_path,
            )
        except Exception as e:
            logger.error("SVD fallback also failed: %s. Generating zero embeddings.", e)
            for node in self.graph.nodes():
                self._embeddings[str(node)] = np.zeros(64)

    def similarity(self, source_id: int | str, target_id: int | str) -> float:
        """Cosine similarity between Node2Vec embeddings of two object nodes."""
        u = object_node_id(source_id)
        v = object_node_id(target_id)
        emb_u = self._embeddings.get(u)
        emb_v = self._embeddings.get(v)
        if emb_u is None or emb_v is None:
            return 0.0
        return cosine_sim(emb_u, emb_v)


def compute_graph_features(
    source_id: int | str,
    target_id: int | str,
    topology_index: GraphTopologyIndex,
    node2vec: Node2VecEmbeddings,
) -> dict[str, float]:
    """Compute all graph-derived features (topology + Node2Vec similarity)."""
    features = topology_index.compute_features(source_id, target_id)
    features[NODE2VEC_FEATURE_NAME] = node2vec.similarity(source_id, target_id)
    return features