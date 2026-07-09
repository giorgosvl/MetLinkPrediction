# MetLinkPrediction

## Περιγραφή

Το **MetLinkPrediction** είναι ένα end-to-end project για πρόβλεψη πιθανών σχέσεων ανάμεσα σε αντικείμενα της συλλογής του **Metropolitan Museum of Art (MET)**. Η υλοποίηση συνδυάζει καθαρισμό πραγματικών μουσειακών δεδομένων, τοπικό LLM enrichment, semantic embeddings, FAISS similarity search, ετερογενές knowledge graph, supervised link prediction, fuzzy temporal reasoning και curator-facing dashboard με εξηγήσεις.

Ο βασικός στόχος είναι να εντοπίζονται αντικείμενα που πιθανόν συνδέονται πολιτισμικά, σημασιολογικά ή χρονικά, ακόμα και όταν η σχέση δεν είναι άμεσα αποθηκευμένη ως ρητό metadata field.

## Τι κάνει το project

Το σύστημα ξεκινά από το αρχικό αρχείο `MetObjects.txt` του MET Open Access dataset και παράγει:

- καθαρισμένο dataset με σταθερή περιγραφή κάθε αντικειμένου,
- αντιπροσωπευτικό sample 50.000 αντικειμένων,
- εμπλουτισμένα metadata με fast-path extraction και τοπικό LLM όπου χρειάζεται,
- semantic embeddings για κάθε αντικείμενο,
- FAISS index για γρήγορη αναζήτηση γειτονικών αντικειμένων,
- ετερογενές knowledge graph object-to-attribute,
- θετικά/αρνητικά training pairs για link prediction,
- gradient boosting μοντέλο πρόβλεψης σχέσεων,
- fuzzy temporal score που χειρίζεται αβεβαιότητα στις χρονολογήσεις,
- Streamlit και React/FastAPI dashboard για αναζήτηση και επεξήγηση αποτελεσμάτων.

## Αρχιτεκτονική Pipeline

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
      +----------------------+
      |                      |
      v                      v
04_build_embeddings.py   05_build_graph.py
      |                      |
      v                      v
embeddings/              graph/
      |                      |
      +----------+-----------+
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
 dashboard_core.py + Streamlit / FastAPI / React UI
