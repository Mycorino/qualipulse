import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { DemoCallout, getDemoTourPhase, isDemoTourArmed } from "../components/DemoTour";

import {
  StudyAnalysis,
  StudyDetail,
  ValidationSummary,
  createValidationSurvey,
  fetchStudyReportHtml,
  getLatestAnalysis,
  getStudy,
  getValidationSummary,
  triggerAnalysis,
} from "../api/studies";
import { createSurvey } from "../api/surveys";
import { createProject } from "../api/projects";
import { SurveyQuotaBanner } from "../components/SurveyQuotaBanner";
import { useToast } from "../components/Toast";
import { HubShell } from "../components/HubShell";
import { openHtmlDocument } from "../utils/openHtmlDocument";

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
 * survey responses + completed interviews.
 */

type Tab = "overview" | "instruments" | "participants" | "report";

/** Legacy deep links used separate surveys/interviews tabs — fold them in. */
function normalizeTab(raw: string | null): Tab {
  if (raw === "surveys" || raw === "interviews") return "instruments";
  if (raw === "instruments" || raw === "participants" || raw === "report")
    return raw;
  return "overview";
}

export default function StudyOverview() {
  const { t, i18n } = useTranslation(["study", "dashboard"]);
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = normalizeTab(searchParams.get("tab"));
  const [tab, setTab] = useState<Tab>(initialTab);
  const [study, setStudy] = useState<StudyDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tourDismissed, setTourDismissed] = useState(false);
  const { toast } = useToast();

  /** Create a survey inside THIS study and open its editor. Surveys live
   *  in their Study — no detour through a separate global surveys page. */
  const handleCreateSurvey = async () => {
    if (!study) return;
    try {
      const survey = await createSurvey({
        name: t("overview.untitledSurvey"),
        study_id: study.id,
      });
      navigate(`/surveys/${survey.id}/edit`);
    } catch {
      toast(t("overview.toast.surveyCreateFailed"), "error");
    }
  };

  /** Create an interview round inside THIS study and drop into the
   *  workspace — the copilot drafts the objective + guide there. */
  const handleCreateInterview = async () => {
    if (!study) return;
    try {
      const project = await createProject({
        // Participant-facing content follows the researcher's UI language
        // by default — the copilot drafts the guide in project.language.
        name: t("overview.untitledInterview"),
        language: i18n.language?.startsWith("fr") ? "fr" : "en",
        study_id: study.id,
        questions: [],
      });
      navigate(`/projects/${project.id}?tab=setup`);
    } catch {
      toast(t("overview.toast.interviewCreateFailed"), "error");
    }
  };

  useEffect(() => {
    if (!id) return;
    getStudy(id)
      .then(setStudy)
      .catch(() => setError(t("overview.studyNotFound")));
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
      <HubShell active="studies">
        <div className="quanti-showcase">
          <p className="quanti-showcase__section-meta">{error}</p>
        </div>
      </HubShell>
    );
  }

  if (!study) {
    return (
      <HubShell active="studies">
        <div className="quanti-showcase">
          <p className="quanti-showcase__section-meta">{t("overview.loading")}</p>
        </div>
      </HubShell>
    );
  }

  return (
    <HubShell
      active="studies"
      crumbs={[
        { label: t("overview.studiesCrumb"), to: "/studies" },
        { label: study.name },
      ]}
    >
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
            {t("overview.studyWorkspace")}
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
          alignItems: "center",
          justifyContent: "space-between",
          gap: "var(--space-4)",
          padding: "0 var(--space-6)",
          background: "var(--bg-surface)",
          borderBottom: "1px solid var(--border-default)",
        }}
        aria-label={t("overview.sectionsNav")}
      >
        <div style={{ display: "flex", gap: "var(--space-4)" }}>
          {(["overview", "instruments", "participants", "report"] as Tab[]).map((tabKey) => (
            <button
              key={tabKey}
              type="button"
              data-tour={tabKey === "instruments" ? "study-tab-instruments" : undefined}
              onClick={() => setTabAndUrl(tabKey)}
              style={{
                padding: "var(--space-3) 0",
                background: "transparent",
                border: "none",
                borderBottom: `2px solid ${tab === tabKey ? "var(--brand-500)" : "transparent"}`,
                color: tab === tabKey ? "var(--brand-700)" : "var(--text-secondary)",
                fontWeight: tab === tabKey ? 600 : 500,
                fontFamily: "inherit",
                fontSize: "var(--text-sm)",
                cursor: "pointer",
              }}
            >
              {t(`overview.tabs.${tabKey}`)}
            </button>
          ))}
        </div>
        {/* Right-aligned instrument summary — balances the rule and gives the
            study an at-a-glance scope on every tab. */}
        <span
          className="tabular study-tabs__summary"
          style={{
            fontSize: "var(--text-xs)",
            color: "var(--text-tertiary)",
            whiteSpace: "nowrap",
          }}
        >
          {t("dashboard:studyList.surveyCount", { count: study.surveys.length })}
          <span style={{ margin: "0 var(--space-2)", color: "var(--border-strong)" }}>·</span>
          {t("dashboard:studyList.interviewCount", { count: study.projects.length })}
        </span>
      </nav>

      <main style={{ maxWidth: 1120, margin: "0 auto", padding: "var(--space-6)" }}>
        {/* Demo studies are a guided tour, not quota-consuming work — keep
            billing chrome out of them. */}
        {!study.is_demo && <SurveyQuotaBanner />}
        {tab === "overview" && (
          <OverviewTab
            study={study}
            navigate={navigate}
            onCreateSurvey={handleCreateSurvey}
            goToTab={setTabAndUrl}
          />
        )}
        {tab === "instruments" && (
          <InstrumentsTab
            study={study}
            onCreateSurvey={handleCreateSurvey}
            onCreateInterview={handleCreateInterview}
          />
        )}
        {tab === "participants" && <ParticipantsTab study={study} />}
        {tab === "report" && <ReportTab study={study} />}
      </main>

      {/* Demo-tour waypoints through the workspace: first point at the
          Instruments tab, then at the interview round — always the user's
          own click, never a programmatic jump. */}
      {study.is_demo && isDemoTourArmed() && getDemoTourPhase() === "study" && !tourDismissed && (
        <DemoCallout
          selector={
            tab === "instruments"
              ? '[data-tour="workspace-interview-round"]'
              : '[data-tour="study-tab-instruments"]'
          }
          eyebrow={t("overview.tour.eyebrow")}
          title={t(
            tab === "instruments"
              ? "overview.tour.interviewRound_title"
              : "overview.tour.instrumentsTab_title",
          )}
          body={t(
            tab === "instruments"
              ? "overview.tour.interviewRound_body"
              : "overview.tour.instrumentsTab_body",
          )}
          clickHint={t(
            tab === "instruments"
              ? "overview.tour.interviewRound_clickHint"
              : "overview.tour.instrumentsTab_clickHint",
          )}
          skipLabel={t("overview.tour.skip")}
          onSkip={() => setTourDismissed(true)}
        />
      )}
    </div>
    </HubShell>
  );
}

