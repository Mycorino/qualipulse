import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { StudySummary, listStudies } from "../api/studies";
import { DecisionMemoSection } from "../components/DecisionMemoSection";
import { useToast } from "../components/Toast";
import { QuantiTopBar } from "../components/QuantiTopBar";
import { AccountNudges } from "../components/AccountNudges";
import { NewStudyModal } from "../components/NewStudyModal";
import { NextActionChip } from "../components/NextActionChip";
import { ResearchCopilotPanel } from "../components/ResearchCopilotPanel";
import type { CopilotTarget } from "../api/copilot";
import {
  resolveWorkspaceNextAction,
  resolveStudySummaryAction,
  type NbaActionType,
  type NextAction,
  type StudyNbaSummary,
} from "../copilot/nextAction";
import { detectWorkspaceNudges, dismissNudge, type Nudge } from "../copilot/signals";
import { useNudgeAnnounce } from "../copilot/useNudgeAnnounce";

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

/** Monochrome instrument glyphs (inherit the eyebrow's colour via
 *  currentColor). Replaces emoji, which render inconsistently across
 *  OSes and read casual in a B2B workspace. */
function SurveyGlyph() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <rect x="1.5" y="7" width="2.5" height="5.5" rx="0.5" fill="currentColor" />
      <rect x="5.75" y="4" width="2.5" height="8.5" rx="0.5" fill="currentColor" />
      <rect x="10" y="1.5" width="2.5" height="11" rx="0.5" fill="currentColor" />
    </svg>
  );
}

function MicGlyph() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
      <rect x="5" y="1.5" width="4" height="7" rx="2" fill="currentColor" />
      <path
        d="M3 6.5a4 4 0 0 0 8 0M7 10.5v2M5 12.5h4"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function MixGlyph({ mix }: { mix: InstrumentMix }) {
  if (mix === "empty") {
    return (
      <span aria-hidden="true" style={{ opacity: 0.5 }}>
        ·
      </span>
    );
  }
  return (
    <span
      aria-hidden="true"
      style={{ display: "inline-flex", alignItems: "center", gap: "3px" }}
    >
      {mix !== "interview" && <SurveyGlyph />}
      {mix !== "survey" && <MicGlyph />}
    </span>
  );
}

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

/**
 * Minimal Copilot target for the studies-list surface. There's no workspace
 * chat backend — the copilot here only explains and points the user at the
 * real "+ New study" action, so chat is disabled and every method is a stub.
 */
const WORKSPACE_COPILOT_TARGET: CopilotTarget = {
  id: "workspace",
  runTurn: async () => ({ reply: "", proposed_actions: [], memory_updated: false }),
  loadConversation: async () => ({ thread: [], version: 0 }),
  saveConversation: async (_thread, version) => version,
  applyAction: async () => {},
};

/** Short, action-oriented footer status per study card → i18n key suffix. */
const CARD_STATUS_KEY: Partial<Record<NbaActionType, string>> = {
  set_up_study: "needsInstrument",
  analyze_study: "readyToAnalyse",
  collect_study: "collecting",
  done: "reportReady",
};

