import type { NextAction } from "../copilot/nextAction";

interface NextActionChipProps {
  action: NextAction;
  /** "inline" — sits in an empty state / panel. "dock" — compact pill. */
  variant: "dock" | "inline";
  /** Handler for the action. Omit for non-actionable (wait/done) states. */
  onRun?: () => void;
}

/**
 * NextActionChip — renders one resolved next-best-action.
 *
 * The single deterministic suggestion from `resolveNextAction`. Used inline
 * in empty states today; the Copilot dock reuses the "dock" variant in
 * Phase 2b. The ✦ mark signals "this is the Research Copilot."
 */
export function NextActionChip({ action, variant, onRun }: NextActionChipProps) {
  const actionable = action.kind === "do" && !!onRun;
  const glyph = action.kind === "do" ? "✦" : action.kind === "wait" ? "⏳" : "✓";

  if (variant === "dock") {
    return (
      <button
        type="button"
        className={`nba-chip nba-chip--dock nba-chip--${action.kind}`}
        onClick={onRun}
        disabled={!actionable}
        title={action.reason}
      >
        <span className="nba-chip__eyebrow">Next</span>
        <span className="nba-chip__label">{action.label}</span>
      </button>
    );
  }

  return (
    <div className={`nba-chip nba-chip--inline nba-chip--${action.kind}`}>
      {actionable ? (
        <button
          type="button"
          className="btn btn-primary btn-sm nba-chip__cta"
          onClick={onRun}
        >
          <span aria-hidden="true">{glyph}</span> {action.label}
        </button>
      ) : (
        <span className="nba-chip__static">
          <span aria-hidden="true">{glyph}</span> {action.label}
        </span>
      )}
      <p className="nba-chip__reason">{action.reason}</p>
    </div>
  );
}