/* ────────────────────────────────────────────────────────────────────
   Tabs
   ──────────────────────────────────────────────────────────────────── */

/** Recommendation keys this client knows how to localize + route. */
const KNOWN_ACTION_KEYS = [
  "create_survey",
  "publish_survey",
  "share_survey_link",
  "collect_more_responses",
  "open_dashboard_invite",
  "invite_interviews",
  "collect_more_interviews",
  "generate_report",
  "open_report",
] as const;

function OverviewTab({
  study,
  navigate,
  onCreateSurvey,
  goToTab,
}: {
  study: StudyDetail;
  navigate: ReturnType<typeof useNavigate>;
  onCreateSurvey: () => void;
  goToTab: (tab: Tab) => void;
}) {
  const { t } = useTranslation("study");

  // Prefer the structured key so the prompt renders in the UI language;
  // the server's `recommended_action` string is the English fallback for
  // keys this client doesn't know yet.
  const actionKey =
    study.recommended_action_key &&
    (KNOWN_ACTION_KEYS as readonly string[]).includes(study.recommended_action_key)
      ? study.recommended_action_key
      : null;
  const actionText = actionKey
    ? t(
        `overview.recommendedAction.actions.${actionKey}`,
        study.recommended_action_params ?? {},
      )
    : study.recommended_action;

  const onAct = () => {
    const firstSurvey = study.surveys[0];
    const liveSurvey =
      study.surveys.find((s) => s.status === "live") ?? firstSurvey;
    switch (actionKey) {
      case "create_survey":
        onCreateSurvey();
        return;
      case "publish_survey":
      case "share_survey_link":
        // Publishing and the shareable link both live in the builder.
        if (firstSurvey) navigate(`/surveys/${firstSurvey.id}/edit`);
        else onCreateSurvey();
        return;
      case "collect_more_responses":
      case "open_dashboard_invite":
      case "invite_interviews":
        // Collection progress + the Screener Bridge live on the dashboard.
        if (liveSurvey) navigate(`/surveys/${liveSurvey.id}/dashboard`);
        return;
      case "collect_more_interviews":
        goToTab("instruments");
        return;
      case "generate_report":
      case "open_report":
        goToTab("report");
        return;
    }
    // Unknown key (older client vs newer server) — legacy heuristic.
    if (!study.progress.has_live_survey && study.surveys.length === 0) {
      onCreateSurvey();
    } else if (!study.progress.has_live_survey && firstSurvey) {
      navigate(`/surveys/${firstSurvey.id}/edit`);
    } else if (firstSurvey) {
      navigate(`/surveys/${firstSurvey.id}/dashboard`);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-6)" }}>
      {actionText && (
        <RecommendedActionCard text={actionText} onClick={onAct} />
      )}
      <ProgressChecklist study={study} />
      <SummaryStrip study={study} />
    </div>
  );
}

