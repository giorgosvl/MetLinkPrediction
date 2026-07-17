import React, { useState, useCallback, useEffect, useRef } from "react";
import "./App.css";

const API_BASE = "http://localhost:4345/api";

const STATS_DATA = [
  { count: "52,356", label: "Objects in Graph", icon: "📦" },
  { count: "180,742", label: "Relations Map", icon: "🌿" },
  { count: "94%", label: "Avg. Confidence", icon: "🛡️" },
  { count: "12,842", label: "Cultures & Periods", icon: "👥" }
];

function ExplainModal({ state, onClose }) {
  if (!state || !state.open) return null;

  const { loading, error, sourceObject, targetObject, explanation, metrics } = state;

  const handleCopy = () => {
    if (explanation) navigator.clipboard.writeText(explanation);
  };

  return (
    <div className="explain-modal-overlay" onClick={onClose}>
      <div className="explain-modal-card" onClick={(e) => e.stopPropagation()}>
        
        {/* MODAL HEADER */}
        <div className="explain-modal-header">
          <div className="explain-header-left">
            <div className="explain-sparkle-badge">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 3v3m0 12v3M3 12h3m12 0h3m-2.121-7.121l-2.122 2.122m-7.778 7.778l-2.122 2.122m15.556 0l-2.122-2.122m-7.778-7.778l-2.122-2.122"/>
              </svg>
            </div>
            <div className="explain-header-titles">
              <span className="explain-header-tag">Paired AI Relationship Match</span>
              <h3 className="explain-header-title">
                {sourceObject?.title || "Object A"} ➔ {targetObject?.title || "Object B"}
              </h3>
            </div>
          </div>
          <button className="explain-close-btn" onClick={onClose} aria-label="Close">✕</button>
        </div>

        {/* MODAL BODY */}
        <div className="explain-modal-body">
          
          {/* 1. LOADING STATE */}
          {loading && (
            <div className="explain-loading-view">
              <div className="loading-orb-container">
                <div className="loading-pulse-ring"></div>
                <div className="loading-core-sparkle">✦</div>
              </div>
              <h4 className="loading-status-text">Analyzing cultural overlap metrics...</h4>
              <p className="loading-substatus-text">Please wait while the AI model evaluates the relationship.</p>
            </div>
          )}

          {/* 2. ERROR STATE */}
          {!loading && error && (
            <div className="explain-error-view">
              <span className="error-icon">⚠️</span>
              <p className="error-text-msg">{error}</p>
            </div>
          )}

          {/* 3. SUCCESS STATE */}
          {!loading && !error && explanation && (
            <div className="explain-success-view">
              
              {/* Success Banner */}
              <div className="analysis-complete-banner">
                <div className="success-check-circle">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                </div>
                <div className="banner-text-block">
                  <span className="banner-title">Analysis complete</span>
                  <span className="banner-subtitle">The AI model has analyzed the cultural overlap metrics.</span>
                </div>
              </div>

              {/* Title / Status */}
              <h4 className="analysis-result-title">Σύνοψη Σχέσης & Ανάλυση</h4>

              {/* Explanation Text */}
              <div className="analysis-narrative-text">
                {explanation ? explanation.replace(/\*\*/g, "") : ""}
              </div>

              {/* Metrics Card */}
              {metrics && (
                <div className="overlap-metrics-card">
                  <div className="metrics-card-header">
                    <span className="metrics-header-icon">📊</span>
                    <span className="metrics-header-title">Overlap Metrics</span>
                  </div>
                  <div className="metrics-list-table">
                    {Object.entries(metrics).map(([key, value]) => {
                      const displayKey = key.charAt(0).toUpperCase() + key.slice(1).replace('_', ' ');
                      let displayVal = value;
                      if (typeof value === "number") {
                        displayVal = value.toFixed(3);
                      } else if (typeof value === "boolean") {
                        displayVal = value ? "true" : "false";
                      }
                      
                      return (
                        <div key={key} className="metric-row-item">
                          <span className="metric-row-name">{displayKey}</span>
                          <span className={`metric-row-value ${typeof value === 'boolean' ? 'boolean-val' : 'numeric-val'}`}>
                            {displayVal}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}

        </div>

        {/* MODAL FOOTER */}
        <div className="explain-modal-footer">
          <button 
            type="button" 
            className="copy-explanation-gradient-btn" 
            onClick={handleCopy} 
            disabled={!explanation || loading}
          >
            <span className="btn-copy-icon">📋</span>
            Copy Explanation
          </button>
          <button 
            type="button" 
            className="explain-footer-close-btn" 
            onClick={onClose}
          >
            Close
          </button>
        </div>

      </div>
    </div>
  );
}

export default function App() {
  const [activeTab, setActiveTab] = useState("explorer");
  const [radius, setRadius] = useState(12);
  const [limit, setLimit] = useState(8);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  
  const [searchedBaseObject, setSearchedBaseObject] = useState(null);
  const [selected, setSelected] = useState(null);
  
  const [related, setRelated] = useState([]);
  const [loadingRelated, setLoadingRelated] = useState(false);
  const [error, setError] = useState(null);
  const [explainState, setExplainState] = useState(null);
  const [savedCollections, setSavedCollections] = useState([]);

  // A-B Matrix Comparator States
  const [compSourceId, setCompSourceId] = useState("");
  const [compTargetId, setCompTargetId] = useState("");
  const [compSourceObject, setCompSourceObject] = useState(null);
  const [compTargetObject, setCompTargetObject] = useState(null);

  // AI Museum Assistant States
  const [aiQuery, setAiQuery] = useState("");
  const [aiMessages, setAiMessages] = useState([]); 
  const [aiLastResultIds, setAiLastResultIds] = useState([]);
  const [aiLoading, setAiLoading] = useState(false);

  const skipNextSearchRef = useRef(false);

  // 💡 ΔΗΜΙΟΥΡΓΙΑ REFS ΓΙΑ ΤΟ ΑΥΤΟΜΑΤΟ SCROLL
  const explorerResultsRef = useRef(null);
  const chatEndRef = useRef(null);

  // 💡 EFFECT 1: Αυτόματο scroll στα αποτελέσματα του Explorer
  useEffect(() => {
    if (activeTab === "explorer" && (related.length > 0 || searchResults.length > 0) && explorerResultsRef.current) {
      explorerResultsRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [related, searchResults, activeTab]);

  // 💡 EFFECT 2: Αυτόματο scroll στο κάτω μέρος του AI Chat
  useEffect(() => {
    if (activeTab === "assistant" && chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [aiMessages, aiLoading, activeTab]);

  // Live Search
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
      .then((data) => {
        setSearchResults(data);
        setRelated([]); 
      })
      .catch((err) => {
        if (err.name !== "AbortError") setError("Could not reach the API.");
      });
    return () => controller.abort();
  }, [searchQuery, radius]);

  // Φόρτωση του επιλεγμένου αντικειμένου στο Workspace
  const loadObjectIntoWorkspace = useCallback((item, autoFetchRelated = false) => {
    skipNextSearchRef.current = true;
    setSearchQuery(item.title);
    setSearchResults([]);
    setRelated([]);
    setError(null);
    setLoadingRelated(true);
    
    fetch(`${API_BASE}/object/${item.object_id}`)
      .then((res) => res.json())
      .then((data) => {
        setSearchedBaseObject(data); 
        setSelected(data);           
        
        if (autoFetchRelated) {
          fetch(`${API_BASE}/related/${item.object_id}?k=${limit}`)
            .then((r) => r.json())
            .then((relatedData) => {
              setRelated(relatedData);
              setLoadingRelated(false);
            })
            .catch(() => {
              setError("Could not load associated entities.");
              setLoadingRelated(false);
            });
        } else {
          setLoadingRelated(false);
        }
      })
      .catch(() => {
        setError("Could not load that object.");
        setLoadingRelated(false);
      });
  }, [limit]);

  const handleSelectSuggestion = useCallback((item) => {
    loadObjectIntoWorkspace(item, false);
  }, [loadObjectIntoWorkspace]);

  const handleSelectFromCollections = useCallback((item) => {
    setActiveTab("explorer");
    loadObjectIntoWorkspace(item, true);
  }, [loadObjectIntoWorkspace]);

  const handleFindRelated = useCallback(() => {
    if (!searchedBaseObject) return;
    setLoadingRelated(true);
    setError(null);
    setSearchResults([]); 

    fetch(`${API_BASE}/related/${searchedBaseObject.object_id}?k=${limit}`)
      .then((res) => res.json())
      .then((data) => {
        setRelated(data);
        setLoadingRelated(false);
      })
      .catch(() => {
        setError("Could not compute related objects.");
        setLoadingRelated(false);
      });
  }, [searchedBaseObject, limit]);

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

  const toggleSaveCollection = useCallback((item) => {
    setSavedCollections((prev) => {
      const exists = prev.find((x) => x.object_id === item.object_id);
      if (exists) {
        return prev.filter((x) => x.object_id !== item.object_id);
      } else {
        return [...prev, item];
      }
    });
  }, []);

  const isBookmarked = (objectId) => savedCollections.some(x => x.object_id === objectId);

  const handleLoadABObjects = () => {
    if (!compSourceId.trim() || !compTargetId.trim()) return;
    setError(null);
    
    fetch(`${API_BASE}/object/${compSourceId}`)
      .then(res => res.json())
      .then(data => setCompSourceObject(data))
      .catch(() => setError("Could not find Source Object. Check the Object ID."));

    fetch(`${API_BASE}/object/${compTargetId}`)
      .then(res => res.json())
      .then(data => setCompTargetObject(data))
      .catch(() => setError("Could not find Target Object. Check the Object ID."));
  };

  const quickSelectOptions = savedCollections;

  const AI_SUGGESTED_QUESTIONS = [
    "Show me Greek helmets made of bronze",
    "Find Egyptian ceremonial objects",
    "Which medieval objects are related to weapons?",
    "Show me similar objects made from bronze",
  ];

  const handleAIAssistantSubmit = useCallback((queryText) => {
    const q = (queryText ?? aiQuery).trim();
    if (!q || aiLoading) return;

    setAiMessages((prev) => [...prev, { role: "user", text: q }]);
    setAiQuery("");
    setAiLoading(true);

    fetch(`${API_BASE}/ai-search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: q, previous_object_ids: aiLastResultIds }),
    })
      .then((res) => {
        if (!res.ok) throw new Error(`Server returned ${res.status}`);
        return res.json();
      })
      .then((data) => {
        const results = data.results || [];
        setAiMessages((prev) => [
          ...prev,
          { role: "assistant", text: data.summary, results, intent: data.intent?.intent },
        ]);
        if (results.length > 0) {
          setAiLastResultIds(results.map((r) => r.object_id));
        }
        setAiLoading(false);
      })
      .catch(() => {
        setAiMessages((prev) => [
          ...prev,
          { role: "assistant", text: "⚠️ Κάτι πήγε στραβά κατά την επικοινωνία με τον AI βοηθό. Δοκίμασε ξανά.", results: [] },
        ]);
        setAiLoading(false);
      });
  }, [aiQuery, aiLastResultIds, aiLoading]);

  return (
    <div className="app-container">
      <header className="global-header">
        <div className="brand-wrapper">
          <div className="brand-badge">THE MET</div>
          <span className="brand-title">Knowledge Graph</span>
        </div>
        <nav className="nav-links">
          <span className={`nav-item ${activeTab === "explorer" ? "active" : ""}`} onClick={() => setActiveTab("explorer")}>Explorer</span>
          <span className={`nav-item ${activeTab === "collections" ? "active" : ""}`} onClick={() => setActiveTab("collections")}>Collections ({savedCollections.length})</span>
          <span className={`nav-item ${activeTab === "matrix" ? "active" : ""}`} onClick={() => setActiveTab("matrix")}>Relations Matrix</span>
          <span className={`nav-item ${activeTab === "assistant" ? "active" : ""}`} onClick={() => setActiveTab("assistant")}>✨ AI Assistant</span>
        </nav>
        <div className="model-pipeline-badge">
          <div className="pipeline-status-pill"><span className="pulse-dot"></span><span>Vector DB: Connected</span></div>
          <div className="model-name-pill"><span>🤖 llama3.1</span></div>
        </div>
      </header>

      <div className="dashboard-workspace" style={{ display: "grid", gridTemplateColumns: "260px 1fr 320px", gap: "20px" }}>
        
        {/* LEFT COLUMN */}
        <aside className="left-filter-sidebar">
          <h3 className="filter-headline">Filter & Controls</h3>
          <div className="filter-group-wrapper">
            <div className="filter-label-row"><span>Search Range (Radius)</span><span>{radius}</span></div>
            <input type="range" className="range-slider-input" min="2" max="50" value={radius} onChange={(e) => setRadius(Number(e.target.value))} />
          </div>
          <div className="filter-group-wrapper">
            <div className="filter-label-row"><span>Max Relations Grid</span><span>{limit}</span></div>
            <input type="range" className="range-slider-input" min="1" max="50" value={limit} onChange={(e) => setLimit(Number(e.target.value))} />
          </div>
        </aside>

        {/* CENTER COLUMN */}
        <main className="center-content-arena">
          {activeTab === "explorer" && (
            <>
              <div className="search-container-block">
                <span style={{ color: "var(--text-muted)" }}>🔍</span>
                <input
                  type="text"
                  className="search-input-field"
                  placeholder="Search catalog by title, culture, or object ID..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleFindRelated(); }}
                />
                <button type="button" className="search-action-btn" onClick={handleFindRelated}>Search</button>
              </div>

              <section className="statistics-grid-strip">
                {STATS_DATA.map((stat, idx) => (
                  <div className="stat-card-item" key={idx}>
                    <div className="stat-icon-box">{stat.icon}</div>
                    <div>
                      <div className="stat-number">{stat.count}</div>
                      <div className="stat-label">{stat.label}</div>
                    </div>
                  </div>
                ))}
              </section>

              <section style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
                <h3 className="filter-headline" style={{ margin: 0 }}>
                  {related.length > 0 ? `Objects related to "${searchedBaseObject?.title}"` : "Artifact Workspace"}
                </h3>

                {loadingRelated && <div style={{ color: "var(--text-muted)" }}>Calculating vector distances & relationships...</div>}

                {/* 💡 ΣΥΝΔΕΣΗ ΤΟΥ REF ΜΕ ΤΟ CONTAINER ΤΩΝ ΑΠΟΤΕΛΕΣΜΑΤΩΝ ΣΤΟΝ EXPLORER */}
                <div ref={explorerResultsRef} className="results-grid-container">
                  {/* Live αποτελέσματα αναζήτησης */}
                  {searchResults.length > 0 && searchResults.map((item) => (
                    <div className="artifact-display-card" key={item.object_id} onClick={() => handleSelectSuggestion(item)}>
                      <button type="button" className="bookmark-btn" onClick={(e) => { e.stopPropagation(); toggleSaveCollection(item); }}>
                        {isBookmarked(item.object_id) ? "★" : "☆"}
                      </button>
                      <img src={item.image_url || "https://images.unsplash.com/photo-1580136579312-94651dfd596d?w=400"} alt={item.title} className="card-image-hero" />
                      <div className="card-body-details">
                        <h4 className="artifact-title-text">{item.title}</h4>
                        <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>ID: {item.object_id}</div>
                      </div>
                    </div>
                  ))}

                  {/* Αποτελέσματα Similarity */}
                  {searchResults.length === 0 && related.map((item) => (
                    <div 
                      className={`artifact-display-card ${selected?.object_id === item.object.object_id ? "active-focus-card" : ""}`} 
                      key={item.object.object_id} 
                      onClick={() => setSelected(item.object)}
                      style={{ 
                        border: selected?.object_id === item.object.object_id ? "2px solid var(--accent-blue)" : "1px solid rgba(255,255,255,0.08)", 
                        cursor: "pointer" 
                      }}
                    >
                      <button type="button" className="bookmark-btn" onClick={(e) => { e.stopPropagation(); toggleSaveCollection(item.object); }}>
                        {isBookmarked(item.object.object_id) ? "★" : "☆"}
                      </button>
                      <img src={item.object.image_url || "https://images.unsplash.com/photo-1580136579312-94651dfd596d?w=400"} alt={item.object.title} className="card-image-hero" />
                      <div className="card-body-details">
                        <h4 className="artifact-title-text">{item.object.title}</h4>
                        <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Similarity: {Math.round(item.cosine_similarity * 100)}%</div>
                      </div>
                    </div>
                  ))}
                </div>

                {searchResults.length === 0 && related.length === 0 && !loadingRelated && (
                  <div className="premium-welcome-wrapper">
                    <div className="premium-welcome-card">
                      <h1 className="premium-welcome-title">Uncover Hidden Links</h1>
                      
                      <div className="premium-star-divider">
                        <span className="divider-line"></span>
                        <span className="divider-star">✦</span>
                        <span className="divider-line"></span>
                      </div>
                      
                      <p className="premium-welcome-subtitle">
                        Ξεκινήστε πληκτρολογώντας έναν όρο στην αναζήτηση για να εντοπίσετε το αντικείμενο-στόχο. 
                        Στη συνέχεια, πατήστε <strong>Search</strong> για να ενεργοποιήσετε τον AI υπολογισμό εγγύτητας (Similarity) στον Γράφο Γνώσης.
                      </p>
                      
                      <div className="premium-welcome-badges">
                        <span className="premium-badge badge-antiquities">
                          <span className="badge-icon">🏛️</span> Antiquities
                        </span>
                        <span className="premium-badge badge-paintings">
                          <span className="badge-icon">🎨</span> Paintings
                        </span>
                        <span className="premium-badge badge-arms">
                          <span className="badge-icon">⚔️</span> Arms & Armor
                        </span>
                      </div>

                    </div>
                  </div>
                )}
              </section>
            </>
          )}

          {activeTab === "collections" && (
            <section style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
              <h2>My Saved Collections ({savedCollections.length})</h2>
              <div className="results-grid-container">
                {savedCollections.map((item) => (
                  <div className="artifact-display-card" key={item.object_id} onClick={() => handleSelectFromCollections(item)} style={{ cursor: "pointer" }}>
                    <button type="button" className="bookmark-btn" onClick={(e) => { e.stopPropagation(); toggleSaveCollection(item); }}>
                      {isBookmarked(item.object_id) ? "★" : "☆"}
                    </button>
                    <img src={item.image_url || "https://images.unsplash.com/photo-1580136579312-94651dfd596d?w=400"} alt={item.title} className="card-image-hero" />
                    <div className="card-body-details">
                      <h4 className="artifact-title-text">{item.title}</h4>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>ID: {item.object_id}</div>
                    </div>
                  </div>
                ))}
              </div>
              {savedCollections.length === 0 && (
                <p style={{ color: "var(--text-muted)", textAlign: "center", marginTop: "20px" }}>No saved artifacts in your collection yet.</p>
              )}
            </section>
          )}

          {activeTab === "matrix" && (
            <section className="matrix-viewport-container">
              <div className="matrix-main-card">
                
                {/* HEADER ROW */}
                <div className="matrix-card-header">
                  <div className="matrix-header-left">
                    <div className="matrix-header-badge">
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M17 1l4 4-4 4M3 23l-4-4 4-4M21 5H9a4 4 0 0 0-4 4v10M3 19h12a4 4 0 0 0 4-4V5"/>
                      </svg>
                    </div>
                    <div>
                      <h2 className="matrix-main-title">Manual A-B Comparator</h2>
                      <p className="matrix-main-subtitle">Επιλέξτε αντικείμενα από τις συλλογές και συγκρίνετε τα IDs τους.</p>
                    </div>
                  </div>
                  <div className="matrix-header-info-box">
                    <span className="info-icon">ℹ️</span>
                    <span>Συγκρίνετε δύο αντικείμενα και ανακαλύψτε πιθανές σχέσεις</span>
                  </div>
                </div>

                {/* DROPDOWN SELECTORS ROW */}
                <div className="matrix-selectors-row">
                  
                  {/* OBJECT A SELECTOR */}
                  <div className="selector-card">
                    <div className="selector-card-title-row">
                      <div className="selector-icon-wrapper purple-glow">📦</div>
                      <div>
                        <span className="selector-label">Επιλέξτε Αντικείμενο Α</span>
                        <span className="selector-sublabel">από τις συλλογές</span>
                      </div>
                    </div>
                    <div className="custom-select-wrapper">
                      <span className="select-search-icon">🔍</span>
                      <select 
                        className="matrix-styled-select"
                        value={compSourceId}
                        onChange={(e) => {
                          setCompSourceId(e.target.value);
                          const selectedObj = quickSelectOptions.find(o => o.object_id === e.target.value);
                          if (selectedObj) setCompSourceObject(selectedObj);
                        }}
                      >
                        <option value="">Επιλέξτε από τις συλλογές...</option>
                        {quickSelectOptions.map(o => (
                          <option key={o.object_id} value={o.object_id}>{o.title} (ID: {o.object_id})</option>
                        ))}
                      </select>
                    </div>
                  </div>

                  {/* SWAP CIRCLE CONNECTOR */}
                  <div className="matrix-connector-circle">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <path d="M17 11l4-4-4-4M21 7H9M7 13l-4 4 4 4M3 17h12"/>
                    </svg>
                  </div>

                  {/* OBJECT B SELECTOR */}
                  <div className="selector-card">
                    <div className="selector-card-title-row">
                      <div className="selector-icon-wrapper blue-glow">📦</div>
                      <div>
                        <span className="selector-label">Επιλέξτε Αντικείμενο Β</span>
                        <span className="selector-sublabel">από τις συλλογές</span>
                      </div>
                    </div>
                    <div className="custom-select-wrapper">
                      <span className="select-search-icon">🔍</span>
                      <select 
                        className="matrix-styled-select"
                        value={compTargetId}
                        onChange={(e) => {
                          setCompTargetId(e.target.value);
                          const selectedObj = quickSelectOptions.find(o => o.object_id === e.target.value);
                          if (selectedObj) setCompTargetObject(selectedObj);
                        }}
                      >
                        <option value="">Επιλέξτε από τις συλλογές...</option>
                        {quickSelectOptions.map(o => (
                          <option key={o.object_id} value={o.object_id}>{o.title} (ID: {o.object_id})</option>
                        ))}
                      </select>
                    </div>
                  </div>

                </div>

                {/* CUSTOM ID INPUTS & LOAD SECTION */}
                <div className="matrix-inputs-action-card">
                  
                  {/* INPUT A */}
                  <div className="matrix-input-group">
                    <div className="matrix-input-header">
                      <span className="input-tag-icon purple-text">🏷️</span>
                      <span className="matrix-input-label">Custom ID Αντικειμένου Α</span>
                      <span className="matrix-input-info-hint" title="Εισάγετε το μοναδικό ID">ℹ️</span>
                    </div>
                    <input 
                      type="text" 
                      placeholder="π.χ. 1975.1.2" 
                      className="matrix-neon-input" 
                      value={compSourceId} 
                      onChange={(e) => setCompSourceId(e.target.value)} 
                    />
                  </div>

                  {/* INPUT B */}
                  <div className="matrix-input-group">
                    <div className="matrix-input-header">
                      <span className="input-tag-icon blue-text">🏷️</span>
                      <span className="matrix-input-label">Custom ID Αντικειμένου Β</span>
                      <span className="matrix-input-info-hint" title="Εισάγετε το μοναδικό ID">ℹ️</span>
                    </div>
                    <input 
                      type="text" 
                      placeholder="π.χ. 42.50.3" 
                      className="matrix-neon-input" 
                      value={compTargetId} 
                      onChange={(e) => setCompTargetId(e.target.value)} 
                    />
                  </div>

                  {/* 3D CUBE GLOWING ILLUSTRATION */}
                  <div className="matrix-cube-illustration-wrapper">
                    <div className="cube-grid-bg"></div>
                    <div className="glowing-cube">
                      <div className="cube-face cube-face-top"></div>
                      <div className="cube-face cube-face-left"></div>
                      <div className="cube-face cube-face-right"></div>
                      <div className="cube-face cube-face-bottom"></div>
                      <div className="cube-face cube-face-back"></div>
                      <div className="cube-face cube-face-front"></div>
                    </div>
                  </div>

                  {/* ACTION BUTTON & SECURITY TAG */}
                  <div className="matrix-action-button-block">
                    <button type="button" className="matrix-compare-btn" onClick={handleLoadABObjects}>
                      <span className="btn-link-icon">🔗</span>
                      Φόρτωση & Σύγκριση
                    </button>
                    <div className="matrix-security-badge">
                      <span className="security-shield-icon">🛡️</span>
                      <span>Τα IDs παραμένουν ιδιωτικά και δεν αποθηκεύονται.</span>
                    </div>
                  </div>

                </div>

                {/* MATCHED PREVIEWS */}
                {(compSourceObject && compTargetObject) && (
                  <div className="matrix-matched-previews-container">
                    <div className="preview-artifact-item">
                      {compSourceObject.image_url && (
                        <img src={compSourceObject.image_url} alt="" className="preview-item-img" />
                      )}
                      <div>
                        <span className="preview-role-tag source-tag">OBJECT A</span>
                        <h4 className="preview-item-title">{compSourceObject.title}</h4>
                      </div>
                    </div>

                    <button 
                      type="button" 
                      className="matrix-ai-trigger-btn"
                      onClick={() => handleExplainRelationship(compSourceObject, compTargetObject)}
                    >
                      ✨ Run AI Overlap Analysis
                    </button>

                    <div className="preview-artifact-item text-right justify-end">
                      <div>
                        <span className="preview-role-tag target-tag">OBJECT B</span>
                        <h4 className="preview-item-title">{compTargetObject.title}</h4>
                      </div>
                      {compTargetObject.image_url && (
                        <img src={compTargetObject.image_url} alt="" className="preview-item-img" />
                      )}
                    </div>
                  </div>
                )}

                {/* BOTTOM TIP BAR */}
                <div className="matrix-tip-bar">
                  <div className="tip-bulb-icon-circle">💡</div>
                  <div className="tip-text-content">
                    <span className="tip-title">Συμβουλή</span>
                    <p className="tip-description">Επιλέξτε αντικείμενα από τις συλλογές ή εισάγετε τα IDs χειροκίνητα για να ξεκινήσετε τη σύγκριση.</p>
                  </div>
                </div>

              </div>
            </section>
          )}

          {activeTab === "assistant" && (
            <section className="ai-assistant-shell">
              <div className="ai-assistant-intro">
                <h2 className="ai-assistant-title">✨ AI Museum Assistant</h2>
                <p className="ai-assistant-subtitle">
                  Ρώτησέ με με φυσική γλώσσα -- εγώ μεταφράζω το ερώτημά σου σε φίλτρα, ψάχνω στην πραγματική
                  βάση/γράφο, και μετά σου εξηγώ τα αποτελέσματα. Δεν απαντάω ποτέ από τη δική μου γνώση.
                </p>
              </div>

              <div className="ai-chat-transcript">
                {aiMessages.length === 0 && (
                  <div className="ai-suggested-row">
                    {AI_SUGGESTED_QUESTIONS.map((q) => (
                      <button
                        key={q}
                        type="button"
                        className="ai-suggested-chip"
                        onClick={() => handleAIAssistantSubmit(q)}
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                )}

                {aiMessages.map((msg, i) => (
                  <div key={i} className={`ai-message ai-message--${msg.role}`}>
                    {msg.role === "user" ? (
                      <div className="ai-message-bubble ai-message-bubble--user">{msg.text}</div>
                    ) : (
                      <div className="ai-message-bubble ai-message-bubble--assistant">
                        {msg.intent && <span className="ai-intent-tag">{msg.intent}</span>}
                        <p className="ai-message-text">{msg.text}</p>

                        {msg.results && msg.results.length > 0 && (
                          <div className="results-grid-container ai-results-grid">
                            {msg.results.map((obj) => (
                              <div
                                key={obj.object_id}
                                className="artifact-display-card"
                                onClick={() => loadObjectIntoWorkspace(obj, true)}
                              >
                                <button
                                  type="button"
                                  className="bookmark-btn"
                                  onClick={(e) => { e.stopPropagation(); toggleSaveCollection(obj); }}
                                >
                                  {isBookmarked(obj.object_id) ? "★" : "☆"}
                                </button>
                                <img
                                  src={obj.image_url || "https://images.unsplash.com/photo-1580136579312-94651dfd596d?w=400"}
                                  alt={obj.title}
                                  className="card-image-hero"
                                />
                                <div className="card-body-details">
                                  <h4 className="artifact-title-text">{obj.title}</h4>
                                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                                    {obj.culture || "culture unknown"} · {obj.department || "department unknown"}
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}

                {aiLoading && (
                  <div className="ai-message ai-message--assistant">
                    <div className="ai-message-bubble ai-message-bubble--assistant ai-message-bubble--loading">
                      <span className="ai-loading-dot" />
                      <span className="ai-loading-dot" />
                      <span className="ai-loading-dot" />
                    </div>
                  </div>
                )}

                {/* 💡 ΣΥΝΔΕΣΗ ΤΟΥ REF ΜΕ ΤΟ ΤΕΛΟΣ ΤΟΥ CHAT TRANSCRIPT */}
                <div ref={chatEndRef} />
              </div>

              <div className="ai-input-row">
                <input
                  type="text"
                  className="ai-input-field"
                  placeholder="π.χ. Show me Greek helmets made of bronze..."
                  value={aiQuery}
                  onChange={(e) => setAiQuery(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") handleAIAssistantSubmit(); }}
                  disabled={aiLoading}
                />
                <button
                  type="button"
                  className="ai-send-btn"
                  onClick={() => handleAIAssistantSubmit()}
                  disabled={aiLoading || !aiQuery.trim()}
                >
                  {aiLoading ? "…" : "Ask"}
                </button>
              </div>
            </section>
          )}
        </main>

        {/* RIGHT COLUMN */}
        <aside className="right-relationship-sidebar" style={{ background: "rgba(255,255,255,0.01)", borderLeft: "1px solid var(--border-dim)", padding: "20px", display: "flex", flexDirection: "column", gap: "20px", overflowY: "auto" }}>
          <h3 className="filter-headline" style={{ margin: 0, borderBottom: "1px solid var(--border-dim)", paddingBottom: "10px" }}>Relationship Sandbox</h3>
          
          {searchedBaseObject ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
              
              {/* OBJECT A */}
              <div style={{ background: "rgba(59, 130, 246, 0.05)", border: "1px solid rgba(59, 130, 246, 0.2)", borderRadius: "8px", padding: "12px" }}>
                <span style={{ fontSize: "0.7rem", color: "var(--accent-blue)", fontWeight: 700, textTransform: "uppercase", display: "block", marginBottom: "6px" }}>[A] Root Artifact</span>
                {searchedBaseObject.image_url && (
                  <img src={searchedBaseObject.image_url} alt="" style={{ width: "100%", height: "120px", objectFit: "cover", borderRadius: "4px", marginBottom: "8px" }} />
                )}
                <strong style={{ fontSize: "0.85rem", display: "block", color: "white", marginBottom: "4px" }}>{searchedBaseObject.title}</strong>
                <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>ID: {searchedBaseObject.object_id}</span>
              </div>

              {/* ACTION BUTTON */}
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "8px" }}>
                <span style={{ fontSize: "1.5rem", color: "var(--text-muted)" }}>⬇️</span>
                {selected && searchedBaseObject.object_id !== selected.object_id ? (
                  <button 
                    type="button" 
                    className="primary-action-trigger" 
                    style={{ 
                      width: "100%", 
                      padding: "10px", 
                      fontSize: "0.8rem", 
                      fontWeight: 700, 
                      background: "var(--accent-blue)", 
                      border: "none", 
                      borderRadius: "6px", 
                      color: "white", 
                      cursor: "pointer",
                      boxShadow: "0 4px 12px rgba(37, 99, 235, 0.2)"
                    }}
                    onClick={() => handleExplainRelationship(searchedBaseObject, selected)}
                  >
                    ✨ Explain Overlap with AI
                  </button>
                ) : (
                  <div style={{ textAlign: "center", padding: "6px 12px", border: "1px dashed var(--border-dim)", borderRadius: "6px", width: "100%" }}>
                    <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Select related artifact below</span>
                  </div>
                )}
              </div>

              {/* OBJECT B */}
              {selected && (
                <div style={{ background: "rgba(255,255,255,0.02)", border: "1px solid var(--border-dim)", borderRadius: "8px", padding: "12px" }}>
                  <span style={{ fontSize: "0.7rem", color: "var(--text-secondary)", fontWeight: 700, textTransform: "uppercase", display: "block", marginBottom: "6px" }}>[B] Compared Artifact</span>
                  {selected.image_url && (
                    <img src={selected.image_url} alt="" style={{ width: "100%", height: "120px", objectFit: "cover", borderRadius: "4px", marginBottom: "8px" }} />
                  )}
                  <strong style={{ fontSize: "0.85rem", display: "block", color: "white", marginBottom: "4px" }}>{selected.title}</strong>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>ID: {selected.object_id}</span>
                </div>
              )}

            </div>
          ) : (
            <div style={{ textAlign: "center", padding: "40px 10px", color: "var(--text-muted)", border: "1.5px dashed var(--border-dim)", borderRadius: "8px" }}>
              <span style={{ fontSize: "1.5rem", display: "block", marginBottom: "10px" }}>🧭</span>
              <p style={{ fontSize: "0.8rem", margin: 0 }}>Αναζητήστε και επιλέξτε ένα έκθεμα για να ξεκινήσει η διαδικασία σύνδεσης.</p>
            </div>
          )}
        </aside>

      </div>
      {error && <p className="page__error" style={{ textAlign: "center", padding: "1rem", color: "#ef4444" }}>{error}</p>}
      <ExplainModal state={explainState} onClose={closeExplainModal} />
    </div>
  );
}