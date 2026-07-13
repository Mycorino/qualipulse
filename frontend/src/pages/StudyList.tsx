import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { StudySummary, listStudies, studyEntryPath } from "../api/studies";
import { SynthesisSummary, listSyntheses, openSynthesisMemoInNewTab } from "../api/synthesis";
import {
  DEMO_TOUR_DONE_KEY,
  DemoCallout,
  armDemoTour,
  dismissFirstRunHint,
  firstRunHintDismissed,
  getDemoTourPhase,
  isDemoTourArmed,
  isDemoTourDone,
} from "../components/DemoTour";
import { DecisionMemoSection } from "../components/DecisionMemoSection";
import { useToast } from "../components/Toast";
import { HubShell } from "../components/HubShell";
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
 * Hub redesign (this file): the flat card grid became a real workspace —
 * navy rail (HubShell), quiet header, one next-best-action strip, a
 * filterable/searchable studies list with a table ↔ card toggle, and a
 * sidecar carrying workspace stats plus the latest decision memo. The
 * visual language extends the marketing page: navy emphasis surfaces,
 * the brand-strip accent, mono meta text.
 *
 * Studies are auto-created on first survey/project creation (Decision 8);
 * "+ New study" opens the angle picker.
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

/** Lifecycle pill per study, derived from the same deterministic resolver
 *  that powers the NBA — one source of truth for "what state is this in". */
type StudyStatus = "draft" | "collecting" | "ready" | "complete";

const STATUS_BY_ACTION: Partial<Record<NbaActionType, StudyStatus>> = {
  set_up_study: "draft",
  collect_study: "collecting",
  analyze_study: "ready",
  done: "complete",
};

type StatusFilter = "all" | "attention" | "collecting" | "complete";
type HubView = "table" | "cards";

const HUB_VIEW_KEY = "hub_view_v1";

interface StudyRow {
  study: StudySummary;
  mix: InstrumentMix;
  action: NextAction;
  status: StudyStatus;
}

