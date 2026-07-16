"""
Week 7: Curator-facing XAI dashboard (Streamlit) - 100% INDEPENDENT & OPTIMIZED.
"""

from __future__ import annotations

import sqlite3
import json
from pathlib import Path
import pandas as pd
import streamlit as st

# Reuse the ALREADY EXISTING Ollama-calling logic + cache helpers.
# Importing this module is lightweight (it does not build the graph or
# load the model -- that only happens if DashboardData() is instantiated,
# which we deliberately do NOT do here, keeping this page's fast/independent
# startup exactly as it was).
from dashboard_core import explain_link
import dashboard_cache as dc

st.set_page_config(page_title="MET Cultural Knowledge Graph", layout="wide")

REPO_ROOT = Path(__file__).resolve().parent
CACHE_DB_PATH = REPO_ROOT / "dashboard_cache.db"
METADATA_PATH = REPO_ROOT / "met_with_extracted_info.csv"

# ----------------------------------------------------------------------
# ⚡ ΑΥΤΟΝΟΜΗ & ΕΛΑΦΡΙΑ ΚΛΑΣΗ ΣΥΝΔΕΣΗΣ ΜΕ ΤΗ ΒΑΣΗ (ΔΕΝ ΚΑΛΕΙ ΤΟ DASHBOARD_CORE)
# ----------------------------------------------------------------------
class FastDashboardData:
    def __init__(self, metadata_path: str, cache_path: str):
        self.db_path = cache_path
        # Φορτώνουμε μόνο το CSV των metadata που είναι απαραίτητο για το UI search
        self.df = pd.read_csv(metadata_path, low_memory=False)
        self.df.set_index("Object ID", inplace=True, drop=False)
        
        # Ανοίγουμε σύνδεση με τη SQLite
        self.db = sqlite3.connect(cache_path, check_same_thread=False)
        
        # Φορτώνουμε τα IDs που έχουν embeddings απευθείας από τη βάση δεδομένων
        self.embedding_ids = self._get_available_object_ids()
        self.id_to_row = {oid: oid for oid in self.embedding_ids}

    def _get_available_object_ids(self) -> list[int]:
        cursor = self.db.cursor()
        # Χρησιμοποιούμε τον σωστό πίνακα 'neighbor_predictions' και τη στήλη 'object_id'
        cursor.execute("SELECT DISTINCT object_id FROM neighbor_predictions")
        return [row[0] for row in cursor.fetchall()]

    def object_info(self, object_id: int) -> dict:
        """Επιστρέφει τις βασικές πληροφορίες για το UI."""
        if object_id not in self.df.index:
            return {"title": "Unknown", "culture": None, "department": None, "material": None, "year": None}
        row = self.df.loc[object_id]
        
        # Υπολογισμός χρονολογίας
        begin = row.get("Object Begin Date")
        end = row.get("Object End Date")
        year_str = "—"
        if pd.notna(begin) and pd.notna(end):
            year_str = f"{int(begin)} - {int(end)}"
        elif pd.notna(begin):
            year_str = str(int(begin))

        return {
            "title": row.get("Title") if pd.notna(row.get("Title")) else row.get("Object Name", "Untitled"),
            "culture": row.get("culture") if pd.notna(row.get("culture")) else None,
            "department": row.get("Department") if pd.notna(row.get("Department")) else None,
            "material": row.get("Medium") if pd.notna(row.get("Medium")) else None,
            "year": year_str,
        }

    def get_related_objects(self, query_id: int, k: int = 8) -> list[tuple[int, dict, float]]:
        """Ανάκτηση των συσχετίσεων απευθείας από τη SQLite (neighbor_predictions)."""
        cursor = self.db.cursor()
        
        cursor.execute("PRAGMA table_info(neighbor_predictions);")
        columns = [col[1] for col in cursor.fetchall()]
        feat_col = "features_json" if "features_json" in columns else ("features" if "features" in columns else None)
        prob_col = "probability" if "probability" in columns else ("score" if "score" in columns else "predicted_prob")

        if feat_col:
            query = f"SELECT candidate_id, {feat_col}, {prob_col} FROM neighbor_predictions WHERE object_id = ? ORDER BY {prob_col} DESC LIMIT ?"
        else:
            query = f"SELECT candidate_id, NULL, {prob_col} FROM neighbor_predictions WHERE object_id = ? ORDER BY {prob_col} DESC LIMIT ?"

        cursor.execute(query, (query_id, k))
        results = []
        for candidate_id, features_raw, probability in cursor.fetchall():
            features = {}
            if features_raw:
                try:
                    features = json.loads(features_raw)
                except Exception:
                    pass
            results.append((candidate_id, features, probability))
        return results

    def batch_get_explanations(self, query_id: int, candidate_ids: list[int]) -> dict[int, str]:
        """⚡ Batch fetch επεξηγήσεων με 1 SQL query από τον πίνακα explanations!"""
        if not candidate_ids:
            return {}
        cursor = self.db.cursor()
        placeholders = ",".join("?" for _ in candidate_ids)
        cursor.execute(
            f"SELECT candidate_id, explanation FROM explanations "
            f"WHERE object_id = ? AND candidate_id IN ({placeholders})",
            [query_id] + candidate_ids
        )
        return {row[0]: row[1] for row in cursor.fetchall()}


# ----------------------------------------------------------------------
# 🚀 ΦΟΡΤΩΣΗ ΔΕΔΟΜΕΝΩΝ (Smart Setup)
# ----------------------------------------------------------------------
@st.cache_resource
def load_data():
    if CACHE_DB_PATH.exists():
        st.info("⚡ Fast Mode Active: Running purely on precomputed SQLite Cache.")
        return FastDashboardData(
            metadata_path=str(METADATA_PATH),
            cache_path=str(CACHE_DB_PATH),
        )
    else:
        st.error(
            f"❌ Cache database not found at {CACHE_DB_PATH}. "
            "Please run 12_precompute_dashboard_cache.py to generate the database first!"
        )
        st.stop()


