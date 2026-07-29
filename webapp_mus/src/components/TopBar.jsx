import React from "react";

/**
 * Global top bar: brand mark, unified catalog search, AI Search shortcut,
 * and utility icons. The search input stays wired to the same
 * searchQuery/onSearch handlers App.jsx already uses -- this component is
 * purely a visual reshell, no new data flow.
 */
export default function TopBar({ searchQuery, onSearchChange, onSubmitSearch, onOpenAssistant, inputRef }) {
  return (
    <header className="hg-topbar">
      <div className="hg-brand">
        <div className="hg-brand-mark">
          <span className="hg-brand-the">THE</span>
          <span className="hg-brand-met">MET</span>
        </div>
        <div className="hg-brand-title">
          <span>Knowledge</span>
          <span>Graph</span>
        </div>
      </div>

      <div className="hg-topbar-search">
        <span className="hg-search-icon" aria-hidden="true">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="7" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
        </span>
        <input
          ref={inputRef}
          type="text"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") onSubmitSearch(); }}
          placeholder="Search catalog by title, culture, or object ID..."
        />
        <button type="button" className="hg-search-go" onClick={onSubmitSearch} aria-label="Search">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
            <circle cx="11" cy="11" r="7" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
        </button>
      </div>

      <button type="button" className="hg-ai-search-btn" onClick={onOpenAssistant}>
        <span aria-hidden="true">✨</span> AI Search
      </button>

      <div className="hg-topbar-icons">
        <button type="button" className="hg-icon-btn" aria-label="Notifications">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 8a6 6 0 10-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
            <path d="M13.73 21a2 2 0 01-3.46 0" />
          </svg>
          <span className="hg-icon-badge">3</span>
        </button>
        <button type="button" className="hg-icon-btn" aria-label="Help">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <path d="M9.09 9a3 3 0 015.83 1c0 2-3 2-3 4" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
        </button>
        <button type="button" className="hg-icon-btn" aria-label="Full screen">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M8 3H5a2 2 0 00-2 2v3m18 0V5a2 2 0 00-2-2h-3m0 18h3a2 2 0 002-2v-3M3 16v3a2 2 0 002 2h3" />
          </svg>
        </button>
      </div>
    </header>
  );
}
