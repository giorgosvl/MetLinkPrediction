"""
Link prediction stage (Month 2, Week 5 of the timeline).

Trains a lightweight classifier that estimates the probability two museum
objects are genuinely related, using:
  - semantic similarity (cosine similarity of their Week 3 embeddings)
  - coarse structural features (shared culture, shared department, how far
    apart their estimated dates are)

CRITICAL DESIGN DECISION -- avoiding a circular / trivial classifier:
  The Week 4 positive pairs (candidate_pairs.csv) were generated because
  two objects share a specific Artist or Tag. If we gave the classifier
  "shares the same artist" as an input feature, it would trivially learn
  "shared_artist == True -> predict link" and get ~100% accuracy without
  ever using the embeddings -- that's not link prediction, that's just
  memorizing how the labels were constructed.

  So the artist/tag identity is used ONLY to generate the ground-truth
  label (comes from a real, concrete, documented relationship) and is
  DELIBERATELY EXCLUDED from the feature set. The classifier only sees:
      [cosine_similarity, shared_culture, shared_department, year_gap]
  This mirrors the real deployment scenario described in the proposal:
  predicting a probable relationship between two objects using semantic
  and coarse metadata signals, without already knowing the specific fact
  (same documented artisan) that would make the answer obvious.

NEGATIVE SAMPLING:
  Random pairs of objects that do NOT share an artist or tag (so they are
  not "secretly" positives we happened not to sample in Week 4), sampled
  1:1 with positives for a balanced training set.

MODEL:
  HistGradientBoostingClassifier (scikit-learn). Chosen over a plain MLP
  for a project at this stage because:
    - it natively handles missing values (many objects have no known
      date range), no imputation hacks needed
    - it needs far less hyperparameter tuning / data than an MLP to get a
      reasonable baseline, which matters given only ~30-60K training pairs
    - built-in feature importance for the write-up / XAI stage (Week 7)
  This satisfies the proposal's "MLP or simple gradient-boosting model"
  requirement -- gradient boosting is the better-justified default here.

Usage:
    python 06_link_prediction.py \
        --embeddings embeddings/embeddings.npy \
        --embedding-ids embeddings/embedding_object_ids.json \
        --pairs graph/candidate_pairs.csv \
        --metadata met_with_extracted_info.csv
"""

from __future__ import annotations

import argparse
import json
import logging
import random
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    classification_report,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

GENERIC_VALUES = {
    "unknown", "unidentified artist", "unidentified", "n/a", "na", "none",
    "various artists", "anonymous",
}


