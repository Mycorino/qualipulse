import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

/**
 * FindingCard — the MBB action-title page unit for mixed-methods reports.
 *
 * Replaces a generic "theme card" for shared-report exports. Encodes the
 * Pyramid Principle: thesis-style action title first, evidence below,
 * implication line at the bottom, confidence pill anchored to a sample
 * note. The discipline is in the composition — every finding-card has a
 * stat or chart AND at least one verbatim AND an implication.
 *
 * Three layout variants by composition:
 *   - "evidence-right" (default): chart left, verbatims stacked right
 *   - "evidence-grid": multiple charts in a 2x2 grid, verbatims below
 *   - "evidence-left": verbatims left, chart right (rare, for narrative
 *      flow when the quote is the lede and the chart confirms it)
 *
 * Confidence pills are part of the visual vocabulary the methodologist
 * required: every finding states whether it is "directional" (n<30 or
 * limited segments), "supported" (statistically significant single-source),
 * or "strong evidence" (mixed-methods agreement).
 */

export type FindingConfidence = "directional" | "supported" | "strong";

interface FindingCardProps {
  /** "FINDING 03 of 07" — uppercase tracker */
  index?: string;
  /** Imperative or thesis form: "Trust gaps cost us 30% of new users". */
  actionTitle: string;
  /** One-paragraph framing — sets up the evidence below in 2-3 sentences. */
  context?: string;
  /** Chart slot (typically a ChartCard). */
  evidence: ReactNode;
  /** Verbatims that reinforce the evidence — typically 1-2 quotes. */
  verbatims: ReactNode;
  /** Implication: "So what" line. Bullets separated by line breaks ok. */
  implication: string;
  /** Sample note: "n=247 · 18 interviews · 4 segments". */
  sampleNote?: string;
  /** Confidence level — drives the pill color and label. */
  confidence?: FindingConfidence;
  /** Layout variant. Defaults to "evidence-right". */
  layout?: "evidence-right" | "evidence-grid" | "evidence-left";
}

export function FindingCard({
  index,
  actionTitle,
  context,
  evidence,
  verbatims,
  implication,
  sampleNote,
  confidence = "supported",
  layout = "evidence-right",
}: FindingCardProps) {
  const { t } = useTranslation("study");
  return (
    <article className={`finding-card finding-card--${layout}`}>
      <header className="finding-card__head">
        {index && <div className="finding-card__index">{index}</div>}
        <h3 className="finding-card__title">{actionTitle}</h3>
        {context && <p className="finding-card__context">{context}</p>}
      </header>
      <div className="finding-card__body">
        <div className="finding-card__evidence">{evidence}</div>
        <div className="finding-card__verbatims">{verbatims}</div>
      </div>
      <footer className="finding-card__foot">
        <div className="finding-card__implication">
          <span className="finding-card__implication-label">{t("findingCard.soWhat")}</span>
          <p className="finding-card__implication-text">{implication}</p>
        </div>
        <div className="finding-card__sample-row">
          <ConfidencePill level={confidence} />
          {sampleNote && <span className="finding-card__sample tabular">{sampleNote}</span>}
        </div>
      </footer>
    </article>
  );
}

function ConfidencePill({ level }: { level: FindingConfidence }) {
  const { t } = useTranslation("study");
  return (
    <span className={`confidence-pill confidence-pill--${level}`}>
      <span className="confidence-pill__dot" aria-hidden="true" />
      {t(`findingCard.confidence.${level}`)}
    </span>
  );
}
