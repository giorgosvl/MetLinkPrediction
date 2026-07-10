"""
Fuzzy temporal matching stage (Month 2, Week 6 of the timeline).

Replaces the raw `year_gap` feature from Week 5 with a proper fuzzy
membership score that reflects historical dating uncertainty, and then
re-trains the Week 5 classifier to measure whether it actually helps --
producing the ablation evidence a thesis reviewer will ask for.

FUZZY MEMBERSHIP FUNCTION:
  For two date ranges [a_begin, a_end] and [b_begin, b_end]:
    gap = max(a_begin, b_begin) - min(a_end, b_end)
  If gap <= 0, the ranges overlap -> membership = 1.0 (full confidence
  they belong to the "same era").
  If gap > 0, membership decays smoothly with the size of the gap using a
  Gaussian-style curve, controlled by `--tolerance` (in years, default 50):
    membership = exp(-(gap^2) / (2 * tolerance^2))

Usage:
    python 07_fuzzy_temporal.py \
        --dataset link_prediction/link_prediction_dataset.csv \
        --metadata met_with_extracted_info.csv
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from xgboost import XGBClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import classification_report, roc_auc_score, confusion_matrix
from sklearn.model_selection import train_test_split

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# Same domain knowledge as 06_link_prediction.py's MONOTONIC_DIRECTIONS
# (kept in sync manually rather than imported, since "06_link_prediction"
# is not a valid Python module name to import from). None of these
# features should ever have a negative marginal effect on link
# probability with everything else held fixed, and year_gap should never
# have a positive one. This is what removes the non-monotonic dips seen
# in the calibration sweep (e.g. probability dropping as cosine_similarity
# rises from 0.60 to 0.65).
MONOTONIC_DIRECTIONS: dict[str, int] = {
    "cosine_similarity": 1,
    "shared_culture": 1,
    "shared_department": 1,
    "common_neighbors": 1,
    "jaccard": 1,
    "adamic_adar": 1,
    "preferential_attachment": 0,
    "node2vec_similarity": 1,
    "fuzzy_temporal_membership": 1,
    "year_gap": -1,
}


def monotone_constraints_for(feature_cols: list[str]) -> str:
    directions = [str(MONOTONIC_DIRECTIONS.get(c, 0)) for c in feature_cols]
    return "(" + ",".join(directions) + ")"


def fuzzy_temporal_membership(
    a_begin: float, a_end: float, b_begin: float, b_end: float, tolerance: float
) -> float:
    """Degree of truth in [0, 1] that two date ranges represent 'the same
    historical era'. 1.0 = overlapping ranges, decaying smoothly to 0 the
    further apart they are, at a rate controlled by `tolerance` (years)."""
    if any(pd.isna(v) for v in (a_begin, a_end, b_begin, b_end)):
        return np.nan

    gap = max(a_begin, b_begin) - min(a_end, b_end)
    if gap <= 0:
        return 1.0
    return float(np.exp(-(gap ** 2) / (2 * tolerance ** 2)))


def train_and_evaluate(data: pd.DataFrame, feature_cols: list[str], seed: int = 42) -> dict:
    X, y = data[feature_cols], data["label"]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=seed, stratify=y
    )
    
    # XGBClassifier replacement
    model = XGBClassifier(
        learning_rate=0.05,
        max_depth=5,
        n_estimators=500,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=seed,
        eval_metric="logloss",
        n_jobs=-1,
        tree_method="hist",
        monotone_constraints=monotone_constraints_for(feature_cols),
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, y_proba)
    cm = confusion_matrix(y_test, y_pred)

    importance = permutation_importance(model, X_test, y_test, n_repeats=10, random_state=seed)
    importance_summary = {
        col: round(float(imp), 4)
        for col, imp in sorted(zip(feature_cols, importance.importances_mean), key=lambda x: -x[1])
    }

    return {
        "features_used": feature_cols,
        "roc_auc": round(auc, 4),
        "confusion_matrix": cm.tolist(),
        "feature_importance": importance_summary,
        "classification_report": classification_report(y_test, y_pred, target_names=["not_linked", "linked"]),
    }, model


def run(dataset_path: str, metadata_path: str, out_dir: str, tolerance: float) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    data = pd.read_csv(dataset_path)
    meta = pd.read_csv(metadata_path, low_memory=False).set_index("Object ID")
    logger.info("Loaded %d pairs, %d metadata rows", len(data), len(meta))

    logger.info("Computing fuzzy temporal membership (tolerance=%.0f years)", tolerance)
    fuzzy_scores = []
    for row in data.itertuples():
        a, b = meta.loc[row.object_id_a], meta.loc[row.object_id_b]
        fuzzy_scores.append(
            fuzzy_temporal_membership(
                a["Object Begin Date"], a["Object End Date"],
                b["Object Begin Date"], b["Object End Date"],
                tolerance,
            )
        )
    data["fuzzy_temporal_membership"] = fuzzy_scores

    known = data["fuzzy_temporal_membership"].notna().sum()
    logger.info("Fuzzy temporal score computed for %d/%d pairs (rest have missing dates)", known, len(data))

    # --- Ablation: year_gap alone vs fuzzy_temporal_membership alone vs both ---
    base_features = [
        "cosine_similarity", "shared_culture", "shared_department",
        "common_neighbors", "jaccard", "adamic_adar", "preferential_attachment", "node2vec_similarity"
    ]
    variants = {
        "raw_year_gap_only": base_features + ["year_gap"],
        "fuzzy_temporal_only": base_features + ["fuzzy_temporal_membership"],
        "both_temporal_features": base_features + ["year_gap", "fuzzy_temporal_membership"],
    }

    results = {}
    for name, feature_cols in variants.items():
        logger.info("--- Training variant: %s ---", name)
        logger.info("Training XGBoost...")
        metrics, model = train_and_evaluate(data, feature_cols)
        results[name] = metrics
        logger.info("%s -> ROC-AUC=%.4f, importances=%s", name, metrics["roc_auc"], metrics["feature_importance"])
        if name == "fuzzy_temporal_only":
            import joblib
            joblib.dump(model, out / "link_predictor_fuzzy.joblib")

    data.to_csv(out / "link_prediction_dataset_with_fuzzy.csv", index=False)
    (out / "fuzzy_ablation_results.json").write_text(json.dumps(
        {k: {kk: vv for kk, vv in v.items() if kk != "classification_report"} for k, v in results.items()},
        indent=2,
    ))
    logger.info("Saved dataset and ablation results to %s", out)
    logger.info("Evaluation completed.")

    logger.info("\n=== SUMMARY: does fuzzy temporal matching help? ===")
    for name, metrics in results.items():
        logger.info("%-24s ROC-AUC=%.4f", name, metrics["roc_auc"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="link_prediction/link_prediction_dataset.csv")
    parser.add_argument("--metadata", default="met_with_extracted_info.csv")
    parser.add_argument("--out-dir", default="fuzzy")
    parser.add_argument("--tolerance", type=float, default=50.0,
                         help="Years over which temporal membership decays to near-zero")
    args = parser.parse_args()
    run(args.dataset, args.metadata, args.out_dir, args.tolerance)