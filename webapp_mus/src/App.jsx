import React, { useState, useCallback, useEffect, useRef } from "react";
import "./App.css";

// ⚡ Διόρθωση θύρας ώστε να χτυπάει σωστά το FastAPI backend σου
const API_BASE = "http://localhost:4345/api";

const PREVIEW_CONNECTION_CARDS = [
  {
    object_id: "1975.1.2",
    title: "Stone of Stogion",
    culture: "Stone",
    department: "Egyptian Art",
    similarity: 0.94,
    probability: 0.88,
    explanation: "This specimen exhibits core stylistic patterns and geometrical alignments common to late period monolithic structures discovered within the region.",
    img: "https://media-cldnry.s-nbcnews.com/image/upload/rockcms/2024-08/240812-Stonehenge-al-1453-500701.jpg",
  },
  {
    object_id: "42.50.3",
    title: "Aaleh Jopham",
    culture: "Stone",
    department: "Islamic Art",
    similarity: 0.89,
    probability: 0.75,
    explanation: "Features intricate surface engravings matching structural signatures found across coastal architectural elements.",
    img: "https://images.unsplash.com/photo-1579783902614-a3fb3927b6a5?w=150&auto=format&fit=crop&q=60",
  },
  {
    object_id: "1989.2.1",
    title: "Masnrune of the Soidom",
    culture: "Stone",
    department: "Medieval Art",
    similarity: 0.85,
    probability: 0.70,
    explanation: "A deeply preserved ceremonial block showcasing distinctive relief work consistent with early structural foundations.",
    img: "https://www.yeovilhistory.info/images2/medieval-mason.jpg",
  },
  {
    object_id: "2001.4.12",
    title: "Stonwe of Soplon",
    culture: "Stone",
    department: "Ancient Near Eastern Art",
    similarity: 0.81,
    probability: 0.64,
    explanation: "Altered positioning markers indicating alternative installation placements inside historical gallery chambers.",
    img: "https://res.cloudinary.com/aenetworks/image/upload/c_fill,ar_2,w_3840,h_1920,g_auto/f_auto/q_auto:eco/v1/stone-of-scone-gettyimages-686968548",
  },
];

