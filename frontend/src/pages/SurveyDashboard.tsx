import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import i18n from "../i18n";

import {
  DiscoveryConfidence,
  QuestionAnalytics,
  SegmentDiscovery,
  SegmentFilter,
  SegmentOperator,
  SegmentPreview,
  SurveyDashboard,
  fetchSurveyReportHtml,
  getDashboard,
  getDiscoveries,
  getSurvey,
  inviteSegment,
  previewSegment,
} from "../api/surveys";
import { getStudy } from "../api/studies";
import { openHtmlDocument } from "../utils/openHtmlDocument";
import { ChartCard } from "../components/ChartCard";
import { DashboardShell, DashboardStrip } from "../components/DashboardShell";
import { MethodologyBox, SmallNWarning } from "../components/MethodologyBox";
import { ScreenerBridge } from "../components/ScreenerBridge";
import { useToast } from "../components/Toast";
import { InstrumentShell } from "../components/InstrumentShell";
import {
  surveySections,
  surveySectionPath,
  surveyStatusPill,
} from "../components/surveyShellNav";

/**
 * SurveyDashboard — `/surveys/:id/dashboard`.
 *
 * Wires the Sprint 1 design-system primitives (DashboardShell,
 * DashboardStrip, ChartCard, MethodologyBox) to the Sprint 6 schema +
 * Sprint 8 analytics endpoint. One ChartCard per question; n<30
 * segments render counts via Wilson-CI-aware ChartCard's `minN` prop.
 *
 * Compare/segments and AI clustering are deliberately out of scope
 * (Sprint 10 + 13). What ships here is the single-survey,
 * single-segment view that proves the methodology contract.
 */
