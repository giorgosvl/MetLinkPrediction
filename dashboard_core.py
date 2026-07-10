"""
Core logic for the Week 7 XAI dashboard -- kept separate from the Streamlit
UI file (09_dashboard_app.py) so it can be tested/run from the command line
without needing Streamlit installed, and so the retrieval/explanation logic
is unit-testable.

Pipeline for one query object:
  1. Find its nearest neighbors by embedding cosine similarity (FAISS if
     the index file exists, else a numpy brute-force fallback).
  2. Score each neighbor with the Week 5/6 trained classifier (same
     feature set: cosine_similarity, shared_culture, shared_department,
     fuzzy_temporal_membership, common_neighbors, jaccard, adamic_adar,
     preferential_attachment, node2vec_similarity).
  3. For the top-K by predicted probability, ask the local LLM to write a
     one-paragraph, plain-language rationale.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests

import sys
from pathlib import Path

# Add root folder to sys.path to enable imports when run from webapp_mus folder
sys.path.append(str(Path(__file__).resolve().parent))
sys.path.append(str(Path(__file__).resolve().parent.parent))

from graph_features import load_graph, GraphTopologyIndex, Node2VecEmbeddings

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
LLM_MODEL = "llama3.1"
REQUEST_TIMEOUT = 30

GENERIC_VALUES = {
    "unknown", "unidentified artist", "unidentified", "n/a", "na", "none",
    "various artists", "anonymous",
}


def normalize_value(value):
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in GENERIC_VALUES:
        return None
    return text


class DashboardData:
    """Loads and holds everything the dashboard needs to answer a query."""

    def __init__(
        self,
        metadata_path: str,
        embeddings_path: str,
        ids_path: str,
        model_path: str,
        graph_path: str = "graph/graph.graphml",
    ):
        self.df = pd.read_csv(metadata_path, low_memory=False).set_index("Object ID")
        vectors = np.load(embeddings_path)
        ids = json.loads(Path(ids_path).read_text())
        self.embedding_ids = ids
        self.id_to_row = {oid: i for i, oid in enumerate(ids)}
        # Pre-normalize once so every similarity query is a plain dot product.
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self.normalized_vectors = vectors / norms
        self.model = joblib.load(model_path)
        logger.info(
            "Loaded dashboard data: %d metadata rows, %d embeddings", len(self.df), len(ids)
        )

        logger.info("Loading graph...")
        self.graph = load_graph(graph_path)
        
        logger.info("Computing graph topology features...")
        self.topology_index = GraphTopologyIndex(self.graph)
        
        # Determine the cache folder dynamically based on where graph_path is located
        cache_dir = Path(graph_path).parent.parent / "cache"
        self.node2vec = Node2VecEmbeddings(self.graph, cache_path=cache_dir / "node2vec_embeddings.pkl")

    def object_info(self, object_id: int) -> dict:
        row = self.df.loc[object_id]
        title = row.get("Title")
        if pd.isna(title):
            title = row.get("Object Name") or f"Untitled object #{object_id}"
        return {
            "object_id": object_id,
            "title": title,
            "culture": row.get("culture"),
            "department": row.get("Department"),
            "material": row.get("material"),
            "year": row.get("year"),
            "object_begin_date": row.get("Object Begin Date"),
            "object_end_date": row.get("Object End Date"),
        }

    def nearest_neighbors(self, object_id: int, k: int = 20) -> list[tuple[int, float]]:
        """Top-k most similar objects by cosine similarity, excluding itself."""
        if object_id not in self.id_to_row:
            raise KeyError(f"No embedding found for Object ID {object_id}")
        query = self.normalized_vectors[self.id_to_row[object_id]]
        sims = self.normalized_vectors @ query  # cosine similarity, since already normalized
        top_idx = np.argsort(-sims)[: k + 1]  # +1 in case the object itself is included

        results = []
        for idx in top_idx:
            candidate_id = self.embedding_ids[idx]
            if candidate_id == object_id:
                continue
            results.append((candidate_id, float(sims[idx])))
            if len(results) >= k:
                break
        return results

    def build_features(self, object_id_a: int, object_id_b: int, cosine: float, tolerance: float = 50.0) -> dict:
        a, b = self.df.loc[object_id_a], self.df.loc[object_id_b]
        culture_a, culture_b = normalize_value(a.get("culture")), normalize_value(b.get("culture"))
        dept_a, dept_b = normalize_value(a.get("Department")), normalize_value(b.get("Department"))

        shared_culture = int(culture_a is not None and culture_a == culture_b)
        shared_department = int(dept_a is not None and dept_a == dept_b)

        begin_a, end_a = a.get("Object Begin Date"), a.get("Object End Date")
        begin_b, end_b = b.get("Object Begin Date"), b.get("Object End Date")
        if any(pd.isna(v) for v in (begin_a, end_a, begin_b, end_b)):
            fuzzy_temporal = np.nan
        else:
            gap = max(begin_a, begin_b) - min(end_a, end_b)
            fuzzy_temporal = 1.0 if gap <= 0 else float(np.exp(-(gap ** 2) / (2 * tolerance ** 2)))

        # Graph topology features
        graph_feats = self.topology_index.compute_features(object_id_a, object_id_b)

        # Node2Vec similarity feature
        n2v_sim = self.node2vec.similarity(object_id_a, object_id_b)

        return {
            "cosine_similarity": cosine,
            "shared_culture": shared_culture,
            "shared_department": shared_department,
            "fuzzy_temporal_membership": fuzzy_temporal,
            "common_neighbors": graph_feats["common_neighbors"],
            "jaccard": graph_feats["jaccard"],
            "adamic_adar": graph_feats["adamic_adar"],
            "preferential_attachment": graph_feats["preferential_attachment"],
            "node2vec_similarity": n2v_sim,
        }

    def predict_link_probability(self, features: dict) -> float:
        feature_cols = [
            "cosine_similarity", "shared_culture", "shared_department",
            "common_neighbors", "jaccard", "adamic_adar", "preferential_attachment", "node2vec_similarity",
            "fuzzy_temporal_membership"
        ]
        X = pd.DataFrame([{c: features[c] for c in feature_cols}])
        return float(self.model.predict_proba(X)[0, 1])


def explain_link(info_a: dict, info_b: dict, features: dict, probability: float) -> str:
    """Ask the local LLM for a plain-language rationale. Falls back to a
    template sentence if Ollama is unreachable."""
    prompt = f"""You are assisting a museum curator. Two catalog objects were
