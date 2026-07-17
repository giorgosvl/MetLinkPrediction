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

class AISearchRequest(BaseModel):
    query: str
    previous_object_ids: list[int] | None = None

class AISearchResponse(BaseModel):
    intent: dict
    summary: str
    results: list[ObjectSummary]

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
# 🧭 AI MUSEUM ASSISTANT -- natural language search
#
# Design (matches the brief): the LLM NEVER answers from its own knowledge
# and never decides what's "related" -- it only (a) turns the user's
# sentence into structured filters/intent, and (b) afterwards writes a
# plain-language summary of what the REAL pipeline (pandas filtering +
# the already-existing link-prediction cache) found. All of the actual
# search/graph/link-prediction logic is 100% reused, untouched.
# ----------------------------------------------------------------------

AI_INTENT_PROMPT = """You are a query-understanding system for a museum search application. You do NOT answer the user's question yourself -- you only extract structured intent as JSON.

Output ONLY a valid JSON object, no markdown, no explanation, in exactly this schema:
{{
  "intent": "search" | "filter_previous" | "explain_single" | "compare" | "chat",
  "culture": string or null,
  "material": string or null,
  "department": string or null,
  "object_type": string or null,
  "year_start": integer or null,
  "year_end": integer or null,
  "keywords": [string, ...],
  "target_index": integer or null,
  "target_index_2": integer or null
}}

Rules:
- "search": a brand new, independent search request.
- "filter_previous": narrows down the list of results ALREADY shown in this conversation.
- "explain_single": asks to explain/describe ONE specific item from the previous results.
- "compare": asks to compare TWO items from the previous results.
- "chat": general conversation, greetings, jokes, or ANY request about topics unrelated to museum objects (e.g. recipes, pastitsio).
- Leave any field null / empty list if not mentioned. Never invent values not implied by the message.
- IMPORTANT TRANSLATION & TYPO RULES: The museum catalog is in ENGLISH. The user might write in Greek with heavy spelling mistakes or typos (e.g., "μαχέρια" instead of "μαχαίρια", "σπαθια", "ασπιδες"). You MUST understand the intended meaning first, correct the typo in your mind, and then translate it into the correct English museum terms.
  Examples: 
  - "δειξε μου μαχερια" -> object_type: "knife", keywords: ["knife", "dagger"]
  - "σπαθια" -> object_type: "sword", keywords: ["sword"]
  - "αγαλματα" -> object_type: "statue", keywords: ["statue", "sculpture"]

There are currently {history_note} previous results in this conversation.

User message: "{query}"

Output ONLY the JSON object, nothing else.
"""

def extract_intent_via_ollama(query: str, has_previous_results: bool) -> dict:
    """Ask Ollama to turn the free-text query into structured intent. Falls
    back to a plain 'search with the raw text as a keyword' intent if the
    model is unreachable or returns something unparseable -- the feature
    should degrade gracefully, not hard-fail, when Ollama is slow/down."""
    history_note = "some" if has_previous_results else "no"
    prompt = AI_INTENT_PROMPT.format(history_note=history_note, query=query)

    fallback = {
        "intent": "search",
        "culture": None,
        "material": None,
        "department": None,
        "object_type": None,
        "keywords": [query],
        "target_index": None,
        "target_index_2": None,
    }

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0, "num_predict": 200},
            },
            timeout=60.0,
        )
        if response.status_code != 200:
            return fallback
        raw = response.json().get("response", "").strip()
        parsed = json.loads(raw)
        # Merge over the fallback so any missing key still has a safe default.
        merged = {**fallback, **parsed}
        if merged.get("intent") not in ("search", "filter_previous", "explain_single", "compare", "chat"):
            merged["intent"] = "search"
        if not isinstance(merged.get("keywords"), list):
            merged["keywords"] = []
        return merged
    except Exception as e:
        print(f"Intent extraction failed, falling back to plain search: {e}")
        return fallback


