import React, { useState } from "react";

const NAV_ITEMS = [
  { key: "explorer", label: "Explorer", icon: "explorer" },
  { key: "collections", label: "Collections", icon: "collections" },
  { key: "matrix", label: "Relations Matrix", icon: "matrix" },
  { key: "assistant", label: "AI Assistant", icon: "assistant", badge: "New" },
  { key: "map", label: "Map", icon: "map" },
];

function NavIcon({ name }) {
  const common = { width: 17, height: 17, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2 };
  switch (name) {
    case "explorer":
      return <svg {...common}><circle cx="11" cy="11" r="7" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>;
    case "collections":
      return <svg {...common}><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></svg>;
    case "matrix":
      return <svg {...common}><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></svg>;
    case "assistant":
      return <svg {...common}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6.3 6.3l2.8 2.8M14.9 14.9l2.8 2.8M6.3 17.7l2.8-2.8M14.9 9.1l2.8-2.8" /></svg>;
    case "map":
      return <svg {...common}><path d="M9 18l-6 3V6l6-3 6 3 6-3v15l-6 3-6-3z" /><line x1="9" y1="3" x2="9" y2="18" /><line x1="15" y1="6" x2="15" y2="21" /></svg>;
    default:
      return null;
  }
}

/**
 * Left navigation rail. Renders the visual nav from the mockup (Explorer /
 * Collections / Relations Matrix / AI Assistant map to real, working tabs;
 * Analytics / Timeline / Map / Saved Views are marked "soon" so nothing
 * dead-ends). The functional Radius / Max Relations controls that already
 * existed are preserved here, tucked into a small collapsible card, so no
 * behavior is lost in the redesign.
 */
export default function Sidebar({ activeTab, onSelectTab, radius, setRadius, limit, setLimit }) {
  const [tuningOpen, setTuningOpen] = useState(false);

  return (
    <aside className="hg-sidebar">
      <nav className="hg-nav">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.key}
            type="button"
            className={`hg-nav-item ${activeTab === item.key ? "hg-nav-item--active" : ""} ${item.soon ? "hg-nav-item--soon" : ""}`}
            onClick={() => onSelectTab(item.key)}
          >
            <span className="hg-nav-icon"><NavIcon name={item.icon} /></span>
            <span className="hg-nav-label">{item.label}</span>
            {item.badge && <span className="hg-nav-badge">{item.badge}</span>}
            {activeTab === item.key && !item.soon && (
              <svg className="hg-nav-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M9 18l6-6-6-6" />
              </svg>
            )}
          </button>
        ))}
      </nav>

      <div className="hg-sidebar-spacer" />

      <details className="hg-tuning-card" open={tuningOpen} onToggle={(e) => setTuningOpen(e.target.open)}>
        <summary>Search Tuning</summary>
        <div className="hg-tuning-row">
          <div className="hg-tuning-label"><span>Search Range</span><span>{radius}</span></div>
          <input type="range" min="2" max="50" value={radius} onChange={(e) => setRadius(Number(e.target.value))} />
        </div>
        <div className="hg-tuning-row">
          <div className="hg-tuning-label"><span>Max Relations</span><span>{limit}</span></div>
          <input type="range" min="1" max="50" value={limit} onChange={(e) => setLimit(Number(e.target.value))} />
        </div>
      </details>

      <div className="hg-graph-status-card">
        <div className="hg-graph-status-head">
          <span>Graph Status</span>
          <span className="hg-live-dot"><i /> Live</span>
        </div>
        <svg className="hg-sparkline" viewBox="0 0 180 46" preserveAspectRatio="none">
          <polyline
            points="0,34 18,30 36,36 54,20 72,26 90,10 108,22 126,14 144,28 162,18 180,24"
            fill="none"
          />
        </svg>
        <button type="button" className="hg-vectordb-pill">
          <i /> Vector DB: Connected
        </button>
      </div>

      <button type="button" className="hg-user-chip" onClick={() => onSelectTab("assistant")}>
        <span className="hg-user-avatar">🦙</span>
        <span className="hg-user-meta">
          <strong>llama3.1</strong>
          <small>AI Assistant</small>
        </span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <path d="M9 18l6-6-6-6" />
        </svg>
      </button>
    </aside>
  );
}