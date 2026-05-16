import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { StudyDetail, getStudy } from "../api/studies";

/**
 * StudyOverview — `/studies/:id`.
 *
 * The Study is the research workspace. Surveys and Projects are
 * instruments inside it. This page shows:
 *   - Recommended next action chip (server-computed)
 *   - 5-step progress checklist
 *   - Tabs: Overview / Surveys / Interviews / Participants / Report
 *
 * Progress signal comes from /studies/:id which counts completed
 * survey responses + completed interviews. The "segments" and "report"
 * tabs land in Sprints 10/11; for now they show a friendly placeholder.
 */

type Tab = "overview" | "surveys" | "interviews" | "participants" | "report";

const TAB_LABELS: Record<Tab, string> = {
  overview: "Overview",
  surveys: "Surveys",
  interviews: "Interviews",
  participants: "Participants",
  report: "Report",
};

export default function StudyOverview() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = (searchParams.get("tab") as Tab) || "overview";
  const [tab, setTab] = useState<Tab>(initialTab);
  const [study, setStudy] = useState<StudyDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    getStudy(id)
      .then(setStudy)
      .catch(() => setError("Study not found"));
  }, [id]);

  const setTabAndUrl = (next: Tab) => {
    setTab(next);
    const params = new URLSearchParams(searchParams);
    if (next === "overview") params.delete("tab");
    else params.set("tab", next);
    setSearchParams(params, { replace: true });
  };

  if (error) {
    return (
      <div className="quanti-showcase">
        <p className="quanti-showcase__section-meta">{error}</p>
      </div>
    );
  }

  if (!study) {
    return (
      <div className="quanti-showcase">
        <p className="quanti-showcase__section-meta">Loading…</p>
      </div>
    );
  }

  return (
    <div style={{ background: "var(--bg-base)", minHeight: "100vh" }}>
      <header
        style={{
          padding: "var(--space-4) var(--space-6)",
          background: "var(--bg-surface)",
          borderBottom: "1px solid var(--border-default)",
          display: "flex",
          alignItems: "center",
          gap: "var(--space-4)",
        }}
      >
        <button
          type="button"
          className="btn btn-ghost"
          onClick={() => navigate("/studies")}
        >
          ← All studies
        </button>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: "var(--text-eyebrow)",
              fontWeight: 600,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "var(--text-tertiary)",
            }}
          >
            Study workspace
          </div>
          <h1
            style={{
              fontFamily: "var(--font-serif)",
              fontSize: "var(--text-2xl)",
              letterSpacing: "-0.02em",
              margin: 0,
              lineHeight: 1.15,
            }}
          >
            {study.name}
          </h1>
        </div>
      </header>

      <nav
        style={{
          display: "flex",
          gap: "var(--space-4)",
          padding: "0 var(--space-6)",
          background: "var(--bg-surface)",
          borderBottom: "1px solid var(--border-default)",
        }}
        aria-label="Study sections"
      >
        {(["overview", "surveys", "interviews", "participants", "report"] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTabAndUrl(t)}
            style={{
              padding: "var(--space-3) 0",
              background: "transparent",
              border: "none",
              borderBottom: `2px solid ${tab === t ? "var(--brand-500)" : "transparent"}`,
              color: tab === t ? "var(--brand-700)" : "var(--text-secondary)",
              fontWeight: tab === t ? 600 : 500,
              fontFamily: "inherit",
              fontSize: "var(--text-sm)",
              cursor: "pointer",
            }}
          >
            {TAB_LABELS[t]}
          </button>
        ))}
      </nav>

      <main style={{ maxWidth: 1120, margin: "0 auto", padding: "var(--space-6)" }}>
        {tab === "overview" && <OverviewTab study={study} navigate={navigate} />}
        {tab === "surveys" && <SurveysTab study={study} navigate={navigate} />}
        {tab === "interviews" && <InterviewsTab study={study} navigate={navigate} />}
        {tab === "participants" && <ParticipantsTab study={study} />}
        {tab === "report" && <ReportTab />}
      </main>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────
   Tabs
   ──────────────────────────────────────────────────────────────────── */

function OverviewTab({
  study,
  navigate,
}: {
  study: StudyDetail;
  navigate: ReturnType<typeof useNavigate>;
}) {
  const onAct = () => {
    // The recommended action is text — for v1 the chip just routes to the
    // most sensible surface for the current state. Sprint 10 wires the
    // chip to a structured action (e.g. directly open the bridge for a
    // suggested segment).
    if (!study.progress.has_live_survey && study.surveys.length === 0) {
      navigate("/surveys");
      return;
    }
    if (!study.progress.has_live_survey && study.surveys.length > 0) {
      navigate(`/surveys/${study.surveys[0].id}/edit`);
      return;
    }
    if (study.surveys.length > 0) {
      navigate(`/surveys/${study.surveys[0].id}/dashboard`);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-6)" }}>
      {study.recommended_action && (
        <RecommendedActionCard text={study.recommended_action} onClick={onAct} />
      )}
      <ProgressChecklist study={study} />
      <SummaryStrip study={study} />
    </div>
  );
}

