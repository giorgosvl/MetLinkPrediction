import React from "react";

const ACTIVITY = [
  { icon: "🔗", text: "New connection discovered", time: "2 min ago" },
  { icon: "🏺", text: "Greek Pottery linked to Etruscan Art", time: "15 min ago" },
  { icon: "🗾", text: "New artifacts added from Japan", time: "1 hour ago" },
];

function MiniGraphIllustration() {
  return (
    <svg className="hg-sandbox-mini" viewBox="0 0 220 100" aria-hidden="true">
      <line x1="110" y1="50" x2="30" y2="20" />
      <line x1="110" y1="50" x2="45" y2="80" />
      <line x1="110" y1="50" x2="185" y2="25" />
      <line x1="110" y1="50" x2="165" y2="82" />
      <line x1="110" y1="50" x2="110" y2="15" />
      <circle cx="110" cy="50" r="9" className="hg-sandbox-node--center" />
      <circle cx="30" cy="20" r="5" className="hg-sandbox-node" />
      <circle cx="45" cy="80" r="5" className="hg-sandbox-node" />
      <circle cx="185" cy="25" r="5" className="hg-sandbox-node" />
      <circle cx="165" cy="82" r="6" className="hg-sandbox-node--cursor" />
      <circle cx="110" cy="15" r="5" className="hg-sandbox-node" />
    </svg>
  );
}

/**
 * Right column. Keeps the existing, fully-functional Object A / Object B
 * relationship-explain flow (props identical to what App.jsx already
 * computes) but restyles it to the mockup's "Relationship Sandbox" card,
 * and adds the decorative-but-real stats grid + activity feed underneath.
 */
export default function RightPanel({
  stats,
  searchedBaseObject,
  selected,
  onExplain,
  onOpenSandbox,
}) {
  return (
    <aside className="hg-rightpanel">
      <div className="hg-sandbox-card">
        <h3>Relationship Sandbox</h3>

        {!searchedBaseObject && (
          <>
            <MiniGraphIllustration />
            <p>Pick an object and explore its connections across the graph.</p>
            <button type="button" className="hg-open-sandbox-btn" onClick={onOpenSandbox}>
              Open Sandbox
            </button>
          </>
        )}

        {searchedBaseObject && (
          <div className="hg-sandbox-pair">
            <div className="hg-sandbox-object hg-sandbox-object--a">
              <span className="hg-sandbox-tag">A · Root Artifact</span>
              {searchedBaseObject.image_url && <img src={searchedBaseObject.image_url} alt="" />}
              <strong>{searchedBaseObject.title}</strong>
              <small>ID: {searchedBaseObject.object_id}</small>
            </div>

            {selected && searchedBaseObject.object_id !== selected.object_id ? (
              <button type="button" className="hg-sandbox-explain-btn" onClick={() => onExplain(searchedBaseObject, selected)}>
                ✨ Explain Overlap
              </button>
            ) : (
              <span className="hg-sandbox-hint">Select a related artifact below</span>
            )}

            {selected && (
              <div className="hg-sandbox-object hg-sandbox-object--b">
                <span className="hg-sandbox-tag">B · Compared Artifact</span>
                {selected.image_url && <img src={selected.image_url} alt="" />}
                <strong>{selected.title}</strong>
                <small>ID: {selected.object_id}</small>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="hg-stats-grid">
        {stats.map((stat) => (
          <div className="hg-stat-card" key={stat.label}>
            <span className="hg-stat-icon">{stat.icon}</span>
            <strong>{stat.count}</strong>
            <span className="hg-stat-label">{stat.label}</span>
            <span className="hg-stat-delta">{stat.delta}</span>
          </div>
        ))}
      </div>

      <div className="hg-activity-card">
        <h3>Activity Feed</h3>
        <ul>
          {ACTIVITY.map((item) => (
            <li key={item.text}>
              <span className="hg-activity-icon">{item.icon}</span>
              <span className="hg-activity-text">{item.text}</span>
              <span className="hg-activity-time">{item.time}</span>
            </li>
          ))}
        </ul>
        <button type="button" className="hg-link-btn">View all activity →</button>
      </div>
    </aside>
  );
}