export default function SurveyDashboardPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const { t } = useTranslation("survey");
  const [data, setData] = useState<SurveyDashboard | null>(null);
  const [study, setStudy] = useState<{ id: string; name: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  // ── Segment filter state ────────────────────────────────────────
  const [filters, setFilters] = useState<SegmentFilter[]>([]);
  const [preview, setPreview] = useState<SegmentPreview | null>(null);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [inviting, setInviting] = useState(false);
  // ── Sprint 10: discoveries ─────────────────────────────────────
  const [discoveries, setDiscoveries] = useState<SegmentDiscovery[]>([]);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    if (!id) return;
    getDashboard(id)
      .then(setData)
      .catch(() => setError(t("dashboard.loadFailed")));
    getSurvey(id)
      .then((s) =>
        getStudy(s.study_id)
          .then((st) => setStudy({ id: st.id, name: st.name }))
          .catch(() => setStudy(null)),
      )
      .catch(() => setStudy(null));
    getDiscoveries(id)
      .then((p) => setDiscoveries(p.discoveries))
      .catch(() => setDiscoveries([]));
  }, [id]);

  /** Discovery card click → pre-populate the Bridge filter + scroll to it. */
  const onApplyDiscovery = (d: SegmentDiscovery) => {
    setFilters(d.ready_filter);
    // Scroll the filter rail into view so the change is obvious.
    setTimeout(() => {
      const target = document.querySelector("[data-bridge-target]") as HTMLElement | null;
      target?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 80);
  };

  // Re-preview whenever filters change. Debounce keeps backend chatter sane.
  useEffect(() => {
    if (!id) return;
    const timer = setTimeout(() => {
      previewSegment(id, filters)
        .then(setPreview)
        .catch(() => setPreview(null));
    }, 300);
    return () => clearTimeout(timer);
  }, [id, filters]);

  const filterDescription = useMemo(() => {
    if (!data || filters.length === 0) return t("dashboard.allCompletedRespondents");
    return filters.map((f) => describeFilter(f, data.questions, t)).join(t("dashboard.filterAnd"));
  }, [filters, data, t]);

  // Server-rendered document export: the backend draws charts from the same
  // aggregates the dashboard uses — a print-ready report, not the SPA chrome.
  const onExportReport = async () => {
    if (!id) return;
    setExporting(true);
    try {
      await openHtmlDocument(
        () => fetchSurveyReportHtml(id),
        `survey-results-${id.slice(0, 8)}.html`,
      );
    } catch {
      toast(t("dashboard.exportReportFailed"), "error");
    } finally {
      setExporting(false);
    }
  };

  const onConfirmInvite = async () => {
    if (!id) return;
    setInviting(true);
    try {
      const result = await inviteSegment(id, filters);
      toast(
        t("dashboard.invitesSent", { count: result.invited_count }) +
          (result.failed_emails.length > 0
            ? ` · ${t("dashboard.emailFailures", { count: result.failed_emails.length })}`
            : ""),
        result.failed_emails.length === 0 ? "success" : "info",
      );
      setReviewOpen(false);
    } catch (e: any) {
      // Backend returns 400 with detail on "no project to invite into"
      const detail = e?.response?.data?.detail;
      toast(detail || t("dashboard.invitesFailed"), "error");
    } finally {
      setInviting(false);
    }
  };

  if (error) {
    return (
      <div className="quanti-showcase">
        <p className="quanti-showcase__section-meta">{error}</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="quanti-showcase">
        <p className="quanti-showcase__section-meta">{t("common.loading")}</p>
      </div>
    );
  }

  return (
    <InstrumentShell
      crumbs={[
        { label: t("dashboard.crumbStudies"), to: "/studies" },
        ...(study ? [{ label: study.name, to: `/studies/${study.id}` }] : []),
        { label: data.name },
      ]}
      eyebrow={t("dashboard.eyebrow")}
      title={data.name}
      status={surveyStatusPill(data.status, t)}
      sections={surveySections(t)}
      activeSection="results"
      onSectionChange={(k) => navigate(surveySectionPath(k, data.survey_id))}
      subNavLabel={t("dashboard.sectionsNavLabel")}
      actions={
        <button
          type="button"
          className="btn btn-secondary"
          onClick={onExportReport}
          disabled={exporting || data.questions.length === 0}
          title={t("dashboard.exportPdfTitle")}
        >
          {exporting ? t("dashboard.exportPdfLoading") : t("dashboard.exportPdf")}
        </button>
      }
    >
      <div style={{ maxWidth: 1180, margin: "0 auto", padding: "var(--space-6) var(--space-5)" }}>
        <MethodologyBox
          fields={[
            {
              label: t("dashboard.sampleSize"),
              value: t("dashboard.completers", { count: data.n_completed }) +
                (data.n_started > data.n_completed ? ` · ${t("dashboard.partial", { count: data.n_started - data.n_completed })}` : ""),
            },
            {
              label: t("dashboard.fieldingWindow"),
              value: data.fielding_started_at
                ? `${formatDate(data.fielding_started_at)}${data.fielding_ended_at ? ` – ${formatDate(data.fielding_ended_at)}` : ""}`
                : "—",
            },
            {
              label: t("dashboard.completionRate"),
              value:
                data.completion_rate_percentage !== null
                  ? `${Math.round(data.completion_rate_percentage)}%`
                  : t("dashboard.belowThreshold", { count: data.min_n_threshold }),
            },
            {
              label: t("dashboard.status"),
              value: data.status.toUpperCase(),
            },
          ]}
          note={
            data.n_started < data.min_n_threshold
              ? t("dashboard.noteBelowThreshold", { count: data.min_n_threshold })
              : t("dashboard.noteWilsonPrefix") +
                String(data.min_n_threshold) +
                t("dashboard.noteWilsonSuffix")
          }
        />

        <div style={{ marginTop: "var(--space-6)" }}>
          <DashboardShell sidebar={<QuestionNav questions={data.questions} />}>
            {discoveries.length > 0 && (
              <DiscoveriesSection
                discoveries={discoveries}
                onApply={onApplyDiscovery}
              />
            )}
            <div data-bridge-target />
            <SegmentFilterRail
              questions={data.questions}
              filters={filters}
              onChange={setFilters}
            />
            {preview && preview.match_count > 0 && (
              <ScreenerBridge
                matchCount={preview.invitable_count}
                filterDescription={filterDescription}
                onInvite={() => setReviewOpen(true)}
                onSaveSegment={() =>
                  toast(t("dashboard.savedSegmentsInfo"), "info")
                }
              />
            )}
            <DashboardStrip
              items={[
                { label: t("dashboard.respondents"), value: String(data.n_started) },
                {
                  label: t("dashboard.completed"),
                  value: String(data.n_completed),
                  delta:
                    data.completion_rate_percentage !== null
                      ? t("dashboard.completionPercent", { percent: Math.round(data.completion_rate_percentage) })
                      : t("dashboard.tooSmall"),
                  deltaTone:
                    data.completion_rate_percentage !== null && data.completion_rate_percentage >= 80
                      ? "positive"
                      : "neutral",
                },
                { label: t("dashboard.questions"), value: String(data.questions.length) },
              ]}
            />

            {data.questions.length === 0 ? (
              <p className="quanti-showcase__section-meta">{t("dashboard.noQuestionsEditor")}</p>
            ) : (
              data.questions.map((q) => (
                <QuestionPanel key={q.question_id} q={q} minN={data.min_n_threshold} />
              ))
            )}
          </DashboardShell>
        </div>
      </div>

      {reviewOpen && preview && (
        <InviteReviewModal
          preview={preview}
          filterDescription={filterDescription}
          inviting={inviting}
          onCancel={() => setReviewOpen(false)}
          onConfirm={onConfirmInvite}
        />
      )}
    </InstrumentShell>
  );
}

