import { ReactNode, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { getMe, type CompanyResponse } from "../api/auth";
import { getCreditUsage, type CreditUsage } from "../api/billing";
import { useAuth } from "../hooks/useAuth";
import { AccountMenu } from "./HeaderControls";
import { personInitials } from "./QuantiTopBar";

/**
 * HubShell — the research-hub app frame: dark navy left rail + content
 * canvas. Phase 1 of the hub redesign wraps only the Studies home;
 * other authenticated pages keep QuantiTopBar until they migrate.
 *
 * The rail inherits the marketing page's emphasis surface
 * (`--surface-emphasis`) so the app reads as the same product the
 * landing page sells. Nav stays honest: only destinations that exist
 * (Studies, Decision memos, Account).
 */

interface HubShellProps {
  /** Opens the command palette (rail search button). */
  onSearch?: () => void;
  /** Scrolls to / reveals the decision-memo section. */
  onMemos?: () => void;
  /** Memo count badge for the rail item; omit to hide. */
  memoCount?: number;
  studyCount?: number;
  children: ReactNode;
}

function StudiesGlyph() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <rect x="2.5" y="2.5" width="11" height="11" rx="2" stroke="currentColor" strokeWidth="1.4" />
      <path d="M5.5 8.5 7 10l3.5-4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function MemoGlyph() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M3 3h10v8.5H8L5 14v-2.5H3V3Z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
    </svg>
  );
}

function AccountGlyph() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="8" cy="5.5" r="2.5" stroke="currentColor" strokeWidth="1.4" />
      <path d="M3.5 13.5c.6-2.6 2.4-3.9 4.5-3.9s3.9 1.3 4.5 3.9" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

export function HubShell({ onSearch, onMemos, memoCount, studyCount, children }: HubShellProps) {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const { t } = useTranslation("dashboard");
  const [me, setMe] = useState<CompanyResponse | null>(null);
  const [credits, setCredits] = useState<CreditUsage | null>(null);

  useEffect(() => {
    getMe().then(setMe).catch(() => setMe(null));
    getCreditUsage().then(setCredits).catch(() => setCredits(null));
  }, []);

  const initial = me ? personInitials(me) : "?";
  const first = me?.first_name?.trim() || "";
  const last = me?.last_name?.trim() || "";
  const personName = [first, last].filter(Boolean).join(" ");
  const primaryLine = personName || me?.name || "";
  const secondaryLine = personName ? me?.name ?? "" : me?.email ?? "";

  const creditTotal = credits
    ? credits.included_credits + credits.purchased_credits + credits.rollover_credits
    : 0;
  const creditPct = creditTotal > 0
    ? Math.max(0, Math.min(100, Math.round((credits!.available_credits / creditTotal) * 100)))
    : 0;

  return (
    <div className="hub-shell">
      <aside className="hub-rail">
        <button
          type="button"
          className="hub-rail__logo"
          onClick={() => navigate("/dashboard")}
          aria-label={t("hub.nav.homeAria")}
        >
          <span className="hub-rail__mark" aria-hidden="true">
            <span />
          </span>
          QualiPulse
        </button>

        {onSearch && (
          <button type="button" className="hub-rail__search" onClick={onSearch}>
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.5" />
              <path d="m10.5 10.5 3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            {t("hub.nav.search")}
            <kbd>⌘K</kbd>
          </button>
        )}

        <nav className="hub-rail__nav" aria-label={t("hub.nav.aria")}>
          <button type="button" className="hub-rail__item hub-rail__item--active" aria-current="page">
            <StudiesGlyph />
            {t("hub.nav.studies")}
            {typeof studyCount === "number" && <span className="hub-rail__count">{studyCount}</span>}
          </button>
          {onMemos && (
            <button type="button" className="hub-rail__item" onClick={onMemos}>
              <MemoGlyph />
              {t("hub.nav.memos")}
              {typeof memoCount === "number" && memoCount > 0 && (
                <span className="hub-rail__count">{memoCount}</span>
              )}
            </button>
          )}
          <button type="button" className="hub-rail__item" onClick={() => navigate("/account")}>
            <AccountGlyph />
            {t("hub.nav.account")}
          </button>
        </nav>

        <div className="hub-rail__foot">
          {credits && creditTotal > 0 && (
            <div className="hub-rail__credits">
              <div className="hub-rail__credits-row">
                <strong>
                  {credits.available_credits} / {creditTotal}
                </strong>
                <span>{t("hub.credits.left")}</span>
              </div>
              <div
                className="hub-rail__meter"
                role="img"
                aria-label={t("hub.credits.meterAria", {
                  available: credits.available_credits,
                  total: creditTotal,
                })}
              >
                <i style={{ width: `${creditPct}%` }} />
              </div>
            </div>
          )}
          <div className="hub-rail__user">
            <div className="hub-rail__user-id">
              <span className="hub-rail__user-name">{primaryLine}</span>
              {secondaryLine && secondaryLine !== primaryLine && (
                <span className="hub-rail__user-org">{secondaryLine}</span>
              )}
            </div>
            <AccountMenu initial={initial} onSignOut={logout} />
          </div>
        </div>
      </aside>

      <main className="hub-shell__main">{children}</main>
    </div>
  );
}
