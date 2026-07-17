import { CSSProperties, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import {
  ReportCatalogEntry,
  ReportKind,
  StudySummary,
  fetchProjectReportHtml,
  fetchStudyReportHtml,
  fetchSurveyReportHtml,
  listReportCatalog,
  listStudies,
} from "../api/studies";
import { SynthesisSummary, listSyntheses } from "../api/synthesis";
import { openHtmlDocument } from "../utils/openHtmlDocument";
import { DecisionMemoSection } from "../components/DecisionMemoSection";
import { HubShell } from "../components/HubShell";
import { useToast } from "../components/Toast";

/**
 * Reports — `/reports`, the library of every generated report document.
 *
 * This is not a launcher into studies: each row opens the finished report
 * itself (the print-ready HTML the study/analysis produced), the same way
 * decision memos open. The hub lists every ready report by its **type**, and
 * each row wears the ink of the document it opens — mirroring the three
 * palettes in services/report_export.py (_PALETTES):
 *
 *   • Decision reports — the mixed-methods superset a study produces (bordeaux)
 *   • Qualitative findings — the interview-only analysis (green)
 *   • Survey results — the quantitative survey document (blue)
 *   • Decision memos — cross-study syntheses (bordeaux; DecisionMemoSection)
 *
 * A mixed-methods study contributes all three of the first families: its two
 * single-method component reports plus the Decision report that supersets them,
 * so the reader can open either the components or the merged board document.
 */

// Mirror of report_export.py _PALETTES + _BASE_DOC_CSS neutrals. Keep in sync.
export interface ReportInk {
  accent: string;
  tint: string;
  deep: string;
  paper: string;
  ink: string;
  ink2: string;
  ink3: string;
  rule: string;
}

// Shared warm-paper neutrals (from _BASE_DOC_CSS); only accent/tint/deep vary.
const PAPER = { paper: "#fcfcfa", ink: "#17201b", ink2: "#4c5852", ink3: "#7a847e", rule: "#dfe5e0" };

const DECISION_INK: ReportInk = { accent: "#7c2434", tint: "#f8eef0", deep: "#4d1420", ...PAPER };
const QUAL_INK: ReportInk = { accent: "#1d5c3f", tint: "#eef4ef", deep: "#10382a", ...PAPER };
const SURVEY_INK: ReportInk = { accent: "#1e4a73", tint: "#edf2f8", deep: "#132f4b", ...PAPER };

// Bordeaux is the page's own ink (headings, memos section).
export const REPORT_INK = DECISION_INK;

/** A report row styled as the document it opens: warm paper, a coloured spine
 *  down the left edge, the report rule for its border. */
function rowStyleFor(ink: ReportInk): CSSProperties {
  return {
    display: "flex",
    alignItems: "center",
    gap: "var(--space-4)",
    flexWrap: "wrap",
    textAlign: "left",
    background: ink.paper,
    border: `1px solid ${ink.rule}`,
    borderLeft: `3px solid ${ink.accent}`,
    borderRadius: "var(--radius-md)",
    padding: "var(--space-3) var(--space-4)",
    color: ink.ink,
  };
}

export const reportRowStyle = rowStyleFor(DECISION_INK);

function ReportBadge({ label, ink }: { label: string; ink: ReportInk }) {
  return (
    <span
      style={{
        fontSize: "var(--text-eyebrow)",
        fontWeight: 600,
        letterSpacing: "0.06em",
        textTransform: "uppercase",
        color: ink.accent,
        background: ink.tint,
        borderRadius: 999,
        padding: "3px 10px",
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </span>
  );
}

/** Section eyebrow in the app-blue default, re-inked to the section's palette
 *  so each family reads as the document colour it opens. */
function ReportEyebrow({ children, ink }: { children: React.ReactNode; ink: ReportInk }) {
  return (
    <div
      style={{
        fontSize: "var(--text-eyebrow)",
        fontWeight: 600,
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        color: ink.accent,
      }}
    >
      {children}
    </div>
  );
}

/** A group of report rows for one report type, in that type's ink. */
function ReportSection({
  ink,
  eyebrow,
  title,
  sub,
  entries,
  badge,
  openLabel,
  openingLabel,
  openingId,
  evidenceLabel,
  demoBadge,
  onOpen,
}: {
  ink: ReportInk;
  eyebrow: string;
  title: string;
  sub: string;
  entries: ReportCatalogEntry[];
  badge: string;
  openLabel: string;
  openingLabel: string;
  openingId: string | null;
  evidenceLabel: (e: ReportCatalogEntry) => string;
  demoBadge: string;
  onOpen: (e: ReportCatalogEntry) => void;
}) {
  if (entries.length === 0) return null;
  return (
    <section className="quanti-showcase__section">
      <div style={{ marginBottom: "var(--space-4)" }}>
        <ReportEyebrow ink={ink}>{eyebrow}</ReportEyebrow>
        <h2 style={{ fontSize: "var(--text-xl)", fontWeight: 700, margin: 0, color: ink.ink }}>{title}</h2>
        <p style={{ color: ink.ink3, fontSize: "var(--text-sm)", margin: "4px 0 0" }}>{sub}</p>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
        {entries.map((e) => {
          const rowId = rowKey(e);
          const opening = openingId === rowId;
          return (
            <button
              key={rowId}
              type="button"
              disabled={opening}
              onClick={() => onOpen(e)}
              style={{ ...rowStyleFor(ink), cursor: opening ? "progress" : "pointer" }}
            >
              <ReportBadge label={badge} ink={ink} />
              <div style={{ flex: 1, minWidth: 220 }}>
                <div style={{ fontWeight: 600 }}>
                  {e.study_name}
                  {e.is_demo && <span className="hub-demo-badge">{demoBadge}</span>}
                </div>
                <div style={{ fontSize: "var(--text-xs)", color: ink.ink3 }}>{evidenceLabel(e)}</div>
              </div>
              <span
                style={{
                  fontSize: "var(--text-sm)",
                  fontWeight: 600,
                  color: ink.accent,
                  whiteSpace: "nowrap",
                }}
              >
                <span aria-hidden="true">📄 </span>
                {opening ? openingLabel : openLabel}
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

/** Stable per-row key/opening-id — the document target within a study. */
function rowKey(e: ReportCatalogEntry): string {
  return `${e.kind}:${e.project_id ?? e.survey_id ?? e.analysis_id ?? e.study_id}`;
}

export default function Reports() {
  const { t } = useTranslation("dashboard");
  const { toast } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();

  const [studies, setStudies] = useState<StudySummary[] | null>(null);
  const [catalog, setCatalog] = useState<ReportCatalogEntry[] | null>(null);
  const [memos, setMemos] = useState<SynthesisSummary[] | null>(null);
  // Which report row is currently being fetched (prevents double-open).
  const [openingId, setOpeningId] = useState<string | null>(null);
  // ?newMemo=1 (from the workspace NBA / studies sidecar) opens the create
  // modal in DecisionMemoSection via its openSignal prop.
  const [memoOpenSignal, setMemoOpenSignal] = useState(0);

  useEffect(() => {
    listStudies()
      .then(setStudies)
      .catch(() => toast(t("studyList.loadError"), "error"));
    listReportCatalog()
      .then(setCatalog)
      .catch(() => toast(t("reports.openError"), "error"));
  }, [toast, t]);

  const refreshMemos = () => {
    listSyntheses()
      .then(setMemos)
      .catch(() => toast(t("decisionMemos.loadError"), "error"));
  };
  useEffect(refreshMemos, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (searchParams.get("newMemo") === "1") {
      setMemoOpenSignal((n) => n + 1);
      setSearchParams(
        (sp) => {
          const next = new URLSearchParams(sp);
          next.delete("newMemo");
          return next;
        },
        { replace: true },
      );
    }
  }, [searchParams, setSearchParams]);

  const activeStudies = useMemo(
    () => (studies ?? []).filter((s) => !s.archived_at),
    [studies],
  );

  const byKind = (kind: ReportKind) => (catalog ?? []).filter((e) => e.kind === kind);
  const decisionReports = useMemo(() => byKind("decision"), [catalog]);
  const qualReports = useMemo(() => byKind("qualitative"), [catalog]);
  const surveyReports = useMemo(() => byKind("survey"), [catalog]);

  const readyMemoCount = useMemo(
    () => (memos ?? []).filter((m) => m.status === "ready").length,
    [memos],
  );
  const reportsCount = (catalog?.length ?? 0) + readyMemoCount;

  // Open a report document directly in a new tab — openHtmlDocument claims the
  // tab synchronously (mobile-safe), then the callback fetches the right
  // print-ready HTML for the row's report type.
  const openReport = async (e: ReportCatalogEntry) => {
    const id = rowKey(e);
    setOpeningId(id);
    try {
      await openHtmlDocument(async () => {
        if (e.kind === "decision" && e.analysis_id) {
          return fetchStudyReportHtml(e.study_id, e.analysis_id);
        }
        if (e.kind === "qualitative" && e.project_id) {
          return fetchProjectReportHtml(e.project_id);
        }
        if (e.kind === "survey" && e.survey_id) {
          return fetchSurveyReportHtml(e.survey_id);
        }
        throw new Error("report_not_ready");
      }, `${e.kind}-report-${e.study_id.slice(0, 8)}.html`);
    } catch {
      toast(t("reports.openError"), "error");
    } finally {
      setOpeningId(null);
    }
  };

  const interviewsLabel = (n: number) => t("hub.evidence.interviews", { count: n });
  const responsesLabel = (n: number) => t("hub.evidence.responses", { count: n });
  const bothLabel = (e: ReportCatalogEntry) => {
    const parts: string[] = [];
    if (e.interviews > 0) parts.push(interviewsLabel(e.interviews));
    if (e.responses > 0) parts.push(responsesLabel(e.responses));
    return parts.join(" · ") || "—";
  };

  const hasAnyReport = (catalog?.length ?? 0) > 0 || (memos ?? []).length > 0;
  const demoBadge = t("hub.demoBadge");
  const loading = studies === null || catalog === null;

  return (
    <HubShell active="reports" studies={studies} memoCount={reportsCount} studyCount={studies?.length}>
      <div className="hub-canvas">
        <header className="hub-head">
          <div className="hub-head__text">
            <ReportEyebrow ink={REPORT_INK}>{t("reports.eyebrow")}</ReportEyebrow>
            <h1 className="hub-head__title">{t("reports.title")}</h1>
            <p className="hub-head__sub">{t("reports.sub")}</p>
          </div>
        </header>

        {loading ? (
          <div className="hub-table-wrap" aria-hidden="true">
            {[0, 1, 2].map((i) => (
              <div key={i} className="hub-skel-row">
                <span className="hub-skel" style={{ width: 70, height: 18, borderRadius: 999 }} />
                <span className="hub-skel" style={{ width: "42%", height: 12 }} />
                <span className="hub-skel" style={{ width: 80, height: 10 }} />
              </div>
            ))}
          </div>
        ) : !hasAnyReport ? (
          <div
            style={{
              background: REPORT_INK.paper,
              border: `1px dashed ${REPORT_INK.rule}`,
              borderRadius: "var(--radius-md)",
              padding: "var(--space-8)",
              textAlign: "center",
            }}
          >
            <p style={{ color: REPORT_INK.ink2, maxWidth: 520, margin: "0 auto", lineHeight: 1.5 }}>
              {t("reports.emptyAll")}
            </p>
          </div>
        ) : (
          <>
            {/* ── Decision reports (bordeaux) — the mixed-methods superset ── */}
            <ReportSection
              ink={DECISION_INK}
              eyebrow={t("reports.studyReports.eyebrow")}
              title={t("reports.studyReports.title")}
              sub={t("reports.studyReports.sub")}
              entries={decisionReports}
              badge={t("reports.studyReports.badge")}
              openLabel={t("reports.studyReports.open")}
              openingLabel={t("reports.studyReports.opening")}
              openingId={openingId}
              evidenceLabel={bothLabel}
              demoBadge={demoBadge}
              onOpen={openReport}
            />

            {/* ── Qualitative findings (green) — interview-only analysis ──── */}
            <ReportSection
              ink={QUAL_INK}
              eyebrow={t("reports.qualReports.eyebrow")}
              title={t("reports.qualReports.title")}
              sub={t("reports.qualReports.sub")}
              entries={qualReports}
              badge={t("reports.qualReports.badge")}
              openLabel={t("reports.qualReports.open")}
              openingLabel={t("reports.qualReports.opening")}
              openingId={openingId}
              evidenceLabel={(e) => interviewsLabel(e.interviews)}
              demoBadge={demoBadge}
              onOpen={openReport}
            />

            {/* ── Survey results (blue) — quantitative survey document ───── */}
            <ReportSection
              ink={SURVEY_INK}
              eyebrow={t("reports.surveyReports.eyebrow")}
              title={t("reports.surveyReports.title")}
              sub={t("reports.surveyReports.sub")}
              entries={surveyReports}
              badge={t("reports.surveyReports.badge")}
              openLabel={t("reports.surveyReports.open")}
              openingLabel={t("reports.surveyReports.opening")}
              openingId={openingId}
              evidenceLabel={(e) => responsesLabel(e.responses)}
              demoBadge={demoBadge}
              onOpen={openReport}
            />

            {/* ── Decision memos (bordeaux) ─────────────────────────────── */}
            {/* DecisionMemoSection self-guards: renders create + list at ≥2
                studies, returns null below that. It wears the report's
                bordeaux ink (spine, warm paper) via the `ink` prop. */}
            <DecisionMemoSection
              studies={activeStudies}
              memos={memos}
              onRefresh={refreshMemos}
              openSignal={memoOpenSignal}
              ink={{ ...DECISION_INK, rowStyle: reportRowStyle }}
            />
          </>
        )}
      </div>
    </HubShell>
  );
}