/**
 * InstrumentsTab — ONE list for everything the study collects with.
 *
 * Surveys and interview rounds used to live behind separate tabs; with
 * ≤3 items each that split forced a which-tab decision without adding
 * information. Each row carries its kind in the eyebrow, so one list
 * stays legible. Surveys sort first (screener → interviews mirrors the
 * methodology flow).
 */
function InstrumentsTab({
  study,
  onCreateSurvey,
  onCreateInterview,
}: {
  study: StudyDetail;
  onCreateSurvey: () => void;
  onCreateInterview: () => void;
}) {
  const { t } = useTranslation("study");

  const surveyStatusLabel = (status: string) =>
    status === "live"
      ? t("shell:instrument.statusLive")
      : status === "closed"
        ? t("shell:instrument.statusClosed")
        : t("shell:instrument.statusDraft");

  const createButtons = (
    <div style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap" }}>
      <button type="button" className="btn btn-secondary" onClick={onCreateSurvey}>
        {t("overview.surveys.newSurvey")}
      </button>
      <button type="button" className="btn btn-secondary" onClick={onCreateInterview}>
        {t("overview.interviews.addRound")}
      </button>
    </div>
  );

  if (study.surveys.length === 0 && study.projects.length === 0) {
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
          {t("overview.instruments.empty")}
        </p>
        {createButtons}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
        {study.surveys.map((s) => (
          <Link
            key={s.id}
            // A draft opens where you left off building it; a live or
            // closed survey opens on its results — same rule everywhere.
            to={
              s.status === "draft"
                ? `/surveys/${s.id}/edit`
                : `/surveys/${s.id}/dashboard`
            }
            className="chart-card chart-card--row"
            style={{ textDecoration: "none", color: "inherit", cursor: "pointer" }}
          >
            <div className="chart-card__row-main">
              <div className="chart-card__eyebrow">
                {t("overview.instruments.surveyEyebrow", {
                  role: s.role.toUpperCase(),
                  status: surveyStatusLabel(s.status).toUpperCase(),
                })}
              </div>
              <div className="chart-card__takeaway">{s.name}</div>
            </div>
            <div className="chart-card__footer tabular">
              <span>{t("overview.surveys.questions", { count: s.question_count })}</span>
              <span className="chart-card__footer-divider">·</span>
              <span>{t("overview.surveys.completed", { count: s.completed_count })}</span>
              <span className="chart-card__footer-divider">·</span>
              <span>{t("overview.surveys.total", { count: s.response_count })}</span>
            </div>
          </Link>
        ))}
        {study.projects.map((p, pi) => (
          <Link
            key={p.id}
            to={`/projects/${p.id}`}
            data-tour={study.is_demo && pi === 0 ? "workspace-interview-round" : undefined}
            className="chart-card chart-card--row"
            style={{ textDecoration: "none", color: "inherit" }}
          >
            <div className="chart-card__row-main">
              <div className="chart-card__eyebrow">
                {t("overview.instruments.interviewEyebrow", { language: p.language.toUpperCase() })}
              </div>
              <div className="chart-card__takeaway">{p.name}</div>
            </div>
            <div className="chart-card__footer tabular">
              <span>{t("overview.interviews.completed", { count: p.completed_participant_count })}</span>
              <span className="chart-card__footer-divider">·</span>
              <span>{t("overview.interviews.inProgress", { count: p.in_progress_participant_count })}</span>
              <span className="chart-card__footer-divider">·</span>
              <span>{t("overview.interviews.links", { count: p.interview_link_count })}</span>
            </div>
          </Link>
        ))}
      </div>
      {createButtons}
    </div>
  );
}

