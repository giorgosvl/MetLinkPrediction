import React from "react";

const FLOATING_CARDS = [
  { label: "JAPAN", sub: "11th Century", top: "6%", left: "68%", accent: "cyan" },
  { label: "ITALY", sub: "Renaissance", top: "70%", left: "10%", accent: "amber" },
  { label: "EGYPT", sub: "New Kingdom", top: "68%", left: "72%", accent: "gold" },
];

/**
 * Purely decorative: a rotating wireframe sphere with orbiting nodes and a
 * few labeled artifact chips, built with CSS animation + inline SVG only
 * (no Three.js) to keep this cheap to render and easy to ship without a
 * 3D pipeline. Swap for a real graph-driven view later if desired.
 */
export default function NetworkVisualization() {
  return (
    <div className="hg-network" aria-hidden="true">
      <div className="hg-network-glow" />

      <svg className="hg-network-sphere" viewBox="0 0 400 400">
        <g className="hg-sphere-ring hg-sphere-ring--a">
          <ellipse cx="200" cy="200" rx="170" ry="170" />
        </g>
        <g className="hg-sphere-ring hg-sphere-ring--b">
          <ellipse cx="200" cy="200" rx="170" ry="60" />
        </g>
        <g className="hg-sphere-ring hg-sphere-ring--c">
          <ellipse cx="200" cy="200" rx="60" ry="170" />
        </g>
        {[...Array(14)].map((_, i) => {
          const angle = (i / 14) * Math.PI * 2;
          const r = 170;
          const x = 200 + r * Math.cos(angle);
          const y = 200 + r * Math.sin(angle);
          return <circle key={i} className="hg-sphere-dot" cx={x} cy={y} r="2.5" style={{ animationDelay: `${i * 0.2}s` }} />;
        })}
      </svg>

      <div className="hg-network-core">
        <div className="hg-network-core-glow" />
      </div>

      {FLOATING_CARDS.map((card, i) => (
        <div
          key={card.label}
          className={`hg-float-card hg-float-card--${card.accent}`}
          style={{ top: card.top, left: card.left, animationDelay: `${i * 0.6}s` }}
        >
          <span className="hg-float-card-swatch" />
          <div>
            <strong>{card.label}</strong>
            <small>{card.sub}</small>
          </div>
        </div>
      ))}

      <div className="hg-scroll-hint">
        <span className="hg-scroll-dot" />
        Scroll to explore
      </div>
    </div>
  );
}
