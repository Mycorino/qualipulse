/**
 * ScreenerBridge — the wedge affordance.
 *
 * The PM's "magic feature" from the agent reviews: take a filtered subset
 * of survey respondents and convert them into AI voice interviews in one
 * click. This is the conversion mechanic for the credit upsell — survey
 * volume drives interview consumption which drives plan upgrades.
 *
 * Always-visible on a filtered-results dashboard view. Brand-tinted
 * background, primary CTA. Shows the credit cost upfront so users never
 * have a surprise charge — credits are only consumed when the participant
 * actually completes the interview, but we surface the *upper bound* so
 * the commitment is transparent.
 */
interface ScreenerBridgeProps {
  /** Number of respondents matching the current filter. */
  matchCount: number;
  /** Human-readable filter description, e.g. "Detractors who use mobile daily". */
  filterDescription: string;
  /** Available credit balance (so we can soft-warn if it's not enough). */
  availableCredits?: number;
  onInvite?: () => void;
  onSaveSegment?: () => void;
}

export function ScreenerBridge({
  matchCount,
  filterDescription,
  availableCredits,
  onInvite,
  onSaveSegment,
}: ScreenerBridgeProps) {
  const insufficient =
    typeof availableCredits === "number" && availableCredits < matchCount;
  return (
    <aside className="screener-bridge" role="complementary" aria-label="Convert survey respondents to interviews">
      <div className="screener-bridge__icon" aria-hidden="true">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
          <path d="M13 2 L3 14 L12 14 L11 22 L21 10 L12 10 Z" />
        </svg>
      </div>
      <div className="screener-bridge__main">
        <div className="screener-bridge__headline">
          <strong className="tabular">{matchCount}</strong>{" "}
          {matchCount === 1 ? "respondent matches" : "respondents match"} your filter
        </div>
        <div className="screener-bridge__filter">{filterDescription}</div>
        <div className="screener-bridge__meta">
          Will consume up to <strong className="tabular">{matchCount}</strong>{" "}
          credit{matchCount === 1 ? "" : "s"} — credits are only charged when an interview completes.
          {typeof availableCredits === "number" && (
            <>
              {" "}
              You have <strong className="tabular">{availableCredits}</strong> available.
            </>
          )}
        </div>
        {insufficient && (
          <div className="screener-bridge__warning">
            ⚠ Your filter exceeds your available credits. We'll invite the first {availableCredits} respondents
            and queue the rest — or top up to invite everyone.
          </div>
        )}
      </div>
      <div className="screener-bridge__actions">
        <button type="button" className="btn btn-primary" onClick={onInvite} disabled={matchCount === 0}>
          Invite to AI interview →
        </button>
        <button type="button" className="btn btn-secondary" onClick={onSaveSegment}>
          Save segment
        </button>
      </div>
    </aside>
  );
}