flagged as potentially related by a machine learning model. Write ONE short
paragraph (2-3 sentences) in plain language explaining why, using ONLY the
facts given below. Do not invent facts not listed here.

Object A: "{info_a['title']}" ({info_a['culture'] or 'culture unknown'}, {info_a['department'] or 'department unknown'})
Object B: "{info_b['title']}" ({info_b['culture'] or 'culture unknown'}, {info_b['department'] or 'department unknown'})

Facts:
- Predicted link probability: {probability:.0%}
- Textual/semantic similarity score: {features['cosine_similarity']:.2f} (0=unrelated, 1=near-identical descriptions)
- Same culture: {"yes" if features['shared_culture'] else "no"}
- Same department: {"yes" if features['shared_department'] else "no"}
- Estimated date ranges overlap or are close: {"yes" if (not pd.isna(features['fuzzy_temporal_membership']) and features['fuzzy_temporal_membership'] > 0.5) else "unclear or no"}
"""
    try:
        response = requests.post(
            OLLAMA_URL,
            json={"model": LLM_MODEL, "prompt": prompt, "stream": False, "options": {"temperature": 0.3}},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()["response"].strip()
    except (requests.RequestException, KeyError) as exc:
        logger.warning("LLM explanation unavailable (%s), using template fallback", exc)
        return _template_explanation(info_a, info_b, features, probability)


def _template_explanation(info_a: dict, info_b: dict, features: dict, probability: float) -> str:
    reasons = []
    if features["shared_culture"]:
        reasons.append(f"both are attributed to {info_a['culture']}")
    if features["shared_department"]:
        reasons.append(f"both belong to the {info_a['department']} department")
    if not pd.isna(features["fuzzy_temporal_membership"]) and features["fuzzy_temporal_membership"] > 0.5:
        reasons.append("their estimated dates are close or overlapping")
    reasons.append(f"their descriptions have a semantic similarity of {features['cosine_similarity']:.2f}")

    reason_text = "; ".join(reasons)
    return (
        f"System flags a {probability:.0%} link probability between "
        f"\"{info_a['title']}\" and \"{info_b['title']}\", because {reason_text}. "
        f"(offline template explanation -- local LLM unavailable)"
    )


def demo(metadata_path: str, embeddings_path: str, ids_path: str, model_path: str, graph_path: str, object_id: int, top_k: int) -> None:
    """CLI entry point for testing without Streamlit."""
    data = DashboardData(metadata_path, embeddings_path, ids_path, model_path, graph_path)
    query_info = data.object_info(object_id)
    print(f"\nQuery object: {query_info}\n")

    neighbors = data.nearest_neighbors(object_id, k=top_k)
    for candidate_id, cosine in neighbors:
        features = data.build_features(object_id, candidate_id, cosine)
        probability = data.predict_link_probability(features)
        candidate_info = data.object_info(candidate_id)

        print(f"--- Candidate {candidate_id}: {candidate_info['title']} "
              f"(probability={probability:.2%}) ---")
        explanation = explain_link(query_info, candidate_info, features, probability)
        print(explanation)
        print()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", default="met_with_extracted_info.csv")
    parser.add_argument("--embeddings", default="embeddings/embeddings.npy")
    parser.add_argument("--embedding-ids", default="embeddings/embedding_object_ids.json")
    parser.add_argument("--model", default="fuzzy/link_predictor_fuzzy.joblib")
    parser.add_argument("--graph", default="graph/graph.graphml")
    parser.add_argument("--object-id", type=int, required=True)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    demo(args.metadata, args.embeddings, args.embedding_ids, args.model, args.graph, args.object_id, args.top_k)