/* ────────────────────────────────────────────────────────────────────
   Sprint 9 sub-components: segment filter rail + draft-review modal
   ──────────────────────────────────────────────────────────────────── */

function describeFilter(filter: SegmentFilter, questions: QuestionAnalytics[], t: (key: string) => string): string {
  const q = questions.find((x) => x.question_id === filter.question_id);
  const label = q?.prompt?.slice(0, 40) || t("dashboard.questionFallback");
  if (filter.operator === "lte") return `${label} ≤ ${filter.value}`;
  if (filter.operator === "gte") return `${label} ≥ ${filter.value}`;
  if (filter.operator === "eq") return `${label} = ${filter.value}`;
  if (filter.operator === "between") {
    const [lo, hi] = filter.value as [number, number];
    return `${label} between ${lo} and ${hi}`;
  }
  if (filter.operator === "in") {
    const ids = (filter.value as string[]) || [];
    return `${label} in [${ids.join(", ")}]`;
  }
  return label;
}

function SegmentFilterRail({
  questions,
  filters,
  onChange,
}: {
  questions: QuestionAnalytics[];
  filters: SegmentFilter[];
  onChange: (next: SegmentFilter[]) => void;
}) {
  const { t } = useTranslation("survey");
  const filterable = questions.filter(
    (q) => q.type === "likert" || q.type === "nps" || q.type === "mc_single" || q.type === "mc_multi",
  );
  if (filterable.length === 0) return null;

  const upsert = (next: SegmentFilter) => {
    const others = filters.filter((f) => f.question_id !== next.question_id);
    onChange([...others, next]);
  };
  const removeFor = (questionId: string) => {
    onChange(filters.filter((f) => f.question_id !== questionId));
  };

  return (
    <section
      style={{
        background: "var(--bg-surface)",
        border: "1px solid var(--border-default)",
        borderRadius: "var(--radius-md)",
        padding: "var(--space-4) var(--space-5)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-3)",
      }}
    >
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--space-3)" }}>
        <span style={{ fontSize: "var(--text-eyebrow)", fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-tertiary)" }}>
          {t("dashboard.filterRespondents")}
        </span>
        {filters.length > 0 && (
          <button type="button" className="btn btn-ghost btn-xs" onClick={() => onChange([])}>
            {t("dashboard.clearAll")}
          </button>
        )}
      </header>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
        {filterable.map((q) => (
          <QuestionFilterRow
            key={q.question_id}
            question={q}
            filter={filters.find((f) => f.question_id === q.question_id)}
            onSet={upsert}
            onClear={() => removeFor(q.question_id)}
          />
        ))}
      </div>
    </section>
  );
}

