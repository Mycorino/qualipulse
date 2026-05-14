import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Survey, createSurvey, listSurveys } from "../api/surveys";
import { useToast } from "../components/Toast";

/**
 * SurveyList — minimal listing + create flow for the quanti track.
 *
 * Linked from the dashboard. New surveys auto-create an implicit Study
 * (per Decision 8 in the roadmap) so researchers never see "create a Study
 * first." The list is workspace-scoped via the existing auth dependency.
 */
export default function SurveyList() {
  const [surveys, setSurveys] = useState<Survey[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const navigate = useNavigate();
  const { toast } = useToast();

  useEffect(() => {
    listSurveys()
      .then(setSurveys)
      .catch(() => toast("Failed to load surveys", "error"));
  }, [toast]);

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      setCreating(true);
      const survey = await createSurvey({ name: name.trim() });
      navigate(`/surveys/${survey.id}/edit`);
    } catch {
      toast("Could not create survey", "error");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="quanti-showcase" style={{ padding: "var(--space-10) var(--report-canvas-pad-x)" }}>
      <header className="quanti-showcase__hero">
        <div className="quanti-showcase__eyebrow">Quanti · Surveys</div>
        <h1 className="quanti-showcase__title">Your surveys</h1>
        <p className="quanti-showcase__subtitle">
          Build a screener, share a link, or validate themes from a finished interview round.
          New surveys auto-create the parent Study; you'll see it in the mixed-methods report once
          the first response lands.
        </p>
      </header>

      <section className="quanti-showcase__section">
        <form onSubmit={onCreate} style={{ display: "flex", gap: "var(--space-3)", maxWidth: 560 }}>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Name your survey…"
            style={{
              flex: 1,
              padding: "10px 14px",
              fontSize: "var(--text-md)",
              border: "1px solid var(--border-default)",
              borderRadius: "var(--radius-md)",
              background: "var(--bg-surface)",
            }}
          />
          <button type="submit" className="btn btn-primary" disabled={creating || !name.trim()}>
            {creating ? "Creating…" : "Create survey"}
          </button>
        </form>
      </section>

      <section className="quanti-showcase__section">
        <h2 className="quanti-showcase__section-title">All surveys</h2>
        {surveys === null ? (
          <p className="quanti-showcase__section-meta">Loading…</p>
        ) : surveys.length === 0 ? (
          <p className="quanti-showcase__section-meta">No surveys yet. Create your first one above.</p>
        ) : (
          <div className="quanti-showcase__grid-2">
            {surveys.map((s) => (
              <a
                key={s.id}
                href={`/surveys/${s.id}/edit`}
                className="chart-card"
                style={{ textDecoration: "none", color: "inherit", cursor: "pointer" }}
              >
                <div className="chart-card__eyebrow">
                  {s.role.toUpperCase()} · {s.status.toUpperCase()}
                </div>
                <div className="chart-card__takeaway">{s.name}</div>
                <div className="chart-card__footer tabular">
                  <span>{s.question_count} questions</span>
                  <span className="chart-card__footer-divider">·</span>
                  <span>{s.completed_count} completed</span>
                  <span className="chart-card__footer-divider">·</span>
                  <span>{s.response_count} total</span>
                </div>
              </a>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
