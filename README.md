# MetLinkPrediction

## Περιγραφή

Το **MetLinkPrediction** είναι ένα end-to-end σύστημα για πρόβλεψη πιθανών σχέσεων ανάμεσα σε αντικείμενα της συλλογής του **Metropolitan Museum of Art (MET)**. Η υλοποίηση συνδυάζει καθαρισμό μουσειακών δεδομένων, τοπικό LLM enrichment, semantic embeddings, FAISS similarity search, ετερογενές knowledge graph, graph topology features, filtered Node2Vec, supervised link prediction με XGBoost, fuzzy temporal reasoning και dashboard με εξηγήσεις για curator-facing χρήση.

Ο στόχος του project είναι να προτείνει αντικείμενα που πιθανόν σχετίζονται, ακόμη και όταν η σχέση δεν υπάρχει άμεσα ως ρητό metadata field. Το σύστημα αξιοποιεί:

- σημασιολογική ομοιότητα περιγραφών,
- δομημένα metadata,
- graph topology,
- temporal uncertainty,
- explainable predictions.

## Pipeline

```text
MetObjects.txt
      |
      v
01_preprocessing.py
      |
      v
met_clean.csv
      |
      v
03_sample_dataset.py
      |
      v
met_sample_50000.csv
      |
      v
02_ollama_extraction.py
      |
      v
met_with_extracted_info.csv
      |
      +--------------------------+
      |                          |
      v                          v
04_build_embeddings.py       05_build_graph.py
      |                          |
      v                          v
embeddings/                  graph/
      |                          |
      +------------+-------------+
                   |
                   v
          graph_features.py
                   |
                   v
          06_link_prediction.py
                   |
                   v
          link_prediction/
                   |
                   v
          07_fuzzy_temporal.py
                   |
                   v
                fuzzy/
                   |
                   v
 dashboard_core.py + dashboard_cache.py + Streamlit / FastAPI / React
```

## Δομή Project

```text
.
├── 01_preprocessing.py
├── 02_ollama_extraction.py
├── 03_sample_dataset.py
├── 04_build_embeddings.py
├── 05_build_graph.py
├── 06_link_prediction.py
├── 07_fuzzy_temporal.py
├── 09_dashboard_app.py
├── 10_calibration_check.py
├── 11_check_separability.py
├── 12_precompute_dashboard_cache.py
├── dashboard_cache.py
├── dashboard_core.py
├── fast_assemble_cache.py
├── precompute_explanations.py
├── graph_features.py
├── MetObjects.txt
├── met_clean.csv
├── met_sample_50000.csv
├── met_with_extracted_info.csv
├── embeddings/
├── graph/
├── link_prediction/
├── fuzzy/
└── webapp_mus/
```

## 1. Preprocessing

Αρχείο: `01_preprocessing.py`

Το πρώτο στάδιο φορτώνει το raw MET Open Access export και κρατά τα πεδία που χρειάζονται για τα επόμενα στάδια.

Κύριες λειτουργίες:

- επιλέγει χρήσιμες στήλες όπως `Object ID`, `Title`, `Object Name`, `Object Date`, `Object Begin Date`, `Object End Date`, `Department`, `Culture`, `Period`, `Country`, `Region`, `City`, `Medium`, `Artist Display Name`, `Classification`, `Tags`,
- κρατά numeric begin/end date fields για fuzzy temporal reasoning,
- δεν πετάει αντικείμενα που δεν έχουν `Title` αλλά έχουν `Object Name`,
- κανονικοποιεί placeholders όπως `Unknown`, `unidentified`, `N/A`, `none`,
- φτιάχνει ενιαίο `Description` field για embedding,
- δημιουργεί `has_sparse_metadata`,
- δημιουργεί `is_duplicate_description`.

Παραγόμενο αρχείο:

```text
met_clean.csv
```

## 2. Representative Sampling

Αρχείο: `03_sample_dataset.py`

Το πλήρες MET dataset είναι μεγάλο για γρήγορο end-to-end πειραματισμό. Για αυτό παράγεται sample 50.000 αντικειμένων.

Η δειγματοληψία δεν είναι απλή τυχαία επιλογή. Το script:

- αφαιρεί exact duplicate descriptions,
- υπολογίζει `quality_score` με βάση populated informative fields,
- φιλτράρει rows χαμηλής πληροφορίας,
- κάνει stratified sampling ως προς το `Classification`,
- κρατά πιο ισορροπημένο και χρήσιμο dataset για embeddings, graph και classifier.