function ParticipantsTab({ study }: { study: StudyDetail }) {
  const { t } = useTranslation("study");
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
        {t("overview.participants.intro")}
      </p>
      <div className="dashboard-strip">
        <div className="dashboard-strip__item">
          <div className="dashboard-strip__label">{t("overview.participants.surveyCompleters")}</div>
          <div className="dashboard-strip__value tabular">{totalSurveyRespondents}</div>
        </div>
        <div className="dashboard-strip__item">
          <div className="dashboard-strip__label">{t("overview.participants.interviewCompleters")}</div>
          <div className="dashboard-strip__value tabular">{totalInterviewers}</div>
        </div>
        <div className="dashboard-strip__item">
          <div className="dashboard-strip__label">{t("overview.participants.inferenceThreshold")}</div>
          <div className="dashboard-strip__value tabular">{t("overview.participants.thresholdValue")}</div>
        </div>
      </div>
    </div>
  );
}

function ReportTab({ study }: { study: StudyDetail }) {
  const studyId = study.id;
  const progress = study.progress;
  const { t, i18n } = useTranslation("study");
  const { toast } = useToast();
  const navigate = useNavigate();
  const [analysis, setAnalysis] = useState<StudyAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  // Sprint 14: per-analysis validation summary
  const [validation, setValidation] = useState<ValidationSummary | null>(null);
  const [spawningValidation, setSpawningValidation] = useState(false);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    setLoading(true);
    getLatestAnalysis(studyId)
      .then((a) => setAnalysis(a))
      .catch(() => setAnalysis(null))
      .finally(() => setLoading(false));
  }, [studyId]);

  // Pull validation summary whenever we have a ready analysis. Returns
  // null when no validation survey has been generated yet — that's the
  // "Validate these themes" CTA's initial state.
  useEffect(() => {
    if (!analysis || analysis.status !== "ready") {
      setValidation(null);
      return;
    }
    getValidationSummary(studyId, analysis.id)
      .then(setValidation)
      .catch(() => setValidation(null));
  }, [studyId, analysis?.id, analysis?.status]);

  const onGenerateValidation = async () => {
    if (!analysis) return;
    setSpawningValidation(true);
    try {
      const result = await createValidationSurvey(studyId, analysis.id);
      toast(t("overview.toast.validationCreated", { count: result.question_count }), "success");
      navigate(`/surveys/${result.survey_id}/edit`);
    } catch (e: any) {
      const detail = e?.response?.data?.detail || t("overview.toast.validationGenerateFailed");
      toast(detail, "error");
    } finally {
      setSpawningValidation(false);
    }
  };

  // Server-rendered document export: the backend draws charts from the same
  // aggregates the analysis used — no more printing the SPA with its chrome.
  const onExportReport = async () => {
    if (!analysis) return;
    setExporting(true);
    try {
      await openHtmlDocument(
        () => fetchStudyReportHtml(studyId, analysis.id),
        `study-report-v${analysis.version}.html`,
      );
    } catch {
      toast(t("overview.toast.exportReportFailed"), "error");
    } finally {
      setExporting(false);
    }
  };

  const onGenerate = async () => {
    setGenerating(true);
    try {
      const fresh = await triggerAnalysis(studyId);
      setAnalysis(fresh);
      if (fresh.status === "failed") {
        toast(fresh.error || t("overview.toast.generationFailed"), "error");
      } else {
        toast(t("overview.toast.reportGenerated"), "success");
      }
    } catch {
      toast(t("overview.toast.reportGenerateFailed"), "error");
    } finally {
      setGenerating(false);
    }
  };

  if (loading) {
    return <p className="quanti-showcase__section-meta">{t("overview.report.loading")}</p>;
  }

  // The index of every report artifact this study can produce, each with
  // its scope named — shown above AND below the study report so the three
  // report types (round analysis / study report / decision memo) stop
  // reading as interchangeable exports.
  const reportsIndex = (
    <ReportsIndex study={study} studyReportReady={analysis?.status === "ready"} />
  );

  // Empty-state CTA when no analysis exists yet.
  if (!analysis) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
      <div
        style={{
          background: "var(--bg-surface)",
          border: "1px dashed var(--border-default)",
          borderRadius: "var(--radius-md)",
          padding: "var(--space-8)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: "var(--space-4)",
          textAlign: "center",
        }}
      >
        <div style={{ maxWidth: 560 }}>
          <h2
            style={{
              fontFamily: "var(--font-serif)",
              fontSize: "var(--text-xl)",
              letterSpacing: "-0.015em",
              marginBottom: "var(--space-2)",
            }}
          >
            {t("overview.report.generateHeadline")}
          </h2>
          <p
            style={{
              color: "var(--text-secondary)",
              fontSize: "var(--text-md)",
              lineHeight: 1.5,
              margin: 0,
            }}
          >
            {t("overview.report.generateBody")}
          </p>
          {progress.total_completed_responses < 30 && (
            <p
              style={{
                fontSize: "var(--text-xs)",
                color: "var(--warning-text)",
                marginTop: "var(--space-3)",
              }}
            >
              {t("overview.report.lowResponseWarning", { count: progress.total_completed_responses })}
            </p>
          )}
        </div>
        <button
          type="button"
          className="btn btn-primary"
          onClick={onGenerate}
          disabled={generating}
        >
          {generating ? t("overview.report.generating") : t("overview.report.generate")}
        </button>
      </div>
      {reportsIndex}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
      {/* Scope line — this is the study-wide report; each interview round
          also has its own Analysis tab, and cross-study decision memos live
          on the Studies home. Naming the scope keeps the three apart. */}
      <p className="quanti-showcase__section-meta" style={{ margin: 0 }}>
        {t("overview.report.scopeNote")}
      </p>
      {/* Report header + regenerate button */}
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "var(--space-3)",
        }}
      >
        <div>
          <div
            style={{
              fontSize: "var(--text-eyebrow)",
              fontWeight: 600,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "var(--brand-700)",
            }}
          >
            {t("overview.report.versionEyebrow", { version: analysis.version })}
          </div>
          <span className="tabular" style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)" }}>
            {analysis.generated_at
              ? t("overview.report.generatedAt", { date: new Date(analysis.generated_at).toLocaleString(i18n.language) })
              : t("overview.report.generatedAtUnknown")}
          </span>
        </div>
        <div style={{ display: "flex", gap: "var(--space-2)" }}>
          {analysis.status === "ready" && analysis.report && (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onExportReport}
              disabled={exporting}
              title={t("overview.report.exportPdfTitle")}
            >
              {exporting ? t("overview.report.exportPdfLoading") : t("overview.report.exportPdf")}
            </button>
          )}
          {!validation && analysis.status === "ready" && (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onGenerateValidation}
              disabled={spawningValidation}
              title={t("overview.report.validateThemesTitle")}
            >
              {spawningValidation ? t("overview.report.validateGenerating") : t("overview.report.validateThemes")}
            </button>
          )}
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onGenerate}
            disabled={generating}
          >
            {generating ? t("overview.report.regenerating") : t("overview.report.regenerate")}
          </button>
        </div>
      </header>

      {validation && <ValidationBanner validation={validation} studyId={studyId} />}

      {analysis.status === "failed" && (
        <div className="methodology-box methodology-box--inline">
          {t("overview.report.lastGenerationFailed", { error: analysis.error || t("overview.report.unknownError") })}
        </div>
      )}

      {/* The report body IS the exported document — same endpoint, same
          renderer, embedded without its floating print toolbar. The in-app
          view and the PDF can never diverge again. */}
      {analysis.status === "ready" && analysis.report && (
        <EmbeddedStudyReport
          studyId={studyId}
          analysisId={analysis.id}
          refreshKey={analysis.generated_at ?? String(analysis.version)}
        />
      )}
      {reportsIndex}
    </div>
  );
}