st.title("MET Cultural Knowledge Graph — Curator Dashboard")
st.caption(
    "Search a catalog object to see machine-predicted relationships to "
    "other objects in the collection, with plain-language explanations."
)
st.caption(f"🗄️ Cache file in use: `{CACHE_DB_PATH}`")

try:
    data = load_data()
except FileNotFoundError as exc:
    st.error(f"Missing pipeline output: {exc}")
    st.stop()


# --- Search ---
search_term = st.text_input("Search by title", placeholder="e.g. Lincoln, vase, portrait...")

if search_term:
    matches = data.df[data.df["Title"].fillna(data.df["Object Name"]).str.contains(
        search_term, case=False, na=False
    )]
    matches = matches[matches.index.isin(data.id_to_row.keys())]
else:
    matches = data.df[data.df.index.isin(data.id_to_row.keys())].head(20)

if matches.empty:
    st.info("No matching objects with available embeddings found.")
    st.stop()

options = {
    f"{idx} — {row['Title'] if pd.notna(row['Title']) else row['Object Name']}": idx
    for idx, row in matches.iterrows()
}
selected_label = st.selectbox("Select an object", list(options.keys()))
selected_id = options[selected_label]

query_info = data.object_info(selected_id)

st.subheader(query_info["title"])
col1, col2, col3, col4 = st.columns(4)
col1.metric("Culture", query_info["culture"] or "—")
col2.metric("Department", query_info["department"] or "—")
col3.metric("Material", query_info["material"] or "—")
col4.metric("Date", str(query_info["year"] or "—"))

top_k = st.slider("Number of candidate relationships to show", min_value=3, max_value=50, value=8)


def _safe_features_for_llm(features: dict) -> dict:
    """Fill in any feature keys explain_link() expects that happen to be
    missing/None in this particular cached row, so a live LLM call never
    crashes on a KeyError -- it just falls back to a neutral value."""
    return {
        "cosine_similarity": features.get("cosine_similarity") or 0.0,
        "shared_culture": features.get("shared_culture") or 0,
        "shared_department": features.get("shared_department") or 0,
        "fuzzy_temporal_membership": features.get("fuzzy_temporal_membership", float("nan")),
    }


# ⚡ NOTE: results are kept in st.session_state (not just the `if
# st.button(...)` block) on purpose. Streamlit reruns the WHOLE script on
# every widget interaction -- including a click on the new per-card
# "Explain the relationship" button below. Without session_state, that
# click would make `st.button("Find related objects")` evaluate to False
# again on the rerun, and the entire results list would disappear the
# moment someone tried to use the new feature.
if "related_results" not in st.session_state:
    st.session_state.related_results = None
    st.session_state.related_query_id = None

if st.button("Find related objects", type="primary"):
    # ⚡ 1. Παίρνουμε τις σχέσεις ακαριαία από τη SQLite
    with st.spinner("Searching database..."):
        st.session_state.related_results = data.get_related_objects(selected_id, k=top_k)
        st.session_state.related_query_id = selected_id

scored = st.session_state.related_results
if scored is not None and st.session_state.related_query_id == selected_id:
    if not scored:
        st.info("No related objects found in database for this ID.")
        st.stop()

    st.divider()

    # ⚡ 2. Παίρνουμε τις (έτοιμες, template) επεξηγήσεις σε BATCH με ΕΝΑ query
    candidate_ids = [candidate_id for candidate_id, _, _ in scored]
    with st.spinner("Fetching explanations..."):
        explanations_cache = data.batch_get_explanations(selected_id, candidate_ids)

    # 3. Εμφάνιση των αποτελεσμάτων ακαριαία
    for candidate_id, features, probability in scored:
        candidate_info = data.object_info(candidate_id)
        with st.container(border=True):
            left, right = st.columns([3, 1])
            with left:
                st.markdown(f"**{candidate_info['title']}**")
                st.caption(
                    f"{candidate_info['culture'] or 'culture unknown'} · "
                    f"{candidate_info['department'] or 'department unknown'} · "
                    f"{candidate_info['year'] or 'date unknown'}"
                )
            with right:
                st.metric("Link probability", f"{probability:.0%}")

            # Εμφάνιση της έτοιμης (template) επεξήγησης -- ΟΠΩΣ ΠΡΙΝ, καμία αλλαγή.
            explanation = explanations_cache.get(candidate_id, "📝 *Explanation precomputation missing for this pair.*")
            st.write(explanation)

            # -----------------------------------------------------------
            # 🧠 NEW FEATURE: on-demand, REAL LLM explanation via Ollama.
            # Extra/optional -- does not replace the template text above.
            # -----------------------------------------------------------
            session_key = f"llm_explanation_{selected_id}_{candidate_id}"
            if st.button("🧠 Explain the relationship", key=f"explain_btn_{selected_id}_{candidate_id}"):
                with st.spinner("Asking the local LLM (Ollama)..."):
                    live_text = explain_link(
                        query_info,
                        candidate_info,
                        _safe_features_for_llm(features),
                        probability,
                    )
                # Persist so it's instant next time (any future page load,
                # not just this session) -- reuses the existing cache table.
                dc.store_explanation(data.db, selected_id, candidate_id, live_text)
                st.session_state[session_key] = live_text

            if session_key in st.session_state:
                st.success(st.session_state[session_key])