Παραγόμενο αρχείο:

```text
met_sample_50000.csv
```

## 3. Local LLM Extraction

Αρχείο: `02_ollama_extraction.py`

Το project χρησιμοποιεί τοπικό Ollama μοντέλο για περιορισμένο metadata enrichment.

Η υλοποίηση είναι σχεδιασμένη ώστε να μην χρησιμοποιεί LLM άσκοπα:

- `material`, `year`, `object_type` αντιγράφονται από ήδη υπάρχοντα structured fields,
- `culture` αντιγράφεται όταν υπάρχει,
- LLM call γίνεται μόνο όταν λείπει το culture αλλά υπάρχει επαρκές descriptive context.

Χαρακτηριστικά:

- concurrent requests με `ThreadPoolExecutor`,
- resumable output,
- checkpointing,
- retries,
- JSON-only prompt,
- default model: `llama3.1`.

Παραγόμενο αρχείο:

```text
met_with_extracted_info.csv
```

## 4. Semantic Embeddings και FAISS

Αρχείο: `04_build_embeddings.py`

Κάθε `Description` μετατρέπεται σε dense vector embedding με local Ollama embedding model.

Default embedding model:

```text
nomic-embed-text
```

Το script:

- καλεί το Ollama embeddings API,
- αποθηκεύει embeddings σε `embeddings.npy`,
- αποθηκεύει mapping των `Object ID` σε `embedding_object_ids.json`,
- κάνει checkpointing για resumable execution,
- κάνει L2 normalization,
- χτίζει FAISS index με `IndexFlatIP`, που σε normalized vectors λειτουργεί ως cosine similarity search.

Παραγόμενα αρχεία:

```text
embeddings/embeddings.npy
embeddings/embedding_object_ids.json
embeddings/met.faiss
```

## 5. Knowledge Graph

Αρχείο: `05_build_graph.py`

Το project χτίζει ετερογενές object-to-attribute graph αντί για object-object clique.

Παράδειγμα:

```text
obj:123 --has_artist--> has_artist:Artist Name
obj:456 --has_artist--> has_artist:Artist Name
```

Αυτή η επιλογή αποφεύγει το combinatorial explosion. Αν 1.000 αντικείμενα μοιράζονται τον ίδιο artist, ένα απευθείας clique θα δημιουργούσε εκατοντάδες χιλιάδες edges. Με hub nodes, το graph μένει πολύ πιο μικρό και ερμηνεύσιμο.

Το graph περιλαμβάνει hubs όπως:

- artist,
- department,
- culture,
- classification,
- tags.

Τα positive candidate pairs για link prediction δειγματοληπτούνται μόνο από πιο συγκεκριμένα hubs όπως artist και tag. Broad hubs όπως culture/classification χρησιμοποιούνται στο graph, αλλά δεν αντιμετωπίζονται ως αρκετά ισχυρά ground-truth positives.

Παραγόμενα αρχεία:

```text
graph/graph.graphml
graph/candidate_pairs.csv
graph/graph_stats.json
```

Τρέχοντα graph statistics:

```json
{
  "total_rows_in_input": 50000,
  "object_nodes": 50000,
  "hub_nodes": 17513,
  "total_edges": 271140,
  "isolated_objects_no_edges": 0,
  "candidate_positive_pairs_sampled": 32154,
  "unique_object_pairs_after_dedup": 32054
}
```

## 6. Graph Features και Filtered Node2Vec

Αρχείο: `graph_features.py`

Η νέα έκδοση προσθέτει graph-derived features στο link prediction.

Topology features:

```text
common_neighbors
jaccard
adamic_adar
preferential_attachment
```

Node2Vec feature:

```text
node2vec_similarity
```

Σημαντική λεπτομέρεια: το project αποφεύγει label leakage από hubs που χρησιμοποιούνται για να παραχθούν τα positive labels. Επειδή τα positive pairs προκύπτουν από shared `has_artist` ή `has_tag`, αυτά τα hub types εξαιρούνται από:

- topology neighbor sets,
- Node2Vec training graph.

Έτσι το μοντέλο δεν μαθαίνει απλά ότι "δύο αντικείμενα έχουν ίδιο artist/tag", αλλά χρησιμοποιεί μη άμεσα leaky structural signal.