def filter_objects_by_intent(intent: dict, candidate_ids: list[int] | None) -> list[int]:
    global DF_META
    if DF_META is None:
        return []

    df = DF_META.copy()
    if candidate_ids is not None and len(candidate_ids) > 0:
        df = df[df["Object ID"].isin(candidate_ids)]

    def contains(column: str, value: str):
        if column not in df.columns:
            return pd.Series(False, index=df.index)
        return df[column].astype(str).str.contains(value, case=False, na=False, regex=False)

    mask = pd.Series(True, index=df.index)

    # 1. 🏛️ ΕΞΥΠΝΗ ΑΥΣΤΗΡΟΤΗΤΑ ΓΙΑ ΠΟΛΙΤΙΣΜΟ / ΧΩΡΑ
    if intent.get("culture"):
        cult = intent["culture"].strip()
        culture_col = "culture" if "culture" in df.columns else "Culture"
        cult_base = cult.replace("ian", "").replace("ish", "").replace("greek", "gree")
        
        culture_mask = contains(culture_col, cult) | contains(culture_col, cult_base) | contains("Department", cult)
        if "Classification" in df.columns:
            culture_mask |= contains("Classification", cult)
            
        mask &= culture_mask

    # 2. 📅 ΑΠΟΛΥΤΑ ΑΥΣΤΗΡΟ ΦΙΛΤΡΟ ΓΙΑ ΗΜΕΡΟΜΗΝΙΕΣ (1800-1900 κλπ)
    year_start = intent.get("year_start")
    year_end = intent.get("year_end")
    if year_start is not None and year_end is not None:
        begin_dates = pd.to_numeric(df["Object Begin Date"], errors="coerce")
        end_dates = pd.to_numeric(df["Object End Date"], errors="coerce")
        mask &= (begin_dates >= float(year_start)) & (end_dates <= float(year_end))

    # 3. Φιλτράρισμα για Υλικό (Material)
    if intent.get("material"):
        mask &= contains("Medium", intent["material"])

    # 4. Φιλτράρισμα για Τμήμα (Department)
    if intent.get("department"):
        mask &= contains("Department", intent["department"])

    # 5. Φιλτράρισμα για Keywords & Object Types
    search_terms = intent.get("keywords") or []
    if intent.get("object_type") and intent["object_type"] not in search_terms:
        search_terms.append(intent["object_type"])
    
    # Αφαιρούμε τα stop-words του πολιτισμού από τα keywords τίτλου
    if intent.get("culture"):
        cult_word = intent["culture"].lower()
        cult_base2 = cult_word.replace("ian", "").replace("ish", "")
        search_terms = [
            t for t in search_terms 
            if t.lower() not in [cult_word, cult_base2, "egypt", "egyptian", "greek", "roman", "american", "america"]
        ]

    search_terms = [t.strip() for t in search_terms if t and len(t.strip()) > 1]

    if search_terms:
        kw_mask = pd.Series(False, index=df.index)
        
        # 💡 ΝΕΑ ΠΡΟΣΘΗΚΗ: Ανίχνευση για μαχαίρια/σπαθιά (ελληνικά, αγγλικά ή ανορθόγραφα)
        terms_lower = [t.lower() for t in search_terms]
        is_knife_or_weapon = any(
            "μαχ" in w or "mach" in w or "max" in w or w in ["knife", "knives", "dagger", "sword", "weapon", "weapons"]
            for w in terms_lower
        )

        if is_knife_or_weapon:
            # Αν ο χρήστης ψάχνει μαχαίρια, εξαναγκάζουμε το pandas να κοιτάξει στο σωστό department
            # και να ψάξει τις σωστές αγγλικές λέξεις "knife" και "dagger", προσπερνώντας το typo!
            kw_mask |= contains("Department", "Arms and Armor") | contains("Class", "Arms")
            kw_mask |= contains("Title", "knife") | contains("Title", "dagger") | contains("Object Name", "knife")

        # Κλασικό φιλτράρισμα για τα υπόλοιπα keywords
        for term in search_terms:
            kw_mask |= contains("Title", term) | contains("Object Name", term)
            if "Tags" in df.columns:
                kw_mask |= contains("Tags", term)
                
        mask &= kw_mask

    matched = df[mask]
    ids = [int(oid) for oid in matched["Object ID"].tolist() if pd.notna(oid)]
    return ids[:24]


