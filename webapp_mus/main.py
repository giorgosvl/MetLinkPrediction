"""
FastAPI backend for the MET Cultural Knowledge Graph dashboard.

Thin routing layer over `dashboard_core.py` (the same, already-tested module
used by the Streamlit version) -- no business logic lives here, only HTTP
wiring. That keeps this file low-risk: the actual search / prediction /
explanation logic was already validated end-to-end before this existed.

Run:
    pip install fastapi uvicorn[standard]
    uvicorn main:app --reload --port 8000

The React frontend (Vite dev server, http://localhost:5173) is allowed via
CORS below -- adjust the origin if you serve the frontend differently.
"""

from __future__ import annotations

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from dashboard_core import DashboardData, explain_link

app = FastAPI(title="MET Cultural Knowledge Graph API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA: DashboardData | None = None


@app.on_event("startup")
def load_data() -> None:
    global DATA
    DATA = DashboardData(
        metadata_path="../met_with_extracted_info.csv",
        embeddings_path="../embeddings/embeddings.npy",
        ids_path="../embeddings/embedding_object_ids.json",
        model_path="../fuzzy/link_predictor_fuzzy.joblib",
    )


class ObjectSummary(BaseModel):
    object_id: int
    title: str
    culture: str | None = None
    department: str | None = None
    material: str | None = None
    year: str | None = None


class RelatedObject(BaseModel):
    object: ObjectSummary
    probability: float
    cosine_similarity: float
    shared_culture: bool
    shared_department: bool
    explanation: str


def _to_summary(info: dict) -> ObjectSummary:
    return ObjectSummary(
        object_id=info["object_id"],
        title=str(info["title"]),
        culture=info.get("culture") if pd.notna(info.get("culture")) else None,
        department=info.get("department") if pd.notna(info.get("department")) else None,
        material=info.get("material") if pd.notna(info.get("material")) else None,
        year=str(info.get("year")) if pd.notna(info.get("year")) else None,
    )


@app.get("/api/search", response_model=list[ObjectSummary])
def search(q: str = Query("", description="Search term matched against Title"), limit: int = 20):
    df = DATA.df
    searchable = df[df.index.isin(DATA.id_to_row.keys())]

    if q:
        title_or_name = searchable["Title"].fillna(searchable["Object Name"])
        searchable = searchable[title_or_name.str.contains(q, case=False, na=False)]

    results = []
    for object_id in searchable.head(limit).index:
        results.append(_to_summary(DATA.object_info(object_id)))
    return results


@app.get("/api/object/{object_id}", response_model=ObjectSummary)
def get_object(object_id: int):
    try:
        return _to_summary(DATA.object_info(object_id))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Object {object_id} not found")


@app.get("/api/related/{object_id}", response_model=list[RelatedObject])
def get_related(object_id: int, k: int = 8, explain: bool = True):
    try:
        query_info = DATA.object_info(object_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Object {object_id} not found")

    try:
        neighbors = DATA.nearest_neighbors(object_id, k=k)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No embedding available for object {object_id}")

    results = []
    for candidate_id, cosine in neighbors:
        features = DATA.build_features(object_id, candidate_id, cosine)
        probability = DATA.predict_link_probability(features)
        candidate_info = DATA.object_info(candidate_id)

        explanation = ""
        if explain:
            explanation = explain_link(query_info, candidate_info, features, probability)

        results.append(RelatedObject(
            object=_to_summary(candidate_info),
            probability=probability,
            cosine_similarity=features["cosine_similarity"],
            shared_culture=bool(features["shared_culture"]),
            shared_department=bool(features["shared_department"]),
            explanation=explanation,
        ))

    results.sort(key=lambda r: -r.probability)
    return results


@app.get("/api/health")
def health():
    return {"status": "ok", "objects_loaded": len(DATA.df) if DATA else 0}