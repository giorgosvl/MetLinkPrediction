"""
Diagnostic: is the ~0.65-0.75 cosine_similarity threshold seen in the
10_calibration_check.py synthetic sweep a genuine property of the data, or
still an artifact?

After fixing graph-topology leakage and node2vec leakage (both derived from
has_artist/has_tag hubs) and adding monotonic constraints, the model's
probability curve became smooth and monotonic but still rises steeply
between cosine ~0.65 and ~0.75. This script checks the RAW
cosine_similarity values in link_prediction_dataset_with_fuzzy.csv, split
by label, to see whether that steepness reflects a real gap between how
similar "genuinely related" vs "unrelated" object descriptions are -- with
no model involved at all, just the embedding geometry.

If the label==1 and label==0 distributions are clearly separated around
that same 0.65-0.75 region, the model's behavior is trustworthy: it's
recovering a real property of the description embeddings, worth reporting
plainly in the thesis as a property of the data/embedding model rather
than as a limitation. If the two distributions overlap heavily and the
model is *still* this confident, that's a sign something else is still
inflating the classifier's confidence and deserves another look.

Usage:
    python 11_check_separability.py --dataset fuzzy/link_prediction_dataset_with_fuzzy.csv
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd


def describe(values: pd.Series, label: str) -> None:
    print(f"\n{label} (n={len(values)}):")
    print(f"  mean={values.mean():.4f}  median={values.median():.4f}  std={values.std():.4f}")
    for q in (0.1, 0.25, 0.5, 0.75, 0.9):
        print(f"  p{int(q*100):02d} = {values.quantile(q):.4f}")


def run(dataset_path: str) -> None:
    data = pd.read_csv(dataset_path)
    if "label" not in data.columns or "cosine_similarity" not in data.columns:
        raise ValueError("Expected columns 'label' and 'cosine_similarity' not found.")

    pos = data.loc[data["label"] == 1, "cosine_similarity"]
    neg = data.loc[data["label"] == 0, "cosine_similarity"]

    describe(pos, "label=1 (genuinely related pairs)")
    describe(neg, "label=0 (unrelated / negative-sampled pairs)")

    # Simple, model-free separability check: what fraction of negatives
    # have a HIGHER cosine_similarity than the median positive, and vice
    # versa? Heavy overlap here (large fractions both ways) would suggest
    # the classifier's near-binary confidence is not fully justified by
    # cosine_similarity alone; near-zero overlap corroborates it.
    median_pos = pos.median()
    median_neg = neg.median()
    frac_neg_above_median_pos = (neg > median_pos).mean()
    frac_pos_below_median_neg = (pos < median_neg).mean()

    print("\n--- Overlap check ---")
    print(f"Median cosine_similarity: positives={median_pos:.4f}  negatives={median_neg:.4f}")
    print(f"Fraction of NEGATIVES above the POSITIVE median: {frac_neg_above_median_pos:.1%}")
    print(f"Fraction of POSITIVES below the NEGATIVE median: {frac_pos_below_median_neg:.1%}")

    print("\nHistogram, positives vs negatives (10 bins over [0,1]):")
    bins = np.linspace(0, 1, 11)
    pos_counts, _ = np.histogram(pos.dropna(), bins=bins)
    neg_counts, _ = np.histogram(neg.dropna(), bins=bins)
    for i in range(10):
        lo, hi = bins[i], bins[i + 1]
        print(f"  [{lo:.1f}-{hi:.1f})  pos={pos_counts[i]:6d}  neg={neg_counts[i]:6d}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="fuzzy/link_prediction_dataset_with_fuzzy.csv")
    args = parser.parse_args()
    run(args.dataset)
