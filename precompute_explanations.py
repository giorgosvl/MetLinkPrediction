"""
Offline Batch Script: precompute_explanations.py
Προ-υπολογίζει όλες τις επεξηγήσεις μέσω Ollama και τις αποθηκεύει στη SQLite.
"""

import sqlite3
import json
import time
from pathlib import Path
import pandas as pd
import requests

# Ρυθμίσεις Διαδρομών
REPO_ROOT = Path(__file__).resolve().parent
CACHE_DB_PATH = REPO_ROOT / "dashboard_cache.db"
METADATA_PATH = REPO_ROOT / "met_with_extracted_info.csv"
OLLAMA_MODEL = "llama3.1"  # Άλλαξέ το στο μοντέλο που έχεις (π.χ. llama3, mistral)

print("⚡ Ξεκινάει η προετοιμασία για τον batch υπολογισμό των επεξηγήσεων...")

if not CACHE_DB_PATH.exists():
    raise FileNotFoundError(f"❌ Η βάση δεδομένων δεν βρέθηκε στο {CACHE_DB_PATH}")

# 1. Φόρτωση των Metadata για να έχουμε τις πληροφορίες των αντικειμένων
print("💾 Φόρτωση του metadata CSV (αυτό μπορεί να πάρει μερικά δευτερόλεπτα)...")
df_meta = pd.read_csv(METADATA_PATH, low_memory=False)
df_meta.set_index("Object ID", inplace=True, drop=False)

def get_object_info(object_id: int) -> dict:
    if object_id not in df_meta.index:
        return {"title": f"Unknown Object ({object_id})", "culture": "Unknown", "department": "Unknown", "medium": "Unknown", "year": "Unknown"}
    
    row = df_meta.loc[object_id]
    begin = row.get("Object Begin Date")
    end = row.get("Object End Date")
    year_str = "—"
    if pd.notna(begin) and pd.notna(end):
        year_str = f"{int(begin)} - {int(end)}"
    elif pd.notna(begin):
        year_str = str(int(begin))

    return {
        "title": row.get("Title") if pd.notna(row.get("Title")) else row.get("Object Name", "Untitled"),
        "culture": row.get("culture") if pd.notna(row.get("culture")) else "Unknown",
        "department": row.get("Department") if pd.notna(row.get("Department")) else "Unknown",
        "medium": row.get("Medium") if pd.notna(row.get("Medium")) else "Unknown",
        "year": year_str,
    }

