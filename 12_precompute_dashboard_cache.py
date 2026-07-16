"""
Warms the dashboard's SQLite cache (dashboard_cache.py) for every object
that has an embedding, so that during a live demo / thesis defense no
query is ever a cold cache miss (which would otherwise mean a
brute-force embedding search + graph feature lookups + XGBoost inference
happening live, in front of an audience).

Run this ONCE, fully, before opening the Streamlit dashboard. After it
finishes, 09_dashboard_app.py never computes anything live -- every
"Find related objects" click is a pure SQLite read, INCLUDING the first
time any given object is queried, because it was already computed here.

Two things get precomputed:
  1. neighbor_predictions (search results + probability) for every object
     -- always done, this is the expensive brute-force + inference part.
  2. explanations (the LLM-written paragraph) for the top
     `--explanations-top-n` candidates of every object -- OFF by default
     (--explanations-top-n 0), because it is much slower (one Ollama call
     per pair) and most curator sessions never look at every single
     candidate for every single object. Turn it on if you specifically
     want the *text* to be instant too, not just the probability.

Usage:
    python 12_precompute_dashboard_cache.py
    python 12_precompute_dashboard_cache.py --limit 500                 # dev/testing
    python 12_precompute_dashboard_cache.py --explanations-top-n 3      # also pre-write
                                                                         # explanations for
                                                                         # the top 3 candidates
                                                                         # of every object
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from dashboard_core import DashboardData

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# Same reasoning as in 09_dashboard_app.py: anchor default paths to this
# script's own folder (the repo root), not to whatever directory you
# happen to run `python 12_precompute_dashboard_cache.py` from -- so this
# always warms the SAME dashboard_cache.db the Streamlit app reads.
# (webapp_mus/ is a separate, unrelated Vite/React project -- ignore its
# leftover dashboard_core.py.)
REPO_ROOT = Path(__file__).resolve().parent


def run(metadata_path: str, embeddings_path: str, ids_path: str, model_path: str,
        graph_path: str, cache_path: str, k: int, limit: int | None,
        explanations_top_n: int) -> None:
    data = DashboardData(metadata_path, embeddings_path, ids_path, model_path, graph_path, cache_path)

    object_ids = list(data.embedding_ids)
    if limit:
        object_ids = object_ids[:limit]

    logger.info(
        "Precomputing neighbor cache for %d objects (k=%d)%s",
        len(object_ids), k,
        f", plus top-{explanations_top_n} explanations per object" if explanations_top_n else "",
    )

    start = time.time()
    for i, object_id in enumerate(object_ids, start=1):
        related = data.get_related_objects(object_id, k=k)  # write-through: computes + caches

        if explanations_top_n:
            query_info = data.object_info(object_id)
            for candidate_id, features, probability in related[:explanations_top_n]:
                candidate_info = data.object_info(candidate_id)
                data.explain_link_cached(object_id, candidate_id, query_info, candidate_info, features, probability)

        if i % 200 == 0 or i == len(object_ids):
            elapsed = time.time() - start
            rate = i / elapsed
            remaining = (len(object_ids) - i) / rate if rate > 0 else float("inf")
            logger.info(
                "%d/%d done (%.1f objects/s, ~%.0fs remaining)",
                i, len(object_ids), rate, remaining,
            )

    import dashboard_cache
    stats = dashboard_cache.cache_stats(data.db)
    logger.info("DONE. Cache is fully warm. Stats: %s", stats)
    logger.info(
        "You can now run `streamlit run 09_dashboard_app.py` -- every "
        "query, including the first one for any object, will be served "
        "straight from %s.", cache_path,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", default=str(REPO_ROOT / "met_with_extracted_info.csv"))
    parser.add_argument("--embeddings", default=str(REPO_ROOT / "embeddings" / "embeddings.npy"))
    parser.add_argument("--embedding-ids", default=str(REPO_ROOT / "embeddings" / "embedding_object_ids.json"))
    parser.add_argument("--model", default=str(REPO_ROOT / "fuzzy" / "link_predictor_fuzzy.joblib"))
    parser.add_argument("--graph", default=str(REPO_ROOT / "graph" / "graph.graphml"))
    parser.add_argument("--cache", default=str(REPO_ROOT / "dashboard_cache.db"))
    parser.add_argument("--k", type=int, default=50, help="How many neighbors to cache per object (should match dashboard_cache.MAX_CACHED_NEIGHBORS)")
    parser.add_argument("--limit", type=int, default=None, help="Only precompute the first N objects (dev/testing)")
    parser.add_argument("--explanations-top-n", type=int, default=0,
                         help="Also pre-generate LLM explanations for the top N candidates of every object (slow, off by default)")
    args = parser.parse_args()
    run(args.metadata, args.embeddings, args.embedding_ids, args.model, args.graph, args.cache, args.k, args.limit, args.explanations_top_n)