function QuestionFilterRow({
  question,
  filter,
  onSet,
  onClear,
}: {
  question: QuestionAnalytics;
  filter: SegmentFilter | undefined;
  onSet: (next: SegmentFilter) => void;
  onClear: () => void;
}) {
  const { t } = useTranslation("survey");
  const isLikertOrNps = question.type === "likert" || question.type === "nps";
  if (isLikertOrNps) {
    const op = (filter?.operator as SegmentOperator) ?? "lte";
    const value = typeof filter?.value === "number" ? (filter.value as number) : 6;
    const max = question.type === "nps" ? 10 : (((question.breakdown.histogram as any[])?.length) || 5);
    return (
      <div style={{ display: "grid", gridTemplateColumns: "1fr auto auto auto auto", gap: "var(--space-2)", alignItems: "center" }}>
        <span style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {question.prompt || t("common.untitledQuestion")}
        </span>
        <select
          value={filter ? op : ""}
          onChange={(e) => {
            const val = e.target.value as SegmentOperator | "";
            if (val === "") onClear();
            else onSet({ question_id: question.question_id, operator: val, value });
          }}
          style={{ fontFamily: "inherit", fontSize: "var(--text-sm)", padding: "4px 6px", border: "1px solid var(--border-default)", borderRadius: "var(--radius-sm)", background: "var(--bg-surface)" }}
        >
          <option value="">{t("dashboard.noFilter")}</option>
          <option value="lte">≤</option>
          <option value="gte">≥</option>
          <option value="eq">=</option>
        </select>
        {filter && (
          <input
            type="number"
            className="tabular"
            value={value}
            min={question.type === "nps" ? 0 : 1}
            max={max}
            onChange={(e) => onSet({ question_id: question.question_id, operator: op, value: Number(e.target.value) })}
            style={{ width: 64, fontFamily: "inherit", fontSize: "var(--text-sm)", padding: "4px 8px", border: "1px solid var(--border-default)", borderRadius: "var(--radius-sm)", background: "var(--bg-surface)" }}
          />
        )}
        {filter && (
          <button type="button" className="btn btn-ghost btn-xs" onClick={onClear} aria-label={t("dashboard.clearFilter")}>
            ×
          </button>
        )}
        {!filter && <span />}
        {!filter && <span />}
      </div>
    );
  }

  // mc_single / mc_multi → list checkboxes for choice IDs
  const choices = (question.breakdown.choices as Array<{ choice_id: string; label: string }>) ?? [];
  const selected = new Set<string>((filter?.value as string[]) ?? []);
  const toggle = (cid: string) => {
    const next = new Set(selected);
    if (next.has(cid)) next.delete(cid);
    else next.add(cid);
    if (next.size === 0) onClear();
    else onSet({ question_id: question.question_id, operator: "in", value: Array.from(next) });
  };
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-1)" }}>
      <span style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)" }}>
        {question.prompt || t("common.untitledQuestion")}
      </span>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
        {choices.map((c) => {
          const isOn = selected.has(c.choice_id);
          return (
            <button
              key={c.choice_id}
              type="button"
              className={`compare-chips__chip${isOn ? " compare-chips__chip--active" : ""}`}
              onClick={() => toggle(c.choice_id)}
              aria-pressed={isOn}
            >
              {c.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────
   Sprint 10: Discoveries section
   ──────────────────────────────────────────────────────────────────── */

function DiscoveriesSection({
  discoveries,
  onApply,
}: {
  discoveries: SegmentDiscovery[];
  onApply: (d: SegmentDiscovery) => void;
}) {
  const { t } = useTranslation("survey");
  return (
    <section
      aria-label={t("dashboard.discoveriesLabel")}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-3)",
      }}
    >
      <header style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: "var(--space-3)" }}>
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
            {t("dashboard.discoveriesEyebrow")}
          </div>
          <h2
            style={{
              fontFamily: "var(--font-serif)",
              fontSize: "var(--text-xl)",
              letterSpacing: "-0.015em",
              margin: "var(--space-1) 0 0",
            }}
          >
            {t("dashboard.discoveriesHeadline", { count: discoveries.length })}
          </h2>
        </div>
        <span style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)" }}>
          {t("dashboard.aiDetects")}
        </span>
      </header>
      <div className="quanti-showcase__grid-2">
        {discoveries.map((d) => (
          <DiscoveryCard key={d.id} discovery={d} onApply={() => onApply(d)} />
        ))}
      </div>
    </section>
  );
}