function ExplainModal({ state, onClose }) {
  if (!state || !state.open) return null;

  const { loading, error, sourceObject, targetObject, explanation, metrics } = state;

  const handleCopy = () => {
    if (explanation) navigator.clipboard.writeText(explanation);
  };

  return (
    <div className="explain-modal-overlay" onClick={onClose}>
      <div className="explain-modal" onClick={(e) => e.stopPropagation()}>
        <div className="explain-modal-header">
          <div className="explain-modal-pair">
            <span className="explain-modal-object">{sourceObject?.title || "Object A"}</span>
            <span className="explain-modal-arrow">↓</span>
            <span className="explain-modal-object">{targetObject?.title || "Object B"}</span>
          </div>
          <button className="explain-modal-close" onClick={onClose} aria-label="Close">✕</button>
        </div>

        <div className="explain-modal-body">
          {loading && (
            <div className="explain-modal-loading">
              <div className="explain-spinner" />
              <p>Asking the local model to explain this relationship…</p>
            </div>
          )}

          {!loading && error && (
            <p className="explain-modal-error">{error}</p>
          )}

          {!loading && !error && explanation && (
            <>
              <div className="explain-modal-text">{explanation.replace(/\*\*/g, '')}</div>

              {metrics && Object.keys(metrics).length > 0 && (
                <details className="explain-metrics">
                  <summary>Similarity Metrics</summary>
                  <ul className="explain-metrics-list">
                    {Object.entries(metrics).map(([key, value]) => (
                      <li key={key}>
                        <span className="explain-metrics-key">{key}</span>
                        <span className="explain-metrics-value">
                          {typeof value === "number" ? value.toFixed(3) : String(value)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </>
          )}
        </div>

        <div className="explain-modal-footer">
          <button className="btn-copy" onClick={handleCopy} disabled={!explanation}>
            Copy
          </button>
          <button className="btn-outline-modal" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

function VitrineShowcase({ title, children, className = "" }) {
  return (
    <div className={`vitrine-wrapper ${className}`}>
      {title && <h2 className="panel-title">{title}</h2>}
      <div className="vitrine-glass-top"></div>
      <div className="vitrine-glass-body">{children}</div>
      <div className="vitrine-base-stand"></div>
    </div>
  );
}

function Header() {
  return (
    <header className="hero-header">
      <div className="hero-overlay"></div>
      <div className="hero-architecture-lines"></div>
      <div className="hero-content">
        <div className="logo-container">
          <span className="logo-main">THE</span>
          <span className="logo-sub">MET</span>
        </div>
        <p className="hero-subtitle">CULTURAL KNOWLEDGE GRAPH</p>
      </div>
    </header>
  );
}

// 🖼️ Αναβαθμισμένο component: Δείχνει την εικόνα του αντικειμένου και αν δεν υπάρχει βάζει το γράμμα
function ObjectThumbnail({ imageUrl, title }) {
  const [error, setError] = useState(false);
  const letter = (title || "?").trim().charAt(0).toUpperCase();

  if (imageUrl && !error) {
    return (
      <div className="card-thumb-wrapper">
        <img 
          src={imageUrl} 
          alt={title} 
          className="conn-thumb" 
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
          onError={() => setError(true)}
        />
      </div>
    );
  }

  return (
    <div className="card-thumb-wrapper card-thumb-fallback">
      <span>{letter}</span>
    </div>
  );
}

function SearchCard({ item, onClick }) {
  // Μια απλή συνάρτηση για να δίνουμε ένα όμορφο emoji ανάλογα με το Department ή το Object Name
  const getIcon = (dept) => {
    if (!dept) return "🏛️";
    const d = dept.toLowerCase();
    if (d.includes("wing") || d.includes("american")) return "🇺🇸";
    if (d.includes("arms") || d.includes("armor")) return "⚔️";
    if (d.includes("european") || d.includes("sculpture")) return "🗿";
    if (d.includes("paintings")) return "🎨";
    return "🏺";
  };

  return (
    <button type="button" className="search-card" onClick={onClick}>
      <ObjectThumbnail imageUrl={item.image_url} title={item.title} />
      <div className="card-info">
        <div className="card-badge-row">
          <span className="museum-mini-badge">
            {getIcon(item.department)} {item.department || "General"}
          </span>
        </div>
        <span className="card-id">ID: {item.object_id}</span>
        <h4 className="card-title">{item.title}</h4>
        
        {/* Εμφάνιση του υλικού ή της χρονολογίας με πιο κομψό τρόπο */}
        <p className="card-meta-text">
          <span>🌍 {item.culture || "Άγνωστη κουλτούρα"}</span>
          {item.year && <span> • ⏳ {item.year}</span>}
        </p>
      </div>
    </button>
  );
}

function InteractiveMap() {
  return (
    <div className="interactive-map">
      <svg className="map-svg" viewBox="0 0 200 100">
        <path d="M10 20 Q 50 10 100 30 T 190 20" fill="none" stroke="rgba(120,170,190,0.4)" strokeWidth="0.75" />
        <path d="M20 50 Q 80 40 120 70 T 180 50" fill="none" stroke="rgba(120,170,190,0.4)" strokeWidth="0.75" />
        <path d="M40 80 Q 90 90 140 60 T 170 80" fill="none" stroke="rgba(120,170,190,0.4)" strokeWidth="0.75" />
        <line x1="35" y1="45" x2="70" y2="35" stroke="rgba(50,70,80,0.8)" strokeWidth="1" />
        <line x1="70" y1="35" x2="105" y2="55" stroke="rgba(50,70,80,0.8)" strokeWidth="1" />
        <line x1="105" y1="55" x2="145" y2="40" stroke="rgba(50,70,80,0.8)" strokeWidth="1" />
        <line x1="105" y1="55" x2="115" y2="75" stroke="rgba(50,70,80,0.8)" strokeWidth="1" />
        <line x1="145" y1="40" x2="175" y2="65" stroke="rgba(50,70,80,0.8)" strokeWidth="1" />
        <circle cx="35" cy="45" r="3.5" fill="#1d1d1d" className="map-node" />
        <circle cx="70" cy="35" r="5" fill="#1d1d1d" className="map-node" />
        <circle cx="105" cy="55" r="5.5" fill="#1d1d1d" className="map-node" />
        <circle cx="145" cy="40" r="4.5" fill="#1d1d1d" className="map-node" />
        <circle cx="115" cy="75" r="3.5" fill="#1d1d1d" className="map-node" />
        <circle cx="175" cy="65" r="4" fill="#1d1d1d" className="map-node" />
      </svg>
    </div>
  );
}

function SearchPanel({
  radius,
  setRadius,
  searchQuery,
  setSearchQuery,
  searchResults,
  onSelectSuggestion,
  selected,
  loadingRelated,
  onFindRelated,
}) {
  return (
    <VitrineShowcase title="Core Object Search">
      <div className="search-bar-container">
        <span className="search-icon">🔍</span>
        <input
          type="text"
          className="main-search-input"
          placeholder="Search catalog object by title, culture, or ID..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
      </div>

      {selected && (
        <div className="selected-object-bar">
          <div className="selected-object-info">
            <ObjectThumbnail imageUrl={selected.image_url} title={selected.title} />
            <div className="card-info">
              <span className="card-id">Object ID: {selected.object_id}</span>
              <h4 className="card-title card-title--selected">{selected.title}</h4>
              <p className="card-meta">Culture: {selected.culture || "unknown"}</p>
              <p className="card-meta">Department: {selected.department || "unknown"}</p>
            </div>
          </div>
          <button
            type="button"
            className="find-related-button"
            onClick={onFindRelated}
            disabled={loadingRelated}
          >
            {loadingRelated ? "Searching..." : "Find Related Objects"}
          </button>
        </div>
      )}

      <div className="search-cards-grid">
        {searchResults.length === 0 && searchQuery.trim() !== "" && (
          <p className="empty-state">No matching objects found.</p>
        )}
        {searchResults.map((item) => (
          <SearchCard key={item.object_id} item={item} onClick={() => onSelectSuggestion(item)} />
        ))}
      </div>

      <div className="search-controls-row">
        <div className="radius-control-box">
          <div className="control-header">
            <span className="control-label">Search Results (2-50)</span>
            <span className="control-value-display">{radius}</span>
          </div>
          <input
            type="range"
            min="2"
            max="50"
            value={radius}
            onChange={(e) => setRadius(Number(e.target.value))}
            className="museum-slider"
          />
          <div className="slider-labels">
            <span>Strict</span>
            <span>Range</span>
            <span>Broad</span>
          </div>
        </div>

        <div className="map-preview-box">
          <span className="control-label">Interactive Map</span>
          <span className="map-subtext">Viewing collection relations.</span>
          <InteractiveMap />
        </div>
      </div>
    </VitrineShowcase>
  );
}

function ControlPanel({ limit, setLimit }) {
  return (
    <div className="panel control-panel">
      <h2 className="panel-title panel-title--flat">Exploration Controls</h2>
      <div className="limit-control-container">
        <div className="control-header">
          <span className="control-label">Related objects (1-50)</span>
          <span className="control-value-display font-large">{limit}</span>
        </div>
        <input
          type="range"
          min="1"
          max="50"
          value={limit}
          onChange={(e) => setLimit(Number(e.target.value))}
          className="museum-slider"
        />
        <div className="slider-labels font-padded">
          <span>Strict</span>
          <span>Broad</span>
        </div>
      </div>
    </div>
  );
}

function ConnectionCard({ item, sourceObject, onExplain }) {
  return (
    <div className="connection-card">
      {/* 🖼️ Μεγάλη εικόνα για το αποτέλεσμα της συσχέτισης */}
      <div className="conn-thumb-wrapper">
        <img 
          src={item.object.image_url} 
          alt={item.object.title} 
          className="conn-thumb"
          onError={(e) => {
            e.target.src = "https://images.unsplash.com/photo-1580136579312-94651dfd596d?w=500";
          }}
        />
      </div>
      <div className="conn-info">
        <span className="card-id">Object ID: {item.object.object_id}</span>
        <h4 className="card-title">{item.object.title}</h4>
        <p className="card-meta"><span className="meta-label">Culture:</span> {item.object.culture || "unknown"}</p>
        <p className="card-meta"><span className="meta-label">Department:</span> {item.object.department || "unknown"}</p>
        <p className="card-meta"><span className="meta-label">Similarity:</span> {item.cosine_similarity.toFixed(2)}</p>
        <p className="card-meta"><span className="meta-label">Probability:</span> {Math.round(item.probability * 100)}%</p>
        {/* <p className="conn-desc">{item.explanation}</p> */}
        <button
          type="button"
          className="btn-explain-relationship"
          onClick={() => onExplain(sourceObject, item.object)}
        >
          💬 Explain Relationship
        </button>
      </div>
    </div>
  );
}

export default function App() {
  const [radius, setRadius] = useState(12);
  const [limit, setLimit] = useState(8);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [selected, setSelected] = useState(null);
  const [related, setRelated] = useState([]);
  const [loadingRelated, setLoadingRelated] = useState(false);
  const [error, setError] = useState(null);
  const [explainState, setExplainState] = useState(null); // { open, loading, error, sourceObject, targetObject, explanation, metrics }

  const skipNextSearchRef = useRef(false);

  useEffect(() => {
    if (skipNextSearchRef.current) {
      skipNextSearchRef.current = false;
      return;
    }
    if (!searchQuery.trim()) {
      setSearchResults([]);
      return;
    }
    const controller = new AbortController();
    fetch(`${API_BASE}/search?q=${encodeURIComponent(searchQuery)}&limit=${radius}`, {
      signal: controller.signal,
    })
      .then((res) => res.json())
      .then(setSearchResults)
      .catch((err) => {
        if (err.name !== "AbortError") setError("Could not reach the API.");
      });
    return () => controller.abort();
  }, [searchQuery, radius]);

  const handleSelectSuggestion = useCallback((item) => {
    skipNextSearchRef.current = true;
    setSearchQuery(item.title);
    setSearchResults([]);
    setRelated([]);
    setError(null);
    fetch(`${API_BASE}/object/${item.object_id}`)
      .then((res) => res.json())
      .then(setSelected)
      .catch(() => setError("Could not load that object."));
  }, []);

  const handleFindRelated = useCallback(() => {
    if (!selected) return;
    setLoadingRelated(true);
    setError(null);
    fetch(`${API_BASE}/related/${selected.object_id}?k=${limit}`)
      .then((res) => res.json())
      .then((data) => {
        setRelated(data);
        setLoadingRelated(false)
      })
      .catch(() => {
        setError("Could not compute related objects.");
        setLoadingRelated(false);
      });
  }, [selected, limit]);

  const handleExplainRelationship = useCallback((sourceObject, targetObject) => {
    if (!sourceObject || !targetObject) return;

    setExplainState({
      open: true,
      loading: true,
      error: null,
      sourceObject,
      targetObject,
      explanation: null,
      metrics: null,
    });

    fetch(`${API_BASE}/explain-relationship`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_object_id: sourceObject.object_id,
        target_object_id: targetObject.object_id,
      }),
    })
      .then((res) => {
        if (!res.ok) throw new Error(`Server returned ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setExplainState((prev) => ({
          ...prev,
          loading: false,
          explanation: data.explanation || "No explanation was returned.",
          metrics: data.metrics || data.similarity_metrics || null,
        }));
      })
      .catch(() => {
        setExplainState((prev) => ({
          ...prev,
          loading: false,
          error: "Could not generate an explanation right now. Please try again.",
        }));
      });
  }, []);

  const closeExplainModal = useCallback(() => {
    setExplainState((prev) => (prev ? { ...prev, open: false } : prev));
  }, []);

  return (
    <div className="app-container">
      <Header />
      <main className="dashboard-grid">
        <div className="grid-row-one-left">
          <SearchPanel
            radius={radius}
            setRadius={setRadius}
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
            searchResults={searchResults}
            onSelectSuggestion={handleSelectSuggestion}
            selected={selected}
            loadingRelated={loadingRelated}
            onFindRelated={handleFindRelated}
          />
        </div>
        <div className="grid-row-one-right">
          <ControlPanel limit={limit} setLimit={setLimit} />
        </div>

        <div className="grid-row-two-right">
          <VitrineShowcase title="Culturally Similar Connections" className="connections-vitrine">
            {loadingRelated ? (
              <div className="preview-overlay">
                <p className="preview-text">Searching...</p>
              </div>
            ) : related.length === 0 ? (
              <div className="connection-preview-wrapper">
                <div className="connection-cards-stack connection-cards-stack--preview">
                  {PREVIEW_CONNECTION_CARDS.map((item, i) => (
                    <div className="connection-card" key={i}>
                      <div className="conn-thumb-wrapper">
                        <img src={item.img} alt="" className="conn-thumb" />
                      </div>
                      <div className="conn-info">
                        <span className="card-id">Object ID: {item.object_id}</span>
                        <h4 className="card-title">{item.title}</h4>
                        <p className="card-meta"><span className="meta-label">Culture:</span> {item.culture || "unknown"}</p>
                        <p className="card-meta"><span className="meta-label">Department:</span> {item.department || "unknown"}</p>
                        <p className="card-meta"><span className="meta-label">Similarity:</span> {item.similarity.toFixed(2)}</p>
                        <p className="card-meta"><span className="meta-label">Probability:</span> {Math.round(item.probability * 100)}%</p>
                        <p className="conn-desc">{item.explanation}</p>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="preview-overlay">
                  <p className="preview-text">
                    {selected
                      ? 'Click "Find Related Objects" above to generate results.'
                      : "Select an object to see suggested connections."}
                  </p>
                </div>
              </div>
            ) : (
              <div className="connection-cards-stack">
                {related.map((item) => (
                  <ConnectionCard key={item.object.object_id} item={item} sourceObject={selected} onExplain={handleExplainRelationship} />
                ))}
              </div>
            )}
          </VitrineShowcase>
        </div>
      </main>
      {error && <p className="page__error" style={{ textAlign: "center", padding: "1rem" }}>{error}</p>}
      <ExplainModal state={explainState} onClose={closeExplainModal} />
    </div>
  );
}