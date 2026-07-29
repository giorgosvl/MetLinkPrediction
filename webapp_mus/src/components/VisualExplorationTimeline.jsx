import React from "react";

const ERAS = [
  { label: "Ancient Egypt", year: "3500 BC", x: 20, y: 80 },
  { label: "Classical Greece", year: "500 BC", x: 190, y: 60 },
  { label: "Byzantine Era", year: "500 AD", x: 360, y: 40 },
  { label: "Renaissance", year: "1500", x: 530, y: 55 },
  { label: "Industrial Age", year: "1800", x: 700, y: 70 },
  { label: "Contemporary", year: "2000+", x: 870, y: 50 },
];

const PATH = "M20,80 C90,20 140,20 190,60 C260,110 330,110 360,40 C430,-30 480,-30 530,55 C610,150 660,150 700,70 C780,-30 830,-30 870,50";

export default function VisualExplorationTimeline() {
  return (
    <section className="hg-timeline-card">
      <div className="hg-section-head">
        <div>
          <h3>Visual Exploration</h3>
          <p className="hg-section-sub">Navigate through time and cultures</p>
        </div>
        <div className="hg-timeline-controls">
          <button type="button" className="hg-period-select">All Periods
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M6 9l6 6 6-6" /></svg>
          </button>
          <button type="button" className="hg-round-btn" aria-label="Previous period">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M15 18l-6-6 6-6" /></svg>
          </button>
          <button type="button" className="hg-round-btn" aria-label="Next period">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M9 18l6-6-6-6" /></svg>
          </button>
        </div>
      </div>

      <svg className="hg-timeline-svg" viewBox="0 0 900 170" preserveAspectRatio="none">
        <defs>
          <linearGradient id="hgTimelineStroke" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#a78bfa" />
            <stop offset="55%" stopColor="#38bdf8" />
            <stop offset="100%" stopColor="#22d3ee" />
          </linearGradient>
          <linearGradient id="hgTimelineFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="rgba(139,92,246,0.28)" />
            <stop offset="100%" stopColor="rgba(139,92,246,0)" />
          </linearGradient>
        </defs>
        <path d={`${PATH} L870,170 L20,170 Z`} fill="url(#hgTimelineFill)" stroke="none" />
        <path d={PATH} fill="none" stroke="url(#hgTimelineStroke)" strokeWidth="3" strokeLinecap="round" />
        {ERAS.map((era) => (
          <circle key={era.label} className="hg-timeline-dot" cx={era.x} cy={era.y} r="5" />
        ))}
      </svg>

      <div className="hg-timeline-labels">
        {ERAS.map((era) => (
          <div key={era.label} className="hg-timeline-label">
            <strong>{era.year}</strong>
            <span>{era.label}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