function DiscoveryCard({
  discovery,
  onApply,
}: {
  discovery: SegmentDiscovery;
  onApply: () => void;
}) {
  const { t } = useTranslation("survey");
  const confidenceLabel: Record<DiscoveryConfidence, string> = {
    directional: t("dashboard.confidence.directional"),
    supported: t("dashboard.confidence.supported"),
    strong: t("dashboard.confidence.strong"),
  };
  return (
    <article
      style={{
        background: "var(--bg-surface)",
        border: "1px solid var(--border-default)",
        borderLeft: "3px solid var(--brand-500)",
        borderRadius: "var(--radius-md)",
        padding: "var(--space-5)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-3)",
      }}
    >
      <header style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "var(--space-3)" }}>
        <h3
          style={{
            fontFamily: "var(--font-serif)",
            fontSize: "var(--text-lg)",
            fontWeight: 600,
            letterSpacing: "-0.015em",
            lineHeight: 1.3,
            margin: 0,
            color: "var(--text-primary)",
          }}
        >
          {discovery.title}
        </h3>
        <span className={`confidence-pill confidence-pill--${discovery.confidence}`}>
          <span className="confidence-pill__dot" aria-hidden="true" />
          {confidenceLabel[discovery.confidence]}
        </span>
      </header>
      <p style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)", lineHeight: 1.5, margin: 0 }}>
        {discovery.description}
      </p>
      <div style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)" }} className="tabular">
        {t("dashboard.basedOnQuestion")} "<em>{shortenPrompt(discovery.metric_question_prompt, 70)}</em>"
        {discovery.metric_choice_label ? <> · {t("dashboard.choice")} <em>{discovery.metric_choice_label}</em></> : null}
      </div>
      <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-1)" }}>
        <button type="button" className="btn btn-primary" onClick={onApply}>
          {t("dashboard.interviewSegment")}
        </button>
      </div>
    </article>
  );
}

function shortenPrompt(prompt: string, max: number): string {
  if (prompt.length <= max) return prompt;
  return prompt.slice(0, max - 1).trimEnd() + "…";
}

function InviteReviewModal({
  preview,
  filterDescription,
  inviting,
  onCancel,
  onConfirm,
}: {
  preview: SegmentPreview;
  filterDescription: string;
  inviting: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const { t } = useTranslation("survey");
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("dashboard.reviewModal.ariaLabel")}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(13, 15, 26, 0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "var(--space-5)",
        zIndex: 100,
      }}
      onClick={onCancel}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--bg-surface)",
          borderRadius: "var(--radius-lg)",
          maxWidth: 560,
          width: "100%",
          padding: "var(--space-6)",
          boxShadow: "var(--shadow-lg)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-4)",
        }}
      >
        <div>
          <div style={{ fontSize: "var(--text-eyebrow)", fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--brand-600)" }}>
            {t("dashboard.reviewModal.eyebrow")}
          </div>
          <h2 style={{ fontFamily: "var(--font-serif)", fontSize: "var(--text-xl)", letterSpacing: "-0.015em", marginTop: "var(--space-2)" }}>
            <span className="tabular">{preview.invitable_count}</span> {t("dashboard.reviewModal.invitesReady", { count: preview.invitable_count })}
          </h2>
          <p style={{ color: "var(--text-secondary)", fontSize: "var(--text-sm)", marginTop: "var(--space-2)" }}>
            {filterDescription}
          </p>
        </div>

        {preview.sample_invitees.length > 0 && (
          <div>
            <div style={{ fontSize: "var(--text-eyebrow)", fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-tertiary)", marginBottom: "var(--space-2)" }}>
              {t("dashboard.reviewModal.sampleRecipients")}
            </div>
            <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 4 }}>
              {preview.sample_invitees.map((p) => (
                <li
                  key={p.email}
                  style={{
                    padding: "var(--space-1) var(--space-2)",
                    background: "var(--bg-base)",
                    border: "1px solid var(--border-subtle)",
                    borderRadius: "var(--radius-sm)",
                    fontFamily: "var(--font-mono)",
                    fontSize: "var(--text-xs)",
                    color: "var(--text-secondary)",
                  }}
                >
                  {p.email}
                </li>
              ))}
              {preview.invitable_count > preview.sample_invitees.length && (
                <li style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)", paddingLeft: "var(--space-2)" }}>
                  {t("dashboard.reviewModal.andMore", { n: preview.invitable_count - preview.sample_invitees.length })}
                </li>
              )}
            </ul>
          </div>
        )}

        {preview.skipped_anonymous_count > 0 && (
          <div className="methodology-box methodology-box--inline">
            {t("dashboard.reviewModal.skippedAnonymous", { count: preview.skipped_anonymous_count })}
          </div>
        )}

        <p style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)" }}>
          {t("dashboard.reviewModal.creditNote")}
        </p>

        <div style={{ display: "flex", gap: "var(--space-3)", justifyContent: "flex-end", marginTop: "var(--space-2)" }}>
          <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={inviting}>
            {t("dashboard.reviewModal.cancel")}
          </button>
          <button type="button" className="btn btn-primary" onClick={onConfirm} disabled={inviting}>
            {inviting ? t("dashboard.reviewModal.sending") : t("dashboard.reviewModal.sendInvites", { count: preview.invitable_count })}
          </button>
        </div>
      </div>
    </div>
  );
}

