import sqlite3
from pathlib import Path

db_path = Path("dashboard_cache.db")
if not db_path.exists():
    print("❌ Το αρχείο dashboard_cache.db δεν βρέθηκε σε αυτόν τον φάκελο!")
    exit()

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # 1. Έλεγχος αν υπάρχει ο πίνακας explanations
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='explanations';")
    table_exists = cursor.fetchone()

    # 2. Μέτρηση συνόλου προβλέψεων (ζευγαριών)
    cursor.execute("SELECT COUNT(*) FROM neighbor_predictions;")
    total_predictions = cursor.fetchone()[0]

    if not table_exists:
        print("\n❌ Ο πίνακας 'explanations' ΔΕΝ υπάρχει καθόλου στη βάση!")
        print(f"   Αυτό σημαίνει ότι έχεις 0 από τις {total_predictions} επεξηγήσεις έτοιμες.")
        print("   -> Πρέπει οπωσδήποτε να τρέξεις το precompute_explanations.py!")
    else:
        # 3. Μέτρηση υπαρχουσών επεξηγήσεων
        cursor.execute("SELECT COUNT(*) FROM explanations WHERE explanation IS NOT NULL AND explanation != '';")
        computed_explanations = cursor.fetchone()[0]

        percent = (computed_explanations / total_predictions) * 100 if total_predictions > 0 else 0
        
        print("\n📊 ΣΤΑΤΙΣΤΙΚΑ ΤΗΣ ΒΑΣΗΣ ΔΕΔΟΜΕΝΩΝ ΣΟΥ:")
        print(f"   • Συνολικά ζευγάρια στη βάση: {total_predictions}")
        print(f"   • Έτοιμες επεξηγήσεις (computed): {computed_explanations}")
        print(f"   • Ποσοστό ολοκλήρωσης: {percent:.2f}%")

        if computed_explanations >= total_predictions:
            print("\n🎉 Φανταστικά! Όλες οι επεξηγήσεις είναι ήδη υπολογισμένες! Δεν χρειάζεται να τρέξεις τίποτα!")
        else:
            missing = total_predictions - computed_explanations
            print(f"\n⚠️ Προσοχή: Λείπουν ακόμα {missing} επεξηγήσεις.")
            print("   -> Σου προτείνω να τρέξεις το precompute_explanations.py για να τις συμπληρώσεις.")

except Exception as e:
    print(f"❌ Σφάλμα κατά τον έλεγχο της βάσης: {e}")
finally:
    conn.close()