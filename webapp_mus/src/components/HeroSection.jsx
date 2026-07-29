import React from "react";
import NetworkVisualization from "./NetworkVisualization.jsx";

const POPULAR_SEARCHES = ["Ancient Egypt", "Renaissance", "Samurai Armor", "Greek Pottery"];

export default function HeroSection({ objectCount, relationCount, onStartExploring, onPopularSearch }) {
  return (
    <section className="hg-hero">
      <div className="hg-hero-copy">
        <span className="hg-eyebrow">EXPLORE CONNECTIONS</span>
        <h1 className="hg-headline">
          <span className="hg-headline-line hg-headline-line--1">Discover.</span>
          <span className="hg-headline-line hg-headline-line--2">Connect.</span>
          <span className="hg-headline-line hg-headline-line--3">Understand.</span>
        </h1>
        <p className="hg-hero-sub">
          Explore <strong>{objectCount}</strong> objects and <strong>{relationCount}</strong> relationships
          across cultures and time periods.
        </p>

        <div className="hg-hero-actions">
          <button type="button" className="hg-btn-primary" onClick={onStartExploring}>
            Start Exploring
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M5 12h14M13 6l6 6-6 6" />
            </svg>
          </button>
          <button type="button" className="hg-btn-secondary">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
            Watch Demo
          </button>
        </div>

        <div className="hg-popular-row">
          <span>Popular searches:</span>
          {POPULAR_SEARCHES.map((term) => (
            <button type="button" key={term} className="hg-popular-chip" onClick={() => onPopularSearch(term)}>
              {term}
            </button>
          ))}
        </div>
      </div>

      <NetworkVisualization />
    </section>
  );
}