function QuestionNav({ questions }: { questions: QuestionAnalytics[] }) {
  const { t } = useTranslation("survey");
  return (
    <nav className="shell-nav" aria-label={t("dashboard.questionNavLabel")}>
      <div className="shell-nav__group">
        <span className="shell-nav__group-label">{t("dashboard.questions")}</span>
        {questions.map((q, i) => (
          <a key={q.question_id} href={`#q-${q.question_id}`} className="shell-nav__item">
            <span style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)" }} className="tabular">
              {String(i + 1).padStart(2, "0")}
            </span>
            <span style={{ flex: 1, marginLeft: 8, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {q.prompt || t("common.untitledQuestion")}
            </span>
            <span className="shell-nav__count">{q.n_answered}</span>
          </a>
        ))}
      </div>
    </nav>
  );
}

function QuestionPanel({ q, minN }: { q: QuestionAnalytics; minN: number }) {
  const { t } = useTranslation("survey");
  const typeLabel = ["likert", "nps", "mc_single", "mc_multi", "open_text", "short_text"].includes(q.type)
    ? t(`dashboard.typeLabels.${q.type}`)
    : q.type;
  const eyebrow = `${typeLabel} · Q${q.sort_order || ""}`.replace(/ \· Q$/, "");
  // ChartCard handles the small-n warning automatically when n_answered < minN.
  return (
    <div id={`q-${q.question_id}`} style={{ scrollMarginTop: "var(--space-6)" }}>
      <ChartCard
        eyebrow={eyebrow}
        takeaway={q.prompt || t("common.untitledQuestion")}
        n={q.n_answered}
        minN={minN}
      >
        <BreakdownRenderer q={q} minN={minN} />
      </ChartCard>
    </div>
  );
}

function BreakdownRenderer({ q, minN }: { q: QuestionAnalytics; minN: number }) {
  const { t } = useTranslation("survey");
  if (q.n_answered === 0) {
    return <p className="quanti-showcase__section-meta">{t("dashboard.noResponsesYet")}</p>;
  }
  if (q.type === "likert" || q.type === "nps") {
    const histogram = (q.breakdown.histogram as Array<{
      bucket: number;
      count: number;
      percentage: number | null;
    }>) ?? [];
    const max = Math.max(1, ...histogram.map((h) => h.count));
    const isBelowMinN = q.n_answered < minN;
    return (
      <div>
        {q.type === "nps" && typeof q.breakdown.nps_score === "number" && (
          <div
            style={{
              display: "flex",
              alignItems: "baseline",
              gap: "var(--space-3)",
              marginBottom: "var(--space-3)",
            }}
          >
            <span
              className="tabular"
              style={{
                fontFamily: "var(--font-serif)",
                fontSize: "var(--text-2xl)",
                fontWeight: 700,
                color: "var(--brand-700)",
              }}
            >
              {(q.breakdown.nps_score as number) >= 0 ? "+" : ""}
              {q.breakdown.nps_score as number}
            </span>
            <span style={{ fontSize: "var(--text-xs)", letterSpacing: "0.08em", color: "var(--text-tertiary)", textTransform: "uppercase" }}>
              {t("dashboard.npsScore")}
            </span>
          </div>
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)", paddingTop: "var(--space-2)" }}>
          {histogram.map((h) => (
            <div
              key={h.bucket}
              style={{ display: "grid", gridTemplateColumns: "32px 1fr 64px", gap: "var(--space-3)", alignItems: "center" }}
            >
              <span className="tabular" style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)" }}>
                {h.bucket}
              </span>
              <div style={{ height: 10, background: "var(--bg-sunken)", borderRadius: 4, overflow: "hidden" }}>
                <div
                  style={{
                    width: `${(h.count / max) * 100}%`,
                    height: "100%",
                    background: q.type === "nps"
                      ? h.bucket <= 6
                        ? "var(--viz-negative)"
                        : h.bucket <= 8
                          ? "var(--viz-neutral)"
                          : "var(--viz-positive)"
                      : "var(--viz-positive)",
                  }}
                />
              </div>
              <span className="tabular" style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)", textAlign: "right" }}>
                {isBelowMinN
                  ? `${h.count}/${q.n_answered}`
                  : h.percentage !== null
                    ? `${Math.round(h.percentage)}%`
                    : `${h.count}/${q.n_answered}`}
              </span>
            </div>
          ))}
        </div>
        {isBelowMinN && (
          <div style={{ marginTop: "var(--space-3)" }}>
            <SmallNWarning n={q.n_answered} minN={minN} />
          </div>
        )}
        {q.mean !== null && (
          <div className="tabular" style={{ marginTop: "var(--space-3)", fontSize: "var(--text-xs)", color: "var(--text-tertiary)" }}>
            {t("dashboard.mean", { value: q.mean.toFixed(2) })}
          </div>
        )}
      </div>
    );
  }
  if (q.type === "mc_single" || q.type === "mc_multi") {
    const choices = (q.breakdown.choices as Array<{
      choice_id: string;
      label: string;
      count: number;
      percentage: number | null;
    }>) ?? [];
    const max = Math.max(1, ...choices.map((c) => c.count));
    const isBelowMinN = q.n_answered < minN;
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)", paddingTop: "var(--space-2)" }}>
        {choices.map((c) => (
          <div
            key={c.choice_id}
            style={{ display: "grid", gridTemplateColumns: "180px 1fr 64px", gap: "var(--space-3)", alignItems: "center" }}
          >
            <span style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {c.label}
            </span>
            <div style={{ height: 10, background: "var(--bg-sunken)", borderRadius: 4, overflow: "hidden" }}>
              <div style={{ width: `${(c.count / max) * 100}%`, height: "100%", background: "var(--viz-positive)" }} />
            </div>
            <span className="tabular" style={{ fontSize: "var(--text-xs)", color: "var(--text-secondary)", textAlign: "right" }}>
              {isBelowMinN
                ? `${c.count}/${q.n_answered}`
                : c.percentage !== null
                  ? `${Math.round(c.percentage)}%`
                  : `${c.count}/${q.n_answered}`}
            </span>
          </div>
        ))}
        {isBelowMinN && (
          <div style={{ marginTop: "var(--space-3)" }}>
            <SmallNWarning n={q.n_answered} minN={minN} />
          </div>
        )}
      </div>
    );
  }
  if (q.type === "open_text" || q.type === "short_text") {
    const sample = (q.breakdown.sample as string[]) ?? [];
    const total = (q.breakdown.total_texts as number) ?? sample.length;
    return (
      <div>
        <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
          {sample.slice(0, 5).map((text, i) => (
            <li
              key={i}
              style={{
                padding: "var(--space-2) var(--space-3)",
                background: "var(--bg-base)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-sm)",
                fontFamily: "var(--font-serif)",
                fontStyle: "italic",
                fontSize: "var(--text-sm)",
                color: "var(--text-primary)",
                lineHeight: 1.5,
              }}
            >
              "{text}"
            </li>
          ))}
        </ul>
        <p style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)", marginTop: "var(--space-2)" }}>
          {t("dashboard.textResponsesSummary", { shown: Math.min(5, sample.length), total })}
        </p>
      </div>
    );
  }
  return null;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(i18n.language, { month: "short", day: "numeric", year: "numeric" });
}
