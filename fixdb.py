import sqlite3
from pathlib import Path

db_path = Path(__file__).resolve().parent / "dashboard_cache.db"

if not db_path.exists():
    print(f"❌ Database file NOT found at: {db_path}")
    exit()

print(f"Connecting to database at {db_path}...")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 1. Δημιουργία Index στον πίνακα neighbor_predictions για το πεδίο object_id
print("Creating index on neighbor_predictions(object_id)...")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_neighbor_object ON neighbor_predictions(object_id);")

# 2. Δημιουργία σύνθετου Index στον πίνακα explanations για τα object_id και candidate_id
print("Creating composite index on explanations(object_id, candidate_id)...")
cursor.execute("CREATE INDEX IF NOT EXISTS idx_exp_object_cand ON explanations(object_id, candidate_id);")

conn.commit()
conn.close()
print("⚡ Indexes created successfully! Your database is now fully optimized.")