import { useTranslation } from "react-i18next";

/**
 * PrioritizationMatrix — impact × feasibility 2D plot for recommendations.
 *
 * The "so what" engine: every recommendation is positioned on a 2D plane
 * by impact (y, business outcome size) and feasibility (x, ease to ship).
 * Top-right quadrant tinted with the sequential viz scale so the eye
 * lands on the do-now moves. Each rec is a small card showing the
 * shortened title and a linked finding reference.
 *
 * Bubble size encodes effort (small = quick, large = months) so a single
 * glance answers "what should we do next?" — a true MBB-style chart.
 *
 * The matrix is SVG so it renders cleanly in the print stylesheet for
 * the PDF export. Hovering a card highlights its position on the grid;
 * keyboard focus does the same for accessibility.
 */

export interface RecommendationItem {
  /** Short ID for accessibility + hover linking. */
  id: string;
  /** Action-title summary, ~60 chars. */
  title: string;
  /** 0–100 impact score. */
  impact: number;
  /** 0–100 feasibility score (100 = trivial to ship). */
  feasibility: number;
  /** Effort level — drives bubble size. */
  effort?: "quick" | "medium" | "large";
  /** Optional reference, e.g. "Finding 03". */
  findingRef?: string;
}

interface PrioritizationMatrixProps {
  recommendations: RecommendationItem[];
}

export function PrioritizationMatrix({ recommendations }: PrioritizationMatrixProps) {
  const { t } = useTranslation("study");
  return (
    <div className="prio-matrix">
      <div className="prio-matrix__plot">
        <svg
          className="prio-matrix__svg"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          role="img"
          aria-label={t("prioritization.ariaLabel")}
        >
          {/* Quadrant tint — top-right (high impact, high feasibility) is the do-now zone */}
          <rect x={50} y={0} width={50} height={50} fill="var(--viz-seq-2)" opacity={0.6} />
          {/* Grid lines */}
          <line x1={50} y1={0} x2={50} y2={100} stroke="var(--border-default)" strokeWidth={0.3} />
          <line x1={0} y1={50} x2={100} y2={50} stroke="var(--border-default)" strokeWidth={0.3} />
          {/* Quadrant labels */}
          <text x={97} y={4} className="prio-matrix__quadrant-label" textAnchor="end">{t("prioritization.quadrant.doNow")}</text>
          <text x={3} y={4} className="prio-matrix__quadrant-label">{t("prioritization.quadrant.consider")}</text>
          <text x={3} y={97} className="prio-matrix__quadrant-label">{t("prioritization.quadrant.park")}</text>
          <text x={97} y={97} className="prio-matrix__quadrant-label" textAnchor="end">{t("prioritization.quadrant.quickWins")}</text>
          {/* Axis labels — rendered outside SVG via CSS for clean typography */}
        </svg>
        {recommendations.map((rec) => {
          const x = rec.feasibility;
          const y = 100 - rec.impact;
          const bubbleSize = rec.effort === "large" ? 18 : rec.effort === "medium" ? 14 : 10;
          return (
            <div
              key={rec.id}
              className={`prio-matrix__rec prio-matrix__rec--${rec.effort ?? "medium"}`}
              style={{
                left: `${x}%`,
                top: `${y}%`,
                "--bubble-size": `${bubbleSize}px`,
              } as React.CSSProperties}
            >
              <div className="prio-matrix__bubble" aria-hidden="true">
                <span className="tabular">{rec.id}</span>
              </div>
              <div className="prio-matrix__card">
                <div className="prio-matrix__card-title">{rec.title}</div>
                {rec.findingRef && (
                  <div className="prio-matrix__card-ref">↳ {rec.findingRef}</div>
                )}
              </div>
            </div>
          );
        })}
        <div className="prio-matrix__axis prio-matrix__axis--y">{t("prioritization.axis.impact")}</div>
        <div className="prio-matrix__axis prio-matrix__axis--x">{t("prioritization.axis.feasibility")}</div>
      </div>
      <ol className="prio-matrix__legend">
        {recommendations.map((rec) => (
          <li key={rec.id} className="prio-matrix__legend-item">
            <span className={`prio-matrix__legend-dot prio-matrix__legend-dot--${rec.effort ?? "medium"}`}>
              {rec.id}
            </span>
            <div className="prio-matrix__legend-text">
              <strong>{rec.title}</strong>
              {rec.findingRef && (
                <span className="prio-matrix__legend-ref"> · {rec.findingRef}</span>
              )}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
