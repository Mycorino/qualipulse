/**
 * MethodologyBox — credibility anchor for every shared mixed-methods report.
 *
 * Required at the top of every report and again expanded in the appendix.
 * The methodologist's hard line: any survey result without sample size,
 * fielding window, segments, and confidence note is not trustworthy.
 *
 * Inline variant doubles as the "insufficient sample for inference" badge
 * used inside chart cards when n falls below the segment-split threshold.
 */
interface MethodologyField {
  label: string;
  value: string;
}

interface MethodologyBoxProps {
  fields: MethodologyField[];
  /** Optional plain-language note appended below — e.g. "Weighted to match panel composition." */
  note?: string;
}

export function MethodologyBox({ fields, note }: MethodologyBoxProps) {
  return (
    <aside className="methodology-box" role="complementary" aria-label="Study methodology">
      {fields.map(({ label, value }) => (
        <div key={label} className="methodology-box__field">
          <span className="methodology-box__label">{label}</span>
          <span className="methodology-box__value">{value}</span>
        </div>
      ))}
      {note && <p className="methodology-box__note">{note}</p>}
    </aside>
  );
}

interface SmallNWarningProps {
  n: number;
  minN?: number;
}

/** Inline variant — small-n warning chip for use inside dashboards. */
export function SmallNWarning({ n, minN = 30 }: SmallNWarningProps) {
  return (
    <span className="methodology-box methodology-box--inline">
      ⚠ Insufficient sample for inference — n={n} (min {minN})
    </span>
  );
}
