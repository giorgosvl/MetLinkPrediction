"""
Structural graph assembly stage (Month 1, Week 4 of the timeline).

Builds a graph of explicit, concrete links between museum objects, based
purely on already-known structured metadata (no embeddings yet -- that
comes later, at the link-prediction stage in Week 5).

KEY DESIGN DECISION -- heterogeneous graph, not pairwise cliques:
  A naive approach ("if two objects share an artist, connect them
  directly") creates a combinatorial explosion: in this dataset, the
  single most common Artist Display Name ("W. Duke, Sons & Co.", a
  cigarette-card manufacturer) covers 1,052 objects. Connecting every
  pair within that group alone would create 552,826 edges -- more than
  the entire 50,000-row dataset.

  Instead, this script builds a BIPARTITE / heterogeneous graph:
      object --[has_artist]--> Artist:<name>
      object --[has_department]--> Department:<name>
      object --[has_culture]--> Culture:<name>
      object --[has_tag]--> Tag:<value>
  Attribute values become their own nodes ("hubs"). Two objects sharing
  an attribute are connected only *indirectly*, through that hub. This
  keeps the graph size linear in the number of (object, attribute) pairs
  instead of quadratic in group size, and is the standard way knowledge
  graphs represent this kind of many-to-many relationship.

  Generic, non-identifying values are excluded from becoming edges at all
  (e.g. "Unknown", "Unidentified artist") -- they would create a
  meaningless mega-hub connecting almost everything to almost everything.

WHAT THIS SCRIPT PRODUCES for the next stage (Week 5, link prediction):
  Link prediction needs actual object-object PAIRS to train on (positive
  examples = "these two are genuinely related"). Enumerating all pairs
  that share a hub is still combinatorially large for big hubs, so this
  script samples a capped number of pairs per attribute value
  (--max-pairs-per-group, default 15) instead of all of them. This keeps
  the positive-pair set diverse across many different artists/tags
  instead of being dominated by the few largest groups.

Outputs:
  - graph.graphml           the full heterogeneous graph (for inspection,
                             e.g. in Gephi, or reloading with networkx)
  - candidate_pairs.csv     sampled object-object pairs with the shared
                             attribute that justifies the link (ground
                             truth positives for Week 5)
  - graph_stats.json        summary statistics

Usage:
    python 05_build_graph.py --input met_with_extracted_info.csv
"""

from __future__ import annotations

import argparse
import json
import logging
import random
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import networkx as nx
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# Values that should NEVER become graph hubs -- they are placeholders for
# "we don't know", not real shared identity. Connecting objects through
# these would create meaningless mega-hubs.
GENERIC_VALUES = {
    "unknown", "unidentified artist", "unidentified", "n/a", "na", "none",
    "various artists", "anonymous",
}

# Which columns become attribute-node hubs, and the edge-type label used.
# Deliberately excludes very high-cardinality-but-low-specificity fields
# (see note in module docstring re: Culture/Department below).
HUB_COLUMNS = {
    "Artist Display Name": "has_artist",
    "Department": "has_department",
}
# Culture and Classification are included too, but flagged as LOW
# SPECIFICITY hubs: "American" or "Prints" cover a huge fraction of the
# dataset and are not meaningful evidence of a real relationship on their
# own. We still add them to the graph (useful for other purposes, e.g.
# the fuzzy logic stage), but we do NOT sample candidate link-prediction
# pairs from them -- see `PAIR_SAMPLING_COLUMNS` below.
HUB_COLUMNS_LOW_SPECIFICITY = {
    "culture": "has_culture",         # LLM-extracted/fast-path culture field
    "Classification": "has_classification",
}

# Only these hub types are used to sample *candidate positive pairs* for
# link prediction -- they indicate a genuinely specific, non-generic
# shared identity (a named artist/manufacturer, or a specific tag/theme),
# unlike broad categorical buckets like Culture or Classification.
PAIR_SAMPLING_HUB_TYPES = {"has_artist", "has_tag"}

