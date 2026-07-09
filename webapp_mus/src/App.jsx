import React, { useState, useCallback, useEffect, useRef } from "react";
import "./App.css";

const API_BASE = "http://localhost:4345/api";

// ----------------------------------------------------------------
// Εμπλουτισμένα Mock Data προεπισκόπησης για να εμφανίζουν όλες τις πληροφορίες
// ----------------------------------------------------------------
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

// ============================================================================
// REUSABLE 3D VITRINE WRAPPER COMPONENT
// ============================================================================
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

// ============================================================================
// SUB-COMPONENTS
// ============================================================================
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

function ThumbFallback({ title }) {
  const letter = (title || "?").trim().charAt(0).toUpperCase();
  return (
    <div className="card-thumb-wrapper card-thumb-fallback">
      <span>{letter}</span>
    </div>
  );
}

function SearchCard({ item, onClick }) {
  return (
    <button type="button" className="search-card" onClick={onClick}>
      <ThumbFallback title={item.title} />
      <div className="card-info">
        <span className="card-id">Object ID: {item.object_id}</span>
        <h4 className="card-title">{item.title}</h4>
        <p className="card-meta">Culture: {item.culture || "unknown"}</p>
        <p className="card-meta">Department: {item.department || "unknown"}</p>
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
            <ThumbFallback title={selected.title} />
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

function ConnectionCard({ item }) {
  return (
    <div className="connection-card">
      <ThumbFallback title={item.object.title} />
      <div className="conn-info">
        <span className="card-id">Object ID: {item.object.object_id}</span>
        <h4 className="card-title">{item.object.title}</h4>
        <p className="card-meta"><span className="meta-label">Culture:</span> {item.object.culture || "unknown"}</p>
        <p className="card-meta"><span className="meta-label">Department:</span> {item.object.department || "unknown"}</p>
        <p className="card-meta"><span className="meta-label">Similarity:</span> {item.cosine_similarity.toFixed(2)}</p>
        <p className="card-meta"><span className="meta-label">Probability:</span> {Math.round(item.probability * 100)}%</p>
        <p className="conn-desc">{item.explanation}</p>
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
                  <ConnectionCard key={item.object.object_id} item={item} />
                ))}
              </div>
            )}
          </VitrineShowcase>
        </div>
      </main>
      {error && <p className="page__error" style={{ textAlign: "center", padding: "1rem" }}>{error}</p>}
    </div>
  );
}