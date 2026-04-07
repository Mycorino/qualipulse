import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { SkeletonCard } from "../components/Skeleton";
import {
  listProjects,
  unarchiveProject,
  ProjectListItem,
} from "../api/projects";
import { getMe } from "../api/auth";
import type { CompanyResponse } from "../api/auth";

export default function Dashboard() {
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [archivedProjects, setArchivedProjects] = useState<ProjectListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showArchive, setShowArchive] = useState(false);
  const [archiveLoading, setArchiveLoading] = useState(false);
  const [restoringId, setRestoringId] = useState<string | null>(null);
  const [me, setMe] = useState<CompanyResponse | null>(null);
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
    } catch {
      // handled by interceptor
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

  return (
    <div className="dashboard-layout">
      <header className="dashboard-header">
        <h1 className="logo">QualiPulse</h1>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button className="btn btn-ghost" onClick={() => navigate("/account")}>
            Account & Billing
          </button>
          <button className="btn btn-ghost" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>

      <main className="dashboard-main">
        <div className="dashboard-top-row">
          <h2>Projects</h2>
          <button
            className="btn btn-primary"
            onClick={() => navigate("/projects/new")}
          >
            + Create Project
          </button>
        </div>

        {/* Global banners — always visible regardless of project count */}
        {!loading && me?.trial_ends_at && (me?.subscription_tier === "solo" || me?.subscription_tier === "free") && (
          <div className="gs-trial-banner" style={{ marginBottom: 16 }}>
            <span>🎉</span>
            <div>
              <strong>14-day trial active</strong> — You have full Team features until {new Date(me.trial_ends_at).toLocaleDateString()}.
              {" "}<button className="btn-inline" onClick={() => navigate("/account")}>View plans</button>
            </div>
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
              <h2 style={{ color: "#ffffff" }}>Welcome{me?.name ? `, ${me.name}` : ""}! Let's set up your first study.</h2>
              <p>Follow these steps to run your first AI-powered interview.</p>
            </div>

            <div className="getting-started-steps">
              <div className="gs-step">
                <div className="gs-step-icon gs-step-active">1</div>
                <div className="gs-step-content">
                  <h3>Create a project</h3>
                  <p>Describe your research goals and let AI build your interview guide.</p>
                  <button className="btn btn-primary btn-sm" onClick={() => navigate("/projects/new")}>
                    Create project &rarr;
                  </button>
                </div>
              </div>

              <div className="gs-step">
                <div className="gs-step-icon">2</div>
                <div className="gs-step-content">
                  <h3>Share your interview link</h3>
                  <p>Generate a link and send it to participants. They'll complete the interview in their browser.</p>
                </div>
              </div>

              <div className="gs-step">
                <div className="gs-step-icon">3</div>
                <div className="gs-step-content">
                  <h3>Review AI analysis</h3>
                  <p>Once you have responses, trigger an AI analysis to get themes, quotes, and recommendations.</p>
                </div>
              </div>
            </div>

            {me && !me.email_verified && (
              <div className="gs-verify-banner">
                <span>&#128231;</span>
                <div>
                  <strong>Verify your email</strong>
                  <p>Check your inbox for a verification link to unlock all features.</p>
                </div>
              </div>
            )}

          </div>
        ) : (
          <>
          {me && !me.email_verified && (
            <div className="gs-verify-banner" style={{ marginBottom: 16 }}>
              <span>&#128231;</span>
              <div>
                <strong>Verify your email</strong> — Check your inbox for a verification link.
              </div>
            </div>
          )}
          <div className="project-grid">
            {projects.map((p) => (
              <div
                key={p.id}
                className="project-card"
                onClick={() => navigate(`/projects/${p.id}`)}
              >
                <h3 className="project-card-name">{p.name}</h3>
                <div className="project-card-meta">
                  <span className="badge">{p.language.toUpperCase()}</span>
                  <span>{p.question_count} questions</span>
                </div>
                <div className="project-card-stats">
                  {p.completed_count > 0 && (
                    <span className="project-stat project-stat-completed">
                      ✓ {p.completed_count} completed
                    </span>
                  )}
                  {p.in_progress_count > 0 && (
                    <span className="project-stat project-stat-inprogress">
                      ● {p.in_progress_count} in progress
                    </span>
                  )}
                  {p.completed_count === 0 && p.in_progress_count === 0 && (
                    <span className="project-stat project-stat-empty">No responses yet</span>
                  )}
                  {p.analysis_status === "ready" && (
                    <span className="project-stat project-stat-analysis">✦ Analysis ready</span>
                  )}
                  {p.analysis_status === "generating" && (
                    <span className="project-stat project-stat-generating">✦ Analysing…</span>
                  )}
                </div>
                <p className="project-card-date">
                  {new Date(p.created_at).toLocaleDateString()}
                </p>
              </div>
            ))}
          </div>
          </>
        )}

        {/* ── Archive section ─────────────────────────────────────── */}
        <div className="archive-section">
          <button className="archive-toggle" onClick={handleToggleArchive}>
            <span className="archive-toggle-icon">{showArchive ? "▾" : "▸"}</span>
            <span>Archived projects</span>
            {archivedProjects.length > 0 && (
              <span className="archive-count">{archivedProjects.length}</span>
            )}
          </button>

          {showArchive && (
            <div className="archive-list">
              {archiveLoading ? (
                <p className="archive-empty">Loading…</p>
              ) : archivedProjects.length === 0 ? (
                <p className="archive-empty">No archived projects.</p>
              ) : (
                archivedProjects.map((p) => (
                  <div key={p.id} className="archive-row">
                    <div className="archive-row-info">
                      <span className="archive-row-name">{p.name}</span>
                      <span className="archive-row-meta">
                        <span className="badge badge--sm">{p.language.toUpperCase()}</span>
                        <span>
                          Archived {p.archived_at ? new Date(p.archived_at).toLocaleDateString() : ""}
                        </span>
                        {p.completed_count > 0 && (
                          <span>· {p.completed_count} completed</span>
                        )}
                      </span>
                    </div>
                    <div className="archive-row-actions">
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={(e) => handleRestore(e, p.id)}
                        disabled={restoringId === p.id}
                      >
                        {restoringId === p.id ? "Restoring…" : "↩ Restore"}
                      </button>
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/projects/${p.id}`);
                        }}
                      >
                        View
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
