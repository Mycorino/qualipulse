import { ReactNode, useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { getMe, type CompanyResponse } from "../api/auth";
import { getCreditUsage, getPlanDisplay, type CreditUsage, type PlanDisplay } from "../api/billing";
import { listStudies, type StudySummary } from "../api/studies";
import { useAuth } from "../hooks/useAuth";
import { AccountMenu } from "./HeaderControls";
import { personInitials, type Crumb } from "./QuantiTopBar";
import { CommandPalette } from "./CommandPalette";

/**
 * HubShell — the research-hub app frame: dark navy left rail + content
 * canvas. Every authenticated page renders through it (phase 2); the
 * rail inherits the marketing page's emphasis surface so the app reads
 * as the same product the landing page sells.
 *
 * The shell owns the ⌘K command palette, so any page gets the
 * quick-switcher for free. Pages that already hold the studies list
 * (StudyList) pass it in via `studies`; everywhere else the palette
 * lazily fetches on first open. Palette actions route through URL
 * affordances StudyList already honours (`/studies?new=1`,
 * `/studies#decision-memos`) so behaviour is identical from any page.
 */

interface HubShellProps {
  /** Which rail destination the current page belongs to. */
  active?: "studies" | "account";
  /** Optional breadcrumb row rendered at the top of the content area. */
  crumbs?: Crumb[];
  /** Preloaded studies (skips the palette's lazy fetch). */
  studies?: StudySummary[] | null;
  /** Ready-memo count badge for the rail item; omit to hide. */
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

export function HubShell({
  active = "studies",
  crumbs,
  studies,
  memoCount,
  studyCount,
  children,
}: HubShellProps) {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const { t } = useTranslation("dashboard");
  const [me, setMe] = useState<CompanyResponse | null>(null);
  const [credits, setCredits] = useState<CreditUsage | null>(null);
  const [plan, setPlan] = useState<PlanDisplay | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  // Palette data when the host page doesn't hold the studies list itself.
  const [fetchedStudies, setFetchedStudies] = useState<StudySummary[] | null>(null);

  useEffect(() => {
    getMe().then(setMe).catch(() => setMe(null));
    getCreditUsage().then(setCredits).catch(() => setCredits(null));
    getPlanDisplay().then(setPlan).catch(() => setPlan(null));
  }, []);

  const paletteStudies = studies !== undefined ? studies : fetchedStudies;

  const openPalette = useCallback(() => {
    setPaletteOpen(true);
    if (studies === undefined && fetchedStudies === null) {
      listStudies().then(setFetchedStudies).catch(() => setFetchedStudies([]));
    }
  }, [studies, fetchedStudies]);

  const goMemos = useCallback(() => {
    navigate("/studies#decision-memos");
  }, [navigate]);

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

        <button type="button" className="hub-rail__search" onClick={openPalette}>
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.5" />
            <path d="m10.5 10.5 3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          <span className="hub-rail__search-label">{t("hub.nav.search")}</span>
          <kbd>⌘K</kbd>
        </button>

        <nav className="hub-rail__nav" aria-label={t("hub.nav.aria")}>
          <button
            type="button"
            className={`hub-rail__item${active === "studies" ? " hub-rail__item--active" : ""}`}
            aria-current={active === "studies" ? "page" : undefined}
            onClick={() => navigate("/studies")}
          >
            <StudiesGlyph />
            {t("hub.nav.studies")}
            {typeof studyCount === "number" && <span className="hub-rail__count">{studyCount}</span>}
          </button>
          <button type="button" className="hub-rail__item" onClick={goMemos}>
            <MemoGlyph />
            {t("hub.nav.memos")}
            {typeof memoCount === "number" && memoCount > 0 && (
              <span className="hub-rail__count">{memoCount}</span>
            )}
          </button>
          <button
            type="button"
            className={`hub-rail__item${active === "account" ? " hub-rail__item--active" : ""}`}
            aria-current={active === "account" ? "page" : undefined}
            onClick={() => navigate("/account")}
          >
            <AccountGlyph />
            {t("hub.nav.account")}
          </button>
        </nav>

        <div className="hub-rail__foot">
          {(plan || (credits && creditTotal > 0)) && (
            <button
              type="button"
              className="hub-rail__credits"
              onClick={() => navigate("/account/billing")}
              aria-label={t("hub.plan.manageAria")}
            >
              {plan && (
                <div className="hub-rail__plan-row">
                  <span className="hub-rail__plan-name">
                    {plan.is_trial ? t("hub.plan.freeTrial") : plan.plan_name}
                  </span>
                  <span className="hub-rail__plan-cta">
                    {plan.is_trial ? t("hub.plan.upgrade") : t("hub.plan.manage")}
                  </span>
                </div>
              )}
              {credits && creditTotal > 0 && (
                <>
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
                </>
              )}
            </button>
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

      <main className="hub-shell__main">
        {crumbs && crumbs.length > 0 && (
          <nav className="hub-crumbs" aria-label={t("hub.nav.breadcrumbAria")}>
            {crumbs.map((crumb, i) => {
              const isLast = i === crumbs.length - 1;
              return (
                <span key={`${crumb.label}-${i}`} className="hub-crumbs__wrap">
                  {i > 0 && (
                    <span className="hub-crumbs__sep" aria-hidden="true">
                      /
                    </span>
                  )}
                  {crumb.to && !isLast ? (
                    <button
                      type="button"
                      className="hub-crumbs__item hub-crumbs__item--link"
                      onClick={() => navigate(crumb.to!)}
                    >
                      {crumb.label}
                    </button>
                  ) : (
                    <span
                      className="hub-crumbs__item"
                      aria-current={isLast ? "page" : undefined}
                    >
                      {crumb.label}
                    </span>
                  )}
                </span>
              );
            })}
          </nav>
        )}
        {children}
      </main>

      <CommandPalette
        open={paletteOpen}
        onOpen={openPalette}
        onClose={() => setPaletteOpen(false)}
        studies={paletteStudies}
        onNewStudy={() => navigate("/studies?new=1")}
        onMemos={goMemos}
      />
    </div>
  );
}