def normalize_value(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in GENERIC_VALUES:
        return None
    return text


def load_embeddings(embeddings_path: str, ids_path: str) -> dict[int, np.ndarray]:
    vectors = np.load(embeddings_path)
    ids = json.loads(Path(ids_path).read_text())
    if len(ids) != len(vectors):
        raise ValueError(
            f"Mismatch: {len(ids)} ids but {len(vectors)} embedding vectors -- "
            "the embeddings file and id-mapping file are out of sync."
        )
    embeddings = dict(zip(ids, vectors))
    logger.info("Loaded %d embeddings (dim=%d)", len(embeddings), vectors.shape[1])
    return embeddings


def build_identity_index(df: pd.DataFrame) -> dict[int, set[str]]:
    """For each Object ID, the set of 'specific identity' tokens
    (artist name, individual tags) used to check that a sampled negative
    pair doesn't actually share a concrete identity (which would make it
    a mislabeled negative)."""
    index: dict[int, set[str]] = {}
    for _, row in df.iterrows():
        tokens: set[str] = set()
        artist = normalize_value(row.get("Artist Display Name"))
        if artist:
            tokens.add(f"artist:{artist}")
        tags_raw = row.get("Tags")
        if pd.notna(tags_raw):
            for tag in str(tags_raw).split("|"):
                tag = normalize_value(tag)
                if tag:
                    tokens.add(f"tag:{tag}")
        index[row["Object ID"]] = tokens
    return index


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def midpoint_year(row: pd.Series) -> float:
    begin, end = row.get("Object Begin Date"), row.get("Object End Date")
    if pd.notna(begin) and pd.notna(end):
        return (float(begin) + float(end)) / 2
    if pd.notna(begin):
        return float(begin)
    if pd.notna(end):
        return float(end)
    return np.nan


def build_features(
    object_id_a: int, object_id_b: int,
    embeddings: dict[int, np.ndarray], meta: dict[int, dict],
) -> dict | None:
    if object_id_a not in embeddings or object_id_b not in embeddings:
        return None
    a, b = meta[object_id_a], meta[object_id_b]

    cos = cosine_sim(embeddings[object_id_a], embeddings[object_id_b])
    shared_culture = int(
        a["culture"] is not None and a["culture"] == b["culture"]
    )
    shared_department = int(
        a["department"] is not None and a["department"] == b["department"]
    )
    year_a, year_b = a["year_mid"], b["year_mid"]
    year_gap = abs(year_a - year_b) if not (np.isnan(year_a) or np.isnan(year_b)) else np.nan

    return {
        "object_id_a": object_id_a,
        "object_id_b": object_id_b,
        "cosine_similarity": cos,
        "shared_culture": shared_culture,
        "shared_department": shared_department,
        "year_gap": year_gap,
    }


def sample_negatives(
    all_ids: list[int], identity_index: dict[int, set[str]],
    positive_pairs: set[tuple[int, int]], n_needed: int, seed: int = 42,
) -> list[tuple[int, int]]:
    rng = random.Random(seed)
    negatives: set[tuple[int, int]] = set()
    max_attempts = n_needed * 50
    attempts = 0

    while len(negatives) < n_needed and attempts < max_attempts:
        attempts += 1
        a, b = rng.sample(all_ids, 2)
        pair = tuple(sorted((a, b)))
        if pair in positive_pairs or pair in negatives:
            continue
        if identity_index.get(a, set()) & identity_index.get(b, set()):
            continue  # they actually DO share a concrete identity -- not a valid negative
        negatives.add(pair)

    if len(negatives) < n_needed:
        logger.warning(
            "Could only sample %d/%d negatives after %d attempts",
            len(negatives), n_needed, attempts,
        )
    return list(negatives)


def run(embeddings_path: str, ids_path: str, pairs_path: str, metadata_path: str,
        out_dir: str, seed: int = 42) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    embeddings = load_embeddings(embeddings_path, ids_path)
    df = pd.read_csv(metadata_path, low_memory=False)
    positive_df = pd.read_csv(pairs_path)

    logger.info("Building per-object metadata (culture/department/year midpoint)")
    meta: dict[int, dict] = {}
    for _, row in df.iterrows():
        meta[row["Object ID"]] = {
            "culture": normalize_value(row.get("culture")),
            "department": normalize_value(row.get("Department")),
            "year_mid": midpoint_year(row),
        }
    identity_index = build_identity_index(df)

    # --- Positive examples ---
    positive_pairs_set = {
        tuple(sorted((int(r.object_id_a), int(r.object_id_b))))
        for r in positive_df.itertuples()
    }
    positive_rows = []
    for a, b in positive_pairs_set:
        feats = build_features(a, b, embeddings, meta)
        if feats:
            feats["label"] = 1
            positive_rows.append(feats)
    logger.info(
        "%d/%d positive pairs have embeddings for both objects (usable)",
        len(positive_rows), len(positive_pairs_set),
    )

    # --- Negative examples (1:1 with usable positives) ---
    all_ids = [oid for oid in df["Object ID"] if oid in embeddings]
    negatives = sample_negatives(all_ids, identity_index, positive_pairs_set, len(positive_rows), seed)
    negative_rows = []
    for a, b in negatives:
        feats = build_features(a, b, embeddings, meta)
        if feats:
            feats["label"] = 0
            negative_rows.append(feats)
    logger.info("%d negative pairs sampled", len(negative_rows))

    data = pd.DataFrame(positive_rows + negative_rows)
    if len(data) < 50:
        raise ValueError(
            f"Only {len(data)} usable training pairs -- too few objects have "
            "embeddings. Make sure Week 3 (04_build_embeddings.py) has finished "
            "for a large enough share of your dataset before running this step."
        )

    feature_cols = ["cosine_similarity", "shared_culture", "shared_department", "year_gap"]
    X, y = data[feature_cols], data["label"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=seed, stratify=y
    )

    logger.info("Training HistGradientBoostingClassifier on %d pairs (%d train / %d test)",
                len(data), len(X_train), len(X_test))
    model = HistGradientBoostingClassifier(random_state=seed)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]

    auc = roc_auc_score(y_test, y_proba)
    report = classification_report(y_test, y_pred, target_names=["not_linked", "linked"])
    logger.info("Test ROC-AUC: %.3f", auc)
    logger.info("Classification report:\n%s", report)

    importance = permutation_importance(model, X_test, y_test, n_repeats=10, random_state=seed)
    importance_summary = {
        col: round(float(imp), 4)
        for col, imp in sorted(
            zip(feature_cols, importance.importances_mean), key=lambda x: -x[1]
        )
    }
    logger.info("Permutation feature importance: %s", json.dumps(importance_summary, indent=2))

    # Save everything needed for Week 6 (fuzzy logic will refine year_gap
    # into a proper membership score) and Week 7 (XAI dashboard).
    data.to_csv(out / "link_prediction_dataset.csv", index=False)
    import joblib
    joblib.dump(model, out / "link_predictor.joblib")
    (out / "evaluation.json").write_text(json.dumps({
        "roc_auc": round(auc, 4),
        "n_train": len(X_train),
        "n_test": len(X_test),
        "feature_importance": importance_summary,
    }, indent=2))

    logger.info("Saved dataset, model, and evaluation metrics to %s", out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--embeddings", default="embeddings/embeddings.npy")
    parser.add_argument("--embedding-ids", default="embeddings/embedding_object_ids.json")
    parser.add_argument("--pairs", default="graph/candidate_pairs.csv")
    parser.add_argument("--metadata", default="met_with_extracted_info.csv")
    parser.add_argument("--out-dir", default="link_prediction")
    args = parser.parse_args()
    run(args.embeddings, args.embedding_ids, args.pairs, args.metadata, args.out_dir)