def generate_ai_summary_live(query: str, result_infos: list[dict]) -> str:
    """One short LLM-written summary of what the (already computed) search
    found. The LLM is given ONLY the titles/culture/department it should
    talk about -- it cannot add facts the search didn't actually return."""
    if not result_infos:
        return "Δεν βρέθηκαν αντικείμενα που να ταιριάζουν με το ερώτημά σου. Δοκίμασε διαφορετικούς όρους."

    lines = "\n".join(
        f"- {r['title']} ({r.get('culture') or 'άγνωστος πολιτισμός'}, {r.get('department') or 'άγνωστο τμήμα'})"
        for r in result_infos[:12]
    )
    prompt = f"""You are a museum research assistant. The user asked: "{query}"

The search pipeline (not you) found these {len(result_infos)} matching objects:
{lines}

Write a short, engaging 2-3 sentence summary in Greek describing what was found and any obvious shared pattern (culture, department, material). Use ONLY the facts listed above -- do not invent anything. Do not use markdown other than bolding."""

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 300},
            },
            timeout=120.0,
        )
        if response.status_code == 200:
            return response.json().get("response", "").strip()
        return f"Βρέθηκαν {len(result_infos)} αντικείμενα που ταιριάζουν με το ερώτημά σου."
    except Exception as e:
        print(f"AI summary generation failed: {e}")
        return f"Βρέθηκαν {len(result_infos)} αντικείμενα που ταιριάζουν με το ερώτημά σου. (Το Ollama δεν απάντησε -- δείχνω μόνο τα αποτελέσματα.)"


def generate_object_description_live(obj_info: dict) -> str:
    """Single-object plain-language description, used by the 'explain_single'
    intent (e.g. 'tell me about the first one')."""
    prompt = f"""You are an expert museum curator. Describe the following museum object engagingly, in Greek, in 2-3 sentences. Use ONLY the facts given -- do not invent anything.

Title: {obj_info.get('title')}
Culture: {obj_info.get('culture') or 'unknown'}
Department: {obj_info.get('department') or 'unknown'}
Medium/Material: {obj_info.get('medium') or 'unknown'}
Date/Era: {obj_info.get('year') or 'unknown'}"""

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 300},
            },
            timeout=120.0,
        )
        if response.status_code == 200:
            return response.json().get("response", "").strip()
        return "📝 *Ollama service is busy. Unable to generate a description.*"
    except Exception as e:
        print(f"Object description generation failed: {e}")
        return "📝 *Ollama is not running locally. Run 'ollama serve' and try again.*"


def generate_chat_reply_live(query: str) -> str:
    """Fallback for messages that aren't a search/filter/explain/compare --
    a short, on-topic reply that nudges the user back towards the museum
    search, without pretending to browse the collection itself."""
    prompt = f"""You are a friendly museum research assistant embedded in a search tool for the Metropolitan Museum of Art collection. The user said: "{query}"

This is not a search request. Reply briefly (1-2 sentences, in Greek), and if relevant, suggest they try a search like "Show me Greek helmets" or "Find Egyptian ceremonial objects"."""

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.4, "num_predict": 300},
            },
            timeout=90.0,
        )
        if response.status_code == 200:
            return response.json().get("response", "").strip()
        return "Πες μου τι θα ήθελες να αναζητήσεις στη συλλογή του μουσείου."
    except Exception:
        return "Πες μου τι θα ήθελες να αναζητήσεις στη συλλογή του μουσείου."


