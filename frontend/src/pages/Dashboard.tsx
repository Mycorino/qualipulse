import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../hooks/useAuth";
import { SkeletonCard } from "../components/Skeleton";
import {
  listProjects,
  unarchiveProject,
  ProjectListItem,
} from "../api/projects";
import { getMe, resendVerification } from "../api/auth";
import type { CompanyResponse } from "../api/auth";
import LanguageSwitcher from "../components/LanguageSwitcher";

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
        {!loading && me?.trial_ends_at && new Date(me.trial_ends_at) > new Date() && (
          <div className="gs-trial-banner" style={{ marginBottom: 16 }}>
            <span>🎉</span>
            <div>
              <strong>{t("trialBanner.title")}</strong> — {t("trialBanner.desc", {
                date: new Date(me.trial_ends_at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })
              })}
              {" "}<button className="btn-inline" onClick={() => navigate("/account")}>{t("trialBanner.viewPlans")}</button>
            </div>
          </div>
        )}

        {loadError && (
          <div className="error-banner" style={{ marginBottom: 16 }}>
            {t("loadError")}
          </div>
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
                  <button className="btn btn-primary btn-sm" onClick={() => navigate("/projects/new")}>
                    {t("gettingStarted.step1Cta")}
                  </button>
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
            {projects.map((p) => (
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
                <p className="project-card-date">
                  {new Date(p.created_at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}
                </p>
              </div>
            ))}
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