# 2. Σύνδεση στη SQLite
conn = sqlite3.connect(CACHE_DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Δημιουργία του πίνακα explanations αν δεν υπάρχει
cursor.execute("""
CREATE TABLE IF NOT EXISTS explanations (
    object_id INTEGER,
    candidate_id INTEGER,
    explanation TEXT,
    computed_at TEXT,
    PRIMARY KEY (object_id, candidate_id)
);
""")
conn.commit()

# 3. Ανάκτηση όλων των ζευγαριών που χρειάζονται επεξήγηση
# (Παίρνουμε τα ζευγάρια από το neighbor_predictions που ΔΕΝ έχουν ήδη επεξήγηση στο explanations)
print("🔍 Αναζήτηση ζευγαριών στη βάση που δεν έχουν ακόμη επεξήγηση...")

# Ανίχνευση στηλών για το Query
cursor.execute("PRAGMA table_info(neighbor_predictions);")
columns = [col[1] for col in cursor.fetchall()]
feat_col = "features_json" if "features_json" in columns else ("features" if "features" in columns else None)
prob_col = "probability" if "probability" in columns else ("score" if "score" in columns else "predicted_prob")

# Φτιάχνουμε ένα συντακτικά έγκυρο SQL query για τη SQLite
if feat_col:
    query = f"""
    SELECT np.object_id, np.candidate_id, np.{feat_col} as features, np.{prob_col} as prob
    FROM neighbor_predictions np
    LEFT JOIN explanations e ON np.object_id = e.object_id AND np.candidate_id = e.candidate_id
    WHERE e.explanation IS NULL
    """
else:
    query = f"""
    SELECT np.object_id, np.candidate_id, NULL as features, np.{prob_col} as prob
    FROM neighbor_predictions np
    LEFT JOIN explanations e ON np.object_id = e.object_id AND np.candidate_id = e.candidate_id
    WHERE e.explanation IS NULL
    """

cursor.execute(query)
pairs_to_process = cursor.fetchall()

total_pairs = len(pairs_to_process)
print(f"📋 Βρέθηκαν {total_pairs} ζευγάρια που χρειάζονται επεξηγήσεις από το Ollama.")

if total_pairs == 0:
    print("🎉 Όλα τα ζευγάρια έχουν ήδη επεξηγήσεις! Δεν χρειάζεται να τρέξει τίποτα.")
    conn.close()
    exit()

# 4. Loop κλήσης του Ollama και αποθήκευσης
success_count = 0

try:
    for idx, row in enumerate(pairs_to_process, start=1):
        obj_id = row["object_id"]
        cand_id = row["candidate_id"]
        prob = row["prob"] if row["prob"] is not None else 0.0
        
        # Parse features
        features = {}
        if feat_col and row["features"]:
            try:
                features = json.loads(row["features"]) if isinstance(row["features"], str) else row["features"]
            except Exception:
                pass
                
        # Ανάκτηση πληροφοριών αντικειμένων
        query_info = get_object_info(obj_id)
        cand_info = get_object_info(cand_id)
        
        # Φτιάχνουμε το prompt (ακριβώς ίδιο με αυτό της main)
        prompt = f"""
        You are an expert museum curator explaining connections in the Metropolitan Museum of Art (MET) collection.
        Explain why these two objects are predicted to be related (Link Probability: {prob:.1%}).

        Object A (Query):
        - Title: {query_info.get('title')}
        - Culture: {query_info.get('culture')}
        - Department: {query_info.get('department')}
        - Medium/Material: {query_info.get('medium')}
        - Date/Era: {query_info.get('year')}

        Object B (Related Candidate):
        - Title: {cand_info.get('title')}
        - Culture: {cand_info.get('culture')}
        - Department: {cand_info.get('department')}
        - Medium/Material: {cand_info.get('medium')}
        - Date/Era: {cand_info.get('year')}

        Shared Features Analysis:
        - Shared Culture? {"Yes" if features.get('shared_culture') else "No"}
        - Shared Department? {"Yes" if features.get('shared_department') else "No"}
        - Description Semantic Similarity (Cosine): {features.get('cosine_similarity', features.get('cosine', 0.0)):.2f}

        Write a concise, engaging 2-3 sentence explanation in Greek highlighting why they connect. Do not output any markdown formatting other than bolding. Do not mention system variables.
        """
        
        print(f"[{idx}/{total_pairs}] 🤖 Generating explanation for pair ({obj_id} -> {cand_id})...", end="", flush=True)
        
        # Κλήση Ollama API
        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 150}
                },
                timeout=25.0
            )
            
            if response.status_code == 200:
                explanation = response.json().get("response", "").strip()
                
                # Αποθήκευση στη SQLite
                cursor.execute(
                    "INSERT OR REPLACE INTO explanations (object_id, candidate_id, explanation, computed_at) VALUES (?, ?, ?, datetime('now'))",
                    (obj_id, cand_id, explanation)
                )
                conn.commit()
                print(" ✅ Αποθηκεύτηκε!")
                success_count += 1
            else:
                print(f" ❌ Σφάλμα Ollama (Status: {response.status_code})")
                
        except requests.exceptions.RequestException as e:
            print(f" ❌ Αποτυχία σύνδεσης με το Ollama (Είναι ανοιχτό;): {e}")
            print("Διακοπή του script λόγω σφάλματος σύνδεσης.")
            break
            
        # Μικρή καθυστέρηση για να μην υπερθερμανθεί η CPU/GPU
        time.sleep(0.2)

except KeyboardInterrupt:
    print("\n🛑 Το script διακόπηκε από το χρήστη. Οι μέχρι τώρα επεξηγήσεις έχουν αποθηκευτεί με ασφάλεια!")

finally:
    conn.close()
    print(f"\n🎉 Η διαδικασία ολοκληρώθηκε! Προ-υπολογίστηκαν {success_count} νέες επεξηγήσεις.")