Το Node2Vec cache γράφεται τοπικά σε:

```text
cache/node2vec_embeddings_filtered.pkl
```

Ο φάκελος `cache/` δεν χρειάζεται να γίνει commit, επειδή μπορεί να ξαναδημιουργηθεί.

## 7. Link Prediction

Αρχείο: `06_link_prediction.py`

Το supervised link prediction στάδιο εκπαιδεύει μοντέλο που εκτιμά πιθανότητα σχέσης ανάμεσα σε δύο αντικείμενα.

Positive examples:

- προέρχονται από `graph/candidate_pairs.csv`,
- βασίζονται σε τεκμηριωμένη shared identity όπως artist ή tag.

Negative examples:

- τυχαία sampled object pairs,
- αποκλείονται pairs που μοιράζονται artist/tag,
- ισορροπούνται 1:1 με τα positives.

Features:

```text
cosine_similarity
shared_culture
shared_department
year_gap
common_neighbors
jaccard
adamic_adar
preferential_attachment
node2vec_similarity
```

Μοντέλο:

```text
XGBClassifier
```

Η νέα έκδοση χρησιμοποιεί **monotonic constraints**. Η λογική είναι ότι:

- περισσότερη σημασιολογική ομοιότητα δεν πρέπει να μειώνει την πιθανότητα link,
- περισσότερη κοινή graph evidence δεν πρέπει να μειώνει την πιθανότητα,
- μεγαλύτερο `year_gap` δεν πρέπει να αυξάνει την πιθανότητα.

Αυτό μειώνει non-monotonic artifacts που μπορεί να εμφανιστούν σε calibration sweeps.

Τρέχοντα αποτελέσματα:

```json
{
  "roc_auc": 0.9676,
  "n_train": 51286,
  "n_test": 12822,
  "confusion_matrix": [
    [5957, 454],
    [714, 5697]
  ],
  "feature_importance": {
    "cosine_similarity": 0.3388,
    "adamic_adar": 0.0179,
    "year_gap": 0.0041,
    "node2vec_similarity": 0.0037,
    "preferential_attachment": 0.0035,
    "shared_department": 0.0001,
    "shared_culture": 0.0,
    "common_neighbors": 0.0,
    "jaccard": 0.0
  }
}
```

Παραγόμενα αρχεία:

```text
link_prediction/link_prediction_dataset.csv
link_prediction/link_predictor.joblib
link_prediction/evaluation.json
```

## 8. Fuzzy Temporal Reasoning

Αρχείο: `07_fuzzy_temporal.py`

Οι χρονολογήσεις σε μουσειακά δεδομένα είναι συχνά ranges και όχι ακριβείς ημερομηνίες. Το `year_gap` χάνει αυτή την αβεβαιότητα, επειδή μετατρέπει ranges σε midpoint.

Η fuzzy λογική συγκρίνει δύο ranges:

```text
[a_begin, a_end]
[b_begin, b_end]
```

Αν επικαλύπτονται:

```text
membership = 1.0
```

Αν δεν επικαλύπτονται:

```text
membership = exp(-(gap^2) / (2 * tolerance^2))
```

Default tolerance:

```text
50 years
```

Το script κάνει ablation study σε τρεις εκδοχές:

- raw `year_gap`,
- μόνο `fuzzy_temporal_membership`,
- και τα δύο temporal features.

Τρέχοντα fuzzy ablation results:

```json
{
  "raw_year_gap_only": {
    "roc_auc": 0.9676
  },
  "fuzzy_temporal_only": {
    "roc_auc": 0.9674
  },
  "both_temporal_features": {
    "roc_auc": 0.9676
  }
}
```

Συμπέρασμα: η σημασιολογική ομοιότητα παραμένει το ισχυρότερο signal, ενώ τα graph και temporal features προσθέτουν συμπληρωματική πληροφορία.

Παραγόμενα αρχεία:

```text
fuzzy/link_prediction_dataset_with_fuzzy.csv
fuzzy/link_predictor_fuzzy.joblib
fuzzy/fuzzy_ablation_results.json
```

## 9. Calibration και Separability Diagnostics

### Calibration Check

Αρχείο: `10_calibration_check.py`

Το script ελέγχει αν οι predicted probabilities είναι χρήσιμες ή αν κολλάνε κοντά στο 1.0.

