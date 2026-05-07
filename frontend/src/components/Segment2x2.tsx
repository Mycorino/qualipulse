/**
 * Segment2x2 — the MECE-forcing page unit.
 *
 * 2x2 grid where each quadrant carries an axis label, a representative
 * verbatim, a segment chip, and a sample count. Cell backgrounds are
 * tinted with the sequential viz scale based on relative volume share so
 * the eye lands on the heaviest quadrant first.
 *
 * Equal-height cells, never asymmetric. The discipline: one quote per
 * cell, never two. If a cell has more important nuance, that's a
 * different finding — a Segment2x2 is one shape.
 */

interface Quadrant {
  /** Axis label, e.g. "HIGH NEED · LOW SOLUTION". Uppercase tracked. */
  label: string;
  /** The verbatim quote. */
  quote: string;
  /** Segment chip — role, age, region, etc. */
  segment: string;
  /** Sample size of respondents in this quadrant. */
  n: number;
  /** Optional name (only when consented). */
  name?: string;
}

interface Segment2x2Props {
  /** Top-axis label (the X dimension). */
  xAxisLabel: string;
  /** Left-axis label (the Y dimension). */
  yAxisLabel: string;
  /** Order: top-left, top-right, bottom-left, bottom-right. */
  quadrants: [Quadrant, Quadrant, Quadrant, Quadrant];
}

export function Segment2x2({ xAxisLabel, yAxisLabel, quadrants }: Segment2x2Props) {
  const total = quadrants.reduce((a, b) => a + b.n, 0);
  // Map share → sequential scale step (1..5).
  const tints = quadrants.map((q) => {
    const share = total > 0 ? q.n / total : 0;
    if (share >= 0.4) return "viz-seq-5";
    if (share >= 0.3) return "viz-seq-4";
    if (share >= 0.2) return "viz-seq-3";
    if (share >= 0.1) return "viz-seq-2";
    return "viz-seq-1";
  });

  return (
    <div className="segment-2x2" role="figure" aria-label="Segment 2x2 matrix">
      <div className="segment-2x2__top-axis">
        <span className="segment-2x2__axis-label segment-2x2__axis-label--x">{xAxisLabel}</span>
      </div>
      <div className="segment-2x2__grid">
        <span className="segment-2x2__axis-label segment-2x2__axis-label--y" aria-hidden="true">
          {yAxisLabel}
        </span>
        {quadrants.map((q, i) => (
          <div
            key={i}
            className="segment-2x2__cell"
            style={{ background: `var(--${tints[i]})` }}
          >
            <div className="segment-2x2__cell-label">{q.label}</div>
            <blockquote className="segment-2x2__quote">{q.quote}</blockquote>
            <div className="segment-2x2__cell-foot">
              <span className="segment-2x2__chip">{q.segment}</span>
              <span className="segment-2x2__count tabular">n={q.n}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
