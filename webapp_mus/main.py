"""
FastAPI backend for the MET Cultural Knowledge Graph dashboard.
FULLY AUTONOMOUS LIVE OLLAMA VERSION - No dashboard_core dependencies.
"""

from __future__ import annotations

import sqlite3
import json
from pathlib import Path
import pandas as pd
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="MET Cultural Knowledge Graph API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent if BACKEND_DIR.name == "webapp_mus" else BACKEND_DIR

CACHE_DB_PATH = REPO_ROOT / "dashboard_cache.db"
METADATA_PATH = REPO_ROOT / "met_with_extracted_info.csv"

# Όνομα του μοντέλου Ollama που θα χρησιμοποιηθεί
OLLAMA_MODEL = "llama3.1" 

class ObjectSummary(BaseModel):
    object_id: int
    title: str
    culture: str | None
    department: str | None
    medium: str | None
    year: str | None
    image_url: str | None  # 🖼️ Προσθήκη στήλης για το URL της εικόνας

class RelatedObject(BaseModel):
    object: ObjectSummary
    probability: float
    cosine_similarity: float
    shared_culture: bool
    shared_department: bool
    explanation: str

class ExplainRequest(BaseModel):
    source_object_id: int
    target_object_id: int

class ExplainResponse(BaseModel):
    explanation: str
    metrics: dict

DF_META: pd.DataFrame | None = None

@app.on_event("startup")
def load_data() -> None:
    global DF_META
    if not CACHE_DB_PATH.exists():
        raise FileNotFoundError(f"❌ Cache database not found at {CACHE_DB_PATH}.")
    
    print("⚡ Loading metadata CSV...")
    DF_META = pd.read_csv(METADATA_PATH, low_memory=False)
    DF_META.set_index("Object ID", inplace=True, drop=False)
    print("⚡ Autonomous Hybrid backend is ready!")

def get_db_connection():
    conn = sqlite3.connect(CACHE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_object_info(object_id: int) -> dict:
    global DF_META
    title = f"Unknown Object ({object_id})"
    culture = None
    department = None
    medium = None
    year_str = "—"
    image_url = ""

    # 1. Τράβηγμα στοιχείων από το CSV
    if DF_META is not None and object_id in DF_META.index:
        row = DF_META.loc[object_id]
        
        title = row.get("Title") if pd.notna(row.get("Title")) else row.get("Object Name", "Untitled")
        culture = row.get("culture") if pd.notna(row.get("culture")) else None
        department = row.get("Department") if pd.notna(row.get("Department")) else None
        medium = row.get("Medium") if pd.notna(row.get("Medium")) else None
        
        begin = row.get("Object Begin Date")
        end = row.get("Object End Date")
        if pd.notna(begin) and pd.notna(end):
            year_str = f"{int(begin)} - {int(end)}"
        elif pd.notna(begin):
            year_str = str(int(begin))

    # 2. 🌐 Live κλήση στο API του MET για να βρούμε την ΠΡΑΓΜΑΤΙΚΗ εικόνα του συγκεκριμένου ID
    try:
        met_api_url = f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{object_id}"
        res = requests.get(met_api_url, timeout=2.0)
        if res.status_code == 200:
            data = res.json()
            # Παίρνουμε τη μικρή εικόνα (primaryImageSmall) για να φορτώνει σφαίρα το UI
            image_url = data.get("primaryImageSmall", data.get("primaryImage", ""))
    except Exception:
        pass 

    # Αν το μουσείο δεν έχει καθόλου φωτογραφία για το έκθεμα, βάζουμε ένα default placeholder
    if not image_url:
        image_url = "https://images.unsplash.com/photo-1580136579312-94651dfd596d?w=500" 

    return {
        "object_id": int(object_id),
        "title": str(title),
        "culture": culture,
        "department": department,
        "medium": medium,
        "year": year_str,
        "image_url": image_url  # 👈 Επιστρέφεται σωστά πλέον!
    }

# ----------------------------------------------------------------------
# 🤖 ΑΥΤΟΝΟΜΗ LIVE ΓΕΝΝΗΣΗ ΕΠΕΞΗΓΗΣΗΣ ΜΕΣΩ OLLAMA API
# ----------------------------------------------------------------------
def generate_ollama_explanation_live(query_info: dict, cand_info: dict, features: dict, probability: float) -> str:
    """Καλεί απευθείας το τοπικό Ollama API για να δημιουργήσει την επεξήγηση."""
    prompt = f"""
    You are an expert museum curator explaining connections in the Metropolitan Museum of Art (MET) collection.
    Explain why these two objects are predicted to be related (Link Probability: {probability:.1%}).

    Object A (Query):
    - Title: {query_info.get('title')}
    - Culture: {query_info.get('culture', 'Unknown')}
    - Department: {query_info.get('department', 'Unknown')}
    - Medium/Material: {query_info.get('medium', 'Unknown')}
    - Date/Era: {query_info.get('year', 'Unknown')}

    Object B (Related Candidate):
    - Title: {cand_info.get('title')}
    - Culture: {cand_info.get('culture', 'Unknown')}
    - Department: {cand_info.get('department', 'Unknown')}
    - Medium/Material: {cand_info.get('medium', 'Unknown')}
    - Date/Era: {cand_info.get('year', 'Unknown')}

    Shared Features Analysis:
    - Shared Culture? {"Yes" if features.get('shared_culture') else "No"}
    - Shared Department? {"Yes" if features.get('shared_department') else "No"}
    - Description Semantic Similarity (Cosine): {features.get('cosine_similarity', 0.0):.2f}

    Write a concise, engaging 2-3 sentence explanation in Greek highlighting why they connect. Do not output any markdown formatting other than bolding. Do not mention system variables.
    """
    
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 400
                }
            },
            timeout=200.0
        )
        if response.status_code == 200:
            result_json = response.json()
            return result_json.get("response", "").strip()
        else:
            print(f"Ollama returned status code {response.status_code}")
            return "📝 *Ollama service is busy. Unable to generate explanation.*"
    except Exception as e:
        print(f"Failed to communicate with Ollama: {e}")
        return "📝 *Ollama is not running locally. Run 'ollama serve' and try again.*"