Περιλαμβάνει:

- synthetic sweep με μεταβολή του `cosine_similarity`,
- histogram predicted probabilities στο πραγματικό dataset,
- thresholds όπως 0.5, 0.8, 0.9, 0.95, 0.99.

### Separability Check

Αρχείο: `11_check_separability.py`

Το νέο diagnostic εξετάζει αν το απότομο probability threshold γύρω από cosine similarity 0.65-0.75 είναι πραγματικό χαρακτηριστικό των δεδομένων ή artifact.

Δεν χρησιμοποιεί το μοντέλο. Κοιτάζει απευθείας τις raw cosine similarity distributions για:

- `label = 1`,
- `label = 0`.

Έτσι βοηθά να τεκμηριωθεί αν το classifier behavior αντανακλά πραγματικό separability στο embedding space.

## 10. Dashboard και Explainability

Αρχεία:

```text
dashboard_core.py
dashboard_cache.py
12_precompute_dashboard_cache.py
09_dashboard_app.py
webapp_mus/
```

Το dashboard επιτρέπει αναζήτηση αντικειμένου και εμφάνιση πιθανών related objects.

Η λογική στο `dashboard_core.py`:

1. φορτώνει metadata, embeddings, trained model και graph,
2. βρίσκει nearest neighbors με cosine similarity,
3. υπολογίζει metadata, fuzzy, graph topology και Node2Vec features,
4. προβλέπει link probability,
5. ζητά από το local LLM σύντομη curator-friendly εξήγηση,
6. αν το LLM δεν είναι διαθέσιμο, επιστρέφει deterministic fallback explanation.

Η νεότερη έκδοση προσθέτει SQLite-backed cache μέσω `dashboard_cache.py`. Το cache κρατά:

- precomputed neighbor predictions για κάθε query object,
- feature values και predicted probabilities,
- προαιρετικά cached explanation text ανά object pair.

Αυτό μειώνει σημαντικά το latency στο dashboard, επειδή ένα επαναλαμβανόμενο query μπορεί να εξυπηρετηθεί ως απλό SQLite read αντί να ξανατρέχει embedding search, graph feature lookup, XGBoost inference και LLM explanation.

Το `12_precompute_dashboard_cache.py` μπορεί να ζεστάνει το cache πριν από demo ή παρουσίαση. Το ίδιο το `dashboard_cache.db` δεν γίνεται commit επειδή είναι generated SQLite artifact και μπορεί να ξεπεράσει το 1 GB.

Υπάρχουν δύο UI επιλογές:

- Streamlit: `09_dashboard_app.py`,
- FastAPI + React/Vite: `webapp_mus/`.

## Εγκατάσταση

### Python dependencies

```bash
pip install pandas numpy requests scikit-learn joblib networkx streamlit fastapi uvicorn xgboost node2vec
```

Για FAISS:

```bash
pip install faiss-cpu
```

### Ollama

Για LLM extraction και explanations:

```bash
ollama pull llama3.1
```

Για embeddings:

```bash
ollama pull nomic-embed-text
```

Προαιρετικά για parallel Ollama:

```powershell
$env:OLLAMA_NUM_PARALLEL="4"
ollama serve
```

## Εκτέλεση Pipeline

```bash
python 01_preprocessing.py
python 03_sample_dataset.py --input met_clean.csv --output met_sample_50000.csv --n 50000
python 02_ollama_extraction.py --input met_sample_50000.csv --output met_with_extracted_info.csv --workers 4
python 04_build_embeddings.py --input met_with_extracted_info.csv --out-dir embeddings --workers 4
python 05_build_graph.py --input met_with_extracted_info.csv --out-dir graph
python 06_link_prediction.py --embeddings embeddings/embeddings.npy --embedding-ids embeddings/embedding_object_ids.json --pairs graph/candidate_pairs.csv --metadata met_with_extracted_info.csv --graph graph/graph.graphml --out-dir link_prediction
python 07_fuzzy_temporal.py --dataset link_prediction/link_prediction_dataset.csv --metadata met_with_extracted_info.csv --out-dir fuzzy
```

Diagnostics:

```bash
python 10_calibration_check.py --model fuzzy/link_predictor_fuzzy.joblib --dataset fuzzy/link_prediction_dataset_with_fuzzy.csv
python 11_check_separability.py --dataset fuzzy/link_prediction_dataset_with_fuzzy.csv
```

