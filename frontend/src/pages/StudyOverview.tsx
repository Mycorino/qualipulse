import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import {
  QuantifiedTheme,
  StudyAnalysis,
  StudyDetail,
  ThemeValidationSnapshot,
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

type Tab = "overview" | "surveys" | "interviews" | "participants" | "report";

export default function StudyOverview() {
  const { t, i18n } = useTranslation(["study", "dashboard"]);
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = (searchParams.get("tab") as Tab) || "overview";
  const [tab, setTab] = useState<Tab>(initialTab);
  const [study, setStudy] = useState<StudyDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
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
          {(["overview", "surveys", "interviews", "participants", "report"] as Tab[]).map((tabKey) => (
            <button
              key={tabKey}
              type="button"
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
          <OverviewTab study={study} navigate={navigate} onCreateSurvey={handleCreateSurvey} />
        )}
        {tab === "surveys" && (
          <SurveysTab study={study} onCreateSurvey={handleCreateSurvey} />
        )}
        {tab === "interviews" && (
          <InterviewsTab study={study} onCreateInterview={handleCreateInterview} />
        )}
        {tab === "participants" && <ParticipantsTab study={study} />}
        {tab === "report" && <ReportTab studyId={study.id} progress={study.progress} />}
      </main>
    </div>
    </HubShell>
  );
}

/* ────────────────────────────────────────────────────────────────────
   Tabs
   ──────────────────────────────────────────────────────────────────── */

function OverviewTab({
  study,
  navigate,
  onCreateSurvey,
}: {
  study: StudyDetail;
  navigate: ReturnType<typeof useNavigate>;
  onCreateSurvey: () => void;
}) {
  const onAct = () => {
    // The recommended action is text — for v1 the chip just routes to the
    // most sensible surface for the current state. Sprint 10 wires the
    // chip to a structured action (e.g. directly open the bridge for a
    // suggested segment).
    if (!study.progress.has_live_survey && study.surveys.length === 0) {
      onCreateSurvey();
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
  onCreateSurvey,
}: {
  study: StudyDetail;
  onCreateSurvey: () => void;
}) {
  const { t } = useTranslation("study");
  if (study.surveys.length === 0) {
    return (
      <EmptyState
        message={t("overview.surveys.empty")}
        ctaLabel={t("overview.surveys.newSurvey")}
        onAct={onCreateSurvey}
      />
    );
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
        {study.surveys.map((s) => (
          <a
            key={s.id}
            href={`/surveys/${s.id}/edit`}
            className="chart-card chart-card--row"
            style={{ textDecoration: "none", color: "inherit", cursor: "pointer" }}
          >
            <div className="chart-card__row-main">
              <div className="chart-card__eyebrow">
                {t("overview.surveys.roleStatus", { role: s.role.toUpperCase(), status: s.status.toUpperCase() })}
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
          </a>
        ))}
      </div>
      <button
        type="button"
        className="btn btn-secondary"
        style={{ alignSelf: "flex-start" }}
        onClick={onCreateSurvey}
      >
        {t("overview.surveys.newSurvey")}
      </button>
    </div>
  );
}

function InterviewsTab({
  study,
  onCreateInterview,
}: {
  study: StudyDetail;
  onCreateInterview: () => void;
}) {
  const { t } = useTranslation("study");
  if (study.projects.length === 0) {
    return (
      <EmptyState
        message={t("overview.interviews.empty")}
        ctaLabel={t("overview.interviews.addRound")}
        onAct={onCreateInterview}
      />
    );
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
        {study.projects.map((p) => (
          <a
            key={p.id}
            href={`/projects/${p.id}`}
            className="chart-card chart-card--row"
            style={{ textDecoration: "none", color: "inherit" }}
          >
            <div className="chart-card__row-main">
              <div className="chart-card__eyebrow">{t("overview.interviews.eyebrow", { language: p.language.toUpperCase() })}</div>
              <div className="chart-card__takeaway">{p.name}</div>
            </div>
            <div className="chart-card__footer tabular">
              <span>{t("overview.interviews.completed", { count: p.completed_participant_count })}</span>
              <span className="chart-card__footer-divider">·</span>
              <span>{t("overview.interviews.inProgress", { count: p.in_progress_participant_count })}</span>
              <span className="chart-card__footer-divider">·</span>
              <span>{t("overview.interviews.links", { count: p.interview_link_count })}</span>
            </div>
          </a>
        ))}
      </div>
      <button
        type="button"
        className="btn btn-secondary"
        style={{ alignSelf: "flex-start" }}
        onClick={onCreateInterview}
      >
        {t("overview.interviews.addRound")}
      </button>
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

function ReportTab({
  studyId,
  progress,
}: {
  studyId: string;
  progress: StudyDetail["progress"];
}) {
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
      const data = await fetchStudyReportHtml(studyId, analysis.id);
      const url = URL.createObjectURL(new Blob([data], { type: "text/html" }));
      window.open(url, "_blank", "noopener");
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
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

  // Empty-state CTA when no analysis exists yet.
  if (!analysis) {
    return (
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
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
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

      {analysis.report && (
        <>
          {/* Executive summary */}
          <section
            style={{
              background: "var(--bg-surface)",
              border: "1px solid var(--border-default)",
              borderRadius: "var(--radius-lg)",
              padding: "var(--space-6) var(--space-8)",
            }}
          >
            <div
              style={{
                fontSize: "var(--text-eyebrow)",
                fontWeight: 600,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: "var(--text-tertiary)",
                marginBottom: "var(--space-3)",
              }}
            >
              {t("overview.report.executiveSummary")}
            </div>
            <p
              style={{
                fontFamily: "var(--font-serif)",
                fontSize: "var(--text-lg)",
                lineHeight: 1.5,
                color: "var(--text-primary)",
                margin: 0,
                letterSpacing: "-0.01em",
                maxWidth: "62ch",
              }}
            >
              {analysis.report.executive_summary}
            </p>
          </section>

          {/* Themes */}
          <section style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
            <div
              style={{
                fontSize: "var(--text-eyebrow)",
                fontWeight: 600,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: "var(--text-tertiary)",
              }}
            >
              {t("overview.report.themes", { count: analysis.report.themes.length })}
            </div>
            {analysis.report.themes.map((theme, i) => (
              <ThemeCard
                key={i}
                theme={theme}
                validation={validation?.per_theme?.[String(i)] ?? null}
              />
            ))}
          </section>

          {/* Methodology */}
          <section
            style={{
              background: "var(--bg-sunken)",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-4) var(--space-5)",
            }}
          >
            <div
              style={{
                fontSize: "var(--text-eyebrow)",
                fontWeight: 600,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: "var(--text-tertiary)",
                marginBottom: "var(--space-2)",
              }}
            >
              {t("overview.report.methodology")}
            </div>
            <p
              style={{
                fontSize: "var(--text-sm)",
                color: "var(--text-secondary)",
                lineHeight: 1.5,
                margin: 0,
              }}
            >
              {analysis.report.methodology_note}
            </p>
            <div
              className="tabular"
              style={{
                fontSize: "var(--text-xs)",
                color: "var(--text-tertiary)",
                marginTop: "var(--space-2)",
              }}
            >
              {t("overview.report.methodologyStats_survey", { count: analysis.report.generated_with_survey_count })}
              {t("overview.report.metaSeparator")}
              {t("overview.report.methodologyStats_responses", { count: analysis.report.generated_with_response_count })}
              {t("overview.report.metaSeparator")}
              {t("overview.report.methodologyStats_interview", { count: analysis.report.generated_with_interview_count })}
            </div>
          </section>
        </>
      )}
    </div>
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

function ThemeCard({
  theme,
  validation,
}: {
  theme: QuantifiedTheme;
  validation: ThemeValidationSnapshot | null;
}) {
  const { t } = useTranslation("study");
  return (
    <article
      style={{
        background: "var(--bg-surface)",
        border: "1px solid var(--border-default)",
        borderRadius: "var(--radius-lg)",
        padding: "var(--space-6) var(--space-7)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-4)",
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: "var(--space-3)",
        }}
      >
        <h3
          style={{
            fontFamily: "var(--font-serif)",
            fontSize: "var(--text-headline)",
            letterSpacing: "-0.02em",
            lineHeight: 1.2,
            margin: 0,
            maxWidth: "44ch",
          }}
        >
          {theme.title}
        </h3>
        <span className={`confidence-pill confidence-pill--${theme.confidence}`}>
          <span className="confidence-pill__dot" aria-hidden="true" />
          {t(`overview.theme.confidence.${theme.confidence}`)}
        </span>
      </header>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "var(--space-4)",
        }}
      >
        {/* Survey signal */}
        {theme.survey_signal && (
          <div>
            <div
              style={{
                fontSize: "var(--text-eyebrow)",
                fontWeight: 600,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: "var(--text-tertiary)",
                marginBottom: "var(--space-2)",
              }}
            >
              {t("overview.theme.surveySignal")}
            </div>
            <p
              style={{
                fontFamily: "var(--font-serif)",
                fontSize: "var(--text-md)",
                lineHeight: 1.4,
                color: "var(--text-primary)",
                margin: 0,
              }}
            >
              {theme.survey_signal.summary}
            </p>
            <div
              className="tabular"
              style={{
                fontSize: "var(--text-xs)",
                color: "var(--text-tertiary)",
                marginTop: "var(--space-1)",
              }}
            >
              {t("overview.theme.n", { count: theme.survey_signal.n })}
              {theme.survey_signal.segment_over_index
                ? t("overview.theme.overIndex", { value: theme.survey_signal.segment_over_index.toFixed(1) })
                : ""}
              {theme.survey_signal.segment_label
                ? t("overview.theme.segmentLabel", { label: theme.survey_signal.segment_label })
                : ""}
            </div>
          </div>
        )}

        {/* Interview evidence */}
        {theme.interview_evidence && (
          <div>
            <div
              style={{
                fontSize: "var(--text-eyebrow)",
                fontWeight: 600,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: "var(--text-tertiary)",
                marginBottom: "var(--space-2)",
              }}
            >
              {t("overview.theme.interviewEvidence", { xOfY: theme.interview_evidence.x_of_y })}
            </div>
            <blockquote
              style={{
                fontFamily: "var(--font-serif)",
                fontSize: "var(--text-md)",
                fontStyle: "italic",
                lineHeight: 1.5,
                color: "var(--text-primary)",
                margin: 0,
                paddingLeft: "var(--space-3)",
                borderLeft: "3px solid var(--brand-500)",
              }}
            >
              "{theme.interview_evidence.anchor_quote}"
            </blockquote>
          </div>
        )}
      </div>

      {validation && <ThemeValidationPanel validation={validation} />}

      {/* Recommendation footer */}
      <footer
        style={{
          borderTop: "1px solid var(--border-subtle)",
          paddingTop: "var(--space-4)",
        }}
      >
        <div
          style={{
            fontSize: "var(--text-eyebrow)",
            fontWeight: 600,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: "var(--brand-700)",
            marginBottom: "var(--space-2)",
          }}
        >
          {t(`overview.theme.kind.${theme.recommendation.kind}`)}
        </div>
        <p
          style={{
            fontFamily: "var(--font-serif)",
            fontSize: "var(--text-md)",
            fontWeight: 500,
            color: "var(--text-primary)",
            margin: 0,
            lineHeight: 1.4,
          }}
        >
          {theme.recommendation.action}
        </p>
        {theme.recommendation.rationale && (
          <p
            style={{
              fontSize: "var(--text-sm)",
              color: "var(--text-secondary)",
              marginTop: "var(--space-2)",
              lineHeight: 1.5,
            }}
          >
            {theme.recommendation.rationale}
          </p>
        )}
      </footer>
    </article>
  );
}

function ThemeValidationPanel({
  validation,
}: {
  validation: ThemeValidationSnapshot;
}) {
  const { t } = useTranslation("study");
  if (validation.n_answered === 0) {
    return (
      <div
        style={{
          padding: "var(--space-3) var(--space-4)",
          background: "var(--bg-sunken)",
          borderRadius: "var(--radius-sm)",
          fontSize: "var(--text-xs)",
          color: "var(--text-tertiary)",
        }}
      >
        {t("overview.themeValidation.awaiting")}
      </div>
    );
  }
  const pct = validation.agreement_pct;
  return (
    <div
      style={{
        background: "var(--info-bg)",
        border: "1px solid var(--info-border)",
        borderRadius: "var(--radius-sm)",
        padding: "var(--space-3) var(--space-4)",
      }}
    >
      <div
        style={{
          fontSize: "var(--text-eyebrow)",
          fontWeight: 600,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: "var(--info-text)",
          marginBottom: "var(--space-1)",
        }}
      >
        {t("overview.themeValidation.title", { count: validation.n_answered })}
      </div>
      <div
        className="tabular"
        style={{
          fontFamily: "var(--font-serif)",
          fontSize: "var(--text-md)",
          color: "var(--info-text)",
        }}
      >
        {pct === null ? (
          <span>
            {t("overview.themeValidation.agreedCounts", {
              agreed: validation.distribution["4"] + validation.distribution["5"],
              total: validation.n_answered,
            })}
          </span>
        ) : (
          <span>
            <strong>{Math.round(pct)}%</strong> {t("overview.themeValidation.agreedPct")}
            {validation.ci_low !== null && validation.ci_high !== null && (
              <span style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)" }}>
                {t("overview.themeValidation.ci", { low: Math.round(validation.ci_low), high: Math.round(validation.ci_high) })}
              </span>
            )}
          </span>
        )}
      </div>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────
   Building blocks
   ──────────────────────────────────────────────────────────────────── */

function RecommendedActionCard({ text, onClick }: { text: string; onClick: () => void }) {
  const { t } = useTranslation("study");
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
          {t("overview.recommendedAction.eyebrow")}
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
