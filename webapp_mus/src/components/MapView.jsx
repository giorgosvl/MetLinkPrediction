import React, { useEffect, useMemo, useState } from "react";
import { MapContainer, TileLayer, CircleMarker, Tooltip, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";

const API_BASE = "http://localhost:4345/api";

// Approximate country centroids for the ~70 countries most common in the
// MET catalog. This is a schematic lookup (not survey-grade geocoding) --
// good enough to place a marker "in" the right country on a world map.
// Countries present in the data but missing here still show up in the
// list panel below the map, just without a pin, so no data is silently
// dropped.
const COUNTRY_CENTROIDS = {
  "egypt": [26.8, 30.8], "greece": [39.0, 22.0], "italy": [42.8, 12.6],
  "france": [46.6, 2.3], "spain": [40.2, -3.7], "germany": [51.2, 10.4],
  "great britain": [54.0, -2.0], "united kingdom": [54.0, -2.0], "england": [52.5, -1.5],
  "netherlands": [52.2, 5.5], "belgium": [50.6, 4.5], "austria": [47.6, 14.1],
  "switzerland": [46.8, 8.2], "portugal": [39.6, -8.0], "russia": [61.5, 96.0],
  "turkey": [39.0, 35.2], "iran": [32.4, 53.7], "persia": [32.4, 53.7],
  "iraq": [33.2, 43.7], "syria": [34.8, 38.5], "israel": [31.5, 34.8],
  "lebanon": [33.9, 35.9], "jordan": [30.6, 36.2], "afghanistan": [33.9, 67.7],
  "china": [35.9, 104.2], "japan": [36.2, 138.3], "india": [21.0, 78.0],
  "korea": [36.5, 127.9], "south korea": [36.5, 127.9], "cambodia": [12.6, 104.9],
  "thailand": [15.9, 100.9], "indonesia": [-0.8, 113.9], "vietnam": [14.1, 108.3],
  "nepal": [28.4, 84.1], "tibet": [31.7, 88.1], "mongolia": [46.9, 103.8],
  "mexico": [23.6, -102.5], "peru": [-9.2, -75.0], "guatemala": [15.8, -90.2],
  "colombia": [4.6, -74.3], "bolivia": [-16.3, -63.6], "ecuador": [-1.8, -78.2],
  "united states": [39.8, -98.6], "usa": [39.8, -98.6], "canada": [56.1, -106.3],
  "brazil": [-14.2, -51.9], "argentina": [-38.4, -63.6], "chile": [-35.7, -71.5],
  "morocco": [31.8, -7.1], "algeria": [28.0, 1.7], "tunisia": [33.9, 9.5],
  "libya": [26.3, 17.2], "sudan": [12.9, 30.2], "ethiopia": [9.1, 40.5],
  "nigeria": [9.1, 8.7], "ghana": [7.9, -1.0], "congo": [-4.0, 21.8],
  "south africa": [-30.6, 22.9], "mali": [17.6, -4.0], "benin": [9.3, 2.3],
  "cyprus": [35.1, 33.4], "crete": [35.2, 24.9], "cuba": [21.5, -77.8],
  "korea (south)": [36.5, 127.9], "sri lanka": [7.9, 80.8], "myanmar": [21.9, 95.9],
  "burma": [21.9, 95.9], "pakistan": [30.4, 69.3], "poland": [51.9, 19.1],
  "hungary": [47.2, 19.5], "czech republic": [49.8, 15.5], "ukraine": [48.4, 31.2],
  "sweden": [60.1, 18.6], "norway": [60.5, 8.5], "denmark": [56.3, 9.5],
  "finland": [61.9, 25.7], "ireland": [53.4, -8.2], "scotland": [56.5, -4.2],
};

function normalizeCountryKey(name) {
  return name.trim().toLowerCase();
}

/**
 * The Map tab is now kept permanently mounted (see App.jsx) and just
 * hidden with display:none between visits, instead of being torn down and
 * recreated -- that remount cycle was the cause of markers becoming
 * unresponsive after the first visit. The tradeoff: Leaflet measures its
 * container size when it's still 0x0 (hidden), so every time the tab
 * becomes visible again we need to explicitly tell it to re-measure.
 */
function InvalidateSizeOnShow({ active }) {
  const map = useMap();
  useEffect(() => {
    if (!active) return;
    const timer = setTimeout(() => map.invalidateSize(), 60);
    return () => clearTimeout(timer);
  }, [active, map]);
  return null;
}

function radiusForCount(count, maxCount) {
  const min = 6, max = 26;
  if (maxCount <= 0) return min;
  return min + (max - min) * Math.sqrt(count / maxCount);
}

/**
 * Map tab. Fetches real per-country object counts from the backend
 * (/api/geo-distribution, built directly off the existing Country column),
 * plots them as markers on a real OpenStreetMap base layer via
 * react-leaflet, and clicking a marker or list row pulls real objects
 * (/api/objects-by-country) straight into the normal Explorer results grid.
 *
 * Uses OSM's public tile server, which is fine for local dev/demo traffic;
 * swap the TileLayer URL for a paid provider (Mapbox/Stadia/etc.) before
 * any production deployment with real user volume, per OSM's usage policy.
 */
export default function MapView({ onSelectCountry, active }) {
  const [countries, setCountries] = useState([]);
  const [coverage, setCoverage] = useState({ total: 0, withCountry: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`${API_BASE}/geo-distribution`)
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return;
        setCountries(Array.isArray(data?.countries) ? data.countries : []);
        setCoverage({ total: data?.total_objects || 0, withCountry: data?.objects_with_country || 0 });
      })
      .catch(() => { if (!cancelled) setError("Could not load geographic distribution."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const maxCount = useMemo(
    () => countries.reduce((m, c) => Math.max(m, c.count), 0),
    [countries]
  );

  const plotted = useMemo(
    () => countries
      .map((c) => ({ ...c, pos: COUNTRY_CENTROIDS[normalizeCountryKey(c.country)] }))
      .filter((c) => c.pos),
    [countries]
  );

  const unplotted = useMemo(
    () => countries.filter((c) => !COUNTRY_CENTROIDS[normalizeCountryKey(c.country)]),
    [countries]
  );

  return (
    <section className="hg-map-view">
      <div className="hg-section-head">
        <div>
          <h3>Map</h3>
          <p className="hg-section-sub">
            {loading
              ? "Loading geographic distribution..."
              : `${countries.length} countries represented in the catalog`}
          </p>
          {!loading && coverage.total > 0 && (
            <p className="hg-map-coverage">
              <span className="hg-map-coverage-dot" />
              {coverage.withCountry.toLocaleString()} of {coverage.total.toLocaleString()} objects
              ({Math.round((coverage.withCountry / coverage.total) * 100)}%) have a known country of origin —
              the rest have sparse metadata and aren't plotted on the map.
            </p>
          )}
        </div>
      </div>

      {error && <p style={{ color: "#f87171", fontSize: "0.85rem" }}>{error}</p>}

      <div className="hg-map-layout">
        <div className="hg-map-canvas">
          <MapContainer center={[20, 10]} zoom={2} minZoom={2} worldCopyJump style={{ height: "100%", width: "100%" }}>
            <InvalidateSizeOnShow active={active} />
            <TileLayer
              attribution='&copy; OpenStreetMap contributors'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            {plotted.map((c) => (
              <CircleMarker
                key={c.country}
                center={c.pos}
                radius={radiusForCount(c.count, maxCount)}
                pathOptions={{ color: "#22d3ee", weight: 1.5, fillColor: "#8b5cf6", fillOpacity: 0.55 }}
                eventHandlers={{ click: () => onSelectCountry(c.country) }}
              >
                <Tooltip direction="top" offset={[0, -4]}>
                  <strong>{c.country}</strong> — {c.count} objects
                </Tooltip>
              </CircleMarker>
            ))}
          </MapContainer>
        </div>

        <div className="hg-map-list">
          <h4>All countries</h4>
          <ul>
            {countries.map((c) => (
              <li key={c.country}>
                <button type="button" onClick={() => onSelectCountry(c.country)}>
                  <span className="hg-map-list-name">
                    {c.country}
                    {!COUNTRY_CENTROIDS[normalizeCountryKey(c.country)] && (
                      <span className="hg-map-list-unmapped" title="No pin available for this country yet">•</span>
                    )}
                  </span>
                  <span className="hg-map-list-count">{c.count}</span>
                </button>
              </li>
            ))}
          </ul>
          {!loading && unplotted.length > 0 && (
            <p className="hg-map-list-footnote">
              {unplotted.length} {unplotted.length === 1 ? "country doesn't" : "countries don't"} have a map pin yet — still clickable from the list above.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}