"""
Representative 50,000-row sampling stage.

Runs after preprocessing (01_preprocessing.py). Purpose: shrink the dataset
from ~456K to a fixed, high-quality, diverse sample that is:
  - large enough for meaningful embeddings / graph / link-prediction work
  - small enough to realistically process end-to-end on consumer hardware
    within the LLM extraction time budget
  - NOT a naive random sample -- a naive `df.sample(50000)` would inherit the
    same problems as the full dataset (18% duplicate descriptions, and
    heavily skewed toward a few Classifications like Prints/Photographs
    which make up >100K rows on their own), giving a biased, lower-quality
    subset.

Method:
  1. Drop exact-duplicate descriptions, keeping the highest-quality copy of
     each (duplicates add no new information to embeddings/link prediction
     and were flagged as a data-quality issue in the review).
  2. Compute a `quality_score` per row = count of populated informative
     fields (Culture, Period, Country, Region, City, Medium, Artist, Artist
     Nationality, Classification, Excavation, Tags) + 1 if Object Date is
     present. Rows with very low scores contribute little signal to the
     graph/link-prediction stages downstream.
  3. Filter out rows below a minimum quality threshold (`--min-quality`,
     default 3) -- these are rows the model realistically cannot learn
     useful structure from.
  4. Stratified sampling across `Classification` (the most complete
     categorical field, ~83% populated) so the 50K sample preserves the
     shape of the collection rather than being dominated by the 2-3 largest
     categories, while still favoring higher-quality rows within each
     stratum.

Usage:
    python 03_sample_dataset.py --input met_clean.csv --output met_sample_50000.csv --n 50000
"""

from __future__ import annotations

import argparse
import logging

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

QUALITY_FIELDS = [
    "Culture", "Period", "Country", "Region", "City", "Medium",
    "Artist Display Name", "Artist Nationality", "Classification",
    "Excavation", "Tags",
]


def compute_quality_score(df: pd.DataFrame) -> pd.Series:
    score = df[QUALITY_FIELDS].notna().sum(axis=1)
    if "Object Date" in df.columns:
        score = score + df["Object Date"].notna().astype(int)
    return score


def drop_duplicate_descriptions(df: pd.DataFrame, quality: pd.Series) -> pd.DataFrame:
    before = len(df)
    df = df.assign(_quality=quality)
    # keep the highest-quality row per duplicate description group
    df = df.sort_values("_quality", ascending=False)
    df = df.drop_duplicates(subset=["Description"], keep="first")
    df = df.drop(columns="_quality")
    logger.info("Dropped %d exact-duplicate-description rows (%d -> %d)",
                before - len(df), before, len(df))
    return df


def stratified_sample(df: pd.DataFrame, n: int, strata_col: str = "Classification") -> pd.DataFrame:
    """Sample n rows total, proportionally across strata, favoring higher
    quality_score within each stratum. Rows with missing strata value are
    grouped into a single 'Unknown' bucket rather than dropped."""
    df = df.copy()
    df[strata_col] = df[strata_col].fillna("Unknown")

    strata_sizes = df[strata_col].value_counts()
    proportions = (strata_sizes / strata_sizes.sum() * n).round().astype(int)

    # Correct rounding drift so totals sum exactly to n
    drift = n - proportions.sum()
    if drift != 0:
        proportions.iloc[0] += drift

    sampled_parts = []
    for stratum, k in proportions.items():
        if k <= 0:
            continue
        group = df[df[strata_col] == stratum].sort_values("quality_score", ascending=False)
        sampled_parts.append(group.head(k))

    sample = pd.concat(sampled_parts, ignore_index=True)

    # If under-filled due to small strata running out of rows, top up
    # from the highest-quality remaining rows overall.
    if len(sample) < n:
        remaining_needed = n - len(sample)
        used_ids = set(sample["Object ID"])
        topup = (
            df[~df["Object ID"].isin(used_ids)]
            .sort_values("quality_score", ascending=False)
            .head(remaining_needed)
        )
        sample = pd.concat([sample, topup], ignore_index=True)
        logger.info("Topped up %d rows from highest-quality remainder", len(topup))

    return sample


def run(input_path: str, output_path: str, n: int, min_quality: int) -> None:
    df = pd.read_csv(input_path, low_memory=False)
    logger.info("Loaded %d rows from %s", len(df), input_path)

    quality = compute_quality_score(df)
    df = drop_duplicate_descriptions(df, quality)

    df["quality_score"] = compute_quality_score(df)
    before = len(df)
    df = df[df["quality_score"] >= min_quality].copy()
    logger.info("Dropped %d rows below min_quality=%d (%d -> %d)",
                before - len(df), min_quality, before, len(df))

    if len(df) < n:
        logger.warning(
            "Only %d rows available after filtering, which is fewer than "
            "the requested sample size %d -- returning all available rows.",
            len(df), n,
        )
        n = len(df)

    sample = stratified_sample(df, n)
    sample = sample.drop(columns="quality_score")
    sample = sample.sort_values("Object ID").reset_index(drop=True)

    sample.to_csv(output_path, index=False)
    logger.info("Saved %d-row representative sample to %s", len(sample), output_path)

    # Quick diagnostic summary
    logger.info("Sample Classification distribution (top 10):\n%s",
                sample["Classification"].fillna("Unknown").value_counts().head(10))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="met_clean.csv")
    parser.add_argument("--output", default="met_sample_50000.csv")
    parser.add_argument("--n", type=int, default=50000)
    parser.add_argument("--min-quality", type=int, default=3,
                         help="Minimum number of populated informative fields to keep a row")
    args = parser.parse_args()
    run(args.input, args.output, args.n, args.min_quality)