def save_explanation_to_db(query_id: int, candidate_id: int, explanation: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR REPLACE INTO explanations (object_id, candidate_id, explanation, computed_at) "
            "VALUES (?, ?, ?, datetime('now'))",
            (query_id, candidate_id, explanation)
        )
        conn.commit()
    except Exception as e:
        print(f"Warning: Could not cache explanation to DB: {e}")
    finally:
        conn.close()

# ----------------------------------------------------------------------
# API ENDPOINTS
# ----------------------------------------------------------------------

@app.get("/api/search")
def search_objects(q: str = "", limit: int = 20):
    global DF_META
    if DF_META is None:
        print("⚠️ DF_META is not loaded yet!")
        return []
    
    # Αν ο χρήστης δεν έχει γράψει τίποτα, δείξε τα πρώτα 20
    if not q.strip():
        sub_df = DF_META.head(limit)
    else:
        # Μετατρέπουμε σε string και κάνουμε safe έλεγχο case-insensitive
        # Ψάχνουμε τόσο στη στήλη Title όσο και στη στήλη Object Name
        mask_title = DF_META["Title"].astype(str).str.contains(q, case=False, na=False)
        mask_name = DF_META["Object Name"].astype(str).str.contains(q, case=False, na=False)
        
        sub_df = DF_META[mask_title | mask_name].head(limit)
    
    results = []
    for _, row in sub_df.iterrows():
        # Εξασφαλίζουμε ότι διαβάζουμε σωστά το 'Object ID' από το CSV
        obj_id = row.get("Object ID")
        if pd.isna(obj_id):
            continue
            
        results.append(get_object_info(int(obj_id)))
        
    return results


@app.get("/api/object/{object_id}", response_model=ObjectSummary)
def get_object_details(object_id: int):
    global DF_META
    if DF_META is None or object_id not in DF_META.index:
        raise HTTPException(status_code=404, detail=f"Object {object_id} not found")
    return ObjectSummary(**get_object_info(object_id))


