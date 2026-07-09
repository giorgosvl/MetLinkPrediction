"""
Local LLM structured-extraction stage (v2 -- fast).

v1 called the LLM sequentially for every one of the 456K rows, which is
infeasible (hours-to-weeks depending on hardware). This version cuts the
actual LLM workload dramatically, based on a simple fact checked against
your real data: `material`, `year`, and `object_type` are ALREADY known
structured fields (Medium, Object Begin/End Date, Object Name) for the
large majority of rows. Calling an LLM to re-derive them from a description
that was built out of those same fields adds latency and hallucination risk
for zero new information.

Strategy:
  1. FAST PATH (no LLM call): for each row, fill `material`/`year`/
     `object_type`/`culture` directly from the structured source columns
     whenever they are present. This is instant and 100% accurate (it's
     just a copy), and covers the large majority of rows.
  2. LLM PATH (only where genuinely needed): only rows still missing
     `culture` after the fast path get sent to the local model -- that's
     the one field without a reliable 1:1 structured source column, and the
     field where free-text inference can plausibly add value.
  3. The LLM calls that remain are run CONCURRENTLY via a thread pool
     (`--workers`, default 4), which is safe with Ollama as long as you
     raise `OLLAMA_NUM_PARALLEL` (see note below) -- sequential requests
     under-utilize a GPU/CPU that can serve several requests at once.

Before running, if you want real concurrency, start Ollama with:
    OLLAMA_NUM_PARALLEL=4 ollama serve
(4 matches the default --workers below; raise both together if your
hardware can take it, lower both if you see timeouts / OOM.)

Usage:
    python 02_ollama_extraction.py
    python 02_ollama_extraction.py --workers 8 --limit 5000   # e.g. a dev sample
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_INPUT_FILE = "met_clean.csv"
DEFAULT_OUTPUT_FILE = "met_with_extracted_info.csv"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3.1"
SAVE_EVERY = 200
REQUEST_TIMEOUT = 60  # seconds
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5

EXTRACTION_KEYS = ["material", "year", "object_type", "culture"]

PROMPT_TEMPLATE = """You are an information extraction system for museum catalog records.

Infer the CULTURE (people, civilization, or region of origin) implied by the
text below. Use only information present in the text; if it cannot be
inferred, return an empty string.

Return ONLY valid JSON, with no explanation and no markdown code fences, in
exactly this format:
{{"culture": ""}}

TEXT:
{text}
"""


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    return text


def fast_path_extraction(row: pd.Series) -> dict[str, Any]:
    """Fill extraction fields directly from already-structured columns.

    No LLM call, no latency, no hallucination risk -- this is a plain copy.
    """
    year = row.get("Object Date")
    if pd.isna(year) and pd.notna(row.get("Object Begin Date")):
        year = row["Object Begin Date"]

    return {
        "material": row.get("Medium") if pd.notna(row.get("Medium")) else None,
        "year": year if pd.notna(year) else None,
        "object_type": row.get("Object Name") if pd.notna(row.get("Object Name")) else None,
        "culture": row.get("Culture") if pd.notna(row.get("Culture")) else None,
    }


def needs_llm_culture(row: pd.Series) -> bool:
    """Only send rows to the LLM that are missing Culture but have *some*
    contextual text (Description) that could plausibly imply it. Rows with
    an already-known Culture never need an LLM call."""
    return pd.isna(row.get("Culture")) and isinstance(row.get("Description"), str) and len(row["Description"]) > 20


def call_ollama_for_culture(text: str) -> str | None:
    """Call the local model for a single culture inference, with retries."""
    prompt = PROMPT_TEMPLATE.format(text=text)
    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(
                OLLAMA_URL,
                json={
                    "model": MODEL_NAME,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0},
                },
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            raw_output = response.json()["response"]
            data = json.loads(_strip_code_fences(raw_output))
            return data.get("culture") or None

        except (requests.RequestException, json.JSONDecodeError, KeyError) as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    logger.warning("Culture inference failed after %d attempts: %s", MAX_RETRIES, last_error)
    return None


def load_resume_state(source_columns: list[str], output_file: str) -> tuple[pd.DataFrame, set[Any]]:
    output_path = Path(output_file)
    if output_path.exists():
        done_df = pd.read_csv(output_path)
        done_ids = set(done_df["Object ID"])
        logger.info("Resuming: %d rows already processed", len(done_ids))
        return done_df, done_ids
    logger.info("No existing output found, starting from scratch")
    return pd.DataFrame(columns=source_columns + EXTRACTION_KEYS), set()


def run(input_file: str, output_file: str, workers: int = 4, limit: int | None = None) -> None:
    source_df = pd.read_csv(input_file, low_memory=False)
    if limit:
        source_df = source_df.head(limit)

    done_df, done_ids = load_resume_state(list(source_df.columns), output_file)
    remaining = source_df[~source_df["Object ID"].isin(done_ids)].reset_index(drop=True)
    logger.info("%d rows remaining", len(remaining))

    # --- Step 1: fast path for every remaining row (no LLM) ---
    merged_rows: list[dict[str, Any]] = []
    llm_needed_indices: list[int] = []
    for idx, row in remaining.iterrows():
        merged = {**row.to_dict(), **fast_path_extraction(row)}
        merged_rows.append(merged)
        if needs_llm_culture(row):
            llm_needed_indices.append(idx)

    logger.info(
        "Fast path filled %d/%d rows with no LLM call. %d rows need an LLM culture inference.",
        len(merged_rows) - len(llm_needed_indices), len(merged_rows), len(llm_needed_indices),
    )

    # --- Step 2: concurrent LLM calls only for the rows that need it ---
    results = done_df.to_dict("records")
    results.extend(merged_rows)  # fast-path values already in place; LLM will patch culture in below

    processed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_idx = {
            executor.submit(call_ollama_for_culture, remaining.iloc[idx]["Description"]): idx
            for idx in llm_needed_indices
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            culture = future.result()
            # position in `results` = len(done_df) + idx, since merged_rows was appended in order
            results[len(done_df) + idx]["culture"] = culture
            processed += 1

            if processed % SAVE_EVERY == 0:
                pd.DataFrame(results).to_csv(output_file, index=False)
                logger.info("Checkpoint saved (%d/%d LLM calls done)", processed, len(llm_needed_indices))

    pd.DataFrame(results).to_csv(output_file, index=False)
    logger.info("DONE. Final file saved to %s (%d total rows, %d LLM calls made)",
                output_file, len(results), len(llm_needed_indices))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=DEFAULT_INPUT_FILE, help="Input CSV (e.g. met_clean.csv or met_sample_50000.csv)")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_FILE, help="Output CSV path")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent Ollama requests")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N rows (dev/testing)")
    args = parser.parse_args()
    run(input_file=args.input, output_file=args.output, workers=args.workers, limit=args.limit)
