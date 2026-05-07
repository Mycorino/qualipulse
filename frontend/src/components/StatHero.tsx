import type { ReactNode } from "react";
import { VerbatimCard } from "./VerbatimCard";

/**
 * StatHero — the page-unit pattern for "stat + verbatim" pairings.
 *
 * The viz designer's #1 layout: 60/40 chart-or-stat-left, single quote
 * card on the right. The stat in serif anchors the page; the quote gives
 * it a human voice. One stat per StatHero — never a comparison.
 *
 * On <720px the grid collapses to stacked rows; the stat stays first so
 * the quote always reads as supporting evidence, not the lede.
 */
interface StatHeroProps {
  /** Uppercase eyebrow above the stat — segment, question, or section reference. */
  eyebrow?: string;
  /** The headline number. Pre-format it: "73%", "+25", "3.2×", "$184k". */
  stat: string;
  /** One-sentence framing of what the stat represents. Serif, two-line max. */
  description: string;
  /** Sample-size / fielding meta, e.g. "n=247 · 95% CI ±5pp". */
  meta?: string;
  /** Optional verbatim props passed through to a right-rail VerbatimCard. */
  quote: {
    text: string;
    audioSrc?: string;
    segments?: string[];
    name?: string;
  };
  /** Replace the stat block with a custom ReactNode (e.g. an inline mini-chart). */
  children?: ReactNode;
}

export function StatHero({ eyebrow, stat, description, meta, quote, children }: StatHeroProps) {
  return (
    <section className="stat-hero">
      <div className="stat-hero__main">
        {eyebrow && <div className="stat-hero__eyebrow">{eyebrow}</div>}
        {children ? (
          children
        ) : (
          <div className="stat-hero__stat tabular">{stat}</div>
        )}
        <p className="stat-hero__description">{description}</p>
        {meta && <p className="stat-hero__meta tabular">{meta}</p>}
      </div>
      <div className="stat-hero__quote">
        <VerbatimCard
          quote={quote.text}
          audioSrc={quote.audioSrc}
          segments={quote.segments}
          name={quote.name}
        />
      </div>
    </section>
  );
}