function SurveysTab({
  study,
  navigate,
}: {
  study: StudyDetail;
  navigate: ReturnType<typeof useNavigate>;
}) {
  if (study.surveys.length === 0) {
    return <EmptyState message="No surveys yet — head to the Surveys page to create one." ctaLabel="Go to surveys" onAct={() => navigate("/surveys")} />;
  }
  return (
    <div className="quanti-showcase__grid-2">
      {study.surveys.map((s) => (
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
  );
}

function InterviewsTab({
  study,
  navigate,
}: {
  study: StudyDetail;
  navigate: ReturnType<typeof useNavigate>;
}) {
  if (study.projects.length === 0) {
    return (
      <EmptyState
        message="No interview track yet. The Screener Bridge will create one for you when you invite respondents to interviews."
        ctaLabel="Open a survey dashboard"
        onAct={() => {
          if (study.surveys.length > 0) navigate(`/surveys/${study.surveys[0].id}/dashboard`);
          else navigate("/surveys");
        }}
      />
    );
  }
  return (
    <div className="quanti-showcase__grid-2">
      {study.projects.map((p) => (
        <a
          key={p.id}
          href={`/projects/${p.id}`}
          className="chart-card"
          style={{ textDecoration: "none", color: "inherit" }}
        >
          <div className="chart-card__eyebrow">INTERVIEW · {p.language.toUpperCase()}</div>
          <div className="chart-card__takeaway">{p.name}</div>
          <div className="chart-card__footer tabular">
            <span>{p.completed_participant_count} completed</span>
            <span className="chart-card__footer-divider">·</span>
            <span>{p.in_progress_participant_count} in progress</span>
            <span className="chart-card__footer-divider">·</span>
            <span>{p.interview_link_count} link(s)</span>
          </div>
        </a>
      ))}
    </div>
  );
}

function ParticipantsTab({ study }: { study: StudyDetail }) {
  const totalSurveyRespondents = study.surveys.reduce(
    (sum, s) => sum + s.completed_count,
    0,
  );
  const totalInterviewers = study.projects.reduce(
    (sum, p) => sum + p.completed_participant_count,
    0,
  );
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
      <p className="quanti-showcase__section-meta">
        StudyParticipant identity is the join key across instruments — same human across survey
        answers and interview transcripts. The full participant browser ships in Sprint 11
        alongside the mixed-methods report.
      </p>
      <div className="dashboard-strip">
        <div className="dashboard-strip__item">
          <div className="dashboard-strip__label">Survey completers</div>
          <div className="dashboard-strip__value tabular">{totalSurveyRespondents}</div>
        </div>
        <div className="dashboard-strip__item">
          <div className="dashboard-strip__label">Interview completers</div>
          <div className="dashboard-strip__value tabular">{totalInterviewers}</div>
        </div>
        <div className="dashboard-strip__item">
          <div className="dashboard-strip__label">Inference threshold</div>
          <div className="dashboard-strip__value tabular">n≥30</div>
        </div>
      </div>
    </div>
  );
}

function ReportTab() {
  return (
    <div className="chart-card">
      <div className="chart-card__eyebrow">Sprint 11</div>
      <div className="chart-card__takeaway">
        The mixed-methods report lands in Sprint 11 — quantified themes pairing survey signal with interview evidence.
      </div>
      <p style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)", lineHeight: 1.5 }}>
        Each theme will combine survey aggregates (n, %, segment over-index) with interview verbatim and a recommended action (product / marketing / next-research).
        Today this tab is a placeholder; the data flows through `study_analyses` once that sprint ships.
      </p>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────
   Building blocks
   ──────────────────────────────────────────────────────────────────── */

function RecommendedActionCard({ text, onClick }: { text: string; onClick: () => void }) {
  return (
    <div
      style={{
        background: "var(--brand-gradient-soft)",
        border: "1.5px solid var(--brand-300)",
        borderRadius: "var(--radius-lg)",
        padding: "var(--space-5) var(--space-6)",
        display: "flex",
        alignItems: "center",
        gap: "var(--space-4)",
        boxShadow: "var(--shadow-xs)",
      }}
    >
      <div
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          width: 40,
          height: 40,
          borderRadius: "var(--radius-md)",
          background: "var(--brand-500)",
          color: "#fff",
          flex: "0 0 auto",
        }}
        aria-hidden="true"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M13 2 L3 14 L12 14 L11 22 L21 10 L12 10 Z" />
        </svg>
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: "var(--text-eyebrow)",
            fontWeight: 600,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: "var(--brand-700)",
          }}
        >
          Recommended next step
        </div>
        <p
          style={{
            fontSize: "var(--text-md)",
            color: "var(--text-primary)",
            margin: "var(--space-1) 0 0",
            lineHeight: 1.4,
          }}
        >
          {text}
        </p>
      </div>
      <button type="button" className="btn btn-primary" onClick={onClick}>
        Take action →
      </button>
    </div>
  );
}

