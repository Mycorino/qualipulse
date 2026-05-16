import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../hooks/useAuth";
import { SkeletonCard } from "../components/Skeleton";
import {
  createDemoProject,
  listProjects,
  unarchiveProject,
  ProjectListItem,
} from "../api/projects";
import { getMe, resendVerification } from "../api/auth";
import type { CompanyResponse } from "../api/auth";
import client from "../api/client";

interface CreditsUsage {
  included_credits: number;
  purchased_credits: number;
  rollover_credits: number;
  used_credits: number;
  overage_credits: number;
  available_credits: number;
  period_start: string | null;
  period_end: string | null;
}

import DashboardInsights from "../components/DashboardInsights";
import LanguageSwitcher from "../components/LanguageSwitcher";
import { AccountMenu } from "../components/HeaderControls";

export default function Dashboard() {
  const { t, i18n } = useTranslation(["dashboard", "common"]);
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [archivedProjects, setArchivedProjects] = useState<ProjectListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showArchive, setShowArchive] = useState(false);
  const [archiveLoading, setArchiveLoading] = useState(false);
  const [restoringId, setRestoringId] = useState<string | null>(null);
  const [me, setMe] = useState<CompanyResponse | null>(null);
  const [resendingVerification, setResendingVerification] = useState(false);
  const [verificationResent, setVerificationResent] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [seedingDemo, setSeedingDemo] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [sortBy, setSortBy] = useState<"newest" | "oldest" | "responses" | "name">("newest");
  const [trialBannerDismissed, setTrialBannerDismissed] = useState(false);
  const [credits, setCredits] = useState<CreditsUsage | null>(null);
  const [creditsBannerDismissed, setCreditsBannerDismissed] = useState(false);
  const navigate = useNavigate();
  const { logout } = useAuth();

  useEffect(() => {
    loadProjects();
    // Dashboard is the app's entry after login — this is where we sync
    // i18n.language to the account's preferred_language. Without this,
    // a French researcher on an English-locale browser would see localised
    // components (which read from i18n) render in English even though the
    // backend already knows their real language. We only switch when the
    // two actually disagree so we don't fight a user who just clicked the
    // language switcher in this session.
    getMe()
      .then((data) => {
        setMe(data);
        const accountLang = (data.preferred_language || "").slice(0, 2);
        const uiLang = (i18n.language || "").slice(0, 2);
        if (accountLang && accountLang !== uiLang && (accountLang === "fr" || accountLang === "en")) {
          i18n.changeLanguage(accountLang);
        }
      })
      .catch(() => {});
    // Credits usage — 404 for legacy plans, that's fine; we just won't show the banner.
    client.get<CreditsUsage>("/billing/usage")
      .then((r) => setCredits(r.data))
      .catch(() => setCredits(null));
  }, []);

  async function loadProjects() {
    try {
      const data = await listProjects();
      setProjects(data);
      setLoadError(false);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }

  async function loadArchived() {
    setArchiveLoading(true);
    try {
      const data = await listProjects(true);
      setArchivedProjects(data);
    } catch {
      // handled by interceptor
    } finally {
      setArchiveLoading(false);
    }
  }

  async function handleToggleArchive() {
    const next = !showArchive;
    setShowArchive(next);
    if (next && archivedProjects.length === 0) {
      await loadArchived();
    }
  }

  async function handleResendVerification() {
    setResendingVerification(true);
    try {
      await resendVerification();
      setVerificationResent(true);
    } catch {
      // handled by interceptor
    } finally {
      setResendingVerification(false);
    }
  }

  async function handleCreateDemo() {
    setSeedingDemo(true);
    try {
      const project = await createDemoProject();
      navigate(`/projects/${project.id}?tab=analysis&demo=1`);
    } catch {
      // interceptor handles toast
    } finally {
      setSeedingDemo(false);
    }
  }

  async function handleRestore(e: React.MouseEvent, projectId: string) {
    e.stopPropagation();
    setRestoringId(projectId);
    try {
      await unarchiveProject(projectId);
      const restored = archivedProjects.find((p) => p.id === projectId);
      if (restored) {
        setArchivedProjects((prev) => prev.filter((p) => p.id !== projectId));
        setProjects((prev) => [{ ...restored, archived_at: null }, ...prev]);
      }
    } catch {
      // handled by interceptor
    } finally {
      setRestoringId(null);
    }
  }

  function getProjectMax(tier: string | undefined): string | number {
    if (!tier) return 1;
    if (tier === "starter" || tier === "solo" || tier === "free") return 1;
    if (tier === "team") return 5;
    return "∞";
  }

  // Real projects (non-demo) for counting and gating
  const realProjects = projects.filter((p) => !p.is_demo);

  const sortedProjects = [...projects].sort((a, b) => {
    switch (sortBy) {
      case "oldest":
        return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      case "responses":
        return (b.completed_count || 0) - (a.completed_count || 0);
      case "name":
        return a.name.localeCompare(b.name);
      case "newest":
      default:
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    }
  });

  return (
    <div className="dashboard-layout">
      <header className="dashboard-header">
        <span className="logo">QualiPulse</span>
        <button
          className="dashboard-hamburger"
          onClick={() => setMenuOpen((v) => !v)}
          aria-label={menuOpen ? "Close menu" : "Open menu"}
          aria-expanded={menuOpen}
        >
          <span className="dashboard-hamburger-bar" />
          <span className="dashboard-hamburger-bar" />
          <span className="dashboard-hamburger-bar" />
        </button>
        <nav className={`dashboard-nav dashboard-nav--with-avatar${menuOpen ? " dashboard-nav--open" : ""}`}>
          <button
            className="btn btn-ghost"
            style={{ minHeight: 44 }}
            onClick={() => { setMenuOpen(false); navigate("/studies"); }}
            title="Run a screener, validation, or mixed-methods study"
          >
            Studies
          </button>
          <span className="nav-only-mobile" style={{ display: "contents" } as React.CSSProperties}>
            <LanguageSwitcher variant="light" />
            <button className="btn btn-ghost" style={{ minHeight: 44 }} onClick={() => { setMenuOpen(false); navigate("/account"); }}>
              {t("common:account")}
            </button>
            <button className="btn btn-ghost" style={{ minHeight: 44 }} onClick={() => { setMenuOpen(false); logout(); }}>
              {t("common:signOut")}
            </button>
          </span>
          <AccountMenu
            initial={(me?.name || me?.email || "?").trim().charAt(0).toUpperCase()}
            onSignOut={logout}
          />
        </nav>
      </header>

      <main className="dashboard-main">
        {/* Hub identity header — brand-tinted band with greeting + metric pills */}
        {(() => {
          const completedTotal = realProjects.reduce((acc, p) => acc + (p.completed_count || 0), 0);
          const inProgressTotal = realProjects.reduce((acc, p) => acc + (p.in_progress_count || 0), 0);
          const analysesReady = realProjects.filter((p) => p.analysis_status === "ready").length;
          // Greet by the user's actual first name when we have it, falling
          // back to the company name's first token only as a last resort.
          // "Welcome back, Sarah" beats "Welcome back, Northwind".
          const firstName =
            (me?.first_name || "").trim() ||
            (me?.name || "").trim().split(" ")[0];
          const hasProjects = realProjects.length > 0;
          return (
            <section className="hub-header" aria-label={t("hubHeader.aria", "Workspace overview")}>
              <span className="eyebrow-tag eyebrow-tag--ghost hub-header__eyebrow">
                {t("hubHeader.eyebrow", "Your research workspace")}
              </span>
              <h1 className="hub-header__title">
                {hasProjects
                  ? (firstName ? t("hubHeader.welcomeBackName", { name: firstName }) : t("hubHeader.welcomeBack"))
                  : t("hubHeader.firstStudy")}
              </h1>
              {!loading && me && (
                <p className="hub-header__subtitle">
                  {hasProjects
                    ? t("hubHeader.contextLine", {
                        projects: realProjects.length,
                        completed: completedTotal,
                      })
                    : t("hubHeader.firstStudySubtitle")}
                </p>
              )}
              <div className="hub-header__row">
                <div className="hub-header__pills" aria-hidden={!hasProjects}>
                  {hasProjects && (
                    <>
                      {/* Hide the "N projects" pill when count <= 1 — the
                          subtitle already states it, no value in repeating. */}
                      {realProjects.length > 1 && (
                        <span className="hub-header__pill">
                          <strong>{realProjects.length}</strong>{" "}
                          {t("hubHeader.pillProjects", { count: realProjects.length })}
                        </span>
                      )}
                      {completedTotal > 0 && (
                        <span className="hub-header__pill hub-header__pill--success">
                          <strong>{completedTotal}</strong>{" "}
                          {t("hubHeader.pillCompleted", { count: completedTotal })}
                        </span>
                      )}
                      {inProgressTotal > 0 && (
                        <span className="hub-header__pill hub-header__pill--info">
                          <strong>{inProgressTotal}</strong>{" "}
                          {t("hubHeader.pillInProgress", { count: inProgressTotal })}
                        </span>
                      )}
                      {analysesReady > 0 && (
                        <span className="hub-header__pill hub-header__pill--success pulse-soft">
                          ✦ <strong>{analysesReady}</strong>{" "}
                          {t("hubHeader.pillAnalysesReady", { count: analysesReady })}
                        </span>
                      )}
                    </>
                  )}
                </div>
                <div className="hub-header__cta" style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                  {!loading && me && (
                    <span style={{ fontSize: 13, color: "var(--text-tertiary)" }}>
                      {t("projectCount", { count: realProjects.length, max: getProjectMax(me.subscription_tier) })}
                    </span>
                  )}
                  {projects.length > 1 && (
                    <select
                      value={sortBy}
                      onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
                      style={{
                        fontSize: 13,
                        padding: "6px 10px",
                        borderRadius: 6,
                        border: "1px solid var(--border-subtle)",
                        background: "white",
                        color: "var(--text-secondary)",
                        cursor: "pointer",
                      }}
                    >
                      <option value="newest">{t("sort.newest", "Newest first")}</option>
                      <option value="oldest">{t("sort.oldest", "Oldest first")}</option>
                      <option value="responses">{t("sort.responses", "Most responses")}</option>
                      <option value="name">{t("sort.name", "Name A–Z")}</option>
                    </select>
                  )}
                  <button
                    className="btn btn-primary"
                    onClick={() => navigate("/projects/new")}
                  >
                    {t("createProject")}
                  </button>
                </div>
              </div>
            </section>
          );
        })()}

        {/* Global banners */}
        {!loading && me?.trial_ends_at && new Date(me.trial_ends_at) > new Date() && (() => {
          const trialEnd = new Date(me.trial_ends_at);
          const msLeft = trialEnd.getTime() - Date.now();
          const daysLeft = Math.max(1, Math.ceil(msLeft / (1000 * 60 * 60 * 24)));
          const endingSoon = daysLeft <= 3;
          // Per-trial-end-date dismissal key. Ignored when ≤3 days left.
          const dismissKey = `trial-banner-dismissed-${trialEnd.toISOString().slice(0, 10)}`;
          const wasDismissed = trialBannerDismissed || localStorage.getItem(dismissKey) === "true";
          if (wasDismissed && !endingSoon) return null;
          const formattedDate = trialEnd.toLocaleDateString(undefined, {
            day: "numeric",
            month: "short",
            year: "numeric",
          });
          return (
            <div
              className={`gs-trial-banner${endingSoon ? " gs-trial-banner--urgent" : ""}`}
              style={{ marginBottom: 16 }}
            >
              <span aria-hidden="true" style={{ display: "inline-flex", alignItems: "center", color: endingSoon ? "var(--danger-text, #b91c1c)" : "var(--primary, #4369f5)" }}>
                {endingSoon ? (
                  /* Triangle alert (Lucide-style) */
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
                ) : (
                  /* Sparkles (Lucide-style) */
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"/><path d="M20 3v4"/><path d="M22 5h-4"/></svg>
                )}
              </span>
              <div style={{ flex: 1 }}>
                <strong>
                  {endingSoon
                    ? t("trialBanner.endingSoonTitle", { count: daysLeft })
                    : t("trialBanner.title")}
                </strong>{" "}
                <span className="gs-trial-badge">
                  {t("trialBanner.daysLeft", { count: daysLeft })}
                </span>
                <div style={{ marginTop: 4, fontSize: 13, lineHeight: 1.5 }}>
                  {endingSoon
                    ? t("trialBanner.endingSoonDesc", { date: formattedDate })
                    : t("trialBanner.desc", { date: formattedDate })}
                </div>
              </div>
              <button
                className={endingSoon ? "btn btn-primary btn-sm" : "btn-inline"}
                onClick={() => navigate("/account")}
                style={{ whiteSpace: "nowrap", flexShrink: 0 }}
              >
                {endingSoon ? t("trialBanner.upgradeCta") : t("trialBanner.viewPlans")}
              </button>
              {!endingSoon && (
                <button
                  type="button"
                  className="gs-trial-banner-dismiss"
                  aria-label={t("trialBanner.dismissAria")}
                  onClick={() => {
                    localStorage.setItem(dismissKey, "true");
                    setTrialBannerDismissed(true);
                  }}
                >
                  ×
                </button>
              )}
            </div>
          );
        })()}

        {/* Credits usage banner: fires at ≥80%, becomes critical at 100%.
            Only renders for accounts on a credit plan (404 from /billing/usage
            means legacy account — banner is silently skipped). */}
        {!loading && credits && (() => {
          const total =
            credits.included_credits +
            credits.purchased_credits +
            credits.rollover_credits;
          if (total === 0) return null;
          const percent = Math.min(100, Math.round((credits.used_credits / total) * 100));
          if (percent < 80) return null;
          const isCritical = percent >= 100;
          // Per-period dismissal so the banner returns when the new period starts.
          const periodKey = credits.period_end?.slice(0, 10) ?? "no-period";
          const dismissKey = `credits-banner-dismissed-${periodKey}`;
          const wasDismissed =
            creditsBannerDismissed || localStorage.getItem(dismissKey) === "true";
          // 100% banner cannot be dismissed — they need to act.
          if (wasDismissed && !isCritical) return null;
          return (
            <div
              className={`gs-trial-banner${isCritical ? " gs-trial-banner--urgent" : ""}`}
              style={{ marginBottom: 16 }}
            >
              <span aria-hidden="true">{isCritical ? "🚫" : "⚠️"}</span>
              <div style={{ flex: 1 }}>
                <strong>
                  {isCritical
                    ? t("creditsBanner.criticalTitle", { defaultValue: "You're out of credits" })
                    : t("creditsBanner.warningTitle", {
                        defaultValue: "{{percent}}% of your credits used",
                        percent,
                      })}
                </strong>
                <div style={{ marginTop: 4, fontSize: 13, lineHeight: 1.5 }}>
                  {isCritical
                    ? t("creditsBanner.criticalDesc", {
                        defaultValue:
                          "New interviews will be blocked until you buy a credit pack or your next billing period begins.",
                      })
                    : t("creditsBanner.warningDesc", {
                        defaultValue:
                          "{{used}} of {{total}} credits used this period. Top up to avoid interruption.",
                        used: credits.used_credits,
                        total,
                      })}
                </div>
              </div>
              <button
                className="btn btn-primary btn-sm"
                onClick={() => navigate("/account?tab=billing")}
                style={{ whiteSpace: "nowrap", flexShrink: 0 }}
              >
                {t("creditsBanner.cta", { defaultValue: "Buy credits" })}
              </button>
              {!isCritical && (
                <button
                  type="button"
                  className="gs-trial-banner-dismiss"
                  aria-label={t("creditsBanner.dismissAria", { defaultValue: "Dismiss" })}
                  onClick={() => {
                    localStorage.setItem(dismissKey, "true");
                    setCreditsBannerDismissed(true);
                  }}
                >
                  ×
                </button>
              )}
            </div>
          );
        })()}

        {/* Onboarding hand-off hint: real project exists but zero responses */}
        {!loading && (() => {
          const realProjectsList = projects.filter((p) => !p.is_demo);
          if (realProjectsList.length === 0) return null;
          const totalResponses = realProjectsList.reduce(
            (acc, p) => acc + (p.completed_count || 0) + (p.in_progress_count || 0),
            0
          );
          if (totalResponses > 0) return null;
          const newest = [...realProjectsList].sort(
            (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
          )[0];
          return (
            <div className="handoff-hint" role="status">
              <span aria-hidden="true">→</span>
              <div className="handoff-hint__body">
                <strong>{t("handoffHint.title")}</strong>{" "}
                <span>{t("handoffHint.desc")}</span>
              </div>
              <button
                className="btn btn-primary btn-sm handoff-hint__cta"
                onClick={() => navigate(`/projects/${newest.id}`)}
              >
                {t("handoffHint.cta")}
              </button>
            </div>
          );
        })()}

        {loadError && (
          <div className="error-banner" style={{ marginBottom: 16 }}>
            {t("loadError")}
          </div>
        )}

        {/* AI-driven priority re-prompt + personalised study recommendations.
            Only renders once we have a loaded `me` so the priority block knows
            whether the prompt is due. Degrades silently when there's nothing
            useful to show. */}
        {/* Only show priority prompt + recommendations once the user has
            at least one real (non-demo) project — showing it immediately
            after onboarding is too early and adds friction. */}
        {!loading && me && realProjects.length > 0 && (
          <DashboardInsights me={me} onPriorityUpdated={setMe} />
        )}

        {loading ? (
          <div className="project-grid">
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </div>
        ) : projects.length === 0 ? (
          <div className="getting-started">
            <div className="getting-started-header">
              <h2 style={{ color: "#ffffff" }}>{t("gettingStarted.welcome", { name: me?.name ? `, ${me.name}` : "" })}</h2>
              <p>{t("gettingStarted.subtitle")}</p>
            </div>

            <div className="getting-started-steps">
              <div className="gs-step">
                <div className="gs-step-icon gs-step-active">1</div>
                <div className="gs-step-content">
                  <h3>{t("gettingStarted.step1Title")}</h3>
                  <p>{t("gettingStarted.step1Desc")}</p>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <button className="btn btn-primary btn-sm" onClick={() => navigate("/projects/new")}>
                      {t("gettingStarted.step1Cta")}
                    </button>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={handleCreateDemo}
                      disabled={seedingDemo}
                    >
                      {seedingDemo ? t("gettingStarted.demoLoading") : t("gettingStarted.demoCta")}
                    </button>
                  </div>
                </div>
              </div>

              <div className="gs-step">
                <div className="gs-step-icon">2</div>
                <div className="gs-step-content">
                  <h3>{t("gettingStarted.step2Title")}</h3>
                  <p>{t("gettingStarted.step2Desc")}</p>
                </div>
              </div>

              <div className="gs-step">
                <div className="gs-step-icon">3</div>
                <div className="gs-step-content">
                  <h3>{t("gettingStarted.step3Title")}</h3>
                  <p>{t("gettingStarted.step3Desc")}</p>
                </div>
              </div>
            </div>

            {me && !me.email_verified && (
              <div className="gs-verify-banner">
                <span>&#128231;</span>
                <div>
                  <strong>{t("common:verifyEmail")}</strong>
                  <p>{t("common:verifyEmailDesc")}</p>
                  {verificationResent ? (
                    <span style={{ fontSize: 13, color: "#16a34a" }}>{t("common:emailSent")}</span>
                  ) : (
                    <button
                      className="btn-inline"
                      disabled={resendingVerification}
                      onClick={handleResendVerification}
                    >
                      {resendingVerification ? t("common:resending") : t("common:resendEmail")}
                    </button>
                  )}
                </div>
              </div>
            )}

          </div>
        ) : (
          <>
          {me && !me.email_verified && (
            <div className="gs-verify-banner" style={{ marginBottom: 16 }}>
              <span>&#128231;</span>
              <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                <span><strong>{t("common:verifyEmail")}</strong> — {t("common:verifyEmailDesc")}</span>
                {verificationResent ? (
                  <span style={{ fontSize: 13, color: "#16a34a" }}>{t("common:emailSent")}</span>
                ) : (
                  <button
                    className="btn-inline"
                    disabled={resendingVerification}
                    onClick={handleResendVerification}
                  >
                    {resendingVerification ? t("common:resending") : t("common:resendEmail")}
                  </button>
                )}
              </div>
            </div>
          )}
          <div className="project-grid">
            {sortedProjects.map((p) => {
              // Staleness nudge: a project is "stale" when it has some
              // responses and they stopped coming in more than 14 days ago.
              // This is the gentle kick the researcher needs to remember
              // they have unfinished work — but we only compute it from
              // fields that are already in the list payload, so the grid
              // never fans out N AI calls.
              const daysSinceLastResponse = p.last_response_at
                ? Math.floor(
                    (Date.now() - new Date(p.last_response_at).getTime()) /
                      (1000 * 60 * 60 * 24)
                  )
                : null;
              const isStale =
                p.completed_count > 0 &&
                daysSinceLastResponse !== null &&
                daysSinceLastResponse >= 14;
              const hasResponsesNoAnalysis =
                p.completed_count >= 3 && !p.analysis_status;

              return (
                <div
                  key={p.id}
                  className="project-card"
                  style={{ maxWidth: 400 }}
                  role="button"
                  tabIndex={0}
                  onClick={() => {
                    const deepLinkTab = hasResponsesNoAnalysis || p.analysis_status === "ready" ? "?tab=analysis" : "";
                    navigate(`/projects/${p.id}${deepLinkTab}`);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      const deepLinkTab = hasResponsesNoAnalysis || p.analysis_status === "ready" ? "?tab=analysis" : "";
                      navigate(`/projects/${p.id}${deepLinkTab}`);
                    }
                  }}
                >
                  <h3 className="project-card-name">{p.name}</h3>
                  <div className="project-card-meta">
                    <span className="badge">{p.language.toUpperCase()}</span>
                    <span>{t("projectCard.questions", { count: p.question_count })}</span>
                  </div>
                  <div className="project-card-stats">
                    {p.completed_count > 0 && (
                      <span className="project-stat project-stat-completed">
                        {t("projectCard.completed", { count: p.completed_count })}
                      </span>
                    )}
                    {p.in_progress_count > 0 && (
                      <span className="project-stat project-stat-inprogress">
                        {t("projectCard.inProgress", { count: p.in_progress_count })}
                      </span>
                    )}
                    {p.completed_count === 0 && p.in_progress_count === 0 && (
                      <span className="project-stat project-stat-empty">{t("projectCard.noResponses")}</span>
                    )}
                    {p.analysis_status === "ready" && (
                      <span className="project-stat project-stat-analysis pulse-soft">{t("projectCard.analysisReady")}</span>
                    )}
                    {p.analysis_status === "generating" && (
                      <span className="project-stat project-stat-generating">{t("projectCard.analysing")}</span>
                    )}
                  </div>

                  {/* Gentle nudge row: only one message, picked by priority.
                      "Analyse now" beats "stale" — if they've got responses
                      and haven't analysed, that's the action we want. */}
                  {hasResponsesNoAnalysis ? (
                    <p
                      className="project-card-nudge project-card-nudge--action"
                      style={{
                        margin: "8px 0 0",
                        fontSize: 12,
                        color: "var(--primary)",
                        fontWeight: 500,
                      }}
                    >
                      {t("projectCard.nudgeAnalyse", {
                        defaultValue:
                          "✦ Ready to analyse — you have {{count}} completed interviews",
                        count: p.completed_count,
                      })}
                    </p>
                  ) : isStale ? (
                    <p
                      className="project-card-nudge project-card-nudge--stale"
                      style={{
                        margin: "8px 0 0",
                        fontSize: 12,
                        color: "var(--text-tertiary)",
                      }}
                    >
                      {t("projectCard.nudgeStale", {
                        defaultValue:
                          "No responses in {{count}} days — try resharing the link or loosening screening",
                        count: daysSinceLastResponse!,
                      })}
                    </p>
                  ) : null}

                  <p className="project-card-date">
                    {p.last_response_at
                      ? t("projectCard.lastActivity", {
                          date: new Date(p.last_response_at).toLocaleDateString(undefined, { day: "numeric", month: "short" }),
                          defaultValue: "Last response {{date}}",
                        })
                      : t("projectCard.created", {
                          date: new Date(p.created_at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }),
                          defaultValue: "Created {{date}}",
                        })}
                  </p>
                </div>
              );
            })}
          </div>
          </>
        )}

        {/* Archive section */}
        <div className="archive-section">
          <button className="archive-toggle" onClick={handleToggleArchive}>
            <span className="archive-toggle-icon">{showArchive ? "▾" : "▸"}</span>
            <span>{t("archive.title")}</span>
            {archivedProjects.length > 0 && (
              <span className="archive-count">{archivedProjects.length}</span>
            )}
          </button>

          {showArchive && (
            <div className="archive-list">
              {archiveLoading ? (
                <p className="archive-empty">{t("archive.loading")}</p>
              ) : archivedProjects.length === 0 ? (
                <p className="archive-empty">{t("archive.empty")}</p>
              ) : (
                archivedProjects.map((p) => (
                  <div key={p.id} className="archive-row">
                    <div className="archive-row-info">
                      <span className="archive-row-name">{p.name}</span>
                      <span className="archive-row-meta">
                        <span className="badge badge--sm">{p.language.toUpperCase()}</span>
                        <span>
                          {p.archived_at
                            ? t("archive.archived", { date: new Date(p.archived_at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) })
                            : ""}
                        </span>
                        {p.completed_count > 0 && (
                          <span>· {t("projectCard.completed", { count: p.completed_count })}</span>
                        )}
                      </span>
                    </div>
                    <div className="archive-row-actions">
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={(e) => handleRestore(e, p.id)}
                        disabled={restoringId === p.id}
                      >
                        {restoringId === p.id ? t("common:restoring") : t("archive.restore")}
                      </button>
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/projects/${p.id}`);
                        }}
                      >
                        {t("archive.view")}
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
