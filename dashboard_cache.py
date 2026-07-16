"""
SQLite-backed cache for the Week 7 curator dashboard.

Problem this solves:
  Every click on "Find related objects" redoes, from scratch:
    - a brute-force cosine-similarity search over all embeddings
    - graph-topology feature lookups (common_neighbors, jaccard, ...)
    - a Node2Vec similarity lookup
    - an XGBoost inference call
    - a full Ollama LLM round-trip to generate the explanation paragraph
  None of this changes between requests for the same (object_id) or the
  same (object_id, candidate_id) pair -- recomputing it every time is pure
  wasted latency, and the LLM call in particular is the slowest part
  (multi-second).

This module adds a small local SQLite database (no server, no extra
service to run) with two tables:
  - neighbor_predictions: up to MAX_CACHED_NEIGHBORS precomputed
    candidate rows per query object (features + probability), so a repeat
    query -- or a query with a smaller `k` than a previous one -- is a
    pure DB read.
  - explanations: the generated LLM text, keyed by (object_id,
    candidate_id), so the same pair is never sent to Ollama twice.

The cache is purely additive / write-through: a miss just means
dashboard_core.py computes the value the normal way once and stores it
here for next time. The dashboard never fails to answer a query just
because the cache is cold or the batch precompute job
(12_precompute_dashboard_cache.py) hasn't reached that object yet.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_CACHE_PATH = Path("dashboard_cache.db")

# How many candidate neighbors we cache per query object. Must be >= the
# largest `k` the UI slider allows (50 -- see 09_dashboard_app.py) so that
# ANY requested k can always be served from one cached batch, instead of
# re-querying embeddings whenever the curator moves the slider.
MAX_CACHED_NEIGHBORS = 50

SCHEMA = """
CREATE TABLE IF NOT EXISTS neighbor_predictions (
    object_id INTEGER NOT NULL,
    candidate_id INTEGER NOT NULL,
    rank INTEGER NOT NULL,
    cosine_similarity REAL,
    shared_culture INTEGER,
    shared_department INTEGER,
    common_neighbors REAL,
    jaccard REAL,
    adamic_adar REAL,
    preferential_attachment REAL,
    node2vec_similarity REAL,
    fuzzy_temporal_membership REAL,
    probability REAL NOT NULL,
    computed_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (object_id, candidate_id)
);

CREATE INDEX IF NOT EXISTS idx_neighbor_object
    ON neighbor_predictions (object_id, probability DESC);

CREATE TABLE IF NOT EXISTS explanations (
    object_id INTEGER NOT NULL,
    candidate_id INTEGER NOT NULL,
    explanation TEXT NOT NULL,
    computed_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (object_id, candidate_id)
);
"""

# Feature keys stored per neighbor row, in a fixed order used by both the
# INSERT and the dict <-> row conversion below.
NEIGHBOR_FEATURE_KEYS = [
    "cosine_similarity", "shared_culture", "shared_department",
    "common_neighbors", "jaccard", "adamic_adar", "preferential_attachment",
    "node2vec_similarity", "fuzzy_temporal_membership",
]


def connect(cache_path: str | Path = DEFAULT_CACHE_PATH) -> sqlite3.Connection:
    """Open (creating if needed) the cache database and ensure the schema exists.

    `check_same_thread=False` because Streamlit can call into the cached
    resource from more than one script-run thread.
    """
    conn = sqlite3.connect(str(cache_path), check_same_thread=False)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def get_cached_neighbors(conn: sqlite3.Connection, object_id: int, k: int) -> list[dict] | None:
    """Return the top-k cached neighbor rows for object_id, sorted by
    predicted probability descending, or None on a cache miss (fewer than
    k rows cached) -- the caller should then compute fresh and call
    store_neighbors().
    """
    needed = min(k, MAX_CACHED_NEIGHBORS)
    (count,) = conn.execute(
        "SELECT COUNT(*) FROM neighbor_predictions WHERE object_id = ?", (object_id,)
    ).fetchone()
    if count < needed:
        return None

    cur = conn.execute(
        f"""
        SELECT candidate_id, {", ".join(NEIGHBOR_FEATURE_KEYS)}, probability
        FROM neighbor_predictions
        WHERE object_id = ?
        ORDER BY probability DESC
        LIMIT ?
        """,
        (object_id, k),
    )
    columns = [d[0] for d in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def store_neighbors(conn: sqlite3.Connection, object_id: int, rows: list[dict]) -> None:
    """Persist up to MAX_CACHED_NEIGHBORS neighbor rows for object_id.

    Each row must have a "candidate_id", a "probability", and all keys in
    NEIGHBOR_FEATURE_KEYS. Overwrites any existing rows for this object
    (INSERT OR REPLACE), so re-running a warm-cache precompute is safe.
    """
    payload = [
        (
            object_id,
            row["candidate_id"],
            rank,
            *(row[k] for k in NEIGHBOR_FEATURE_KEYS),
            row["probability"],
        )
        for rank, row in enumerate(rows[:MAX_CACHED_NEIGHBORS])
    ]
    conn.executemany(
        f"""
        INSERT OR REPLACE INTO neighbor_predictions
            (object_id, candidate_id, rank, {", ".join(NEIGHBOR_FEATURE_KEYS)}, probability)
        VALUES ({", ".join(["?"] * (4 + len(NEIGHBOR_FEATURE_KEYS)))})
        """,
        payload,
    )
    conn.commit()


def get_cached_explanation(conn: sqlite3.Connection, object_id: int, candidate_id: int) -> str | None:
    row = conn.execute(
        "SELECT explanation FROM explanations WHERE object_id = ? AND candidate_id = ?",
        (object_id, candidate_id),
    ).fetchone()
    return row[0] if row else None


def store_explanation(conn: sqlite3.Connection, object_id: int, candidate_id: int, explanation: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO explanations (object_id, candidate_id, explanation) VALUES (?, ?, ?)",
        (object_id, candidate_id, explanation),
    )
    conn.commit()


def cache_stats(conn: sqlite3.Connection) -> dict:
    n_objects = conn.execute(
        "SELECT COUNT(DISTINCT object_id) FROM neighbor_predictions"
    ).fetchone()[0]
    n_rows = conn.execute("SELECT COUNT(*) FROM neighbor_predictions").fetchone()[0]
    n_explanations = conn.execute("SELECT COUNT(*) FROM explanations").fetchone()[0]
    return {
        "objects_with_cached_neighbors": n_objects,
        "neighbor_rows_cached": n_rows,
        "explanations_cached": n_explanations,
    }