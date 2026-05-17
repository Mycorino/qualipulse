import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { StudySummary, listStudies } from "../api/studies";
import { useToast } from "../components/Toast";
import { QuantiTopBar } from "../components/QuantiTopBar";

/**
 * StudyList — `/studies`.
 *
 * Index of the workspace's research efforts. Each card is a Study with
 * counts. Studies are auto-created on first survey or project creation
 * (Decision 8), so this page is read-only — no "create Study" CTA. To
 * start a new study, the researcher creates a Survey (or eventually a
 * Project), which auto-creates a Study with the same name.
 *
 * Sprint 10.5+ will probably make this page the post-login landing for
 * accounts with ≥1 Study; today it's reachable via direct URL and from
 * "View as Study" links on the existing Surveys/Projects pages.
 */
export default function StudyList() {
  const [studies, setStudies] = useState<StudySummary[] | null>(null);
  const navigate = useNavigate();
  const { toast } = useToast();

  useEffect(() => {
    listStudies()
      .then(setStudies)
      .catch(() => toast("Failed to load studies", "error"));
  }, [toast]);

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-base)" }}>
      <QuantiTopBar crumbs={[{ label: "Studies" }]} />
      <div className="quanti-showcase" style={{ padding: "var(--space-10) var(--report-canvas-pad-x)" }}>
      <header className="quanti-showcase__hero">
        <div className="quanti-showcase__eyebrow">Research workspace</div>
        <h1 className="quanti-showcase__title">Your studies</h1>
        <p className="quanti-showcase__subtitle">
          A Study is one research effort — a screener survey, the interviews it leads to, and the
          validation that follows. Create a Survey or Project from the existing pages and a Study
          forms around it automatically.
        </p>
      </header>

      <section className="quanti-showcase__section">
        {studies === null ? (
          <p className="quanti-showcase__section-meta">Loading…</p>
        ) : studies.length === 0 ? (
          <div
            style={{
              background: "var(--bg-surface)",
              border: "1px dashed var(--border-default)",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-8)",
              textAlign: "center",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: "var(--space-4)",
            }}
          >
            <p style={{ color: "var(--text-secondary)", maxWidth: 520, margin: 0, lineHeight: 1.5 }}>
              No studies yet. Create your first survey from a template — a Study will form around it
              and you'll find it here.
            </p>
            <button type="button" className="btn btn-primary" onClick={() => navigate("/surveys")}>
              Go to surveys
            </button>
          </div>
        ) : (
          <div className="quanti-showcase__grid-2">
            {studies.map((s) => (
              <a
                key={s.id}
                href={`/studies/${s.id}`}
                className="chart-card"
                style={{ textDecoration: "none", color: "inherit", cursor: "pointer" }}
              >
                <div className="chart-card__eyebrow">
                  STUDY · {new Date(s.created_at).toLocaleDateString(undefined, { month: "short", year: "numeric" })}
                </div>
                <div className="chart-card__takeaway">{s.name}</div>
                <div className="chart-card__footer tabular">
                  <span>
                    {s.survey_count} survey{s.survey_count === 1 ? "" : "s"}
                  </span>
                  <span className="chart-card__footer-divider">·</span>
                  <span>
                    {s.project_count} interview{s.project_count === 1 ? "" : "s"}
                  </span>
                  <span className="chart-card__footer-divider">·</span>
                  <span>
                    {s.participant_count} participant{s.participant_count === 1 ? "" : "s"}
                  </span>
                </div>
              </a>
            ))}
          </div>
        )}
      </section>
      </div>
    </div>
  );
}