def fetch_pair_features(source_id: int, target_id: int) -> tuple[dict, float]:
    """Same lookup /api/explain-relationship does, factored out so the
    'compare' intent below can reuse it without duplicating the DB logic."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA table_info(neighbor_predictions);")
        columns = [col[1] for col in cursor.fetchall()]
        feat_col = "features_json" if "features_json" in columns else ("features" if "features" in columns else None)
        prob_col = "probability" if "probability" in columns else ("score" if "score" in columns else "predicted_prob")

        def fetch(a: int, b: int):
            if feat_col:
                cursor.execute(
                    f"SELECT {feat_col} AS feat, {prob_col} AS prob FROM neighbor_predictions WHERE object_id = ? AND candidate_id = ?",
                    (a, b),
                )
            else:
                cursor.execute(
                    f"SELECT NULL AS feat, {prob_col} AS prob FROM neighbor_predictions WHERE object_id = ? AND candidate_id = ?",
                    (a, b),
                )
            return cursor.fetchone()

        row = fetch(source_id, target_id) or fetch(target_id, source_id)
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

        features["cosine_similarity"] = float(features.get("cosine_similarity", features.get("cosine", 0.0)))
        features["shared_culture"] = bool(features.get("shared_culture", False))
        features["shared_department"] = bool(features.get("shared_department", False))
        return features, probability
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


@app.post("/api/ai-search", response_model=AISearchResponse)
def ai_search(payload: AISearchRequest):
    """Natural-language front door to the EXISTING search pipeline. The LLM
    only classifies intent + extracts filters (or writes the final summary);
    the actual search/filter/compare work reuses get_object_info(),
    filter_objects_by_intent() (plain pandas over the same DF_META
    /api/search already uses), and fetch_pair_features() /
    generate_ollama_explanation_live() for comparisons -- nothing about the
    Knowledge Graph or Link Prediction pipeline is touched or reimplemented."""
    global DF_META
    if DF_META is None:
        raise HTTPException(status_code=503, detail="Data not loaded yet")

    previous_ids = payload.previous_object_ids or []
    has_previous = len(previous_ids) > 0

    intent = extract_intent_via_ollama(payload.query, has_previous)
    kind = intent.get("intent", "search")

    try:
        if kind == "filter_previous" and has_previous:
            ids = filter_objects_by_intent(intent, candidate_ids=previous_ids)
            results = [get_object_info(oid) for oid in ids]
            summary = generate_ai_summary_live(payload.query, results)
            return AISearchResponse(intent=intent, summary=summary, results=[ObjectSummary(**r) for r in results])

        if kind == "explain_single" and has_previous and intent.get("target_index"):
            idx = int(intent["target_index"]) - 1
            if 0 <= idx < len(previous_ids):
                obj_info = get_object_info(previous_ids[idx])
                summary = generate_object_description_live(obj_info)
                return AISearchResponse(intent=intent, summary=summary, results=[ObjectSummary(**obj_info)])
            return AISearchResponse(
                intent=intent,
                summary="Δεν βρήκα αυτό το αντικείμενο στα προηγούμενα αποτελέσματα.",
                results=[],
            )

        if kind == "compare" and has_previous and intent.get("target_index") and intent.get("target_index_2"):
            idx1 = int(intent["target_index"]) - 1
            idx2 = int(intent["target_index_2"]) - 1
            if 0 <= idx1 < len(previous_ids) and 0 <= idx2 < len(previous_ids):
                info1 = get_object_info(previous_ids[idx1])
                info2 = get_object_info(previous_ids[idx2])
                features, probability = fetch_pair_features(previous_ids[idx1], previous_ids[idx2])
                summary = generate_ollama_explanation_live(info1, info2, features, probability)
                return AISearchResponse(
                    intent=intent, summary=summary,
                    results=[ObjectSummary(**info1), ObjectSummary(**info2)],
                )
            return AISearchResponse(
                intent=intent,
                summary="Δεν βρήκα και τα δύο αντικείμενα στα προηγούμενα αποτελέσματα.",
                results=[],
            )

        if kind == "chat":
            summary = generate_chat_reply_live(payload.query)
            return AISearchResponse(intent=intent, summary=summary, results=[])

        # Default: fresh "search" intent (also the fallback for
        # filter_previous/explain_single/compare when there's no history yet).
        ids = filter_objects_by_intent(intent, candidate_ids=None)
        results = [get_object_info(oid) for oid in ids]
        summary = generate_ai_summary_live(payload.query, results)
        return AISearchResponse(intent=intent, summary=summary, results=[ObjectSummary(**r) for r in results])

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
def health():
    return {"status": "ok", "optimized": True}