Dashboard cache precompute:

```bash
python 12_precompute_dashboard_cache.py
python 12_precompute_dashboard_cache.py --limit 500
python 12_precompute_dashboard_cache.py --explanations-top-n 3
```

## Εκτέλεση Dashboard

### Streamlit

```bash
streamlit run 09_dashboard_app.py
```

Αν έχει προηγηθεί πλήρες `12_precompute_dashboard_cache.py`, τα περισσότερα dashboard queries εξυπηρετούνται απευθείας από το `dashboard_cache.db`.

### FastAPI + React

Backend:

```bash
cd webapp_mus
pip install fastapi uvicorn[standard]
uvicorn main:app --reload --port 8000
```

Frontend:

```bash
cd webapp_mus
npm install
npm run dev
```

Default frontend URL:

```text
http://localhost:5173
```

## Git LFS και Μεγάλα Αρχεία

Τα μεγαλύτερα artifacts αποθηκεύονται μέσω Git LFS:

```text
MetObjects.txt
met_clean.csv
embeddings/embeddings.npy
embeddings/met.faiss
```

Μετά από clone:

```bash
git lfs install
git lfs pull
```

Το `cache/` δεν γίνεται commit, επειδή περιέχει επαναδημιουργήσιμα Node2Vec cache files. Το `dashboard_cache.db` επίσης δεν γίνεται commit, επειδή είναι generated SQLite cache και ξαναχτίζεται με `12_precompute_dashboard_cache.py`.

## Κύριες Τεχνικές Αποφάσεις

### Αποφυγή duplicate-driven similarity

Τα duplicate descriptions μπορούν να δημιουργήσουν τεχνητά υψηλό semantic similarity. Το preprocessing και sampling στάδιο τα εντοπίζει και περιορίζει την επίδρασή τους.

### Heterogeneous graph αντί για clique

Τα objects συνδέονται με attribute hubs αντί να δημιουργούνται όλα τα object-object edges. Αυτό κρατά το graph αποδοτικό και ερμηνεύσιμο.

### Αποφυγή label leakage

Τα artist/tag hubs παράγουν positive labels, άρα αφαιρούνται από τα topology features και από το Node2Vec training graph. Αυτό προστατεύει το μοντέλο από το να μάθει απλώς τον κανόνα δημιουργίας των labels.

### Monotonic XGBoost

Οι monotonic constraints ενσωματώνουν domain knowledge στο μοντέλο και μειώνουν παράλογη μη-μονότονη συμπεριφορά στις πιθανότητες.

### Fuzzy temporal uncertainty

Οι χρονολογήσεις μοντελοποιούνται ως ranges με fuzzy overlap αντί για απλή απόσταση midpoints.

### Local-first LLM

Το LLM χρησιμοποιείται μόνο όπου προσθέτει αξία: culture inference όταν λείπει metadata και φυσική γλώσσα για explanations.

## Περιορισμοί

- Τα labels βασίζονται σε metadata-derived weak supervision, όχι σε χειροκίνητη curator annotation.
- Το ROC-AUC μετρά ranking quality, όχι τέλεια probability calibration.
- Το Node2Vec cache μπορεί να χρειαστεί χρόνο για να ξαναχτιστεί.
- Η ποιότητα των explanations εξαρτάται από το τοπικό LLM.
- Το sample των 50.000 αντικειμένων είναι αντιπροσωπευτικό subset, όχι ολόκληρη η συλλογή.

## Μελλοντικές Βελτιώσεις

- calibrated probabilities με isotonic regression ή Platt scaling,
- curator-labeled validation set,
- περισσότερα graph embedding experiments,
- visual similarity από εικόνες αντικειμένων,
- RDF/JSON-LD export predicted relationships,
- richer filters στο dashboard,
- model cards και πιο αναλυτικό evaluation report.

## Συμπέρασμα

Το MetLinkPrediction είναι πλήρες prototype για cultural heritage link prediction. Η νεότερη έκδοση έχει πιο ισχυρό structural feature layer, προστασία από graph leakage, XGBoost με monotonic constraints, fuzzy temporal modeling και diagnostics που βοηθούν να εξηγηθεί αν η συμπεριφορά του classifier προκύπτει από πραγματικό signal ή από artifacts.