export default function StudyList() {
  const { t } = useTranslation("dashboard");
  const [studies, setStudies] = useState<StudySummary[] | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [nudges, setNudges] = useState<Nudge[]>([]);
  const { toast } = useToast();
  const navigate = useNavigate();
  const announce = useNudgeAnnounce(nudges);

  useEffect(() => {
    listStudies()
      .then(setStudies)
      .catch(() => toast(t("studyList.loadError"), "error"));
  }, [toast, t]);

  // Detect studies that gained a report since the researcher's last visit.
  useEffect(() => {
    if (!studies) return;
    setNudges(
      detectWorkspaceNudges(
        studies.map((s) => ({ id: s.id, name: s.name, hasReport: s.has_report })),
      ),
    );
  }, [studies]);

  // The copilot's portfolio-triage suggestion — which study needs you.
  const runWorkspaceAction = (a: NextAction) => {
    if (a.actionType === "start_study") setPickerOpen(true);
    else if (a.targetId) navigate(`/studies/${a.targetId}`);
  };

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-base)" }}>
      <QuantiTopBar crumbs={[{ label: t("studyList.crumb") }]} />
      <div
        className="quanti-showcase quanti-showcase--list"
        style={{ padding: "var(--space-8) var(--report-canvas-pad-x)" }}
      >
        <AccountNudges />

        <header className="quanti-showcase__hero quanti-showcase__hero--bar">
          <div className="quanti-showcase__hero-text">
            <div className="quanti-showcase__eyebrow">{t("studyList.eyebrow")}</div>
            <h1 className="quanti-showcase__title">{t("studyList.title")}</h1>
            <p className="quanti-showcase__subtitle">{t("studyList.subtitle")}</p>
          </div>
          <button type="button" className="btn btn-primary" onClick={() => setPickerOpen(true)}>
            {t("studyList.newStudy")}
          </button>
        </header>

        <div className="sr-only" aria-live="polite" role="status">
          {announce}
        </div>

        {studies && studies.length > 0 && (() => {
          const nba = resolveWorkspaceNextAction(studies.map(toNbaSummary));
          // When nothing needs the researcher (no actionable NBA, no fresh
          // nudges) the strip is purely reassurance — demote it to a quiet
          // inline line so it doesn't out-shout the actual studies below.
          const quiet = nba.kind === "done" && nudges.length === 0;
          return (
            <div className={`workspace-nba${quiet ? " workspace-nba--quiet" : ""}`}>
              <span className="workspace-nba__eyebrow">{t("studyList.copilotEyebrow")}</span>
              {nudges.map((n) => (
                <div
                  key={n.id}
                  className={`copilot-nudge copilot-nudge--${n.tone}`}
                >
                  <span className="copilot-nudge__text">{n.text}</span>
                  <button
                    type="button"
                    className="copilot-nudge__dismiss"
                    onClick={() => {
                      dismissNudge(n.id);
                      setNudges((ns) => ns.filter((x) => x.id !== n.id));
                    }}
                    aria-label={t("studyList.dismissUpdate")}
                  >
                    ✕
                  </button>
                </div>
              ))}
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
            <p className="quanti-showcase__section-meta">{t("studyList.loading")}</p>
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
                {t("studyList.emptyText")}
              </p>
              <button type="button" className="btn btn-primary" onClick={() => setPickerOpen(true)}>
                {t("studyList.newStudy")}
              </button>
            </div>
          ) : (
            <div className="quanti-showcase__grid-2">
              {studies.map((s) => {
                const mix = instrumentMix(s);
                const action = resolveStudySummaryAction(toNbaSummary(s));
                const needsAttention = action.kind === "do";
                return (
                  <a
                    key={s.id}
                    href={`/studies/${s.id}`}
                    className={`chart-card${needsAttention ? " chart-card--needs-attention" : ""}`}
                    style={{ textDecoration: "none", color: "inherit", cursor: "pointer" }}
                  >
                    <div
                      className="chart-card__eyebrow"
                      style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}
                    >
                      <MixGlyph mix={mix} />
                      <span>{t(`studyList.studyType.${mix}`)}</span>
                    </div>
                    <div className="chart-card__takeaway">{s.name}</div>
                    <div className="chart-card__footer tabular">
                      <span>{t("studyList.surveyCount", { count: s.survey_count })}</span>
                      <span className="chart-card__footer-divider">·</span>
                      <span>{t("studyList.interviewCount", { count: s.project_count })}</span>
                      <span className="chart-card__footer-divider">·</span>
                      <span className={needsAttention ? "study-card__status--attention" : undefined}>
                        {needsAttention ? "✦ " : ""}
                        {t(`studyList.status.${CARD_STATUS_KEY[action.actionType] ?? "inProgress"}`)}
                      </span>
                    </div>
                  </a>
                );
              })}
            </div>
          )}
        </section>

        {studies !== null && <DecisionMemoSection studies={studies} />}
      </div>

      {pickerOpen && <NewStudyModal onClose={() => setPickerOpen(false)} />}

      {/* First-run handhold: only on the empty studies screen. The Copilot
          auto-opens once to explain research and point at "+ New study".
          There's no workspace chat backend, so we don't mount it once the
          user has studies — the workspace NBA strip covers guidance there. */}
      {studies !== null && studies.length === 0 && (
        <ResearchCopilotPanel
          target={WORKSPACE_COPILOT_TARGET}
          onApplied={() => {}}
          mission={t("studyList.copilotMission")}
          disableInput
          autoOpen
          intro={{
            lead: t("copilot.workspace.introLead"),
            ctaLabel: t("copilot.workspace.createFirst"),
            onCta: () => setPickerOpen(true),
          }}
        />
      )}
    </div>
  );
}
