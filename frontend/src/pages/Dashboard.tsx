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
import LanguageSwitcher from "../components/LanguageSwitcher";
import DashboardInsights from "../components/DashboardInsights";

export default function Dashboard() {
  const { t } = useTranslation(["dashboard", "common"]);
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
  const navigate = useNavigate();
  const { logout } = useAuth();

  useEffect(() => {
    loadProjects();
    getMe().then(setMe).catch(() => {});
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

  return (
    <div className="dashboard-layout">
      <header className="dashboard-header" style={{ flexWrap: "wrap" }}>
        <span className="logo">QualiPulse</span>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <LanguageSwitcher variant="light" />
          <button className="btn btn-ghost" style={{ minHeight: 44 }} onClick={() => navigate("/account")}>
            {t("common:account")}
          </button>
          <button className="btn btn-ghost" style={{ minHeight: 44 }} onClick={logout}>
            {t("common:signOut")}
          </button>
        </div>
      </header>

      <main className="dashboard-main">
        <div className="dashboard-top-row">
          <h1 style={{ fontSize: "inherit", fontWeight: "inherit", margin: 0 }}>{t("title")}</h1>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            {!loading && me && (
              <span style={{ fontSize: 13, color: "var(--muted, #6b7280)" }}>
                {t("projectCount", { count: projects.length, max: getProjectMax(me.subscription_tier) })}
              </span>
            )}
            <button
              className="btn btn-primary"
              onClick={() => navigate("/projects/new")}
            >
              {t("createProject")}
            </button>
          </div>
        </div>

        {/* Global banners */}
        {!loading && me?.trial_ends_at && new Date(me.trial_ends_at) > new Date() && (() => {
          const trialEnd = new Date(me.trial_ends_at);
          const msLeft = trialEnd.getTime() - Date.now();
          const daysLeft = Math.max(1, Math.ceil(msLeft / (1000 * 60 * 60 * 24)));
          const endingSoon = daysLeft <= 3;
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
              <span aria-hidden="true">{endingSoon ? "⚠️" : "🎉"}</span>
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
        {!loading && me && projects.length > 0 && (
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
            {projects.map((p) => {
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
                  onClick={() => navigate(`/projects/${p.id}`)}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); navigate(`/projects/${p.id}`); } }}
                >
                  <h3 className="project-card-name">{p.name}</h3>
                  <div className="project-card-meta">
                    <span className="badge">{p.language.toUpperCase()}</span>
                    <span>{p.question_count} questions</span>
                  </div>
                  <div className="project-card-stats">
                    {p.completed_count > 0 && (
                      <span className="project-stat project-stat-completed">
                        ✓ {t("projectCard.completed", { count: p.completed_count })}
                      </span>
                    )}
                    {p.in_progress_count > 0 && (
                      <span className="project-stat project-stat-inprogress">
                        ● {t("projectCard.inProgress", { count: p.in_progress_count })}
                      </span>
                    )}
                    {p.completed_count === 0 && p.in_progress_count === 0 && (
                      <span className="project-stat project-stat-empty">{t("projectCard.noResponses")}</span>
                    )}
                    {p.analysis_status === "ready" && (
                      <span className="project-stat project-stat-analysis">✦ {t("projectCard.analysisReady")}</span>
                    )}
                    {p.analysis_status === "generating" && (
                      <span className="project-stat project-stat-generating">✦ {t("projectCard.analysing")}</span>
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
                        color: "var(--accent, #4338ca)",
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
                        color: "var(--muted, #6b7280)",
                      }}
                    >
                      {t("projectCard.nudgeStale", {
                        defaultValue:
                          "⏸ No new responses in {{count}} days",
                        count: daysSinceLastResponse!,
                      })}
                    </p>
                  ) : null}

                  <p className="project-card-date">
                    {new Date(p.created_at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}
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
