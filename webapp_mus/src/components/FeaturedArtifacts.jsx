import React from "react";

const FALLBACK_IMG = "https://images.unsplash.com/photo-1580136579312-94651dfd596d?w=400";

// Static curated showcase for the empty/landing state -- purely a visual
// front door, independent of the live search/related pipeline. Clicking a
// card runs it through the real search flow like any other result would.
const FEATURED = [
  { title: "Winged Victory of Samothrace", meta: "Greece, 190 BC", img: FALLBACK_IMG },
  { title: "Attic Black-Figure Amphora", meta: "Greece, 530 BC", img: FALLBACK_IMG },
  { title: "Samurai Armor (Yoroi)", meta: "Japan, 1600s", img: FALLBACK_IMG },
  { title: "The Starry Night", meta: "Vincent van Gogh · Netherlands, 1889", img: FALLBACK_IMG },
  { title: "Portrait of a Man", meta: "Roman, 1st Century", img: FALLBACK_IMG },
];

export default function FeaturedArtifacts({ onPick }) {
  return (
    <section className="hg-featured">
      <div className="hg-section-head">
        <h3>Featured Artifacts</h3>
        <button type="button" className="hg-link-btn" onClick={() => onPick && onPick("")}>View all</button>
      </div>
      <div className="hg-featured-row">
        {FEATURED.map((item) => (
          <button type="button" key={item.title} className="hg-featured-card" onClick={() => onPick && onPick(item.title)}>
            <img src={item.img} alt={item.title} loading="lazy" />
            <div className="hg-featured-card-body">
              <strong>{item.title}</strong>
              <small>{item.meta}</small>
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}