/**
 * EmbeddedStudyReport — renders the server-generated report.html inside the
 * Reports tab. The document is fetched with auth (iframes can't carry the
 * bearer token) and mounted via a blob URL, which stays same-origin so the
 * frame can be auto-sized to its content.
 */
function EmbeddedStudyReport({
  studyId,
  analysisId,
  refreshKey,
}: {
  studyId: string;
  analysisId: string;
  refreshKey: string;
}) {
  const { t } = useTranslation("study");
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [height, setHeight] = useState(900);

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    setUrl(null);
    setFailed(false);
    (async () => {
      try {
        const blob = await fetchStudyReportHtml(studyId, analysisId, { embed: true });
        if (cancelled) return;
        objectUrl = URL.createObjectURL(new Blob([blob], { type: "text/html" }));
        setUrl(objectUrl);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [studyId, analysisId, refreshKey]);

  const measure = () => {
    const body = iframeRef.current?.contentDocument?.body;
    if (body) setHeight(Math.max(600, body.scrollHeight + 32));
  };

  // If the frame's document is unreachable after load, the browser blocked
  // it (a CSP without `frame-src blob:`, an aggressive extension, …). Rather
  // than leave a mystery-blank box, fall back to the "open the PDF" message —
  // the export button above still works.
  const handleLoad = () => {
    const doc = iframeRef.current?.contentDocument;
    if (!doc || !doc.body) {
      setFailed(true);
      return;
    }
    measure();
    // Re-measure after fonts/SVGs settle the layout.
    window.setTimeout(measure, 300);
    window.setTimeout(measure, 1200);
  };

  if (failed) {
    return <p className="quanti-showcase__section-meta">{t("overview.report.embedFailed")}</p>;
  }
  if (!url) {
    return <p className="quanti-showcase__section-meta">{t("overview.report.loading")}</p>;
  }
  return (
    <iframe
      ref={iframeRef}
      src={url}
      title={t("overview.report.embedTitle")}
      onLoad={handleLoad}
      style={{
        width: "100%",
        height,
        border: "1px solid var(--border-default)",
        borderRadius: "var(--radius-md)",
        background: "#fcfcfa",
        display: "block",
      }}
    />
  );
}

/**
 * ReportsIndex — the one place that lists every report artifact a study
 * can produce, each with a scope badge: per-round analyses (this round
 * only), the mixed-methods study report (this page), and cross-study
 * decision memos (Studies home). Answers "which report do I export?"
 * without hunting across three surfaces.
 */
// The three report families share one colour identity with the exported
// PDFs (services/report_export.py): qual rounds are forest green, survey
// results are ink blue, and mixed-methods artifacts (study report +
// decision memos) are bordeaux. Keep in sync with _PALETTES server-side.
const REPORT_FAMILY_COLORS = {
  qual: { color: "#1d5c3f", background: "#eef4ef" },
  quant: { color: "#1e4a73", background: "#edf2f8" },
  mixed: { color: "#7c2434", background: "#f8eef0" },
} as const;

function ReportsIndex({
  study,
  studyReportReady,
}: {
  study: StudyDetail;
  studyReportReady: boolean;
}) {
  const { t } = useTranslation("study");

  const badge = (label: string, family: keyof typeof REPORT_FAMILY_COLORS) => (
    <span
      style={{
        fontSize: "var(--text-eyebrow)",
        fontWeight: 600,
        letterSpacing: "0.06em",
        textTransform: "uppercase",
        color: REPORT_FAMILY_COLORS[family].color,
        background: REPORT_FAMILY_COLORS[family].background,
        borderRadius: 999,
        padding: "3px 10px",
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </span>
  );

  const rowStyle: CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: "var(--space-3)",
    padding: "var(--space-3) var(--space-4)",
    borderTop: "1px solid var(--border-subtle)",
    color: "inherit",
    textDecoration: "none",
    fontSize: "var(--text-sm)",
  };

  return (
    <section
      style={{
        background: "var(--bg-surface)",
        border: "1px solid var(--border-default)",
        borderRadius: "var(--radius-md)",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          fontSize: "var(--text-eyebrow)",
          fontWeight: 600,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: "var(--text-tertiary)",
          padding: "var(--space-3) var(--space-4)",
        }}
      >
        {t("overview.reportsIndex.title")}
      </div>

      {/* This study's mixed-methods report — it renders on this page. */}
      <div style={rowStyle}>
        {badge(t("overview.reportsIndex.scopeStudy"), "mixed")}
        <span style={{ flex: 1, minWidth: 0 }}>{t("overview.reportsIndex.studyReportLabel")}</span>
        <span className="tabular" style={{ color: "var(--text-tertiary)", fontSize: "var(--text-xs)" }}>
          {studyReportReady
            ? t("overview.reportsIndex.ready")
            : t("overview.reportsIndex.notGenerated")}
        </span>
      </div>

      {/* Per-round qualitative analyses. */}
      {study.projects.map((p) => (
        <Link key={p.id} to={`/projects/${p.id}?tab=analysis`} style={rowStyle}>
          {badge(t("overview.reportsIndex.scopeRound"), "qual")}
          <span
            style={{
              flex: 1,
              minWidth: 0,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {p.name}
          </span>
          <span className="tabular" style={{ color: "var(--text-tertiary)", fontSize: "var(--text-xs)" }}>
            {p.has_ready_analysis
              ? t("overview.reportsIndex.ready")
              : t("overview.reportsIndex.noAnalysisYet")}
          </span>
          <span aria-hidden="true" style={{ color: "var(--text-tertiary)" }}>→</span>
        </Link>
      ))}

      {/* Quantitative survey results — each source survey exports its own
          ink-blue results report from its dashboard. Validation
          micro-surveys are folded into the study report, so they don't get
          a row of their own. */}
      {study.surveys
        .filter((s) => s.role !== "validation")
        .map((s) => (
          <Link key={s.id} to={`/surveys/${s.id}/dashboard`} style={rowStyle}>
            {badge(t("overview.reportsIndex.scopeSurvey"), "quant")}
            <span
              style={{
                flex: 1,
                minWidth: 0,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {s.name}
            </span>
            <span className="tabular" style={{ color: "var(--text-tertiary)", fontSize: "var(--text-xs)" }}>
              {t("overview.reportsIndex.surveyResponses", { count: s.completed_count })}
            </span>
            <span aria-hidden="true" style={{ color: "var(--text-tertiary)" }}>→</span>
          </Link>
        ))}

      {/* Cross-study decision memos live on the Studies home. */}
      <Link to="/studies" style={rowStyle}>
        {badge(t("overview.reportsIndex.scopeCross"), "mixed")}
        <span style={{ flex: 1, minWidth: 0 }}>{t("overview.reportsIndex.memosLabel")}</span>
        <span aria-hidden="true" style={{ color: "var(--text-tertiary)" }}>→</span>
      </Link>
    </section>
  );
}

function ValidationBanner({
  validation,
  studyId,
}: {
  validation: ValidationSummary;
  studyId: string;
}) {
  const { t } = useTranslation("study");
  const navigate = useNavigate();
  const isDraft = validation.survey_status === "draft";
  return (
    <div
      style={{
        background: isDraft ? "var(--brand-gradient-soft)" : "var(--info-bg)",
        border: `1px solid ${isDraft ? "var(--brand-300)" : "var(--info-border)"}`,
        color: isDraft ? "var(--brand-700)" : "var(--info-text)",
        borderRadius: "var(--radius-md)",
        padding: "var(--space-3) var(--space-4)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "var(--space-3)",
      }}
    >
      <div>
        <div style={{ fontWeight: 600, fontSize: "var(--text-sm)" }}>
          {t("overview.validationBanner.title", { status: validation.survey_status.toUpperCase() })}
        </div>
        <div className="tabular" style={{ fontSize: "var(--text-xs)", marginTop: 2 }}>
          {t("overview.validationBanner.progress", { completed: validation.n_completed, total: validation.n_responses })}
          {isDraft && t("overview.validationBanner.draftSuffix")}
        </div>
      </div>
      <button
        type="button"
        className="btn btn-secondary btn-sm"
        onClick={() => navigate(`/surveys/${validation.survey_id}/edit`)}
      >
        {isDraft ? t("overview.validationBanner.editPublish") : t("overview.validationBanner.openSurvey")}
      </button>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────
   Building blocks
   ──────────────────────────────────────────────────────────────────── */

function RecommendedActionCard({ text, onClick }: { text: string; onClick: () => void }) {
  const { t } = useTranslation("study");
  return (
    <div className="reco-card">
      <div className="reco-card__icon" aria-hidden="true">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M13 2 L3 14 L12 14 L11 22 L21 10 L12 10 Z" />
        </svg>
      </div>
      <div className="reco-card__body">
        <div className="reco-card__eyebrow">{t("overview.recommendedAction.eyebrow")}</div>
        <p className="reco-card__text">{text}</p>
      </div>
      <button type="button" className="btn btn-primary" onClick={onClick}>
        {t("overview.recommendedAction.takeAction")}
      </button>
    </div>
  );
}

function ProgressChecklist({ study }: { study: StudyDetail }) {
  const { t } = useTranslation("study");
  const steps: Array<{ label: string; done: boolean; detail?: string }> = [
    {
      label: t("overview.checklist.surveyPublished"),
      done: study.progress.has_live_survey,
      detail: study.progress.has_live_survey ? t("overview.checklist.live") : t("overview.checklist.notYet"),
    },
    {
      label: t("overview.checklist.responsesCollected"),
      done: study.progress.total_completed_responses > 0,
      detail: t("overview.checklist.completed", { count: study.progress.total_completed_responses }),
    },
    {
      label: t("overview.checklist.inferenceThreshold"),
      done: study.progress.segments_identified_placeholder,
      detail:
        study.progress.total_completed_responses >= 30
          ? t("overview.checklist.segmentCutsAllowed")
          : t("overview.checklist.moreResponsesNeeded", { count: 30 - study.progress.total_completed_responses }),
    },
    {
      label: t("overview.checklist.interviewsCompleted"),
      done: study.progress.interviews_completed > 0,
      detail: t("overview.checklist.completed", { count: study.progress.interviews_completed }),
    },
    {
      label: t("overview.checklist.mixedMethodsReport"),
      done: study.progress.report_ready_placeholder,
      detail: study.progress.report_ready_placeholder ? t("overview.checklist.ready") : t("overview.checklist.notYet"),
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
          {t("overview.checklist.title")}
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
  const { t } = useTranslation("study");
  return (
    <div className="dashboard-strip">
      <div className="dashboard-strip__item">
        <div className="dashboard-strip__label">{t("overview.summary.surveys")}</div>
        <div className="dashboard-strip__value tabular">{study.surveys.length}</div>
        <div className="dashboard-strip__delta dashboard-strip__delta--neutral">
          {study.progress.has_live_survey ? t("overview.summary.live") : t("overview.summary.drafts")}
        </div>
      </div>
      <div className="dashboard-strip__item">
        <div className="dashboard-strip__label">{t("overview.summary.surveyResponses")}</div>
        <div className="dashboard-strip__value tabular">{study.progress.total_completed_responses}</div>
        <div className="dashboard-strip__delta dashboard-strip__delta--neutral">
          {study.progress.total_completed_responses >= 30 ? t("overview.summary.inferenceGrade") : t("overview.summary.buildingSample")}
        </div>
      </div>
      <div className="dashboard-strip__item">
        <div className="dashboard-strip__label">{t("overview.summary.interviews")}</div>
        <div className="dashboard-strip__value tabular">{study.progress.interviews_completed}</div>
        <div className="dashboard-strip__delta dashboard-strip__delta--neutral">
          {t("overview.summary.projects", { count: study.projects.length })}
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
