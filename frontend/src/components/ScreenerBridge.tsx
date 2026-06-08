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
import { useTranslation } from "react-i18next";

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
  const { t } = useTranslation("survey");
  const insufficient =
    typeof availableCredits === "number" && availableCredits < matchCount;
  return (
    <aside className="screener-bridge" role="complementary" aria-label={t("screenerBridge.ariaLabel")}>
      <div className="screener-bridge__icon" aria-hidden="true">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
          <path d="M13 2 L3 14 L12 14 L11 22 L21 10 L12 10 Z" />
        </svg>
      </div>
      <div className="screener-bridge__main">
        <div className="screener-bridge__headline">
          <strong className="tabular">{matchCount}</strong>{" "}
          {t("screenerBridge.matchesHeadline", { count: matchCount })}
        </div>
        <div className="screener-bridge__filter">{filterDescription}</div>
        <div className="screener-bridge__meta">
          {t("screenerBridge.willConsumePrefix")} <strong className="tabular">{matchCount}</strong>{" "}
          {t("screenerBridge.creditsSuffix", { count: matchCount })}
          {typeof availableCredits === "number" && (
            <>
              {" "}
              {t("screenerBridge.available", { n: availableCredits })}
            </>
          )}
        </div>
        {insufficient && (
          <div className="screener-bridge__warning">
            {t("screenerBridge.insufficient", { n: availableCredits })}
          </div>
        )}
      </div>
      <div className="screener-bridge__actions">
        <button type="button" className="btn btn-primary" onClick={onInvite} disabled={matchCount === 0}>
          {t("screenerBridge.inviteToInterview")}
        </button>
        <button type="button" className="btn btn-secondary" onClick={onSaveSegment}>
          {t("screenerBridge.saveSegment")}
        </button>
      </div>
    </aside>
  );
}
