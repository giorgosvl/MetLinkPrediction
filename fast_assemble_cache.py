import sqlite3
import json
import pandas as pd
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
CACHE_DB_PATH = REPO_ROOT / "dashboard_cache.db"
METADATA_PATH = REPO_ROOT / "met_with_extracted_info.csv"

print("💾 Φόρτωση metadata...")
df_meta = pd.read_csv(METADATA_PATH, low_memory=False)
df_meta.set_index("Object ID", inplace=True, drop=False)

def get_title(obj_id):
    if obj_id in df_meta.index and pd.notna(df_meta.loc[obj_id, 'Title']):
        return df_meta.loc[obj_id, 'Title']
    return f"Αντικείμενο {obj_id}"

# Ορισμός των Templates που μας έδωσε το LLM
TEMPLATES = {
    "both": "Το έκθεμα **{obj_title}** συνδέεται στενά με το **{cand_title}**. Και τα δύο ανήκουν στον πολιτισμό '{culture}' και εκτίθενται στο τμήμα '{department}', αναδεικνύοντας την κοινή καλλιτεχνική κληρονομιά.",
    "culture": "Υπάρχει ισχυρός ιστορικός δεσμός καθώς το **{obj_title}** και το **{cand_title}** μοιράζονται την ίδια πολιτισμική προέλευση ({culture}), αποτυπώνοντας την αισθητική της συγκεκριμένης περιόδου.",
    "department": "Τα αντικείμενα **{obj_title}** και **{cand_title}** παρουσιάζουν κοινά στοιχεία καθώς φιλοξενούνται στο ίδιο τμήμα του μουσείου ({department}), προσφέροντας μια ολοκληρωμένη εικόνα της συγκεκριμένης συλλογής.",
    "generic": "Η συσχέτιση μεταξύ του **{obj_title}** και του **{cand_title}** προκύπτει από τη σημασιολογική ομοιότητα των χαρακτηριστικών τους, των υλικών κατασκευής ({medium}) και του ιστορικού τους πλαισίου."
}

conn = sqlite3.connect(CACHE_DB_PATH)
cursor = conn.cursor()

# Δημιουργία πίνακα αν δεν υπάρχει
cursor.execute("""
CREATE TABLE IF NOT EXISTS explanations (
    object_id INTEGER, candidate_id INTEGER, explanation TEXT, computed_at TEXT,
    PRIMARY KEY (object_id, candidate_id)
);
""")

print("🔍 Ανάκτηση των 2.500.000 ζευγαριών...")
cursor.execute("PRAGMA table_info(neighbor_predictions);")
columns = [col[1] for col in cursor.fetchall()]
feat_col = "features_json" if "features_json" in columns else ("features" if "features" in columns else None)

cursor.execute(f"SELECT object_id, candidate_id, {feat_col if feat_col else 'NULL'} FROM neighbor_predictions")
rows = cursor.fetchall()

print(f"🚀 Ξεκινάει η σύνθεση για {len(rows)} εγγραφές...")
insert_data = []

for idx, row in enumerate(rows):
    obj_id, cand_id, feat_str = row
    
    # Parsing των χαρακτηριστικών
    shared_culture = False
    shared_department = False
    culture = "Άγνωστος"
    medium = "Διάφορα υλικά"
    department = "Γενική Συλλογή"
    
    if feat_str:
        try:
            feats = json.loads(feat_str) if isinstance(feat_str, str) else feat_str
            shared_culture = feats.get("shared_culture", False)
            shared_department = feats.get("shared_department", False)
        except:
            pass
            
    if obj_id in df_meta.index:
        meta = df_meta.loc[obj_id]
        culture = meta.get("culture", culture) if pd.notna(meta.get("culture")) else culture
        medium = meta.get("Medium", medium) if pd.notna(meta.get("Medium")) else medium
        department = meta.get("Department", department) if pd.notna(meta.get("Department")) else department

    obj_title = get_title(obj_id)
    cand_title = get_title(cand_id)

    # Επιλογή template βάσει των features
    if shared_culture and shared_department:
        tpl = TEMPLATES["both"]
    elif shared_culture:
        tpl = TEMPLATES["culture"]
    elif shared_department:
        tpl = TEMPLATES["department"]
    else:
        tpl = TEMPLATES["generic"]

    # Σύνθεση του τελικού κειμένου (Instant)
    explanation = tpl.format(
        obj_title=obj_title, cand_title=cand_title, 
        culture=culture, department=department, medium=medium
    )
    
    insert_data.append((obj_id, cand_id, explanation))
    
    # Ανά 50.000 εγγραφές γράφουμε στη βάση για να μην γεμίσει η RAM
    if len(insert_data) >= 50000:
        cursor.executemany("INSERT OR REPLACE INTO explanations (object_id, candidate_id, explanation, computed_at) VALUES (?, ?, ?, datetime('now'))", insert_data)
        conn.commit()
        print(f"💾 Προχώρησε: {idx + 1}/{len(rows)}")
        insert_data = []

# Γράφουμε τα τελευταία υπολειπόμενα
if insert_data:
    cursor.executemany("INSERT OR REPLACE INTO explanations (object_id, candidate_id, explanation, computed_at) VALUES (?, ?, ?, datetime('now'))", insert_data)
    conn.commit()

conn.close()
print("🎉 Η βάση γέμισε με 2.500.000 επεξηγήσεις μέσα σε λίγα λεπτά!")