# A hub with more than this many connected objects is treated the same
# way as Culture/Classification: too generic to be meaningful evidence of
# a real relationship (e.g. the tag "Men" covers 12,376 objects in this
# dataset -- sharing it says almost nothing specific about two objects).
# It ALSO prevents a memory blow-up: naively enumerating all pairs for a
# 12,376-object hub is 76.5 million pairs before any sampling happens.
MAX_GROUP_SIZE_FOR_PAIR_SAMPLING = 200


def normalize_value(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in GENERIC_VALUES:
        return None
    return text


def add_object_nodes(graph: nx.Graph, df: pd.DataFrame) -> None:
    for _, row in df.iterrows():
        node_id = f"obj:{row['Object ID']}"
        graph.add_node(
            node_id,
            node_type="object",
            title=row.get("Title"),
            classification=row.get("Classification"),
            culture=row.get("culture"),
            material=row.get("material"),
            year=row.get("year"),
            department=row.get("Department"),
            has_sparse_metadata=bool(row.get("has_sparse_metadata", False)),
        )


def add_hub_edges(graph: nx.Graph, df: pd.DataFrame, column: str, edge_type: str) -> int:
    """Add object->attribute-hub edges for one column. Returns edge count."""
    count = 0
    for _, row in df.iterrows():
        value = normalize_value(row.get(column))
        if value is None:
            continue
        object_node = f"obj:{row['Object ID']}"
        hub_node = f"{edge_type}:{value}"
        if hub_node not in graph:
            graph.add_node(hub_node, node_type="hub", hub_type=edge_type, value=value)
        graph.add_edge(object_node, hub_node, edge_type=edge_type)
        count += 1
    return count


def add_tag_edges(graph: nx.Graph, df: pd.DataFrame) -> int:
    """Tags are pipe-delimited (e.g. 'Men|Portraits'), so they need splitting
    rather than being treated as one column value like the other hubs."""
    count = 0
    for _, row in df.iterrows():
        tags_raw = row.get("Tags")
        if pd.isna(tags_raw):
            continue
        object_node = f"obj:{row['Object ID']}"
        for tag in str(tags_raw).split("|"):
            tag = normalize_value(tag)
            if tag is None:
                continue
            hub_node = f"has_tag:{tag}"
            if hub_node not in graph:
                graph.add_node(hub_node, node_type="hub", hub_type="has_tag", value=tag)
            graph.add_edge(object_node, hub_node, edge_type="has_tag")
            count += 1
    return count


def sample_candidate_pairs(
    graph: nx.Graph, max_pairs_per_group: int, seed: int = 42
) -> list[dict]:
    """For each hub used in PAIR_SAMPLING_HUB_TYPES, sample up to
    `max_pairs_per_group` object-object pairs connected through it.

    Capping prevents a few giant hubs (e.g. a manufacturer with 1,000+
    objects) from dominating the positive-pair set used to train the
    Week 5 link predictor -- without the cap, the classifier would mostly
    just learn to recognize a handful of huge groups instead of general
    relational structure.
    """
    rng = random.Random(seed)
    pairs: list[dict] = []
    skipped_generic_hubs = 0

    for hub_node, attrs in graph.nodes(data=True):
        if attrs.get("node_type") != "hub" or attrs.get("hub_type") not in PAIR_SAMPLING_HUB_TYPES:
            continue
        neighbors = list(graph.neighbors(hub_node))
        if len(neighbors) < 2:
            continue

        if len(neighbors) > MAX_GROUP_SIZE_FOR_PAIR_SAMPLING:
            # Too generic (e.g. tag "Men") -- skip entirely rather than
            # treating a huge, low-information group as ground truth, and
            # rather than materializing millions of pairs in memory.
            skipped_generic_hubs += 1
            continue

        # Safe to enumerate now: bounded by
        # MAX_GROUP_SIZE_FOR_PAIR_SAMPLING**2 / 2 in the worst case.
        all_pairs = list(combinations(neighbors, 2))
        sampled = (
            rng.sample(all_pairs, max_pairs_per_group)
            if len(all_pairs) > max_pairs_per_group
            else all_pairs
        )
        for obj_a, obj_b in sampled:
            pairs.append({
                "object_id_a": obj_a.replace("obj:", ""),
                "object_id_b": obj_b.replace("obj:", ""),
                "shared_hub_type": attrs["hub_type"],
                "shared_value": attrs["value"],
                "group_size": len(neighbors),
            })

    logger.info(
        "Skipped %d hub(s) larger than %d objects (too generic for pair sampling)",
        skipped_generic_hubs, MAX_GROUP_SIZE_FOR_PAIR_SAMPLING,
    )
    return pairs


def compute_stats(graph: nx.Graph, df: pd.DataFrame, pairs: list[dict]) -> dict:
    object_nodes = [n for n, a in graph.nodes(data=True) if a.get("node_type") == "object"]
    hub_nodes = [n for n, a in graph.nodes(data=True) if a.get("node_type") == "hub"]

    isolated_objects = sum(1 for n in object_nodes if graph.degree(n) == 0)

    hub_type_counts: dict[str, int] = defaultdict(int)
    for _, attrs in graph.nodes(data=True):
        if attrs.get("node_type") == "hub":
            hub_type_counts[attrs["hub_type"]] += 1

    dedup_pairs = {tuple(sorted((p["object_id_a"], p["object_id_b"]))) for p in pairs}

    return {
        "total_rows_in_input": len(df),
        "object_nodes": len(object_nodes),
        "hub_nodes": len(hub_nodes),
        "hub_nodes_by_type": dict(hub_type_counts),
        "total_edges": graph.number_of_edges(),
        "isolated_objects_no_edges": isolated_objects,
        "isolated_objects_pct": round(100 * isolated_objects / len(object_nodes), 1),
        "candidate_positive_pairs_sampled": len(pairs),
        "unique_object_pairs_after_dedup": len(dedup_pairs),
    }


def run(input_path: str, out_dir: str, max_pairs_per_group: int) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(input_path, low_memory=False)
    logger.info("Loaded %d rows from %s", len(df), input_path)

    graph = nx.Graph()
    add_object_nodes(graph, df)

    for column, edge_type in HUB_COLUMNS.items():
        n = add_hub_edges(graph, df, column, edge_type)
        logger.info("Added %d edges for %s (%s)", n, column, edge_type)

    for column, edge_type in HUB_COLUMNS_LOW_SPECIFICITY.items():
        n = add_hub_edges(graph, df, column, edge_type)
        logger.info("Added %d edges for %s (%s) [low-specificity, not used for pair sampling]", n, column, edge_type)

    n_tags = add_tag_edges(graph, df)
    logger.info("Added %d tag edges", n_tags)

    pairs = sample_candidate_pairs(graph, max_pairs_per_group)
    logger.info("Sampled %d candidate positive pairs (capped at %d per group)", len(pairs), max_pairs_per_group)

    stats = compute_stats(graph, df, pairs)
    logger.info("Graph stats: %s", json.dumps(stats, indent=2))

    # Save outputs
    nx.write_graphml(graph, out / "graph.graphml")
    pd.DataFrame(pairs).to_csv(out / "candidate_pairs.csv", index=False)
    (out / "graph_stats.json").write_text(json.dumps(stats, indent=2))

    logger.info("Saved graph.graphml, candidate_pairs.csv, graph_stats.json to %s", out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="met_with_extracted_info.csv")
    parser.add_argument("--out-dir", default="graph")
    parser.add_argument("--max-pairs-per-group", type=int, default=15,
                         help="Cap on sampled object pairs per shared-attribute group")
    args = parser.parse_args()
    run(args.input, args.out_dir, args.max_pairs_per_group)
