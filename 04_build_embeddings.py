"""
Semantic embeddings + FAISS index stage (Month 1, Week 3 of the timeline).

Turns each object's Description into a dense vector using a local Ollama
embedding model, then builds a FAISS index for fast nearest-neighbor
search -- this is the foundation the link-prediction stage (Week 5) will
query against.

Why a dedicated embedding model instead of llama3.1:
  llama3.1 is a chat/completion model, not trained to produce good
  similarity-preserving embeddings. Ollama has dedicated embedding models
  -- this script defaults to `nomic-embed-text` (768-dim, good general
  quality, ~270MB) and also documents `mxbai-embed-large` (1024-dim,
  higher quality, ~670MB) as an alternative. Pull whichever you use first:
      ollama pull nomic-embed-text

Design choices, matching the pattern from 02_ollama_extraction.py:
  - Concurrent requests via ThreadPoolExecutor (--workers).
  - Resumable: embeddings are checkpointed to a .npy file + an Object ID
    list, keyed by position, so a killed/restarted run picks up where it
    left off instead of recomputing everything.
  - Vectors are L2-normalized before indexing, and the FAISS index uses
    inner product (IndexFlatIP) on normalized vectors == cosine similarity.
    This is the standard, numerically-stable way to do cosine similarity
    search in FAISS (there's no dedicated "cosine" index type).

Usage:
    python 04_build_embeddings.py --input met_with_extracted_info.csv
    python 04_build_embeddings.py --input met_with_extracted_info.csv --limit 500  # dev sample
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"  # alternative: "mxbai-embed-large" (higher quality, slower)
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5
SAVE_EVERY = 500


def embed_text(text: str) -> list[float] | None:
    """Call the local Ollama embedding model for one piece of text."""
    if not isinstance(text, str) or not text.strip():
        return None

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(
                OLLAMA_EMBED_URL,
                json={"model": EMBED_MODEL, "prompt": text},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()["embedding"]
        except (requests.RequestException, KeyError) as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    logger.warning("Embedding failed after %d attempts: %s", MAX_RETRIES, last_error)
    return None


def load_checkpoint(embeddings_path: Path, ids_path: Path) -> tuple[dict[int, list[float]], int]:
    """Load previously computed embeddings, keyed by Object ID."""
    if embeddings_path.exists() and ids_path.exists():
        vectors = np.load(embeddings_path)
        ids = json.loads(ids_path.read_text())
        done = dict(zip(ids, vectors.tolist()))
        logger.info("Resuming: %d embeddings already computed", len(done))
        return done, vectors.shape[1] if len(vectors) else 0
    return {}, 0


def save_checkpoint(done: dict[int, list[float]], embeddings_path: Path, ids_path: Path) -> None:
    ids = list(done.keys())
    vectors = np.array([done[i] for i in ids], dtype=np.float32)
    np.save(embeddings_path, vectors)
    ids_path.write_text(json.dumps(ids))


def run(input_path: str, out_dir: str, workers: int, limit: int | None) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    embeddings_path = out / "embeddings.npy"
    ids_path = out / "embedding_object_ids.json"

    df = pd.read_csv(input_path, low_memory=False)
    if limit:
        df = df.head(limit)
    logger.info("Loaded %d rows from %s", len(df), input_path)

    done, _ = load_checkpoint(embeddings_path, ids_path)
    remaining = df[~df["Object ID"].isin(done.keys())]
    logger.info("%d rows remaining to embed", len(remaining))

    processed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_id = {
            executor.submit(embed_text, row["Description"]): row["Object ID"]
            for _, row in remaining.iterrows()
        }
        for future in as_completed(future_to_id):
            object_id = future_to_id[future]
            vector = future.result()
            if vector is not None:
                done[object_id] = vector
            processed += 1

            if processed % SAVE_EVERY == 0:
                save_checkpoint(done, embeddings_path, ids_path)
                logger.info("Checkpoint saved (%d/%d)", processed, len(remaining))

    save_checkpoint(done, embeddings_path, ids_path)
    logger.info("DONE. %d embeddings saved to %s (dim=%d)",
                len(done), embeddings_path, len(next(iter(done.values()))) if done else 0)

    build_faiss_index(embeddings_path, ids_path, out)


def build_faiss_index(embeddings_path: Path, ids_path: Path, out_dir: Path) -> None:
    """Build and save a FAISS cosine-similarity index from the saved embeddings.

    Requires `faiss-cpu` (`pip install faiss-cpu --break-system-packages`).
    Kept as a separate function so embeddings can be recomputed without
    forcing a faiss dependency at import time if it's not installed yet.
    """
    try:
        import faiss
    except ImportError:
        logger.warning(
            "faiss not installed -- skipping index build. Install it with "
            "`pip install faiss-cpu --break-system-packages` and re-run "
            "this script (it will reuse the saved embeddings.npy, no need "
            "to recompute)."
        )
        return

    vectors = np.load(embeddings_path).astype(np.float32)
    faiss.normalize_L2(vectors)  # required for cosine similarity via inner product

    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)

    index_path = out_dir / "met.faiss"
    faiss.write_index(index, str(index_path))
    logger.info("FAISS index saved to %s (%d vectors, dim=%d)",
                index_path, index.ntotal, vectors.shape[1])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="met_with_extracted_info.csv")
    parser.add_argument("--out-dir", default="embeddings")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=None, help="Dev/testing: only embed first N rows")
    args = parser.parse_args()
    run(args.input, args.out_dir, args.workers, args.limit)
