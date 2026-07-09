"""
Diagnostic: is the Week 5/6 link predictor properly calibrated, or does its
predicted probability saturate near 1.0 for anything above a similarity
threshold (making the 99% shown for every dashboard result meaningless)?

Two checks:
  1. Synthetic sweep: hold shared_culture/department/temporal fixed, vary
     cosine_similarity smoothly from 0 to 1 -- a well-behaved classifier's
     probability should also increase smoothly, not jump to a plateau.
  2. Real distribution: histogram of predicted probabilities across the
     actual training dataset -- if the vast majority of scores are above
     0.95, the "probability" is not doing much discriminating work at the
     high end, even if overall ROC-AUC looks good (AUC only cares about
     ranking, not about calibration).

Usage:
    python 10_calibration_check.py --model fuzzy/link_predictor_fuzzy.joblib --dataset fuzzy/link_prediction_dataset_with_fuzzy.csv
"""

from __future__ import annotations

import argparse

import joblib
import numpy as np
import pandas as pd


def synthetic_sweep(model) -> None:
    print("\n=== Synthetic sweep: cosine_similarity from 0.0 to 1.0 ===")
    print("(shared_culture=1, shared_department=1, fuzzy_temporal_membership=1.0 held fixed)\n")
    for cos in np.arange(0.0, 1.01, 0.05):
        row = pd.DataFrame([{
            "cosine_similarity": cos,
            "shared_culture": 1,
            "shared_department": 1,
            "fuzzy_temporal_membership": 1.0,
        }])
        prob = model.predict_proba(row)[0, 1]
        bar = "#" * int(prob * 40)
        print(f"cosine={cos:.2f}  prob={prob:.4f}  {bar}")


def real_distribution(model, dataset_path: str) -> None:
    print(f"\n=== Real probability distribution on {dataset_path} ===")
    data = pd.read_csv(dataset_path)
    feature_cols = ["cosine_similarity", "shared_culture", "shared_department", "fuzzy_temporal_membership"]
    probs = model.predict_proba(data[feature_cols])[:, 1]

    print(f"n = {len(probs)}")
    print(f"mean={probs.mean():.4f}  median={np.median(probs):.4f}  std={probs.std():.4f}")
    for threshold in [0.5, 0.8, 0.9, 0.95, 0.99]:
        pct = (probs >= threshold).mean() * 100
        print(f"  fraction with probability >= {threshold}: {pct:.1f}%")

    print("\nHistogram (10 bins):")
    counts, edges = np.histogram(probs, bins=10, range=(0, 1))
    for i, count in enumerate(counts):
        bar = "#" * int(count / max(counts) * 40) if max(counts) else ""
        print(f"  [{edges[i]:.1f}-{edges[i+1]:.1f}) {count:6d}  {bar}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="fuzzy/link_predictor_fuzzy.joblib")
    parser.add_argument("--dataset", default="fuzzy/link_prediction_dataset_with_fuzzy.csv")
    args = parser.parse_args()

    model = joblib.load(args.model)
    synthetic_sweep(model)
    real_distribution(model, args.dataset)
