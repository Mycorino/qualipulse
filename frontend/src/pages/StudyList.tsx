import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { StudySummary, listStudies } from "../api/studies";
import { useToast } from "../components/Toast";
import { QuantiTopBar } from "../components/QuantiTopBar";
import { AccountNudges } from "../components/AccountNudges";
import { NewStudyModal } from "../components/NewStudyModal";
import { NextActionChip } from "../components/NextActionChip";
import {
  resolveWorkspaceNextAction,
  type NextAction,
  type StudyNbaSummary,
} from "../copilot/nextAction";

/**
 * StudyList — `/studies`, and the post-login home.
 *
 * Sprint 17: this page replaced the old project-grid dashboard. One
 * list of all research efforts, each card tagged with its instrument
 * mix (survey-only / interview-only / hybrid) so the angle is
 * glanceable. A legacy interview project surfaces here as an
 * interview-only Study card — no migration the user notices.
 *
 * Studies are auto-created on first survey/project creation (Decision 8),
 * so there's no "create Study" CTA — the angle picker (Sprint 18) will
 * be the deliberate "+ New study" entry point.
 */

type InstrumentMix = "survey" | "interview" | "hybrid" | "empty";

function instrumentMix(s: StudySummary): InstrumentMix {
  const hasSurvey = s.survey_count > 0;
  const hasInterview = s.project_count > 0;
  if (hasSurvey && hasInterview) return "hybrid";
  if (hasSurvey) return "survey";
  if (hasInterview) return "interview";
  return "empty";
}

const MIX_LABEL: Record<InstrumentMix, string> = {
  survey: "Survey",
  interview: "Interview",
  hybrid: "Hybrid",
  empty: "Empty",
};

const MIX_ICON: Record<InstrumentMix, string> = {
  survey: "📊",
  interview: "🎙",
  hybrid: "📊🎙",
  empty: "·",
};

function toNbaSummary(s: StudySummary): StudyNbaSummary {
  return {
    id: s.id,
    name: s.name,
    surveyCount: s.survey_count,
    projectCount: s.project_count,
    completedResponseCount: s.completed_response_count,
    completedInterviewCount: s.completed_interview_count,
    hasReport: s.has_report,
  };
}

function studyStatusLine(s: StudySummary): string {
  if (s.has_report) return "Report ready";
  if (s.completed_interview_count > 0) {
    return `${s.completed_interview_count} interview${s.completed_interview_count === 1 ? "" : "s"} done`;
  }
  if (s.completed_response_count > 0) {
    return `${s.completed_response_count} response${s.completed_response_count === 1 ? "" : "s"} in`;
  }
  return "Collecting — no responses yet";
}

export default function StudyList() {
  const [studies, setStudies] = useState<StudySummary[] | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const { toast } = useToast();
  const navigate = useNavigate();

  useEffect(() => {
    listStudies()
      .then(setStudies)
      .catch(() => toast("Failed to load studies", "error"));
  }, [toast]);

  // The copilot's portfolio-triage suggestion — which study needs you.
  const runWorkspaceAction = (a: NextAction) => {
    if (a.actionType === "start_study") setPickerOpen(true);
    else if (a.targetId) navigate(`/studies/${a.targetId}`);
  };

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-base)" }}>
      <QuantiTopBar crumbs={[{ label: "Studies" }]} />
      <div
        className="quanti-showcase"
        style={{ padding: "var(--space-8) var(--report-canvas-pad-x)" }}
      >
        <AccountNudges />

        <header
          className="quanti-showcase__hero"
          style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: "var(--space-4)", flexWrap: "wrap" }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="quanti-showcase__eyebrow">Research workspace</div>
            <h1 className="quanti-showcase__title">Your studies</h1>
            <p className="quanti-showcase__subtitle">
              A Study is one research effort. It can be a survey, an interview round, or both — the
              instrument mix is shown on each card. Quanti, quali, hybrid: one home for all of it.
            </p>
          </div>
          <button type="button" className="btn btn-primary" onClick={() => setPickerOpen(true)}>
            + New study
          </button>
        </header>

        {studies && studies.length > 0 && (() => {
          const nba = resolveWorkspaceNextAction(studies.map(toNbaSummary));
          return (
            <div className="workspace-nba">
              <span className="workspace-nba__eyebrow">✦ Research Copilot</span>
              <NextActionChip
                action={nba}
                variant="inline"
                onRun={() => runWorkspaceAction(nba)}
              />
            </div>
          );
        })()}

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
                No studies yet. Start one — survey, interviews, or both. A Study forms around your
                first instrument and shows up here.
              </p>
              <button type="button" className="btn btn-primary" onClick={() => setPickerOpen(true)}>
                + New study
              </button>
            </div>
          ) : (
            <div className="quanti-showcase__grid-2">
              {studies.map((s) => {
                const mix = instrumentMix(s);
                return (
                  <a
                    key={s.id}
                    href={`/studies/${s.id}`}
                    className="chart-card"
                    style={{ textDecoration: "none", color: "inherit", cursor: "pointer" }}
                  >
                    <div
                      className="chart-card__eyebrow"
                      style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}
                    >
                      <span aria-hidden="true">{MIX_ICON[mix]}</span>
                      <span>{MIX_LABEL[mix].toUpperCase()} STUDY</span>
                    </div>
                    <div className="chart-card__takeaway">{s.name}</div>
                    <div className="chart-card__footer tabular">
                      <span>{s.survey_count} survey{s.survey_count === 1 ? "" : "s"}</span>
                      <span className="chart-card__footer-divider">·</span>
                      <span>{s.project_count} interview{s.project_count === 1 ? "" : "s"}</span>
                      <span className="chart-card__footer-divider">·</span>
                      <span>{studyStatusLine(s)}</span>
                    </div>
                  </a>
                );
              })}
            </div>
          )}
        </section>
      </div>

      {pickerOpen && <NewStudyModal onClose={() => setPickerOpen(false)} />}
    </div>
  );
}
