"""
Week 7: Curator-facing XAI dashboard (Streamlit).

Thin UI layer on top of `08_dashboard_core.py` -- all the actual retrieval /
prediction / explanation logic lives there so it can be tested without
Streamlit. This file just wires it up to widgets.

Usage:
    streamlit run 09_dashboard_app.py
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard_core import DashboardData, explain_link

st.set_page_config(page_title="MET Cultural Knowledge Graph", layout="wide")


@st.cache_resource
def load_data():
    return DashboardData(
        metadata_path="met_with_extracted_info.csv",
        embeddings_path="embeddings/embeddings.npy",
        ids_path="embeddings/embedding_object_ids.json",
        model_path="fuzzy/link_predictor_fuzzy.joblib",
    )


st.title("MET Cultural Knowledge Graph — Curator Dashboard")
st.caption(
    "Search a catalog object to see machine-predicted relationships to "
    "other objects in the collection, with plain-language explanations."
)

try:
    data = load_data()
except FileNotFoundError as exc:
    st.error(
        f"Missing pipeline output: {exc}\n\n"
        "Make sure you've run, in order: 01_preprocessing.py -> "
        "03_sample_dataset.py -> 02_ollama_extraction.py -> "
        "04_build_embeddings.py -> 05_build_graph.py -> "
        "06_link_prediction.py -> 07_fuzzy_temporal.py, "
        "before launching this dashboard."
    )
    st.stop()

# --- Search ---
search_term = st.text_input("Search by title", placeholder="e.g. Lincoln, vase, portrait...")

if search_term:
    matches = data.df[data.df["Title"].fillna(data.df["Object Name"]).str.contains(
        search_term, case=False, na=False
    )]
    matches = matches[matches.index.isin(data.id_to_row.keys())]  # must have an embedding
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

top_k = st.slider("Number of candidate relationships to show", min_value=3, max_value=20, value=8)

if st.button("Find related objects", type="primary"):
    with st.spinner("Searching embeddings and scoring candidates..."):
        neighbors = data.nearest_neighbors(selected_id, k=top_k)
        scored = []
        for candidate_id, cosine in neighbors:
            features = data.build_features(selected_id, candidate_id, cosine)
            probability = data.predict_link_probability(features)
            scored.append((candidate_id, features, probability))
        scored.sort(key=lambda x: -x[2])

    st.divider()
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

            with st.spinner("Generating explanation..."):
                explanation = explain_link(query_info, candidate_info, features, probability)
            st.write(explanation)