```

## Δομή Αρχείων

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
├── dashboard_core.py
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

## Υλοποίηση ανά Στάδιο

### 1. Preprocessing

Αρχείο: `01_preprocessing.py`

Το πρώτο στάδιο φορτώνει το raw MET export και κρατά μόνο τα πεδία που είναι χρήσιμα για downstream semantic search, graph construction και temporal reasoning.

Βασικές επιλογές υλοποίησης:

- Διατηρούνται τα `Object Begin Date` και `Object End Date`, επειδή χρειάζονται αργότερα για fuzzy temporal matching.
- Δεν απορρίπτονται τυφλά όλα τα rows χωρίς `Title`. Αν υπάρχει `Object Name`, το αντικείμενο παραμένει χρήσιμο.
- Κανονικοποιούνται placeholders όπως `Unknown`, `unidentified`, `N/A`, κενές τιμές κ.λπ.
- Δημιουργείται πεδίο `Description`, δηλαδή μία συμπαγής λεκτική περιγραφή με labeled facts.
- Δημιουργείται flag `has_sparse_metadata`, ώστε να ξεχωρίζουν αντικείμενα με ελλιπή δομημένα metadata.
- Δημιουργείται flag `is_duplicate_description`, επειδή τα duplicate descriptions μπορούν να δημιουργήσουν τεχνητά υψηλές ομοιότητες.

Παραγόμενο αρχείο:

```text
met_clean.csv
```

### 2. Representative Sampling

Αρχείο: `03_sample_dataset.py`

Το πλήρες dataset είναι πολύ μεγάλο για γρήγορη end-to-end επεξεργασία σε consumer hardware. Για αυτό δημιουργείται αντιπροσωπευτικό sample 50.000 αντικειμένων.

Η δειγματοληψία δεν είναι απλό random sample. Η υλοποίηση:

- αφαιρεί exact duplicate descriptions,
- υπολογίζει `quality_score` με βάση πόσα πληροφοριακά metadata fields υπάρχουν,
- φιλτράρει rows χαμηλής ποιότητας,
- κάνει stratified sampling ως προς το `Classification`,
- κρατά καλύτερη ισορροπία ανά κατηγορία αντικειμένων.

Παραγόμενο αρχείο:

```text
met_sample_50000.csv
```

### 3. Local LLM Metadata Extraction

Αρχείο: `02_ollama_extraction.py`

Το project χρησιμοποιεί τοπικό Ollama μοντέλο (`llama3.1`) για περιορισμένη πληροφοριακή εξαγωγή. Η υλοποίηση αποφεύγει να καλεί LLM για πεδία που ήδη υπάρχουν δομημένα.

Η λογική χωρίζεται σε δύο paths:

- **Fast path:** αντιγράφει άμεσα `material`, `year`, `object_type` και `culture` από υπάρχοντα metadata όπου αυτά υπάρχουν.
- **LLM path:** καλεί το τοπικό LLM μόνο όταν λείπει το `Culture` και υπάρχει αρκετή περιγραφή ώστε να μπορεί να εξαχθεί πιθανή πολιτισμική πληροφορία.

Σημαντικά χαρακτηριστικά:

- concurrent requests με `ThreadPoolExecutor`,
- resumable processing μέσω υπάρχοντος output file,
- checkpointing κάθε 200 LLM calls,
- retries και timeout handling,
- JSON-only prompt ώστε το output να είναι parseable.

Παραγόμενο αρχείο:

```text
met_with_extracted_info.csv
```

### 4. Semantic Embeddings και FAISS Index

Αρχείο: `04_build_embeddings.py`

Σε αυτό το στάδιο κάθε `Description` μετατρέπεται σε dense vector embedding μέσω τοπικού Ollama embedding model.

Default μοντέλο:

```text
nomic-embed-text
```

Η υλοποίηση:

- καλεί το Ollama embeddings API,
- αποθηκεύει embeddings σε `.npy`,
- αποθηκεύει mapping `Object ID -> vector row`,
- είναι resumable ώστε να μη χάνονται ώρες υπολογισμού,
- κάνει L2 normalization,
- χτίζει FAISS `IndexFlatIP`, που σε normalized vectors ισοδυναμεί με cosine similarity search.

Παραγόμενα αρχεία:

```text
embeddings/embeddings.npy
embeddings/embedding_object_ids.json
embeddings/met.faiss
```

### 5. Knowledge Graph Construction

Αρχείο: `05_build_graph.py`

Το graph στάδιο χτίζει ετερογενές graph αντί για απλό object-object graph.

Αν δύο αντικείμενα μοιράζονται artist, tag ή department, δεν συνδέονται απευθείας μεταξύ τους. Αντίθετα, δημιουργούνται hub nodes:

```text
obj:123 --has_artist--> has_artist:Artist Name
obj:456 --has_artist--> has_artist:Artist Name
```

Αυτή η επιλογή είναι σημαντική, γιατί αποφεύγει το combinatorial explosion. Αν ένας artist έχει 1.000 αντικείμενα, ένα απευθείας clique θα δημιουργούσε εκατοντάδες χιλιάδες object-object edges. Με το hub-based graph, η πολυπλοκότητα γίνεται σχεδόν γραμμική ως προς τα object-attribute pairs.

Το script δημιουργεί επίσης candidate positive pairs για supervised link prediction. Τα positive pairs προκύπτουν από συγκεκριμένα shared hubs όπως artist και tag, αλλά όχι από υπερβολικά γενικά hubs όπως broad culture/classification.

Παραγόμενα αρχεία:

```text
graph/graph.graphml
graph/candidate_pairs.csv
graph/graph_stats.json
```

Graph statistics από την τρέχουσα εκτέλεση:

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

### 6. Link Prediction

Αρχείο: `06_link_prediction.py`

Το link prediction στάδιο εκπαιδεύει supervised classifier που εκτιμά την πιθανότητα δύο αντικείμενα να σχετίζονται.

Positive examples:

- pairs από το `graph/candidate_pairs.csv`,
- βασίζονται σε τεκμηριωμένη shared identity όπως artist ή tag.

Negative examples:

- random object pairs που δεν μοιράζονται artist ή tag,
- sampled 1:1 με τα positives ώστε το training set να είναι balanced.

Χρησιμοποιούμενα features:

```text
cosine_similarity
shared_culture
shared_department
year_gap
```

Σημαντική σχεδιαστική επιλογή:

Το μοντέλο **δεν** παίρνει ως input το `shared_artist` ή το `shared_tag`, παρότι αυτά χρησιμοποιήθηκαν για την παραγωγή positive labels. Αν τα έπαιρνε ως features, θα μάθαινε απλώς τον τρόπο δημιουργίας των labels και όχι πραγματικό link prediction. Έτσι αποφεύγεται ένας κυκλικός/trivial classifier.

Μοντέλο:

```text
HistGradientBoostingClassifier
```

Επιλέχθηκε γιατί:

- χειρίζεται missing values,
- χρειάζεται λιγότερο tuning από MLP,
- λειτουργεί καλά σε tabular features,
- δίνει δυνατότητα feature importance analysis.

Αποτελέσματα τρέχουσας εκτέλεσης:

```json
{
  "roc_auc": 0.9687,
  "n_train": 51286,
  "n_test": 12822,
  "feature_importance": {
    "cosine_similarity": 0.3913,
    "year_gap": 0.0084,
    "shared_department": 0.0051,
    "shared_culture": 0.004
  }
}
```

Παραγόμενα αρχεία:

```text
link_prediction/link_prediction_dataset.csv
link_prediction/link_predictor.joblib
link_prediction/evaluation.json
```

### 7. Fuzzy Temporal Reasoning

Αρχείο: `07_fuzzy_temporal.py`

Το αρχικό `year_gap` είναι απλοϊκό, γιατί συμπυκνώνει χρονολογικά ranges σε ένα μόνο midpoint. Αυτό χάνει την αβεβαιότητα που υπάρχει σε μουσειακές χρονολογήσεις όπως `circa 1447-1475`.

Η fuzzy temporal υλοποίηση συγκρίνει ranges:

```text
[Object A Begin, Object A End]
[Object B Begin, Object B End]
```

Αν τα ranges επικαλύπτονται:

```text
membership = 1.0
```

Αν δεν επικαλύπτονται, το score μειώνεται ομαλά με Gaussian-style decay:

```text
membership = exp(-(gap^2) / (2 * tolerance^2))
```

Default tolerance:

```text
50 years
```

Το script κάνει ablation study με τρεις εκδοχές:

- raw `year_gap`,
- μόνο `fuzzy_temporal_membership`,
- και τα δύο temporal features.

Αποτελέσματα:

```json
{
  "raw_year_gap_only": {
    "roc_auc": 0.9687
  },
  "fuzzy_temporal_only": {
    "roc_auc": 0.9684
  },
  "both_temporal_features": {
    "roc_auc": 0.9687
  }
}
```

Το αποτέλεσμα δείχνει ότι η σημασιολογική ομοιότητα είναι το κυρίαρχο signal, ενώ τα temporal features λειτουργούν συμπληρωματικά.

Παραγόμενα αρχεία:

```text
fuzzy/link_prediction_dataset_with_fuzzy.csv
fuzzy/link_predictor_fuzzy.joblib
fuzzy/fuzzy_ablation_results.json
```

### 8. Dashboard και Explainability

Αρχεία:

```text
dashboard_core.py
09_dashboard_app.py
webapp_mus/
```

Το dashboard επιτρέπει σε χρήστη/curator να επιλέξει ένα αντικείμενο και να δει πιθανές σχέσεις με άλλα αντικείμενα.

Η λογική βρίσκεται στο `dashboard_core.py`:

1. Φορτώνει metadata, embeddings και trained model.
2. Βρίσκει nearest neighbors με cosine similarity.
3. Υπολογίζει features για κάθε candidate pair.
4. Προβλέπει link probability.
5. Ζητά από το τοπικό LLM να γράψει σύντομη επεξήγηση.
6. Αν το Ollama δεν είναι διαθέσιμο, επιστρέφει deterministic template explanation.

Υπάρχουν δύο UI επιλογές:

- `09_dashboard_app.py`: Streamlit dashboard.
- `webapp_mus/`: FastAPI backend + React/Vite frontend.

### 9. Calibration Check

Αρχείο: `10_calibration_check.py`

Το script ελέγχει αν οι πιθανότητες του classifier είναι ουσιαστικά βαθμονομημένες ή αν κολλάνε κοντά στο 1.0 για πολλά candidates. Περιλαμβάνει:

- synthetic sweep όπου αλλάζει μόνο το cosine similarity,
- histogram των predicted probabilities στο πραγματικό dataset.

Αυτό βοηθά να ξεχωρίσουμε το ranking quality από το probability calibration.

## Εγκατάσταση

### Python dependencies

Ενδεικτικά απαιτούνται:

```bash
pip install pandas numpy requests scikit-learn joblib networkx streamlit fastapi uvicorn
```

Για FAISS:

```bash
pip install faiss-cpu
```

### Ollama

Το project χρησιμοποιεί τοπικό Ollama.

Για LLM extraction και explanations:

```bash
ollama pull llama3.1
```

Για embeddings:

```bash
ollama pull nomic-embed-text
```

Προαιρετικά, για καλύτερη παράλληλη εκτέλεση:

```bash
OLLAMA_NUM_PARALLEL=4 ollama serve
```

Σε Windows PowerShell:

```powershell
$env:OLLAMA_NUM_PARALLEL="4"
ollama serve
```

## Εκτέλεση Pipeline

Τυπική σειρά εκτέλεσης:

```bash
python 01_preprocessing.py
python 03_sample_dataset.py --input met_clean.csv --output met_sample_50000.csv --n 50000
python 02_ollama_extraction.py --input met_sample_50000.csv --output met_with_extracted_info.csv --workers 4
python 04_build_embeddings.py --input met_with_extracted_info.csv --out-dir embeddings --workers 4
python 05_build_graph.py --input met_with_extracted_info.csv --out-dir graph
python 06_link_prediction.py --embeddings embeddings/embeddings.npy --embedding-ids embeddings/embedding_object_ids.json --pairs graph/candidate_pairs.csv --metadata met_with_extracted_info.csv --out-dir link_prediction
python 07_fuzzy_temporal.py --dataset link_prediction/link_prediction_dataset.csv --metadata met_with_extracted_info.csv --out-dir fuzzy
```

Για calibration:

```bash
python 10_calibration_check.py --model fuzzy/link_predictor_fuzzy.joblib --dataset fuzzy/link_prediction_dataset_with_fuzzy.csv
```

## Εκτέλεση Dashboard

### Streamlit

```bash
streamlit run 09_dashboard_app.py
```

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

Το frontend τρέχει συνήθως στο:

```text
http://localhost:5173
```

## Δεδομένα και Μεγάλα Αρχεία

Το repository περιλαμβάνει μεγάλα data/model artifacts. Τα μεγαλύτερα αποθηκεύονται μέσω Git LFS:

```text
MetObjects.txt
met_clean.csv
embeddings/embeddings.npy
embeddings/met.faiss
```

Αν κάνετε clone το repository, χρειάζεται Git LFS:

```bash
git lfs install
git lfs pull
```

## Βασικές Τεχνικές Αποφάσεις

### Αποφυγή duplicate-driven similarity

Το dataset περιέχει πολλά αντικείμενα με πανομοιότυπες περιγραφές. Αν δεν αντιμετωπιστούν, το embedding similarity μπορεί να θεωρήσει duplicate text ως ουσιαστική πολιτισμική σχέση. Για αυτό υπολογίζονται duplicate flags και το sampling αφαιρεί exact duplicate descriptions.

### Heterogeneous graph αντί για object-object clique

Η χρήση hub nodes για artists, departments, cultures, classifications και tags αποτρέπει την εκρηκτική αύξηση edges και κρατά το graph αναγνώσιμο και επεκτάσιμο.

### Αποφυγή label leakage

Τα shared artist/tag χρησιμοποιούνται για να οριστούν positive examples, αλλά δεν δίνονται ως input features στο μοντέλο. Έτσι το μοντέλο δεν μαθαίνει απλώς τον κανόνα παραγωγής των labels.

### Local-first LLM usage

Το LLM δεν χρησιμοποιείται παντού. Χρησιμοποιείται μόνο όπου προσθέτει αξία:

- culture inference όταν λείπει δομημένη πληροφορία,
- plain-language explanation στο dashboard.

Για πληροφορίες που ήδη υπάρχουν στα metadata, η υλοποίηση προτιμά deterministic fast path.

### Fuzzy temporal logic

Οι χρονολογήσεις μουσείων συχνά είναι ranges και όχι ακριβείς ημερομηνίες. Το fuzzy temporal membership χειρίζεται αυτή την αβεβαιότητα καλύτερα από ένα απλό midpoint difference.

## Περιορισμοί

- Τα positive pairs βασίζονται σε shared metadata και όχι σε ανθρώπινη curator annotation.
- Το ROC-AUC δείχνει καλή ικανότητα ranking, αλλά δεν εγγυάται τέλεια calibrated probabilities.
- Η ποιότητα των explanations εξαρτάται από το τοπικό LLM.
- Τα embeddings εξαρτώνται από το επιλεγμένο embedding model.
- Το sample των 50.000 αντικειμένων είναι αντιπροσωπευτικό αλλά όχι ολόκληρη η συλλογή.

## Μελλοντικές Βελτιώσεις

- Χρήση curated ground-truth links από ειδικούς.
- Probability calibration με Platt scaling ή isotonic regression.
- Περισσότερα graph features όπως common neighbors, Adamic-Adar ή node2vec.
- Πειραματισμός με διαφορετικά embedding models.
- Προσθήκη visual similarity για αντικείμενα με εικόνες.
- Καλύτερο UI filtering ανά culture, department, date range και material.
- Export των predicted relationships σε RDF/JSON-LD για χρήση ως knowledge graph artifact.

## Συμπέρασμα

Το project υλοποιεί ένα πλήρες pipeline για cultural heritage link prediction. Η υλοποίηση δεν περιορίζεται σε ένα απλό classifier, αλλά συνδυάζει καθαρισμό δεδομένων, semantic representation, graph-based supervision, fuzzy temporal reasoning και explainable dashboard. Έτσι μπορεί να χρησιμοποιηθεί ως βάση για πειραματική διερεύνηση σχέσεων μέσα σε μεγάλη μουσειακή συλλογή και ως πρακτικό prototype για curator-facing discovery tools.
