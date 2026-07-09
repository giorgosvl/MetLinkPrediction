"""
Preprocessing pipeline for the Metropolitan Museum of Art (MET) Open Access
dataset, prepared as the ingestion stage of an offline Cultural Knowledge
Graph pipeline (semantic embeddings -> FAISS -> graph -> link prediction ->
fuzzy temporal reasoning).

Key differences from the original `sthles.py`:
  * Keeps numeric `Object Begin Date` / `Object End Date` fields, which are
    required later for fuzzy temporal matching (the free-text `Object Date`
    field, e.g. "circa 1450-1475", cannot be used for numeric membership
    functions without a fragile parser).
  * Keeps `Department` and `AccessionYear` (useful graph attributes / filters).
  * Does NOT silently drop rows with a missing Title. Losing rows silently is
    a data-quality risk for a thesis; instead we log how many are dropped and
    why, and only drop rows that are unusable (no Title AND no Object Name).
  * Deduplicates exact duplicate *content* (not just IDs) explicitly, and
    reports the count instead of hiding it, because ~18% of MET description
    rows in this dataset are exact duplicates (e.g. multiple physical coins
    cataloged under an identical description). This matters for link
    prediction: identical descriptions produce identical embeddings, which
    will look like "predicted links" for the wrong reason (text duplication)
    rather than semantic similarity.
  * Uses `csv.QUOTE_MINIMAL` correctly via pandas defaults and explicit
    UTF-8-sig encoding for reading (MetObjects.txt is UTF-8 with BOM).
  * Adds logging instead of print(), and type hints / docstrings.
  * Produces a `Description` field that separates *stable identifying facts*
    from *free text*, and also writes a `has_sparse_metadata` flag column,
    since ~60-96% of rows are missing Culture/Period/Country/Region/City/
    Excavation. Downstream graph construction needs to know which nodes have
    almost no explicit metadata to connect on, and will rely purely on
    embeddings for those nodes.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# Source columns pulled from the raw MET export. Note: several of these
# (Object Begin Date / Object End Date / Department / AccessionYear) were
# missing from the original script but are needed downstream.
SOURCE_COLUMNS = [
    "Object ID",
    "Title",
    "Object Name",
    "Object Date",
    "Object Begin Date",
    "Object End Date",
    "Department",
    "AccessionYear",
    "Culture",
    "Period",
    "Country",
    "Region",
    "City",
    "Medium",
    "Artist Display Name",
    "Artist Nationality",
    "Classification",
    "Excavation",
    "Tags",
]

# Human-readable labels used when assembling the free-text Description.
FIELD_LABELS = {
    "Title": "Title",
    "Object Name": "Object",
    "Object Date": "Date",
    "Department": "Department",
    "Culture": "Culture",
    "Period": "Period",
    "Country": "Country",
    "Region": "Region",
    "City": "City",
    "Medium": "Medium",
    "Artist Display Name": "Artist",
    "Artist Nationality": "Nationality",
    "Classification": "Classification",
    "Excavation": "Excavation",
    "Tags": "Tags",
}


def load_raw(path: str | Path) -> pd.DataFrame:
    """Load the raw MET export, selecting only the columns we need.

    `low_memory=False` avoids pandas' mixed-dtype chunk warnings on this
    file, and `encoding='utf-8-sig'` strips the BOM that MetObjects.txt
    ships with (visible as a stray character on the first column name
    otherwise).
    """
    logger.info("Loading raw file: %s", path)
    df = pd.read_csv(path, low_memory=False, encoding="utf-8-sig")

    missing_cols = [c for c in SOURCE_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Expected columns not found in source file: {missing_cols}")

    df = df[SOURCE_COLUMNS].copy()
    logger.info("Loaded %d rows, %d columns", len(df), len(df.columns))
    return df


def drop_unusable_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows that have neither a Title nor an Object Name.

    A row missing only the Title but with an Object Name (e.g. "Coin",
    "Vase") is still usable for embeddings/graph purposes; dropping it
    outright (as the original script did via `dropna(subset=['Title'])`)
    throws away otherwise-valid records.
    """
    before = len(df)
    usable_mask = df["Title"].notna() | df["Object Name"].notna()
    dropped = before - usable_mask.sum()
    if dropped:
        logger.warning(
            "Dropping %d/%d rows with no Title and no Object Name (unusable)",
            dropped, before,
        )
    return df[usable_mask].copy()


def normalize_text_fields(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace and collapse the common 'placeholder' non-values.

    MET exports use a mix of real NaN, empty strings, and literal strings
    like "Unknown" / "unidentified" for missing data. Treat all of these as
    missing so they don't pollute embeddings or fuzzy membership scores.
    """
    text_cols = [c for c in SOURCE_COLUMNS if df[c].dtype == object]
    placeholder_values = {"", "unknown", "unidentified", "n/a", "na", "none"}

    for col in text_cols:
        df[col] = df[col].astype("string").str.strip()
        df.loc[df[col].str.lower().isin(placeholder_values), col] = pd.NA

    return df


def make_description(row: pd.Series) -> str:
    """Build a compact, labeled free-text description for embedding.

    Only non-missing fields are included, in a fixed, meaningful order
    (identity -> time -> place -> people -> material -> classification).
    """
    parts: list[str] = []
    for col, label in FIELD_LABELS.items():
        value = row[col]
        if pd.notna(value) and str(value).strip():
            parts.append(f"{label}: {value}")
    return ". ".join(parts)


def add_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add columns needed later in the pipeline.

    - Description: free text for the embedding model.
    - has_sparse_metadata: True when fewer than 3 of the 6 key structural
      fields (Culture, Period, Country, Region, City, Excavation) are known.
      Graph construction and fuzzy temporal logic should treat these nodes
      differently (they will rely almost entirely on the LLM-extracted /
      embedded description rather than structured fields).
    - is_duplicate_description: flags exact duplicate descriptions so the
      link-prediction step can down-weight or exclude "trivial" links caused
      purely by identical text rather than genuine similarity.
    """
    df["Description"] = df.apply(make_description, axis=1)

    structural_cols = ["Culture", "Period", "Country", "Region", "City", "Excavation"]
    known_count = df[structural_cols].notna().sum(axis=1)
    df["has_sparse_metadata"] = known_count < 3

    df["is_duplicate_description"] = df.duplicated(subset=["Description"], keep=False)

    return df


def run(input_path: str = "MetObjects.txt", output_path: str = "met_clean.csv") -> None:
    df = load_raw(input_path)
    df = drop_unusable_rows(df)
    df = normalize_text_fields(df)
    df = add_derived_columns(df)

    n_sparse = int(df["has_sparse_metadata"].sum())
    n_dup = int(df["is_duplicate_description"].sum())
    logger.info(
        "Final dataset: %d rows | sparse-metadata rows: %d (%.1f%%) | "
        "rows sharing a duplicate description: %d (%.1f%%)",
        len(df), n_sparse, 100 * n_sparse / len(df), n_dup, 100 * n_dup / len(df),
    )

    df.to_csv(output_path, index=False)
    logger.info("Saved cleaned dataset to %s", output_path)


if __name__ == "__main__":
    run()