@app.get("/api/related/{object_id}", response_model=list[RelatedObject])
def get_related(object_id: int, k: int = 8, explain: bool = True):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        query_info = get_object_info(object_id)
        
        cursor.execute("PRAGMA table_info(neighbor_predictions);")
        columns = [col[1] for col in cursor.fetchall()]
        feat_col = "features_json" if "features_json" in columns else ("features" if "features" in columns else None)
        prob_col = "probability" if "probability" in columns else ("score" if "score" in columns else "predicted_prob")

        if feat_col:
            query = f"SELECT candidate_id, {feat_col}, {prob_col} FROM neighbor_predictions WHERE object_id = ? ORDER BY {prob_col} DESC LIMIT ?"
        else:
            query = f"SELECT candidate_id, NULL, {prob_col} FROM neighbor_predictions WHERE object_id = ? ORDER BY {prob_col} DESC LIMIT ?"

        cursor.execute(query, (object_id, k))
        rows = cursor.fetchall()
        
        if not rows:
            return []

        candidate_ids = [row["candidate_id"] for row in rows]
        
        db_explanations = {}
        if explain and candidate_ids:
            placeholders = ",".join("?" for _ in candidate_ids)
            cursor.execute(
                f"SELECT candidate_id, explanation FROM explanations "
                f"WHERE object_id = ? AND candidate_id IN ({placeholders})",
                [object_id] + candidate_ids
            )
            db_explanations = {row["candidate_id"]: row["explanation"] for row in cursor.fetchall()}

        results = []
        for row in rows:
            cid = row["candidate_id"]
            cand_info = get_object_info(cid)
            
            features = {}
            if feat_col and row[feat_col]:
                try:
                    if isinstance(row[feat_col], str):
                        features = json.loads(row[feat_col])
                    else:
                        features = row[feat_col]
                except Exception:
                    pass
            
            cosine_similarity = float(features.get("cosine_similarity", features.get("cosine", 0.0)))
            shared_culture = bool(features.get("shared_culture", False))
            shared_department = bool(features.get("shared_department", False))
            probability = float(row[prob_col]) if row[prob_col] is not None else 0.0

            features["cosine_similarity"] = cosine_similarity
            features["shared_culture"] = shared_culture
            features["shared_department"] = shared_department

            explanation = ""
            if explain:
                if cid in db_explanations:
                    explanation = db_explanations[cid]
                else:
                    print(f"🤖 Explanation missing in SQLite for pair ({object_id} -> {cid}). Calling Ollama live...")
                    explanation = generate_ollama_explanation_live(query_info, cand_info, features, probability)
                    if "Unable to generate" not in explanation and "Ollama is not running" not in explanation:
                        save_explanation_to_db(object_id, cid, explanation)

            results.append(RelatedObject(
                object=ObjectSummary(**cand_info),
                probability=probability,
                cosine_similarity=cosine_similarity if cosine_similarity > 0 else probability,
                shared_culture=shared_culture,
                shared_department=shared_department,
                explanation=explanation
            ))
            
        return results

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.post("/api/explain-relationship", response_model=ExplainResponse)
def explain_relationship(payload: ExplainRequest):
    """On-demand explanation for a specific (source, target) pair, triggered
    by the 'Explain Relationship' button on the frontend. This is separate
    from the explanation already auto-generated inline by /api/related --
    it always makes a fresh Ollama call for the exact pair the user clicked,
    reusing the same get_object_info() / generate_ollama_explanation_live()
    helpers so behavior (prompt, model, fallback text) stays identical."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        source_id = payload.source_object_id
        target_id = payload.target_object_id

        query_info = get_object_info(source_id)
        cand_info = get_object_info(target_id)

        cursor.execute("PRAGMA table_info(neighbor_predictions);")
        columns = [col[1] for col in cursor.fetchall()]
        feat_col = "features_json" if "features_json" in columns else ("features" if "features" in columns else None)
        prob_col = "probability" if "probability" in columns else ("score" if "score" in columns else "predicted_prob")

        def fetch_pair_row(a: int, b: int):
            if feat_col:
                cursor.execute(
                    f"SELECT {feat_col} AS feat, {prob_col} AS prob FROM neighbor_predictions "
                    f"WHERE object_id = ? AND candidate_id = ?",
                    (a, b),
                )
            else:
                cursor.execute(
                    f"SELECT NULL AS feat, {prob_col} AS prob FROM neighbor_predictions "
                    f"WHERE object_id = ? AND candidate_id = ?",
                    (a, b),
                )
            return cursor.fetchone()

        # The pair may have been cached in either direction depending on
        # which object was the original query -- check both.
        row = fetch_pair_row(source_id, target_id) or fetch_pair_row(target_id, source_id)

        features: dict = {}
        probability = 0.0
        if row is not None:
            if row["feat"]:
                try:
                    raw = row["feat"]
                    features = json.loads(raw) if isinstance(raw, str) else dict(raw)
                except Exception:
                    features = {}
            probability = float(row["prob"]) if row["prob"] is not None else 0.0

        cosine_similarity = float(features.get("cosine_similarity", features.get("cosine", 0.0)))
        shared_culture = bool(features.get("shared_culture", False))
        shared_department = bool(features.get("shared_department", False))
        features["cosine_similarity"] = cosine_similarity
        features["shared_culture"] = shared_culture
        features["shared_department"] = shared_department

        explanation = generate_ollama_explanation_live(query_info, cand_info, features, probability)

        # Reuse the same cache table the auto-explanation uses, so a repeat
        # click (or the card's own inline explanation) is instant next time.
        if "Unable to generate" not in explanation and "Ollama is not running" not in explanation:
            save_explanation_to_db(source_id, target_id, explanation)

        metrics = {
            "probability": probability,
            "cosine_similarity": cosine_similarity,
            "shared_culture": shared_culture,
            "shared_department": shared_department,
        }
        for extra_key in (
            "jaccard", "adamic_adar", "preferential_attachment", "common_neighbors",
            "node2vec_similarity", "fuzzy_temporal_membership",
        ):
            if extra_key in features:
                metrics[extra_key] = features[extra_key]

        return ExplainResponse(explanation=explanation, metrics=metrics)

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.get("/api/health")
def health():
    return {"status": "ok", "optimized": True}