export default function StudyList() {
  const { t } = useTranslation("dashboard");
  const [studies, setStudies] = useState<StudySummary[] | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  // ?new=1 opens the picker directly — used by the demo tour's final CTA.
  const [pickerOpen, setPickerOpen] = useState(() => searchParams.get("new") === "1");
  const [nudges, setNudges] = useState<Nudge[]>([]);
  // Decision memos live here (not in DecisionMemoSection) because they also
  // feed the workspace NBA rungs + memo nudges.
  const [memos, setMemos] = useState<SynthesisSummary[] | null>(null);
  const [memoOpenSignal, setMemoOpenSignal] = useState(0);
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [query, setQuery] = useState("");
  // First-run greeter: a gentle one-time callout ringing the seeded example.
  // Shown only on the collapsed first-run home and only until dismissed or
  // the tour has been taken.
  const [firstRunHintOpen, setFirstRunHintOpen] = useState(
    () => !firstRunHintDismissed() && !isDemoTourDone(),
  );
  const [view, setView] = useState<HubView>(() =>
    localStorage.getItem(HUB_VIEW_KEY) === "cards" ? "cards" : "table",
  );
  const { toast } = useToast();
  const navigate = useNavigate();
  const location = useLocation();
  const announce = useNudgeAnnounce(nudges);

  // The shell's palette routes "New study" here as /studies?new=1 — react
  // to the param appearing while mounted, then strip it so refresh/back
  // doesn't reopen the picker.
  useEffect(() => {
    if (searchParams.get("new") === "1") {
      setPickerOpen(true);
      setSearchParams(
        (sp) => {
          const next = new URLSearchParams(sp);
          next.delete("new");
          return next;
        },
        { replace: true },
      );
    }
  }, [searchParams, setSearchParams]);

  // The rail's "Decision memos" item lands on /studies#decision-memos from
  // any page — scroll once the section has data to render.
  useEffect(() => {
    if (location.hash !== "#decision-memos" || studies === null) return;
    const timer = window.setTimeout(() => {
      document.getElementById("decision-memos")?.scrollIntoView({ behavior: "smooth" });
    }, 80);
    return () => window.clearTimeout(timer);
  }, [location.hash, studies]);

  useEffect(() => {
    listStudies()
      .then(setStudies)
      .catch(() => toast(t("studyList.loadError"), "error"));
  }, [toast, t]);

  const refreshMemos = useCallback(() => {
    listSyntheses()
      .then(setMemos)
      .catch(() => toast(t("decisionMemos.loadError"), "error"));
  }, [toast, t]);

  useEffect(() => {
    refreshMemos();
  }, [refreshMemos]);

  // Onboarding hands off here with ?tour=1. The tour never auto-navigates:
  // the researcher gets to see their home first, then a callout points at
  // the demo study row and *they* click their way in. The demo is seeded in
  // a backend background thread right after onboarding completes, so it may
  // not be in the list yet — re-fetch briefly until it lands. On timeout
  // (seed failed or account predates demos) just drop the param quietly.
  const stripTourParam = useCallback(() => {
    setSearchParams(
      (sp) => {
        const next = new URLSearchParams(sp);
        next.delete("tour");
        return next;
      },
      { replace: true },
    );
  }, [setSearchParams]);
  const [tourStudyId, setTourStudyId] = useState<string | null>(null);
  const [tourAttempts, setTourAttempts] = useState(0);
  const [memoTourDismissed, setMemoTourDismissed] = useState(false);
  const tourRequested = searchParams.get("tour") === "1";
  useEffect(() => {
    if (!tourRequested) return;
    // The memo phase points at the decision-memo card, not the study row —
    // handled separately below; don't re-arm the study-row callout here.
    if (getDemoTourPhase() === "memo") return;
    if (localStorage.getItem(DEMO_TOUR_DONE_KEY) === "1") {
      stripTourParam();
      return;
    }
    if (studies === null) return; // initial load still in flight
    const demos = studies.filter((s) => s.is_demo && !s.archived_at);
    if (demos.length) {
      // The seeder backdates the flagship study furthest — oldest wins.
      const flagship = [...demos].sort((a, b) => a.created_at.localeCompare(b.created_at))[0];
      armDemoTour();
      setTourStudyId(flagship.id);
      return;
    }
    if (tourAttempts >= 8) {
      stripTourParam();
      return;
    }
    const timer = window.setTimeout(() => {
      listStudies()
        .then(setStudies)
        .catch(() => {
          /* transient — the attempt bump below retries */
        })
        .finally(() => setTourAttempts((n) => n + 1));
    }, 1200);
    return () => window.clearTimeout(timer);
  }, [tourRequested, studies, tourAttempts, stripTourParam]);

  // Detect studies that gained a report, memos that finished generating,
  // and memos that went stale since the researcher's last visit.
  useEffect(() => {
    if (!studies) return;
    setNudges(
      detectWorkspaceNudges(
        studies.map((s) => ({ id: s.id, name: s.name, hasReport: s.has_report })),
        (memos ?? []).map((m) => ({
          id: m.id,
          name: m.name,
          status: m.status,
          stale: m.stale ?? false,
        })),
      ),
    );
  }, [studies, memos]);

  const setViewPersisted = (v: HubView) => {
    setView(v);
    localStorage.setItem(HUB_VIEW_KEY, v);
  };

  const scrollToMemos = useCallback(() => {
    document.getElementById("decision-memos")?.scrollIntoView({ behavior: "smooth" });
  }, []);

  // The copilot's portfolio-triage suggestion — which study needs you.
  const runWorkspaceAction = (a: NextAction) => {
    if (a.actionType === "start_study") setPickerOpen(true);
    else if (a.actionType === "generate_memo" || a.actionType === "refresh_memo") {
      setMemoOpenSignal((n) => n + 1);
      scrollToMemos();
    } else if (a.targetId) navigate(`/studies/${a.targetId}`);
  };

  const rows = useMemo<StudyRow[]>(() => {
    return (studies ?? []).map((s) => {
      const action = resolveStudySummaryAction(toNbaSummary(s));
      return {
        study: s,
        mix: instrumentMix(s),
        action,
        status: STATUS_BY_ACTION[action.actionType] ?? "collecting",
      };
    });
  }, [studies]);

  const counts = useMemo(
    () => ({
      all: rows.length,
      attention: rows.filter((r) => r.action.kind === "do").length,
      collecting: rows.filter((r) => r.status === "collecting").length,
      complete: rows.filter((r) => r.status === "complete").length,
    }),
    [rows],
  );

  const visibleRows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return rows.filter((r) => {
      if (filter === "attention" && r.action.kind !== "do") return false;
      if (filter === "collecting" && r.status !== "collecting") return false;
      if (filter === "complete" && r.status !== "complete") return false;
      if (q && !r.study.name.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [rows, filter, query]);

  // Workspace-level totals describe the researcher's OWN work, so they
  // exclude the seeded showcase study entirely — study count and evidence
  // alike. Counting the demo's études but not its interviews/responses
  // (as it did before) reads as broken: "3 studies, 0 data" sitting above
  // a visibly-completed demo showing 4 interviews / 44 responses. Demo rows
  // stay visible in the list, badged, and still counted by the nav tabs.
  const hasDemo = useMemo(() => (studies ?? []).some((s) => s.is_demo), [studies]);
  const totals = useMemo(
    () => ({
      studies: rows.reduce((n, r) => n + (r.study.is_demo ? 0 : 1), 0),
      interviews: rows.reduce(
        (n, r) => n + (r.study.is_demo ? 0 : r.study.completed_interview_count),
        0,
      ),
      responses: rows.reduce(
        (n, r) => n + (r.study.is_demo ? 0 : r.study.completed_response_count),
        0,
      ),
    }),
    [rows],
  );

  // Studies that can join a cross-study decision memo (server requires a
  // ready analysis per study) — gates the sidecar CTA so it never leads to
  // a request the backend would reject.
  const memoEligibleCount = useMemo(
    () => (studies ?? []).filter((s) => s.has_ready_analysis).length,
    [studies],
  );

  const readyMemos = useMemo(
    () =>
      (memos ?? [])
        .filter((m) => m.status === "ready")
        .sort((a, b) => (b.generated_at ?? "").localeCompare(a.generated_at ?? "")),
    [memos],
  );
  const generatingMemo = (memos ?? []).some((m) => m.status === "generating");
  const highlightMemo = readyMemos[0] ?? null;

  const openMemo = async (id: string) => {
    try {
      await openSynthesisMemoInNewTab(id);
    } catch {
      toast(t("decisionMemos.openError"), "error");
    }
  };

  const evidenceLabel = (s: StudySummary, status: StudyStatus) => {
    const parts: string[] = [];
    if (s.completed_interview_count > 0) {
      parts.push(t("hub.evidence.interviews", { count: s.completed_interview_count }));
    }
    if (s.completed_response_count > 0) {
      parts.push(t("hub.evidence.responses", { count: s.completed_response_count }));
    }
    if (parts.length) return parts.join(" · ");
    // "Collecting" + a bare dash reads as contradictory — say what's
    // actually happening: the links are live, nothing has come in yet.
    return status === "collecting" ? t("hub.evidence.waiting") : "—";
  };

  // Single-instrument studies open their one instrument directly — the
  // workspace hop added a click without adding information. It stays one
  // breadcrumb away on the instrument page.
  const openStudy = (s: StudySummary) => navigate(studyEntryPath(s));

  const renderTable = () => (
    <div className="hub-table-wrap">
      <table className="hub-table">
        <thead>
          <tr>
            <th>{t("hub.table.study")}</th>
            <th>{t("hub.table.status")}</th>
            <th>{t("hub.table.evidence")}</th>
            <th className="hub-table__next-col">{t("hub.table.next")}</th>
          </tr>
        </thead>
        <tbody>
          {visibleRows.map(({ study: s, mix, action, status }) => (
            <tr
              key={s.id}
              tabIndex={0}
              data-tour={s.id === tourStudyId ? "demo-study-row" : undefined}
              onClick={() => openStudy(s)}
              onKeyDown={(e) => {
                if (e.key === "Enter") openStudy(s);
              }}
            >
              <td className="hub-table__name">
                {s.name}
                {s.is_demo && <span className="hub-demo-badge">{t("hub.demoBadge")}</span>}
                <span className="hub-table__meta">
                  <MixGlyph mix={mix} /> {t(`studyList.studyType.${mix}`).toLowerCase()}
                </span>
              </td>
              <td>
                <span className={`hub-status hub-status--${status}`}>
                  {status === "collecting" && <i aria-hidden="true" />}
                  {t(`hub.status.${status}`)}
                </span>
              </td>
              <td className="hub-table__evidence">{evidenceLabel(s, status)}</td>
              <td className="hub-table__next-col">
                <span className={`hub-next-chip${action.kind === "do" ? " hub-next-chip--do" : ""}`}>
                  {action.kind === "do" ? "✦ " : ""}
                  {t(`studyList.status.${CARD_STATUS_KEY[action.actionType] ?? "inProgress"}`)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  const renderCards = () => (
    <div className="quanti-showcase__grid-2">
      {visibleRows.map(({ study: s, mix, action }) => {
        const needsAttention = action.kind === "do";
        return (
          <a
            key={s.id}
            href={studyEntryPath(s)}
            data-tour={s.id === tourStudyId ? "demo-study-row" : undefined}
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
            <div className="chart-card__takeaway">
              {s.name}
              {s.is_demo && <span className="hub-demo-badge">{t("hub.demoBadge")}</span>}
            </div>
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
  );

  const renderSkeleton = () => (
    <div className="hub-table-wrap" aria-hidden="true">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="hub-skel-row">
          <span className="hub-skel" style={{ width: "36%", height: 12 }} />
          <span className="hub-skel" style={{ width: 72, height: 18, borderRadius: 999 }} />
          <span className="hub-skel" style={{ width: 110, height: 10 }} />
          <span className="hub-skel" style={{ width: 90, height: 10 }} />
        </div>
      ))}
    </div>
  );

  const hasStudies = studies !== null && studies.length > 0;

  // First-run home: the account has only the seeded demo and no real study
  // yet, so every workspace CTA (workspace NBA, filter tabs, stats sidecar,
  // decision memos) would point at demo data. Collapse the screen to a single
  // primary action + a passive example.
  //
  // The demo tour (PR #286) owns the *first* landing and rings the demo study
  // row — it needs that row rendered as a plain, clickable list item. So the
  // reframe is hard-gated OFF whenever the tour is requested, armed, or has a
  // ringed row (`tourStudyId`). If ever unsure, we render today's full layout.
  const hasRealStudy = totals.studies > 0;
  const tourActive = tourRequested || tourStudyId !== null || isDemoTourArmed();
  const firstRun = hasStudies && !hasRealStudy && !tourActive;

  const demoRows = useMemo(() => rows.filter((r) => r.study.is_demo), [rows]);

  // Launch the guided click-through from the first-run home. Clearing the
  // done flag lets it replay, and setting ?tour=1 hands off to the existing
  // tour effect (finds the flagship demo, arms it, rings the study row).
  const startGuidedTour = () => {
    localStorage.removeItem(DEMO_TOUR_DONE_KEY);
    dismissFirstRunHint();
    setFirstRunHintOpen(false);
    setSearchParams((sp) => {
      const next = new URLSearchParams(sp);
      next.set("tour", "1");
      return next;
    });
  };

  // First-run showcase: the seeded demo studies rendered as a tangible,
  // enticing worked example (completion signals + the decision memo), always
  // visible — the "wow" that a bare create-CTA screen was missing — plus a
  // one-click entry into the guided tour.
  const renderExample = () => (
    <section className="hub-example" data-tour="firstrun-example">
      <div className="hub-example__intro">
        <span className="hub-example__label">{t("hub.firstRun.exampleLead")}</span>
        <button type="button" className="hub-example__tour" onClick={startGuidedTour}>
          ▶ {t("hub.firstRun.guidedTour")}
        </button>
      </div>
      <div className="hub-example__rows">
        {demoRows.map(({ study: s, mix }) => (
          <button
            key={s.id}
            type="button"
            className="hub-example__row"
            onClick={() => openStudy(s)}
          >
            <span className="hub-example__row-name">
              <MixGlyph mix={mix} /> {s.name}
            </span>
            <span className="hub-example__row-meta">
              {t("hub.firstRun.exampleInterviews", { count: s.completed_interview_count })}
              {s.has_report
                ? ` · ${t("hub.firstRun.exampleReportReady")}`
                : s.has_ready_analysis
                  ? ` · ${t("hub.firstRun.exampleAnalysisReady")}`
                  : ""}
            </span>
            <span className="hub-example__row-cue">{t("hub.firstRun.exampleOpen")} →</span>
          </button>
        ))}
        {readyMemos.length > 0 && (
          <button
            type="button"
            className="hub-example__row hub-example__row--memo"
            onClick={() => openMemo(readyMemos[0].id)}
          >
            <span className="hub-example__row-name">
              <span aria-hidden="true">📄 </span>
              {t("hub.firstRun.exampleMemo")}
            </span>
            <span className="hub-example__row-cue">{t("hub.firstRun.exampleOpenReport")} →</span>
          </button>
        )}
      </div>
    </section>
  );

  return (
    <HubShell
      active="studies"
      studies={studies}
      memoCount={readyMemos.length}
      studyCount={studies?.length}
    >
      <div className="hub-canvas">
        <AccountNudges />

        <header className="hub-head">
          <div className="hub-head__text">
            <div className="hub-head__eyebrow">{t("studyList.eyebrow")}</div>
            <h1 className="hub-head__title">{t("studyList.title")}</h1>
            <p className="hub-head__sub">
              {firstRun
                ? t("hub.firstRun.sub")
                : hasStudies
                  ? [
                      counts.collecting > 0
                        ? t("hub.subline.collecting", { count: counts.collecting })
                        : null,
                      totals.interviews > 0
                        ? t("hub.subline.interviews", { count: totals.interviews })
                        : null,
                      totals.responses > 0
                        ? t("hub.subline.responses", { count: totals.responses })
                        : null,
                    ]
                      .filter(Boolean)
                      .join(" · ") || t("hub.subline.quiet")
                  : t("studyList.subtitle")}
            </p>
          </div>
          {!firstRun && (
            <button type="button" className="btn btn-primary" onClick={() => setPickerOpen(true)}>
              {t("studyList.newStudy")}
            </button>
          )}
        </header>

        <div className="sr-only" aria-live="polite" role="status">
          {announce}
        </div>

        {hasStudies && !firstRun && (() => {
          const nba = resolveWorkspaceNextAction(studies!.map(toNbaSummary), {
            eligibleStudyCount: memoEligibleCount,
            readyMemoCount: readyMemos.length,
            staleMemoCount: readyMemos.filter((m) => m.stale).length,
          });
          // When nothing needs the researcher (no actionable NBA, no fresh
          // nudges) the strip is purely reassurance — demote it to a quiet
          // inline line so it doesn't out-shout the actual studies below.
          const quiet = nba.kind === "done" && nudges.length === 0;
          return (
            <div className={`workspace-nba hub-nba${quiet ? " workspace-nba--quiet" : ""}`}>
              <span className="workspace-nba__eyebrow">{t("studyList.copilotEyebrow")}</span>
              {nudges.map((n) => (
                <div key={n.id} className={`copilot-nudge copilot-nudge--${n.tone}`}>
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

        <div className={`hub-grid${hasStudies && !firstRun ? "" : " hub-grid--single"}`}>
          <div className="hub-main">
            {hasStudies && !firstRun && (
              <div className="hub-toolbar">
                {(["all", "attention", "collecting", "complete"] as StatusFilter[]).map((f) => (
                  <button
                    key={f}
                    type="button"
                    className={`hub-fpill${filter === f ? " hub-fpill--active" : ""}`}
                    aria-pressed={filter === f}
                    onClick={() => setFilter(f)}
                  >
                    {t(`hub.filters.${f}`)} <span className="hub-fpill__n">{counts[f]}</span>
                  </button>
                ))}
                <div className="hub-toolbar__right">
                  <div className="hub-search">
                    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                      <circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.5" />
                      <path d="m10.5 10.5 3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                    </svg>
                    <input
                      type="text"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      placeholder={t("hub.searchPlaceholder")}
                      aria-label={t("hub.searchPlaceholder")}
                    />
                  </div>
                  <div className="hub-viewtoggle" role="group" aria-label={t("hub.view.aria")}>
                    <button
                      type="button"
                      className={view === "table" ? "hub-viewtoggle--active" : undefined}
                      aria-label={t("hub.view.table")}
                      aria-pressed={view === "table"}
                      onClick={() => setViewPersisted("table")}
                    >
                      <svg width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                        <path d="M2.5 4.5h11M2.5 8h11M2.5 11.5h11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                      </svg>
                    </button>
                    <button
                      type="button"
                      className={view === "cards" ? "hub-viewtoggle--active" : undefined}
                      aria-label={t("hub.view.cards")}
                      aria-pressed={view === "cards"}
                      onClick={() => setViewPersisted("cards")}
                    >
                      <svg width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                        <rect x="2.5" y="2.5" width="4.6" height="4.6" rx="1.2" stroke="currentColor" strokeWidth="1.3" />
                        <rect x="8.9" y="2.5" width="4.6" height="4.6" rx="1.2" stroke="currentColor" strokeWidth="1.3" />
                        <rect x="2.5" y="8.9" width="4.6" height="4.6" rx="1.2" stroke="currentColor" strokeWidth="1.3" />
                        <rect x="8.9" y="8.9" width="4.6" height="4.6" rx="1.2" stroke="currentColor" strokeWidth="1.3" />
                      </svg>
                    </button>
                  </div>
                </div>
              </div>
            )}

            {studies === null ? (
              renderSkeleton()
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
            ) : firstRun ? (
              <>
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
                    {t("hub.firstRun.heroText")}
                  </p>
                  <button type="button" className="btn btn-primary" onClick={() => setPickerOpen(true)}>
                    {t("studyList.newStudy")}
                  </button>
                </div>
                {renderExample()}
              </>
            ) : visibleRows.length === 0 ? (
              <div className="hub-nomatch">
                <h3>{t("hub.noMatch.title")}</h3>
                <p>{t("hub.noMatch.sub")}</p>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => {
                    setFilter("all");
                    setQuery("");
                  }}
                >
                  {t("hub.noMatch.cta")}
                </button>
              </div>
            ) : view === "table" ? (
              renderTable()
            ) : (
              renderCards()
            )}

            {studies !== null && !firstRun && (
              <DecisionMemoSection
                studies={studies}
                memos={memos}
                onRefresh={refreshMemos}
                openSignal={memoOpenSignal}
              />
            )}
          </div>

          {hasStudies && !firstRun && (
            <aside className="hub-sidecar">
              <div className="hub-panel">
                <h3>{t("hub.stats.title")}</h3>
                <div className="hub-stats">
                  <div>
                    <strong>{totals.studies}</strong>
                    <span>{t("hub.stats.studies", { count: totals.studies })}</span>
                  </div>
                  <div>
                    <strong>{totals.interviews}</strong>
                    <span>{t("hub.stats.interviews", { count: totals.interviews })}</span>
                  </div>
                  <div>
                    <strong>{totals.responses}</strong>
                    <span>{t("hub.stats.responses", { count: totals.responses })}</span>
                  </div>
                  <div>
                    <strong>{readyMemos.length}</strong>
                    <span>{t("hub.stats.memos", { count: readyMemos.length })}</span>
                  </div>
                </div>
                {hasDemo && <p className="hub-stats__note">{t("hub.stats.excludesDemo")}</p>}
              </div>

              {highlightMemo ? (
                <div className="hub-memo" data-tour="decision-memo">
                  <div className="hub-memo__kicker">
                    {t("hub.memoCard.kicker")} · {t("hub.memoCard.studies", { count: highlightMemo.study_count })}
                  </div>
                  <h3>{highlightMemo.name}</h3>
                  {highlightMemo.decision_question && <p>{highlightMemo.decision_question}</p>}
                  {highlightMemo.stale && (
                    <span className="hub-memo__stale" title={t("decisionMemos.staleHint")}>
                      {t("decisionMemos.statusStale")}
                    </span>
                  )}
                  <div className="hub-memo__actions">
                    <button type="button" className="hub-memo__cta" onClick={() => openMemo(highlightMemo.id)}>
                      {t("hub.memoCard.open")} →
                    </button>
                    <button type="button" className="hub-memo__all" onClick={scrollToMemos}>
                      {t("hub.memoCard.all")}
                    </button>
                  </div>
                </div>
              ) : generatingMemo ? (
                <div className="hub-memo">
                  <div className="hub-memo__kicker">{t("hub.memoCard.kicker")}</div>
                  <h3>{t("hub.memoCard.generatingTitle")}</h3>
                  <p>{t("hub.memoCard.generatingText")}</p>
                </div>
              ) : null}
              {/* No memo yet → nothing here. The Decision-memos section below
                  owns creation and its empty state; a second pitch in the
                  sidecar was the same message twice on one screen. */}
            </aside>
          )}
        </div>
      </div>

      {pickerOpen && <NewStudyModal onClose={() => setPickerOpen(false)} />}

      {/* First-run greeter: on the collapsed first-run home (demo-only, tour
          not running), gently ring the seeded example and offer the guided
          tour. Its primary STARTS the tour; skip only dismisses the greeter
          (neither touches the tour-done flag — endOn* are false). */}
      {firstRun && firstRunHintOpen && demoRows.length > 0 && (
        <DemoCallout
          selector='[data-tour="firstrun-example"]'
          eyebrow={t("hub.firstRun.hintEyebrow")}
          title={t("hub.firstRun.hintTitle")}
          body={t("hub.firstRun.hintBody")}
          clickHint={t("hub.firstRun.hintClickHint")}
          skipLabel={t("hub.firstRun.hintSkip")}
          primaryLabel={t("hub.firstRun.hintTakeTour")}
          onPrimary={startGuidedTour}
          onSkip={() => {
            dismissFirstRunHint();
            setFirstRunHintOpen(false);
          }}
          endOnPrimary={false}
          endOnSkip={false}
          dock
        />
      )}

      {/* Demo-tour entry point: rings the demo study row and waits for the
          user's own click — the row's normal navigation carries them into
          the study, where DemoTour picks up (sessionStorage-armed). */}
      {tourStudyId && getDemoTourPhase() === "study" && (
        <DemoCallout
          selector='[data-tour="demo-study-row"]'
          eyebrow={t("hub.tour.eyebrow")}
          title={t("hub.tour.title")}
          body={t("hub.tour.body")}
          clickHint={t("hub.tour.clickHint")}
          skipLabel={t("hub.tour.skip")}
          onSkip={() => {
            setTourStudyId(null);
            stripTourParam();
          }}
        />
      )}

      {/* Capstone: after the interview-round tour, the finale hands back here
          in the "memo" phase. Ring the cross-study decision memo card and let
          the user open its print-ready report — the end of the arc
          interviews → per-study analysis → cross-study decision memo. */}
      {isDemoTourArmed() &&
        getDemoTourPhase() === "memo" &&
        highlightMemo &&
        !memoTourDismissed && (
          <DemoCallout
            selector='[data-tour="decision-memo"]'
            eyebrow={t("hub.memoTour.eyebrow")}
            title={t("hub.memoTour.title")}
            body={t("hub.memoTour.body")}
            clickHint={t("hub.memoTour.clickHint")}
            skipLabel={t("hub.memoTour.skip")}
            primaryLabel={t("hub.memoTour.open")}
            onPrimary={() => openMemo(highlightMemo.id)}
            onSkip={() => setMemoTourDismissed(true)}
          />
        )}

      {/* First-run handhold: only on the empty studies screen. The Copilot
          dock explains research and points at "+ New study" when opened —
          it never auto-opens (the demo tour owns the first-run experience).
          While the ?tour=1 onboarding handoff is polling for the seeded demo
          the list is momentarily empty; don't mount at all during that window.
          There's no workspace chat backend, so we don't mount it once the
          user has studies — the workspace NBA strip covers guidance there. */}
      {studies !== null && studies.length === 0 && searchParams.get("tour") !== "1" && (
        <ResearchCopilotPanel
          target={WORKSPACE_COPILOT_TARGET}
          onApplied={() => {}}
          mission={t("studyList.copilotMission")}
          disableInput
          intro={{
            lead: t("copilot.workspace.introLead"),
            ctaLabel: t("copilot.workspace.createFirst"),
            onCta: () => setPickerOpen(true),
          }}
        />
      )}
    </HubShell>
  );
}