function ProgressChecklist({ study }: { study: StudyDetail }) {
  const steps: Array<{ label: string; done: boolean; detail?: string }> = [
    {
      label: "Survey published",
      done: study.progress.has_live_survey,
      detail: study.progress.has_live_survey ? "Live" : "Not yet",
    },
    {
      label: "Responses collected",
      done: study.progress.total_completed_responses > 0,
      detail: `${study.progress.total_completed_responses} completed`,
    },
    {
      label: "Inference threshold reached",
      done: study.progress.segments_identified_placeholder,
      detail:
        study.progress.total_completed_responses >= 30
          ? "n≥30 — segment cuts allowed"
          : `${30 - study.progress.total_completed_responses} more responses needed`,
    },
    {
      label: "Interviews completed",
      done: study.progress.interviews_completed > 0,
      detail: `${study.progress.interviews_completed} completed`,
    },
    {
      label: "Mixed-methods report",
      done: study.progress.report_ready_placeholder,
      detail: "Lands in Sprint 11",
    },
  ];

  return (
    <section
      style={{
        background: "var(--bg-surface)",
        border: "1px solid var(--border-default)",
        borderRadius: "var(--radius-md)",
        padding: "var(--space-5) var(--space-6)",
      }}
    >
      <header style={{ marginBottom: "var(--space-4)" }}>
        <div
          style={{
            fontSize: "var(--text-eyebrow)",
            fontWeight: 600,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: "var(--text-tertiary)",
          }}
        >
          Study progress
        </div>
      </header>
      <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
        {steps.map((step, i) => (
          <li
            key={step.label}
            style={{
              display: "grid",
              gridTemplateColumns: "24px 1fr auto",
              gap: "var(--space-3)",
              alignItems: "center",
            }}
          >
            <span
              aria-hidden="true"
              style={{
                width: 22,
                height: 22,
                borderRadius: "50%",
                background: step.done ? "var(--brand-500)" : "var(--bg-sunken)",
                color: step.done ? "#fff" : "var(--text-tertiary)",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "var(--text-xs)",
                fontWeight: 600,
                border: step.done ? "none" : "1px solid var(--border-default)",
              }}
              className="tabular"
            >
              {step.done ? "✓" : i + 1}
            </span>
            <span
              style={{
                fontSize: "var(--text-md)",
                color: step.done ? "var(--text-primary)" : "var(--text-secondary)",
                fontWeight: step.done ? 500 : 400,
              }}
            >
              {step.label}
            </span>
            {step.detail && (
              <span style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)" }} className="tabular">
                {step.detail}
              </span>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}

function SummaryStrip({ study }: { study: StudyDetail }) {
  return (
    <div className="dashboard-strip">
      <div className="dashboard-strip__item">
        <div className="dashboard-strip__label">Surveys</div>
        <div className="dashboard-strip__value tabular">{study.surveys.length}</div>
        <div className="dashboard-strip__delta dashboard-strip__delta--neutral">
          {study.progress.has_live_survey ? "Live" : "Drafts"}
        </div>
      </div>
      <div className="dashboard-strip__item">
        <div className="dashboard-strip__label">Survey responses</div>
        <div className="dashboard-strip__value tabular">{study.progress.total_completed_responses}</div>
        <div className="dashboard-strip__delta dashboard-strip__delta--neutral">
          {study.progress.total_completed_responses >= 30 ? "Inference-grade" : "Building sample"}
        </div>
      </div>
      <div className="dashboard-strip__item">
        <div className="dashboard-strip__label">Interviews</div>
        <div className="dashboard-strip__value tabular">{study.progress.interviews_completed}</div>
        <div className="dashboard-strip__delta dashboard-strip__delta--neutral">
          {study.projects.length} project(s)
        </div>
      </div>
    </div>
  );
}

function EmptyState({
  message,
  ctaLabel,
  onAct,
}: {
  message: string;
  ctaLabel: string;
  onAct: () => void;
}) {
  return (
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
      <p style={{ color: "var(--text-secondary)", fontSize: "var(--text-md)", maxWidth: 540, margin: 0, lineHeight: 1.5 }}>
        {message}
      </p>
      <button type="button" className="btn btn-secondary" onClick={onAct}>
        {ctaLabel}
      </button>
    </div>
  );
}
