import React, { useState, useEffect, useRef } from "react";
import { useParams, useNavigate, useSearchParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useToast } from "../components/Toast";
import { getErrorMessage } from "../utils/errorMessages";
import { openHtmlDocument } from "../utils/openHtmlDocument";
import { QUAL_BRAND_SCALE } from "../utils/reportIdentity";
import { SkeletonTable } from "../components/Skeleton";
import { AudioClip } from "../components/AudioClip";
import { InstrumentShell } from "../components/InstrumentShell";
import { getMe } from "../api/auth";
import {
  getProject,
  getLinks,
  getParticipants,
  createLink,
  sendLinkInvites,
  toggleLink,
  setLinkCap,
  updateProject,
  exportCSV,
  archiveProject,
  deleteProject,
  deleteParticipant,
  getAnalysis,
  triggerAnalysis,
  getAnalysisReadiness,
  AnalysisReadiness,
  updateTurn,
  patchQuestion,
  getCodes,
  createCode,
  updateCode,
  deleteCode,
  getTags,
  createTag,
  deleteTag,
  suggestTags,
  getTagSuggestions,
  acceptTagSuggestion,
  rejectTagSuggestion,
  suggestCodes,
  TagSuggestion,
  SuggestedCode,
  getMemos,
  createMemo,
  updateMemo,
  deleteMemo,
  getHeatmap,
  shareAnalysis,
  fetchAnalysisReportHtml,
  getAnalysisHistory,
  getAnalysisByVersion,
  upsertThemeAnnotation,
  getThemeAnnotations,
  saveResearcherContext,
  triggerRefinedAnalysis,
  AnalysisVersionMeta,
  ThemeAnnotation,
  ProjectResponse,
  InterviewLink,
  ParticipantResponse,
  TranscriptTurn,
  AnalysisResponse,
  ManualCode,
  QuoteTag,
  ProjectMemo,
  HeatmapResponse,
  AttributedQuote,
  ScreeningQuestionCreate,
} from "../api/projects";
import { getTranscript, translateTranscript, patchProjectSettings, createGuideQuestion, createScreeningQuestion, regenerateScreeningTranslations, recommendationText, type PaywallDetail } from "../api/projects";
import ScreeningTranslationsEditor from "../components/ScreeningTranslationsEditor";
import BrandingSettings from "../components/BrandingSettings";
import DemoTour, { getDemoTourPhase, isDemoTourArmed } from "../components/DemoTour";
import { getCreditUsage } from "../api/billing";
import { PaywallCard, UnlockModal } from "../components/UnlockPaywall";
import { ResearchCopilotPanel } from "../components/ResearchCopilotPanel";
import { NextActionChip } from "../components/NextActionChip";
import RecruitSharePanel from "../components/RecruitSharePanel";
import { resolveProjectNextAction } from "../copilot/nextAction";
import type { ProjectNbaInput } from "../copilot/nextAction";
import {
  detectProjectNudges,
  dismissNudge,
  activeNudgesFor,
} from "../copilot/signals";
import type { Nudge } from "../copilot/signals";
import { getConversation, runCopilot, saveConversation } from "../api/copilot";
import type { ProposedGuideQuestion } from "../api/copilot";

type Tab = "overview" | "setup" | "responses" | "analysis";

/** The copilot's one-line mission per tab — i18n keys in the dashboard
 * namespace, resolved at render so FR users don't get a mixed-language
 * panel header. */
const PROJECT_MISSION_KEYS: Record<Tab, string> = {
  overview: "copilot.missions.overview",
  setup: "copilot.missions.setup",
  responses: "copilot.missions.responses",
  analysis: "copilot.missions.analysis",
};

const PRESET_COLORS = [
  "#6366f1", "#ec4899", "#f59e0b", "#10b981",
  "#3b82f6", "#8b5cf6", "#ef4444", "#14b8a6",
];

export default function ProjectDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const { t: tAnalysis, i18n } = useTranslation("analysis");
  const { t: tProject } = useTranslation("project");
  const { t: tCommon } = useTranslation("common");
  const { t: tDashboard } = useTranslation("dashboard");
  const [searchParams, setSearchParams] = useSearchParams();

  // ── Header / coachmarks / overflow menu ───────────────────────────────
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const exportMenuRef = useRef<HTMLDivElement>(null);
  const [headerMenuOpen, setHeaderMenuOpen] = useState(false);
  const headerMenuRef = useRef<HTMLDivElement>(null);
  const [participantMenuOpen, setParticipantMenuOpen] = useState(false);
  const participantMenuRef = useRef<HTMLDivElement>(null);
  const [deleteProjectOpen, setDeleteProjectOpen] = useState(false);
  const [deleteProjectTyped, setDeleteProjectTyped] = useState("");
  const [deleteParticipantOpen, setDeleteParticipantOpen] = useState(false);
  const COACHMARK_KEY = "coachmark-analysis-iteration:dismissed";
  const [coachmarkDismissed, setCoachmarkDismissed] = useState<boolean>(
    () => localStorage.getItem(COACHMARK_KEY) === "true"
  );
  const [editAnnouncement, setEditAnnouncement] = useState("");

  // ── First-run welcome modal (shown after project creation) ──────────────
  const [welcomeOpen, setWelcomeOpen] = useState(() => searchParams.get("created") === "1");
  const [welcomeCopied, setWelcomeCopied] = useState(false);

  // ── Core state ─────────────────────────────────────────────────────────────
  const [project, setProject] = useState<ProjectResponse | null>(null);
  const [links, setLinks] = useState<InterviewLink[]>([]);
  // Available interview credits (null = legacy plan / unknown → no gating).
  const [availableCredits, setAvailableCredits] = useState<number | null>(null);
  const [participants, setParticipants] = useState<ParticipantResponse[]>([]);
  const [transcript, setTranscript] = useState<TranscriptTurn[] | null>(null);
  const [selectedParticipant, setSelectedParticipant] = useState<ParticipantResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [copiedToken, setCopiedToken] = useState<string | null>(null);
  // Per-link email-invite panel (null = closed)
  const [inviteLinkId, setInviteLinkId] = useState<string | null>(null);
  const [inviteText, setInviteText] = useState("");
  const [inviteSending, setInviteSending] = useState(false);
  // Per-link participant cap editor: which link is being edited, and the draft
  // value (kept as a string so the input can be transiently empty).
  const [capEditLinkId, setCapEditLinkId] = useState<string | null>(null);
  const [capDraft, setCapDraft] = useState("");
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [analysisPolling, setAnalysisPolling] = useState(false);
  const analysisPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Copilot nudges — "something changed while you were away."
  const [nudges, setNudges] = useState<Nudge[]>([]);
  const [tab, setTabRaw] = useState<Tab>(() => {
    const t = searchParams.get("tab");
    return (t === "setup" || t === "responses" || t === "analysis" || t === "overview")
      ? (t as Tab)
      : "overview";
  });
  // Inline unsaved-changes banner (replaces blocking window.confirm for tab switches)
  const [pendingTab, setPendingTab] = useState<Tab | null>(null);
  // advancedPromptOpen removed — system prompt hidden from researchers
  const [accountName, setAccountName] = useState<string>("");

  // ── Responses tab filters/sort ─────────────────────────────────────────────
  const [responseStatusFilter, setResponseStatusFilter] = useState<"all" | "completed" | "in_progress">("all");
  const [responseSortBy, setResponseSortBy] = useState<"date" | "quality" | "name">("date");

  // ── Analysis version history ───────────────────────────────────────────────
  const [analysisVersions, setAnalysisVersions] = useState<AnalysisVersionMeta[]>([]);
  const [versionHistoryOpen, setVersionHistoryOpen] = useState(false);

  // ── Transcript highlight target (from "View transcript →" in analysis) ───────
  const [highlightTarget, setHighlightTarget] = useState<{ turnIndex: number; quoteText: string } | null>(null);
  const transcriptListRef = useRef<HTMLDivElement>(null);

  // ── Responses layout viewport sizing ──────────────────────────────────────
  // The two-column Responses grid fills the viewport below the page chrome
  // (hub breadcrumb + instrument header + subnav + any banners). That chrome
  // height isn't constant, and a hardcoded CSS calc drifted after the hub
  // redesign, cutting off the bottom of the transcript. Measure the layout's
  // real document offset and hand it to CSS as --responses-top.
  const responsesLayoutRef = useRef<HTMLDivElement | null>(null);
  const measureResponsesLayout = React.useCallback(() => {
    const el = responsesLayoutRef.current;
    if (!el) return;
    const top = Math.max(0, Math.round(el.getBoundingClientRect().top + window.scrollY));
    el.style.setProperty("--responses-top", `${top}px`);
  }, []);
  const setResponsesLayoutRef = React.useCallback(
    (el: HTMLDivElement | null) => {
      responsesLayoutRef.current = el;
      if (el) measureResponsesLayout();
    },
    [measureResponsesLayout],
  );
  useEffect(() => {
    window.addEventListener("resize", measureResponsesLayout);
    // Chrome above the layout can grow/shrink (unsaved-changes banner, title
    // wrap). Any of those changes the body height, so observing body catches
    // them without wiring every banner state through here.
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(measureResponsesLayout) : null;
    ro?.observe(document.body);
    return () => {
      window.removeEventListener("resize", measureResponsesLayout);
      ro?.disconnect();
    };
  }, [measureResponsesLayout]);

  // ── Transcript translation (reading aid) ──────────────────────────────────
  const [transcriptViewMode, setTranscriptViewMode] = useState<"original" | "cleaned" | "translated">("original");
  const [translating, setTranslating] = useState(false);

  // ── Analysis readiness gate + staged progress ─────────────────────────────
  // Non-null readiness opens the gate modal (untagged studies get offered an
  // AI coding pass before synthesis). runHadAutoTag keeps the progress bar at
  // 4 steps once an auto-tag stage has been seen this run.
  const [gateReadiness, setGateReadiness] = useState<AnalysisReadiness | null>(null);
  const [runHadAutoTag, setRunHadAutoTag] = useState(false);

  // ── V4 paywall (unlock modal triggered by 402 from gated endpoints) ──
  const [unlockState, setUnlockState] = useState<{
    open: boolean;
    lockedCount: number;
    mode?: "transcripts" | "credits";
  }>({ open: false, lockedCount: 0 });
  // Helper — extract paywall payload from an Axios 402 response.
  // Returns null when the error isn't a paywall (so the caller can
  // re-throw / show its own error UI).
  const extractPaywall = (err: unknown): PaywallDetail | null => {
    if (typeof err !== "object" || err === null) return null;
    const maybeAxios = err as {
      response?: { status?: number; data?: { detail?: PaywallDetail } | PaywallDetail };
    };
    if (maybeAxios.response?.status !== 402) return null;
    const data = maybeAxios.response.data;
    // FastAPI wraps HTTPException(detail=...) as { detail: ... }
    if (data && typeof data === "object" && "detail" in data) {
      const detail = (data as { detail?: PaywallDetail }).detail;
      if (detail && detail.paywall === true) return detail;
    }
    if (data && typeof data === "object" && "paywall" in data) {
      return data as PaywallDetail;
    }
    return null;
  };

  // ── Synced-segment audio playback ─────────────────────────────────────────
  // Map of turnId → recording <audio> element so transcript spans can seek
  // playback by clicking a segment.
  const recordingAudioRefs = useRef<Record<string, HTMLAudioElement | null>>({});

  // ── Iterative analysis state ───────────────────────────────────────────────
  const [themeAnnotations, setThemeAnnotations] = useState<Record<string, ThemeAnnotation>>({});
  const [researcherContext, setResearcherContext] = useState("");
  const [contextSaving, setContextSaving] = useState<false | "saving" | "saved">(false);
  const contextDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [activeVersionNumber, setActiveVersionNumber] = useState<number | null>(null);
  const [activeVersionReport, setActiveVersionReport] = useState<AnalysisResponse | null>(null);
  const [refineModalOpen, setRefineModalOpen] = useState(false);
  const [refining, setRefining] = useState(false);
  const [annotationPanelOpen, setAnnotationPanelOpen] = useState(false);

  // Analysis sub-tabs: Overview (snapshot for stakeholders) vs Deep dive
  // (full themes / JTBDs / tensions / recommendations / memos / refine /
  // heatmap, with sticky TOC on desktop and accordions on mobile).
  const [analysisSubTab, setAnalysisSubTab] = useState<"overview" | "deep">("overview");

  // ── Codebook persistence ───────────────────────────────────────────────────
  const codebookPrefKey = "qp_codebook_open";
  const codebookInitial = localStorage.getItem(codebookPrefKey) !== "false";
  const [showCodebook, setShowCodebook] = useState(codebookInitial);
  const setShowCodebookPersist = (val: boolean) => {
    localStorage.setItem(codebookPrefKey, String(val));
    setShowCodebook(val);
  };

  // ── Overview inline editors ────────────────────────────────────────────────
  const [editingObjective, setEditingObjective] = useState(false);
  const [objectiveDraft, setObjectiveDraft] = useState("");
  const [editingWelcome, setEditingWelcome] = useState(false);
  const [welcomeDraft, setWelcomeDraft] = useState("");
  const [savingMeta, setSavingMeta] = useState(false);

  // System prompt editor removed — hidden from researchers

  // ── Panel settings ─────────────────────────────────────────────────────────
  // ── Screening editor ───────────────────────────────────────────────────────
  const [editingScreening, setEditingScreening] = useState(false);
  const [screeningDraft, setScreeningDraft] = useState<ScreeningQuestionCreate[]>([]);
  const [screeningSaving, setScreeningSaving] = useState(false);
  const [expandedSQ, setExpandedSQ] = useState<number | null>(null);

  // ── P1: Transcript editing ─────────────────────────────────────────────────
  const [editingTurnId, setEditingTurnId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState("");
  const [savingTurnId, setSavingTurnId] = useState<string | null>(null);
  const [editingOriginalText, setEditingOriginalText] = useState("");

  // ── P2: Analysis filters ───────────────────────────────────────────────────
  const [filtersExpanded, setFiltersExpanded] = useState(false);
  const [activeFilterBy, setActiveFilterBy] = useState<string>("");
  const [activeFilterValues, setActiveFilterValues] = useState<string[]>([]);

  // ── P4: Coding ─────────────────────────────────────────────────────────────
  const [codes, setCodes] = useState<ManualCode[]>([]);
  const [tags, setTags] = useState<QuoteTag[]>([]);
  const [selectionInfo, setSelectionInfo] = useState<{
    turnId: string; text: string; start: number; end: number; x: number; y: number; fromTranslation?: boolean;
  } | null>(null);
  const [newCodeName, setNewCodeName] = useState("");
  const [newCodeColor, setNewCodeColor] = useState(PRESET_COLORS[0]);
  const [showNewCode, setShowNewCode] = useState(false);
  const [creatingCode, setCreatingCode] = useState(false);
  const [renamingCodeId, setRenamingCodeId] = useState<string | null>(null);
  const [renameText, setRenameText] = useState("");

  // ── AI tag + codebook suggestions ──────────────────────────────────────────
  const [tagSuggestions, setTagSuggestions] = useState<TagSuggestion[]>([]);
  const [suggestingTags, setSuggestingTags] = useState(false);
  const [suggestedCodes, setSuggestedCodes] = useState<SuggestedCode[] | null>(null);
  const [suggestedCodesChecked, setSuggestedCodesChecked] = useState<Record<string, boolean>>({});
  const [suggestingCodes, setSuggestingCodes] = useState(false);
  const [addingSuggestedCodes, setAddingSuggestedCodes] = useState(false);

  // ── P5: Guide annotation + inline editing ──────────────────────────────────
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
  const [noteText, setNoteText] = useState("");
  const [expandedQuestionId, setExpandedQuestionId] = useState<string | null>(null);
  const [editingInterviewNotes, setEditingInterviewNotes] = useState<{ id: string; field: "interview_notes" | "desired_learning" } | null>(null);
  const [interviewNotesText, setInterviewNotesText] = useState("");
  const [editingQuestionId, setEditingQuestionId] = useState<string | null>(null);
  const [questionDraft, setQuestionDraft] = useState("");
  const [savingQuestionId, setSavingQuestionId] = useState<string | null>(null);

  // ── P6: Memos ──────────────────────────────────────────────────────────────
  const [memos, setMemos] = useState<ProjectMemo[]>([]);
  const [addingMemoKey, setAddingMemoKey] = useState<string | null>(null);
  const [newMemoContent, setNewMemoContent] = useState("");
  const [editingMemoId, setEditingMemoId] = useState<string | null>(null);
  const [editingMemoContent, setEditingMemoContent] = useState("");

  // ── P7: Heatmap ────────────────────────────────────────────────────────────
  const [heatmap, setHeatmap] = useState<HeatmapResponse | null>(null);
  const [heatmapExpanded, setHeatmapExpanded] = useState(localStorage.getItem("qp_heatmap_open") === "true");
  const [heatmapLoading, setHeatmapLoading] = useState(false);

  // Quality assessment is now auto-run on interview completion and stored in participant fields

  // Stop analysis polling if the user navigates away mid-generation, so the
  // interval doesn't keep fetching + setState on an unmounted component.
  useEffect(() => {
    return () => {
      if (analysisPollRef.current) {
        clearInterval(analysisPollRef.current);
        analysisPollRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!exportMenuOpen && !headerMenuOpen && !participantMenuOpen) return;
    function onDoc(e: MouseEvent) {
      if (!exportMenuRef.current?.contains(e.target as Node)) setExportMenuOpen(false);
      if (!headerMenuRef.current?.contains(e.target as Node)) setHeaderMenuOpen(false);
      if (!participantMenuRef.current?.contains(e.target as Node)) setParticipantMenuOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") { setExportMenuOpen(false); setHeaderMenuOpen(false); setParticipantMenuOpen(false); }
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [exportMenuOpen, headerMenuOpen, participantMenuOpen]);

  // Guard tab switches when there are unsaved edits in Setup
  function hasUnsavedSetupEdits(): boolean {
    return editingScreening || editingQuestionId !== null || editingNoteId !== null || editingInterviewNotes !== null;
  }

  function setTab(next: Tab) {
    if (next === tab) return;
    if (tab === "setup" && hasUnsavedSetupEdits()) {
      // Use inline banner instead of blocking confirm dialog
      setPendingTab(next);
      return;
    }
    applyTab(next);
  }

  function applyTab(next: Tab) {
    setTabRaw(next);
    // Sync URL so tabs are deep-linkable / shareable / back-button friendly
    const sp = new URLSearchParams(searchParams);
    if (next === "overview") sp.delete("tab");
    else sp.set("tab", next);
    setSearchParams(sp, { replace: true });
  }

  function confirmDiscardUnsaved() {
    if (!pendingTab) return;
    setEditingScreening(false);
    setEditingQuestionId(null);
    setEditingNoteId(null);
    setEditingInterviewNotes(null);
    const next = pendingTab;
    setPendingTab(null);
    applyTab(next);
  }

  useEffect(() => {
    if (!id) return;
    loadAll();
  }, [id]);

  // Warn on browser close/refresh when a transcript edit is in progress
  useEffect(() => {
    if (!editingTurnId) return;
    const hasChanges = editingText !== editingOriginalText;
    if (!hasChanges) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [editingTurnId, editingText, editingOriginalText]);

  // Scroll to highlighted turn after transcript loads, then auto-clear
  useEffect(() => {
    if (!transcript || !highlightTarget) return;
    requestAnimationFrame(() => {
      const el = document.getElementById(`turn-${highlightTarget.turnIndex}`);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    });
    // Auto-clear highlight after 4 s so it doesn't stay permanently
    const timer = setTimeout(() => setHighlightTarget(null), 4000);
    return () => clearTimeout(timer);
  }, [transcript, highlightTarget]);

  // Copilot nudge detection — diff this round's state against the stored
  // baseline and surface anything that changed while the researcher was
  // away (analysis finished, interviews crossed the analysable threshold).
  useEffect(() => {
    if (!project) return;
    const completedParts = participants.filter(
      (p) => p.status === "completed",
    );
    setNudges(
      detectProjectNudges(
        project.id,
        {
          analysisStatus: analysis?.status ?? "none",
          completedCount: completedParts.length,
          analysisParticipantCount: analysis?.participant_count ?? 0,
          analysisVersion: analysis?.version ?? 0,
          lowQualityCount: completedParts.filter(
            (p) => p.quality_label === "low",
          ).length,
        },
        tab,
      ),
    );
  }, [
    project?.id,
    analysis?.status,
    analysis?.participant_count,
    participants,
    tab,
  ]);

  // Escape key dismisses the tag popup
  useEffect(() => {
    if (!selectionInfo) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setSelectionInfo(null);
        window.getSelection()?.removeAllRanges();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [selectionInfo]);

  async function loadAll() {
    setLoading(true);
    try {
      const [proj, lnks, parts, ana] = await Promise.all([
        getProject(id!),
        getLinks(id!),
        getParticipants(id!),
        getAnalysis(id!),
      ]);
      setProject(proj);
      setLinks(lnks);
      setParticipants(parts);
      setAnalysis(ana);
      // Credit balance powers the link-gate (target > credits → block).
      getCreditUsage().then((u) => setAvailableCredits(u?.available_credits ?? null));
      // Only auto-switch to responses if no tab was explicitly requested in
      // URL — and never while the demo tour is guiding the user from
      // Overview onwards (the auto-switch would yank the tour to step 7).
      const tourActive =
        (proj.is_demo && isDemoTourArmed()) || searchParams.get("tour") === "1";
      if (parts.length > 0 && !searchParams.get("tab") && !tourActive) setTab("responses");
      if (ana.filters) {
        setActiveFilterBy(ana.filters.filter_by);
        setActiveFilterValues(ana.filters.filter_values);
      }
      if (ana.status === "generating") startPolling();
      // Load annotations and context for the current analysis
      if (ana.analysis_id && ana.status === "ready") {
        getThemeAnnotations(id!, ana.analysis_id).then((anns) => {
          const map: Record<string, ThemeAnnotation> = {};
          for (const a of anns) map[a.theme_title] = a;
          setThemeAnnotations(map);
        }).catch(() => {});
      }
    } catch {
      // handled by interceptor
    } finally {
      setLoading(false);
    }
    Promise.all([
      getCodes(id!).then(setCodes).catch(() => {}),
      getTags(id!).then(setTags).catch(() => {}),
      getMemos(id!).then(setMemos).catch(() => {}),
      getMe().then((m) => setAccountName(m.name || m.email || "")).catch(() => {}),
      getAnalysisHistory(id!).then(setAnalysisVersions).catch(() => {}),
    ]);
  }

  function startPolling() {
    if (analysisPolling) return;
    setAnalysisPolling(true);
    const iv = setInterval(async () => {
      let ana;
      try {
        ana = await getAnalysis(id!);
      } catch {
        // Transient fetch failure — keep polling; don't leave an unhandled
        // rejection or kill the poll on one blip.
        return;
      }
      setAnalysis(ana);
      // Remember that this run had an auto-tag stage so the progress bar
      // keeps showing 4 steps after the stage advances (survives reloads).
      if (ana.stage === "auto_tagging") setRunHadAutoTag(true);
      if (ana.status !== "generating") {
        clearInterval(iv);
        analysisPollRef.current = null;
        setAnalysisPolling(false);
        // Refresh version history now that a new version is ready
        getAnalysisHistory(id!).then(setAnalysisVersions).catch(() => {});
        // Reset active version view and load annotations for new version
        setActiveVersionNumber(null);
        setActiveVersionReport(null);
        if (ana.analysis_id && ana.status === "ready") {
          getThemeAnnotations(id!, ana.analysis_id).then((anns) => {
            const map: Record<string, ThemeAnnotation> = {};
            for (const a of anns) map[a.theme_title] = a;
            setThemeAnnotations(map);
          }).catch(() => {});
          setResearcherContext("");
          setContextSaving(false);
        }
      }
    }, 3000);
    analysisPollRef.current = iv;
  }

  async function handleTriggerAnalysis() {
    if (analysis?.report) {
      const ok = window.confirm(tAnalysis("regenerateConfirm"));
      if (!ok) return;
    }
    // Readiness gate: when no human coding exists at all, offer the AI
    // coding pass before synthesis. Never a wall, the modal always carries
    // a "run anyway" path, and a readiness fetch failure falls through to
    // a plain run.
    try {
      const readiness = await getAnalysisReadiness(id!);
      if (readiness.tagging_state === "untagged" && readiness.completed_count > 0) {
        setGateReadiness(readiness);
        return;
      }
    } catch {
      // Fall through to a plain run.
    }
    await runAnalysisNow(false);
  }

  async function runAnalysisNow(autoTag: boolean) {
    setGateReadiness(null);
    const filters =
      activeFilterBy && activeFilterValues.length > 0
        ? { filter_by: activeFilterBy, filter_values: activeFilterValues }
        : undefined;
    try {
      await triggerAnalysis(id!, filters, autoTag);
    } catch (err) {
      // V4 paywall — AI analysis is gated for free workspaces.
      // Backend returns 402; we open the unlock modal with the
      // analysis framing rather than throwing an opaque error.
      const paywall = extractPaywall(err);
      if (paywall) {
        setUnlockState({
          open: true,
          lockedCount: paywall.locked_completed_count,
        });
        return;
      }
      throw err;
    }
    setRunHadAutoTag(autoTag);
    setAnalysis((prev) => prev ? { ...prev, status: "generating", stage: autoTag ? "auto_tagging" : "preparing", stage_detail: null } : null);
    startPolling();
  }

  function analysisToMarkdown(): string {
    if (!analysis?.report) return "";
    const r = analysis.report;
    const lines: string[] = [];
    lines.push(`# Analysis Report — ${project?.name ?? "Project"}`);
    lines.push(`\n*Based on ${r.participant_count} participant(s) · ${r.confidence} confidence${r.confidence_rationale ? ` — ${r.confidence_rationale}` : ""}*\n`);
    lines.push(`## Summary\n${r.summary}\n`);
    if (r.themes?.length) {
      lines.push("## Key Themes");
      r.themes.forEach((t, i) => {
        lines.push(`\n### ${i + 1}. ${t.title}`);
        lines.push(t.summary);
        if (t.quotes?.length) {
          t.quotes.slice(0, 2).forEach((q) => {
            const text = typeof q === "string" ? q : q.text;
            lines.push(`> "${text}"`);
          });
        }
      });
    }
    if (r.jobs_to_be_done?.length) {
      lines.push("\n## Jobs to Be Done");
      r.jobs_to_be_done.forEach((j) => lines.push(`- **${j.job}**: ${j.insight}`));
    }
    if (r.tensions?.length) {
      lines.push("\n## Tensions");
      r.tensions.forEach((t) => lines.push(`- **${t.tension}**: ${t.detail}`));
    }
    if (r.recommendations?.length) {
      lines.push("\n## Recommendations");
      r.recommendations.forEach((rec) => lines.push(`- ${recommendationText(rec)}`));
    }
    return lines.join("\n");
  }

  const [exportCopied, setExportCopied] = useState(false);

  async function handleCopyMarkdown() {
    const md = analysisToMarkdown();
    await navigator.clipboard.writeText(md);
    setExportCopied(true);
    setTimeout(() => setExportCopied(false), 2000);
  }

  function handleDownloadJSON() {
    if (!analysis?.report) return;
    const blob = new Blob([JSON.stringify(analysis.report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${project?.name ?? "analysis"}-report.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function handleExportReport() {
    try {
      await openHtmlDocument(() => fetchAnalysisReportHtml(id!), "findings-report.html");
    } catch {
      toast(tAnalysis("exportReportError"), "error");
    }
  }

  async function handleShareAnalysis() {
    try {
      const res = await shareAnalysis(id!);
      const url = `${window.location.origin}/reports/${res.share_token}`;
      await navigator.clipboard.writeText(url);
      toast(tProject("toasts.shareLinkCopied"), "success");
    } catch {
      toast(tProject("toasts.shareLinkFailed"), "error");
    }
  }

  // ── Annotation handlers ────────────────────────────────────────────────────

  async function loadAnnotations(analysisId: string) {
    try {
      const annotations = await getThemeAnnotations(id!, analysisId);
      const map: Record<string, ThemeAnnotation> = {};
      for (const ann of annotations) {
        map[ann.theme_title] = ann;
      }
      setThemeAnnotations(map);
    } catch {
      // non-critical
    }
  }

  async function handleAnnotationClick(themeTitle: string, clickedStatus: "confirmed" | "disputed" | "needs_evidence") {
    if (!analysis?.analysis_id) return;
    const existing = themeAnnotations[themeTitle];
    // Clicking the active annotation clears it (toggle off)
    if (existing && existing.status === clickedStatus) {
      // Delete by overriding with a no-op — since we don't have a delete endpoint exposed in the UI,
      // we re-use upsert but the UI will hide cleared annotations. For a proper clear we'd need DELETE.
      // Instead: call delete endpoint via direct API.
      try {
        if (existing.id) {
          await fetch(`/api/projects/${id}/analysis/annotations/${existing.id}`, { method: "DELETE", headers: { Authorization: `Bearer ${localStorage.getItem("token")}` } });
        }
        setThemeAnnotations((prev) => {
          const next = { ...prev };
          delete next[themeTitle];
          return next;
        });
      } catch {
        toast(tProject("toasts.annotationRemoveFailed"), "error");
      }
      return;
    }
    try {
      const saved = await upsertThemeAnnotation(id!, {
        analysis_id: analysis.analysis_id,
        theme_title: themeTitle,
        status: clickedStatus,
        researcher_note: existing?.researcher_note ?? null,
      });
      setThemeAnnotations((prev) => ({ ...prev, [themeTitle]: saved }));
    } catch {
      toast(tProject("toasts.annotationSaveFailed"), "error");
    }
  }

  async function handleAnnotationNoteBlur(themeTitle: string, note: string) {
    if (!analysis?.analysis_id) return;
    const existing = themeAnnotations[themeTitle];
    if (!existing) return;
    try {
      const saved = await upsertThemeAnnotation(id!, {
        analysis_id: analysis.analysis_id,
        theme_title: themeTitle,
        status: existing.status,
        researcher_note: note || null,
      });
      setThemeAnnotations((prev) => ({ ...prev, [themeTitle]: saved }));
    } catch {
      toast(tProject("toasts.noteSaveFailed"), "error");
    }
  }

  function handleResearcherContextChange(value: string) {
    setResearcherContext(value);
    setContextSaving("saving");
    if (contextDebounceRef.current) clearTimeout(contextDebounceRef.current);
    contextDebounceRef.current = setTimeout(async () => {
      if (!analysis?.version) return;
      try {
        await saveResearcherContext(id!, analysis.version, value);
        setContextSaving("saved");
        setTimeout(() => setContextSaving(false), 2000);
      } catch {
        setContextSaving(false);
        toast(tProject("toasts.contextSaveFailed"), "error");
      }
    }, 1500);
  }

  async function handleTriggerRefine() {
    setRefining(true);
    try {
      await triggerRefinedAnalysis(id!);
      setRefineModalOpen(false);
      setAnalysis((prev) => prev ? { ...prev, status: "generating" } : null);
      startPolling();
      // Refresh versions list
      getAnalysisHistory(id!).then(setAnalysisVersions).catch(() => {});
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? tProject("toasts.refineStartFailed");
      toast(msg, "error");
    } finally {
      setRefining(false);
    }
  }

  async function handleViewVersion(versionNumber: number) {
    if (versionNumber === (analysis?.version ?? null)) {
      setActiveVersionNumber(null);
      setActiveVersionReport(null);
      return;
    }
    try {
      const report = await getAnalysisByVersion(id!, versionNumber);
      setActiveVersionReport(report);
      setActiveVersionNumber(versionNumber);
    } catch {
      toast(tProject("toasts.versionLoadFailed"), "error");
    }
  }

  async function handleGenerateLink() {
    // Hard gate: don't field a study you can't pay to complete. 1 credit =
    // 1 completed interview, so target > credits → open the upgrade modal
    // instead of creating a link.
    const tgt = project?.target_participants ?? null;
    if (tgt != null && availableCredits != null && tgt > availableCredits) {
      setUnlockState({ open: true, lockedCount: tgt - availableCredits, mode: "credits" });
      return;
    }
    try {
      const link = await createLink(id!);
      setLinks((prev) => [...prev, link]);
    } catch (err) {
      // Surfaces the backend message (e.g. "verify your email to create
      // interview links") instead of a generic failure.
      toast(getErrorMessage(err, tProject("toasts.linkGenerateFailed")), "error");
    }
  }

  async function handleToggleLink(linkId: string) {
    try {
      const updated = await toggleLink(linkId);
      setLinks((prev) => prev.map((l) => (l.id === linkId ? updated : l)));
    } catch {
      toast(tProject("toasts.linkUpdateFailed"), "error");
    }
  }

  async function handleSaveCap(linkId: string) {
    const raw = capDraft.trim();
    const value = raw === "" ? null : Number(raw);
    if (value !== null && (!Number.isInteger(value) || value < 1)) {
      toast(tProject("overview.capInvalid"), "error");
      return;
    }
    try {
      const updated = await setLinkCap(linkId, value);
      setLinks((prev) => prev.map((l) => (l.id === linkId ? updated : l)));
      setCapEditLinkId(null);
    } catch (err) {
      // The backend refuses a cap below the participants already admitted and
      // says how many there are — surface that instead of a generic failure.
      toast(getErrorMessage(err, tProject("toasts.linkUpdateFailed")), "error");
    }
  }

  function interviewUrl(token: string) {
    return `${window.location.origin}/i/${token}`;
  }

  async function handleSendInvites(linkId: string) {
    const emails = inviteText
      .split(/[\s,;]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (emails.length === 0) return;
    const invalid = emails.filter((e) => !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e));
    if (invalid.length > 0) {
      toast(tProject("overview.inviteInvalid", { emails: invalid.join(", ") }), "error");
      return;
    }
    if (emails.length > 20) {
      toast(tProject("overview.inviteTooMany"), "error");
      return;
    }
    setInviteSending(true);
    try {
      const res = await sendLinkInvites(id!, linkId, emails);
      if (res.failed.length > 0) {
        toast(tProject("overview.inviteFailed", { emails: res.failed.join(", ") }), "error");
      }
      if (res.sent > 0) {
        toast(tProject("overview.inviteSent", { count: res.sent }), "success");
      }
      setInviteText("");
      setInviteLinkId(null);
    } catch (err) {
      toast(getErrorMessage(err, tProject("overview.inviteFailedGeneric")), "error");
    } finally {
      setInviteSending(false);
    }
  }

  async function copyLink(token: string) {
    await navigator.clipboard.writeText(interviewUrl(token));
    setCopiedToken(token);
    setTimeout(() => setCopiedToken(null), 2000);
  }

  async function handleViewTranscript(
    p: ParticipantResponse,
    highlight?: { turnIndex: number; quoteText: string }
  ) {
    // V4 paywall — locked rows open the unlock modal instead of
    // attempting the fetch. Cheaper than letting the request 402.
    if (p.is_locked) {
      const locked = participants.filter((x) => x.is_locked).length;
      setUnlockState({ open: true, lockedCount: locked });
      return;
    }
    if (editingTurnId && editingText !== editingOriginalText) {
      if (!confirm(tProject("confirms.discardTranscript"))) return;
    }
    setSelectedParticipant(p);
    setTranscript(null);
    setEditingTurnId(null);
    setSelectionInfo(null);
    setTagSuggestions([]);
    setTranscriptViewMode("original");
    getTagSuggestions(id!, p.id).then(setTagSuggestions).catch(() => {});
    if (highlight) setHighlightTarget(highlight);
    else setHighlightTarget(null);
    try {
      const result = await getTranscript(id!, p.id);
      setSelectedParticipant(result.participant);
      setTranscript(result.turns);
      // Default to the corrected view when the ASR sense-check produced any
      // fixes — it's strictly more readable, and the raw STT stays one click
      // away (and is still shown beneath each corrected turn).
      if (result.turns.some((t) => t.cleaned_response)) {
        setTranscriptViewMode("cleaned");
      }
    } catch (err) {
      // V4 paywall — backend may return 402 for participants that
      // became locked between list-fetch and transcript-fetch
      // (e.g. subscription expired during the session). Catch it
      // and open the unlock modal rather than silently emptying.
      const paywall = extractPaywall(err);
      if (paywall) {
        setSelectedParticipant(null);
        setUnlockState({
          open: true,
          lockedCount: paywall.locked_completed_count,
        });
        return;
      }
      setTranscript([]);
    }
  }

  // Landing on the Responses tab with an empty right pane reads as a bug —
  // auto-open the most recent unlocked transcript instead. Desktop only:
  // on mobile (≤768px) the detail pane replaces the list, so auto-opening
  // would hide the participant list the user came for. One-shot per visit —
  // a deliberate "back to participants" deselect must stick.
  const autoSelectRef = useRef(false);
  useEffect(() => {
    autoSelectRef.current = false;
  }, [id]);
  useEffect(() => {
    if (tab !== "responses" || loading || autoSelectRef.current) return;
    if (selectedParticipant) {
      autoSelectRef.current = true;
      return;
    }
    if (!window.matchMedia("(min-width: 769px)").matches) return;
    const first = [...participants]
      .sort(
        (a, b) =>
          new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
      )
      .find((p) => !p.is_locked);
    if (!first) return;
    autoSelectRef.current = true;
    handleViewTranscript(first);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, loading, participants, selectedParticipant]);

  async function handleSuggestTags() {
    if (!selectedParticipant || suggestingTags) return;
    setSuggestingTags(true);
    try {
      const fresh = await suggestTags(id!, selectedParticipant.id);
      setTagSuggestions(fresh);
      if (fresh.length === 0) toast(tProject("responses.noTagSuggestions"), "info");
    } catch (err) {
      toast(getErrorMessage(err, tProject("responses.suggestTagsFailed")), "error");
    } finally {
      setSuggestingTags(false);
    }
  }

  async function handleAcceptSuggestion(s: TagSuggestion) {
    try {
      const { tag, code } = await acceptTagSuggestion(id!, s.id);
      setTagSuggestions((prev) => prev.filter((x) => x.id !== s.id));
      setTags((prev) => [...prev, tag]);
      // A proposed new code materialises on accept — reflect it in the codebook.
      setCodes((prev) => (prev.some((c) => c.id === code.id) ? prev.map((c) => (c.id === code.id ? code : c)) : [...prev, code]));
    } catch (err) {
      toast(getErrorMessage(err, tProject("responses.suggestTagsFailed")), "error");
    }
  }

  async function handleRejectSuggestion(s: TagSuggestion) {
    setTagSuggestions((prev) => prev.filter((x) => x.id !== s.id));
    try {
      await rejectTagSuggestion(id!, s.id);
    } catch {
      // Rejection is best-effort; a failed call just leaves the row pending
      // server-side and it reappears on next load.
    }
  }

  async function handleSuggestCodes() {
    if (suggestingCodes) return;
    setSuggestingCodes(true);
    try {
      const proposals = await suggestCodes(id!);
      setSuggestedCodes(proposals);
      setSuggestedCodesChecked(Object.fromEntries(proposals.map((c) => [c.name, true])));
    } catch (err) {
      toast(getErrorMessage(err, tProject("responses.suggestCodesFailed")), "error");
    } finally {
      setSuggestingCodes(false);
    }
  }

  async function handleAddSuggestedCodes() {
    if (!suggestedCodes || addingSuggestedCodes) return;
    const selected = suggestedCodes.filter((c) => suggestedCodesChecked[c.name]);
    if (selected.length === 0) {
      setSuggestedCodes(null);
      return;
    }
    setAddingSuggestedCodes(true);
    try {
      for (const c of selected) {
        const created = await createCode(id!, c.name, c.color);
        setCodes((prev) => [...prev, created]);
      }
      setSuggestedCodes(null);
      toast(tProject("responses.suggestedCodesAdded", { count: selected.length }), "success");
    } catch (err) {
      toast(getErrorMessage(err, tProject("responses.suggestCodesFailed")), "error");
    } finally {
      setAddingSuggestedCodes(false);
    }
  }

  async function handleToggleTranslation() {
    if (!selectedParticipant || !transcript) return;
    const targetLang = (i18n.language || "en").slice(0, 2).toLowerCase();

    // If switching to original, just flip
    if (transcriptViewMode === "translated") {
      setTranscriptViewMode("original");
      return;
    }

    // Switching to translated — check if we already have it cached
    const hasTranslation = transcript.some(
      (t) => t.translated_response && t.translation_language === targetLang
    );
    if (hasTranslation) {
      setTranscriptViewMode("translated");
      return;
    }

    // Need to fetch translation
    setTranslating(true);
    try {
      await translateTranscript(id!, selectedParticipant.id, targetLang);
      // Poll for completion (translation is async on backend)
      let attempts = 0;
      const poll = async (): Promise<void> => {
        attempts += 1;
        const fresh = await getTranscript(id!, selectedParticipant.id);
        const ready = fresh.turns.some(
          (t) => t.translated_response && t.translation_language === targetLang
        );
        if (ready || attempts >= 30) {
          setTranscript(fresh.turns);
          setTranscriptViewMode("translated");
          setTranslating(false);
          if (!ready) toast(tProject("responses.translationFailed"), "error");
          return;
        }
        await new Promise((r) => setTimeout(r, 2000));
        return poll();
      };
      await poll();
    } catch {
      setTranslating(false);
      toast(tProject("responses.translationFailed"), "error");
    }
  }

  async function handleExportCSV() {
    try {
      const blob = await exportCSV(id!);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${project?.name || "export"}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast(tProject("toasts.csvExportFailed"), "error");
    }
  }

  async function handleArchive() {
    if (!confirm(tProject("confirms.archiveProject"))) return;
    try {
      await archiveProject(id!);
      toast(tProject("toasts.projectArchived"), "success");
      navigate("/dashboard");
    } catch {
      toast(tProject("toasts.projectArchiveFailed"), "error");
    }
  }

  async function confirmDeleteProject() {
    const expected = project?.name ?? "";
    if (deleteProjectTyped.trim() !== expected) {
      toast(tProject("toasts.projectDeleteNameMismatch"), "error");
      return;
    }
    setDeleteProjectOpen(false);
    try {
      await deleteProject(id!);
      toast(tProject("toasts.projectDeleted"), "success");
      navigate("/dashboard");
    } catch {
      toast(tProject("toasts.projectDeleteFailed"), "error");
    }
  }

  async function confirmDeleteParticipant() {
    if (!selectedParticipant) return;
    setDeleteParticipantOpen(false);
    try {
      await deleteParticipant(id!, selectedParticipant.id);
      toast(tProject("toasts.participantDeleted"), "success");
      setTranscript(null);
      setSelectedParticipant(null);
      setSelectionInfo(null);
      const fresh = await getParticipants(id!);
      setParticipants(fresh);
    } catch {
      toast(tProject("toasts.participantDeleteFailed"), "error");
    }
  }

  // ── P1: Transcript editing ─────────────────────────────────────────────────

  function startEditTurn(turn: TranscriptTurn) {
    setEditingTurnId(turn.id);
    setEditingText(turn.response_transcript ?? "");
    setEditingOriginalText(turn.response_transcript ?? "");
    setSelectionInfo(null);
  }

  async function saveEditTurn(turn: TranscriptTurn) {
    if (!selectedParticipant) return;
    setSavingTurnId(turn.id);
    try {
      const updated = await updateTurn(id!, selectedParticipant.id, turn.id, editingText);
      setTranscript((prev) =>
        prev
          ? prev.map((t) =>
              t.id === turn.id
                ? { ...t, response_transcript: updated.response_transcript, manually_edited: updated.manually_edited, edited_at: updated.edited_at }
                : t
            )
          : prev
      );
      setEditingTurnId(null);
    } catch {
      toast(tProject("toasts.transcriptSaveFailed"), "error");
    } finally {
      setSavingTurnId(null);
    }
  }

  // ── P4: Quote tagging ──────────────────────────────────────────────────────

  function handleTranscriptMouseUp(turnId: string) {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed) { setSelectionInfo(null); return; }
    const text = sel.toString().trim();
    if (!text) { setSelectionInfo(null); return; }

    const range = sel.getRangeAt(0);
    const rect = range.getBoundingClientRect();

    const anchorEl = sel.anchorNode?.parentElement?.closest("[data-turn-text]") as HTMLElement | null;
    if (!anchorEl) { setSelectionInfo(null); return; }

    const fullText = anchorEl.textContent ?? "";

    // Use the actual selection Range to find the true offset — indexOf would
    // always tag the FIRST occurrence, mis-tagging a phrase that repeats in the
    // turn. Measure the text from the start of the turn up to the selection
    // start, then add any leading whitespace trimmed off `text`.
    let start = -1;
    try {
      const preRange = document.createRange();
      preRange.selectNodeContents(anchorEl);
      preRange.setEnd(range.startContainer, range.startOffset);
      const rawSel = sel.toString();
      const leadingWs = rawSel.length - rawSel.trimStart().length;
      const candidate = preRange.toString().length + leadingWs;
      if (fullText.slice(candidate, candidate + text.length) === text) {
        start = candidate;
      }
    } catch {
      /* fall back to indexOf below */
    }
    if (start === -1) start = fullText.indexOf(text);
    if (start === -1) { setSelectionInfo(null); return; }

    // Viewport-safe x position: clamp so popup (180px wide) stays on screen
    const popupWidth = 200;
    const safeX = Math.min(Math.max(rect.left + rect.width / 2, popupWidth / 2 + 8), window.innerWidth - popupWidth / 2 - 8);
    setSelectionInfo({ turnId, text, start, end: start + text.length, x: safeX, y: rect.top + window.scrollY - 44 });
    setShowNewCode(false);
  }

  async function handleTagWithCode(code: ManualCode) {
    if (!selectionInfo) return;
    try {
      const tag = await createTag(id!, selectionInfo.turnId, {
        manual_code_id: code.id,
        selected_text: selectionInfo.text,
        start_index: selectionInfo.start,
        end_index: selectionInfo.end,
        tagged_from_translation: selectionInfo.fromTranslation || false,
      });
      setTags((prev) => [...prev, tag]);
      setCodes((prev) => prev.map((c) => c.id === code.id ? { ...c, tag_count: c.tag_count + 1 } : c));
    } catch {
      toast(tProject("toasts.quoteTagFailed"), "error");
    } finally {
      setSelectionInfo(null);
      window.getSelection()?.removeAllRanges();
    }
  }

  async function handleCreateAndTag() {
    if (!newCodeName.trim() || !selectionInfo) return;
    setCreatingCode(true);
    try {
      const code = await createCode(id!, newCodeName.trim(), newCodeColor);
      setCodes((prev) => [...prev, code]);
      await handleTagWithCode(code);
      setNewCodeName("");
      setNewCodeColor(PRESET_COLORS[0]);
      setShowNewCode(false);
    } catch {
      toast(tProject("toasts.codeCreateFailed"), "error");
    } finally {
      setCreatingCode(false);
    }
  }

  async function handleDeleteTag(tagId: string) {
    const tag = tags.find((t) => t.id === tagId);
    await deleteTag(id!, tagId);
    setTags((prev) => prev.filter((t) => t.id !== tagId));
    if (tag) {
      setCodes((prev) => prev.map((c) => c.id === tag.manual_code_id ? { ...c, tag_count: Math.max(0, c.tag_count - 1) } : c));
    }
  }

  async function handleDeleteCode(codeId: string) {
    if (!confirm(tProject("confirms.deleteCode"))) return;
    await deleteCode(id!, codeId);
    setCodes((prev) => prev.filter((c) => c.id !== codeId));
    setTags((prev) => prev.filter((t) => t.manual_code_id !== codeId));
  }

  async function handleRenameCode(codeId: string) {
    const trimmed = renameText.trim();
    if (!trimmed) return;
    try {
      const updated = await updateCode(id!, codeId, { name: trimmed });
      setCodes((prev) => prev.map((c) => (c.id === codeId ? { ...c, name: updated.name } : c)));
      setTags((prev) => prev.map((t) => (t.manual_code_id === codeId ? { ...t, code_name: updated.name } : t)));
      setRenamingCodeId(null);
    } catch {
      toast(tProject("toasts.codeRenameFailed"), "error");
    }
  }

  // ── P5: Guide annotation ───────────────────────────────────────────────────

  async function saveInterviewNotes(questionId: string, field: "interview_notes" | "desired_learning") {
    try {
      const updated = await patchQuestion(id!, questionId, { [field]: interviewNotesText });
      setProject((prev) =>
        prev ? { ...prev, questions: prev.questions.map((q) => q.id === questionId ? { ...q, [field]: (updated as unknown as Record<string, unknown>)[field] as string } : q) } : prev
      );
      setEditingInterviewNotes(null);
    } catch {
      toast(tProject("toasts.notesSaveFailed"), "error");
    }
  }

  async function saveQuestionText(questionId: string) {
    if (!questionDraft.trim()) return;
    setSavingQuestionId(questionId);
    try {
      const updated = await patchQuestion(id!, questionId, { main_question: questionDraft.trim() });
      setProject((prev) =>
        prev ? { ...prev, questions: prev.questions.map((q) => q.id === questionId ? { ...q, main_question: updated.main_question } : q) } : prev
      );
      setEditingQuestionId(null);
    } catch {
      toast(tProject("toasts.questionSaveFailed"), "error");
    } finally {
      setSavingQuestionId(null);
    }
  }

  async function moveQuestion(questionId: string, direction: "up" | "down") {
    if (!project) return;
    const allQs = [...project.questions].sort((a, b) => a.section_index - b.section_index || a.question_index - b.question_index);
    const idx = allQs.findIndex((q) => q.id === questionId);
    if (idx < 0) return;
    const swapIdx = direction === "up" ? idx - 1 : idx + 1;
    if (swapIdx < 0 || swapIdx >= allQs.length) return;
    const current = allQs[idx];
    const swap = allQs[swapIdx];
    // Swap question_index values (and section if crossing section boundaries)
    try {
      const [u1, u2] = await Promise.all([
        patchQuestion(id!, current.id, { question_index: swap.question_index, section_index: swap.section_index, section_title: swap.section_title }),
        patchQuestion(id!, swap.id, { question_index: current.question_index, section_index: current.section_index, section_title: current.section_title }),
      ]);
      setProject((prev) =>
        prev ? {
          ...prev,
          questions: prev.questions.map((q) => {
            if (q.id === current.id) return { ...q, question_index: u1.question_index, section_index: u1.section_index, section_title: u1.section_title };
            if (q.id === swap.id) return { ...q, question_index: u2.question_index, section_index: u2.section_index, section_title: u2.section_title };
            return q;
          }),
        } : prev
      );
    } catch {
      toast(tProject("toasts.reorderFailed"), "error");
    }
  }

  async function saveQuestionNote(questionId: string) {
    try {
      const updated = await patchQuestion(id!, questionId, { researcher_notes: noteText });
      setProject((prev) =>
        prev ? { ...prev, questions: prev.questions.map((q) => q.id === questionId ? { ...q, researcher_notes: updated.researcher_notes } : q) } : prev
      );
      setEditingNoteId(null);
    } catch {
      toast(tProject("toasts.noteSaveFailed"), "error");
    }
  }

  async function toggleDeprecateQuestion(questionId: string, currentDeprecatedAt: string | null | undefined) {
    const inProgress = participants.some((p) => p.status === "in_progress");
    if (!currentDeprecatedAt && inProgress) {
      if (!confirm(tProject("confirms.deprecateQuestion"))) return;
    }
    const newDeprecatedAt = currentDeprecatedAt ? null : new Date().toISOString();
    try {
      const updated = await patchQuestion(id!, questionId, { deprecated_at: newDeprecatedAt });
      setProject((prev) =>
        prev ? { ...prev, questions: prev.questions.map((q) => q.id === questionId ? { ...q, deprecated_at: updated.deprecated_at } : q) } : prev
      );
    } catch {
      toast(tProject("toasts.questionUpdateFailed"), "error");
    }
  }

  // ── P6: Memos ──────────────────────────────────────────────────────────────

  function timeAgo(dateStr: string): string {
    const now = new Date();
    const date = new Date(dateStr);
    const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);
    const rtf = new Intl.RelativeTimeFormat(i18n.language, { numeric: "auto" });
    if (seconds < 60) return rtf.format(0, "second");
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return rtf.format(-minutes, "minute");
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return rtf.format(-hours, "hour");
    const days = Math.floor(hours / 24);
    if (days < 30) return rtf.format(-days, "day");
    return date.toLocaleDateString(i18n.language);
  }

  async function handleAddMemo(type: string, linkedKey: string | null) {
    if (!newMemoContent.trim()) return;
    try {
      const memo = await createMemo(id!, { type, linked_key: linkedKey, content: newMemoContent });
      setMemos((prev) => [...prev, memo]);
      setNewMemoContent("");
      setAddingMemoKey(null);
    } catch {
      toast(tProject("toasts.memoSaveFailed"), "error");
    }
  }

  async function handleUpdateMemo(memoId: string) {
    try {
      const updated = await updateMemo(id!, memoId, editingMemoContent);
      setMemos((prev) => prev.map((m) => m.id === memoId ? updated : m));
      setEditingMemoId(null);
    } catch {
      toast(tProject("toasts.memoUpdateFailed"), "error");
    }
  }

  async function handleDeleteMemo(memoId: string) {
    await deleteMemo(id!, memoId);
    setMemos((prev) => prev.filter((m) => m.id !== memoId));
  }

  // ── P7: Heatmap ────────────────────────────────────────────────────────────

  async function loadHeatmap() {
    if (heatmap) {
      const next = !heatmapExpanded;
      setHeatmapExpanded(next);
      localStorage.setItem("qp_heatmap_open", String(next));
      return;
    }
    setHeatmapLoading(true);
    try {
      const data = await getHeatmap(id!);
      setHeatmap(data);
      setHeatmapExpanded(true);
      localStorage.setItem("qp_heatmap_open", "true");
    } catch {
      toast(tProject("toasts.noReadyAnalysis"), "error");
    } finally {
      setHeatmapLoading(false);
    }
  }

  function heatmapColor(count: number): string {
    if (count === 0) return "#f9fafb";
    if (count === 1) return "#bfdbfe";
    if (count === 2) return "#60a5fa";
    return "#1d4ed8";
  }

  // handleAssessQuality removed — quality is auto-run on completion

  // ── P2: Filter helpers ─────────────────────────────────────────────────────

  function getFilterOptions(): Record<string, string[]> {
    const opts: Record<string, Set<string>> = {};
    for (const p of participants) {
      if (p.profession) { opts["profession"] = opts["profession"] || new Set(); opts["profession"].add(p.profession); }
      if (p.age_range) { opts["age_range"] = opts["age_range"] || new Set(); opts["age_range"].add(p.age_range); }
      if (p.country) { opts["country"] = opts["country"] || new Set(); opts["country"].add(p.country); }
      // Screener answers are researcher-designed profile variables — each
      // question becomes its own filter dimension, keyed screening:<qid>.
      for (const a of p.screening_answers ?? []) {
        const key = `screening:${a.question_id}`;
        opts[key] = opts[key] || new Set();
        opts[key].add(a.answer);
      }
    }
    return Object.fromEntries(Object.entries(opts).map(([k, v]) => [k, Array.from(v)]));
  }

  /** Human label for a filter dimension: demographic attrs read as-is,
   *  screening:<qid> resolves to the screener question text. */
  function filterLabel(attr: string): string {
    if (attr.startsWith("screening:")) {
      const qid = attr.slice("screening:".length);
      for (const p of participants) {
        const match = (p.screening_answers ?? []).find((a) => a.question_id === qid);
        if (match) return match.question.length > 60 ? `${match.question.slice(0, 57)}…` : match.question;
      }
      return tAnalysis("screeningFilterLabel");
    }
    return attr.replace("_", " ");
  }

  function toggleFilterValue(attr: string, val: string) {
    if (activeFilterBy !== attr) {
      setActiveFilterBy(attr);
      setActiveFilterValues([val]);
    } else {
      setActiveFilterValues((prev) => prev.includes(val) ? prev.filter((v) => v !== val) : [...prev, val]);
    }
  }

  // ── Render helpers ─────────────────────────────────────────────────────────

  /** Renders response text with a specific quoted substring highlighted in yellow,
   *  falling back to code-tag rendering for the rest of the text. */
  function renderWithQuoteHighlight(text: string, quoteText: string, turnId: string): React.ReactNode {
    if (!quoteText) return renderTaggedText(text, turnId);
    const lower = text.toLowerCase();
    const quoteNorm = quoteText.toLowerCase().trim();
    const idx = lower.indexOf(quoteNorm);
    if (idx === -1) return renderTaggedText(text, turnId);
    const before = text.slice(0, idx);
    const match = text.slice(idx, idx + quoteNorm.length);
    const after = text.slice(idx + quoteNorm.length);
    return (
      <span data-turn-text="">
        {before}
        <mark className="quote-highlight">{match}</mark>
        {after}
      </span>
    );
  }

  // Compute char offsets for each segment by scanning the transcript
  // sequentially. Whisper segment text is usually a verbatim substring of the
  // full transcript; if not, we fall back to a proportional split so the
  // segment span still lines up roughly. The proportional fallback matters
  // because Whisper occasionally normalises whitespace differently between
  // the segment list and the joined .text.
  function computeSegmentRanges(
    text: string,
    segments: import("../api/projects").TranscriptSegment[]
  ): Array<{ start: number; end: number; idx: number; timeStart: number; timeEnd: number }> {
    const ranges = [];
    let cursor = 0;
    for (let i = 0; i < segments.length; i++) {
      const segText = (segments[i].text || "").trim();
      let start = -1;
      let end = -1;
      if (segText) {
        const idx = text.indexOf(segText, cursor);
        if (idx !== -1) {
          start = idx;
          end = idx + segText.length;
          cursor = end;
        }
      }
      if (start === -1) {
        // Proportional fallback so the segment still has a visual home
        start = Math.floor((text.length * i) / segments.length);
        end = i + 1 < segments.length
          ? Math.floor((text.length * (i + 1)) / segments.length)
          : text.length;
      }
      ranges.push({
        start, end, idx: i,
        timeStart: segments[i].start,
        timeEnd: segments[i].end,
      });
    }
    return ranges;
  }

  // Render transcript text split by both quote-tag and segment boundaries.
  // Each emitted span is a "minimal range" that has at most one tag and one
  // segment associated with it, so tags and segments coexist visually
  // without nesting issues. Tags stay the louder visual signal (researcher
  // intent); segment highlighting is the ambient sync layer.
  function renderTranscriptWithSegments(
    text: string,
    turnId: string,
    segments: import("../api/projects").TranscriptSegment[]
  ): React.ReactNode {
    const turnTags = tags.filter((t) => t.turn_id === turnId)
      .sort((a, b) => a.start_index - b.start_index);
    const segRanges = computeSegmentRanges(text, segments);

    const boundaries = new Set<number>([0, text.length]);
    for (const s of segRanges) { boundaries.add(s.start); boundaries.add(s.end); }
    for (const t of turnTags) { boundaries.add(t.start_index); boundaries.add(t.end_index); }
    const points = Array.from(boundaries).filter(p => p >= 0 && p <= text.length).sort((a, b) => a - b);

    const parts: React.ReactNode[] = [];
    for (let i = 0; i < points.length - 1; i++) {
      const start = points[i];
      const end = points[i + 1];
      if (end <= start) continue;
      const piece = text.slice(start, end);
      if (!piece) continue;

      const seg = segRanges.find(s => s.start <= start && end <= s.end);
      const tag = turnTags.find(t => t.start_index <= start && end <= t.end_index);

      const tagColor = tag?.code_color || "#6366f1";
      const className = [
        seg ? "transcript-segment" : "",
        tag ? "transcript-tagged" : "",
      ].filter(Boolean).join(" ");

      parts.push(
        <span
          key={`${turnId}-${i}`}
          className={className || undefined}
          data-segment-idx={seg ? seg.idx : undefined}
          data-segment-start={seg ? seg.timeStart : undefined}
          style={tag ? {
            borderBottom: `2.5px solid ${tagColor}`,
            background: `${tagColor}22`,
            borderRadius: 2,
          } : undefined}
          title={tag ? `Tagged: ${tag.code_name}` : undefined}
          onClick={seg ? () => {
            const audio = recordingAudioRefs.current[turnId];
            if (audio) {
              audio.currentTime = seg.timeStart;
              audio.play().catch(() => {});
            }
          } : undefined}
        >
          {piece}
        </span>
      );
    }
    return <span data-turn-text="" data-turn-id={turnId}>{parts}</span>;
  }

  function renderTaggedText(text: string, turnId: string): React.ReactNode {
    const turnTags = tags.filter((t) => t.turn_id === turnId).sort((a, b) => a.start_index - b.start_index);
    if (!turnTags.length) return <span data-turn-text="">{text}</span>;

    const parts: React.ReactNode[] = [];
    let cursor = 0;
    for (const tag of turnTags) {
      if (tag.start_index > cursor) parts.push(text.slice(cursor, tag.start_index));
      const color = tag.code_color || "#6366f1";
      parts.push(
        <span
          key={tag.id}
          style={{ borderBottom: `2.5px solid ${color}`, background: `${color}22`, borderRadius: 2, cursor: "default", position: "relative" }}
          title={`Tagged: ${tag.code_name}`}
          className="tagged-text"
        >
          {text.slice(tag.start_index, tag.end_index)}
          <button
            className="tag-pill-remove tag-inline-remove"
            onClick={(e) => { e.stopPropagation(); if (confirm(tProject("confirms.removeTag", { name: tag.code_name }))) handleDeleteTag(tag.id); }}
            aria-label={tProject("a11y.removeTag", { name: tag.code_name })}
            title={tProject("a11y.removeTagTitle")}
          >×</button>
        </span>
      );
      cursor = tag.end_index;
    }
    if (cursor < text.length) parts.push(text.slice(cursor));
    return <span data-turn-text="">{parts}</span>;
  }

  function renderAttributedQuote(q: AttributedQuote | string, idx: number): React.ReactNode {
    if (typeof q === "string") {
      return <blockquote key={idx} className="analysis-quote">"{q}"</blockquote>;
    }
    return (
      <blockquote key={idx} className="analysis-quote">
        <div>"{q.text}"</div>
        <div style={{ fontSize: 12, color: "var(--text-tertiary)", marginTop: 4, display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>{q.participant_display_name || q.participant_identifier}</span>
          {q.question_text && <span>· {q.question_text.slice(0, 60)}{q.question_text.length > 60 ? "…" : ""}</span>}
          <button
            className="btn btn-ghost btn-xs"
            style={{ fontSize: 10, padding: "1px 4px" }}
            onClick={() => {
              const p = participants.find(
                (p) => p.display_name === q.participant_display_name ||
                       p.id === q.participant_identifier
              );
              if (p) {
                setTab("responses");
                handleViewTranscript(p, q.turn_index != null ? { turnIndex: q.turn_index, quoteText: q.text } : undefined);
              }
            }}
          >
            View transcript →
          </button>
        </div>
      </blockquote>
    );
  }

  function renderMemoSection(type: string, linkedKey: string): React.ReactNode {
    const sectionMemos = memos.filter((m) => m.linked_key === linkedKey);
    const isAdding = addingMemoKey === linkedKey;
    if (!sectionMemos.length && !isAdding) return null;
    return (
      <div style={{ marginTop: 8 }}>
        {sectionMemos.map((m) => (
          <div key={m.id} className="memo-card">
            {editingMemoId === m.id ? (
              <div>
                <textarea className="field-input" value={editingMemoContent} onChange={(e) => setEditingMemoContent(e.target.value)} rows={3} style={{ width: "100%", marginBottom: 6 }} />
                <div style={{ display: "flex", gap: 6 }}>
                  <button className="btn btn-primary btn-xs" onClick={() => handleUpdateMemo(m.id)}>Save</button>
                  <button className="btn btn-ghost btn-xs" onClick={() => setEditingMemoId(null)}>Cancel</button>
                </div>
              </div>
            ) : (
              <div>
                <p style={{ margin: 0, whiteSpace: "pre-wrap", fontSize: 13 }}>{m.content}</p>
                <div style={{ display: "flex", gap: 6, marginTop: 4, alignItems: "center" }}>
                  <button className="btn btn-ghost btn-xs" onClick={() => { setEditingMemoId(m.id); setEditingMemoContent(m.content); }}>Edit</button>
                  <button className="btn btn-ghost btn-xs btn-danger-text" onClick={() => handleDeleteMemo(m.id)}>Delete</button>
                  <span style={{ fontSize: 11, color: "var(--text-tertiary)", marginLeft: "auto" }}>
                    {timeAgo(m.updated_at || m.created_at)}
                  </span>
                </div>
              </div>
            )}
          </div>
        ))}
        {isAdding && (
          <div style={{ marginTop: 4 }}>
            <textarea className="field-input" value={newMemoContent} onChange={(e) => setNewMemoContent(e.target.value)} placeholder={tProject("responses.memoPlaceholder")} rows={3} style={{ width: "100%", marginBottom: 6 }} autoFocus />
            <div style={{ display: "flex", gap: 6 }}>
              <button className="btn btn-primary btn-xs" onClick={() => handleAddMemo(type, linkedKey)}>Save</button>
              <button className="btn btn-ghost btn-xs" onClick={() => { setAddingMemoKey(null); setNewMemoContent(""); }}>Cancel</button>
            </div>
          </div>
        )}
      </div>
    );
  }

  // ── Early returns ──────────────────────────────────────────────────────────

  if (loading) return <div className="page-center"><p className="muted-text">{tProject("detail.loadingProject")}</p></div>;
  if (!project) return <div className="page-center"><p>{tProject("detail.projectNotFound")}</p></div>;

  const completedCount = participants.filter((p) => p.status === "completed").length;
  const filterOptions = getFilterOptions();
  const hasFilterOptions = Object.keys(filterOptions).length > 0;

  const sections = project.questions.reduce((acc, q) => {
    if (!acc[q.section_title]) acc[q.section_title] = [];
    acc[q.section_title].push(q);
    return acc;
  }, {} as Record<string, typeof project.questions>);

  // ── Screening helpers ──────────────────────────────────────────────────────

  async function saveProjectMeta(fields: { research_objective?: string; welcome_message?: string }) {
    if (!project) return;
    setSavingMeta(true);
    try {
      const updated = await updateProject(id!, {
        name: project.name,
        language: project.language,
        interview_duration_minutes: project.interview_duration_minutes,
        research_objective: fields.research_objective ?? project.research_objective,
        welcome_message: fields.welcome_message ?? project.welcome_message,
        questions: project.questions.map((q) => ({
          section_index: q.section_index, section_title: q.section_title,
          question_index: q.question_index, main_question: q.main_question,
          interview_notes: q.interview_notes, desired_learning: q.desired_learning,
        })),
        screening_questions: (project.screening_questions ?? []).map((sq) => ({
          question: sq.question, options: sq.options, disqualifying_options: sq.disqualifying_options,
        })),
      });
      setProject(updated);
      setEditingObjective(false);
      setEditingWelcome(false);
    } finally {
      setSavingMeta(false);
    }
  }

  function startEditScreening() {
    setScreeningDraft((project?.screening_questions ?? []).map((sq) => ({
      question: sq.question, options: sq.options, disqualifying_options: sq.disqualifying_options,
    })));
    setExpandedSQ(null);
    setEditingScreening(true);
  }

  async function saveScreening() {
    if (!project) return;
    setScreeningSaving(true);
    try {
      const updated = await updateProject(id!, {
        name: project.name,
        language: project.language,
        interview_duration_minutes: project.interview_duration_minutes,
        research_objective: project.research_objective,
        questions: project.questions.map((q) => ({
          section_index: q.section_index, section_title: q.section_title,
          question_index: q.question_index, main_question: q.main_question,
          interview_notes: q.interview_notes, desired_learning: q.desired_learning,
        })),
        screening_questions: screeningDraft.filter((sq) => sq.question.trim()),
      });
      setProject(updated);
      setEditingScreening(false);
      setExpandedSQ(null);
    } catch { toast(tProject("toasts.screeningSaveFailed"), "error"); }
    finally { setScreeningSaving(false); }
  }

  function sqAddQuestion() {
    setScreeningDraft((prev) => [...prev, { question: "", options: ["", ""], disqualifying_options: [] }]);
    setExpandedSQ(screeningDraft.length);
  }
  function sqRemove(i: number) { setScreeningDraft((prev) => prev.filter((_, idx) => idx !== i)); setExpandedSQ(null); }
  function sqSetQuestion(i: number, v: string) { setScreeningDraft((prev) => prev.map((sq, idx) => idx === i ? { ...sq, question: v } : sq)); }
  function sqSetOption(sqIdx: number, optIdx: number, v: string) {
    setScreeningDraft((prev) => prev.map((sq, idx) => {
      if (idx !== sqIdx) return sq;
      const old = sq.options[optIdx];
      return { ...sq, options: sq.options.map((o, oi) => oi === optIdx ? v : o), disqualifying_options: sq.disqualifying_options.map((d) => d === old ? v : d) };
    }));
  }
  function sqAddOption(sqIdx: number) { setScreeningDraft((prev) => prev.map((sq, idx) => idx === sqIdx ? { ...sq, options: [...sq.options, ""] } : sq)); }
  function sqRemoveOption(sqIdx: number, optIdx: number) {
    setScreeningDraft((prev) => prev.map((sq, idx) => {
      if (idx !== sqIdx) return sq;
      const removed = sq.options[optIdx];
      return { ...sq, options: sq.options.filter((_, oi) => oi !== optIdx), disqualifying_options: sq.disqualifying_options.filter((d) => d !== removed) };
    }));
  }
  function sqToggleDisq(sqIdx: number, option: string) {
    setScreeningDraft((prev) => prev.map((sq, idx) => {
      if (idx !== sqIdx) return sq;
      const isDisq = sq.disqualifying_options.includes(option);
      return { ...sq, disqualifying_options: isDisq ? sq.disqualifying_options.filter((d) => d !== option) : [...sq.disqualifying_options, option] };
    }));
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  const isCollecting = links.some((l) => l.is_active);

  // Credit gate: a study targeting more interviews than the workspace has
  // credits (1 credit = 1 completed interview) can't be fielded to target.
  // We hard-block link generation until the researcher lowers the target or
  // tops up. Null credits = legacy plan → no gate.
  const targetParticipants = project?.target_participants ?? null;
  const insufficientCredits =
    targetParticipants != null &&
    availableCredits != null &&
    targetParticipants > availableCredits;

  // Deterministic next-best-action input for this round. Drives the
  // empty-state suggestion today; the Copilot dock (Phase 2b) reuses it.
  const projectNbaInput: ProjectNbaInput = {
    guideQuestionCount: project?.questions?.length ?? 0,
    activeLinkCount: links.filter((l) => l.is_active).length,
    completedCount: participants.filter((p) => p.status === "completed").length,
    inProgressCount: participants.filter((p) => p.status !== "completed").length,
    analysisStatus:
      (analysis?.status as ProjectNbaInput["analysisStatus"]) ?? "none",
    analysisParticipantCount: analysis?.participant_count ?? 0,
    annotationCount: Object.keys(themeAnnotations).length,
    targetParticipants,
  };
  const projectMission = tDashboard(PROJECT_MISSION_KEYS[tab]);
  const projectNextAction = resolveProjectNextAction(projectNbaInput);

  /** Add a blank guide question inline (then edit it in place). The old
   *  wizard used to own this; the copilot drafts whole guides, this is
   *  the manual fallback. */
  const addBlankGuideQuestion = async () => {
    if (!id) return;
    // Guide content follows the PROJECT's language (participants see it),
    // not the researcher's UI language.
    const guideIsFr = (project?.language ?? "en").startsWith("fr");
    try {
      await createGuideQuestion(id, {
        section_title: "Questions",
        main_question: guideIsFr ? "Nouvelle question" : "New question",
      });
      const fresh = await getProject(id);
      setProject(fresh);
    } catch {
      toast(tProject("setup.addQuestionError"), "error");
    }
  };
  const instrumentSections = [
    { key: "overview", label: tProject("detail.tabOverview") },
    { key: "setup", label: tProject("detail.tabSetup") },
    {
      key: "responses",
      label: tProject("detail.tabResponses"),
      badge:
        participants.length > 0
          ? `${completedCount}/${participants.length}`
          : undefined,
    },
    {
      key: "analysis",
      label: tProject("detail.tabAnalysis"),
      badge:
        analysis?.status === "generating" ? (
          <span className="tab-dot tab-dot-pulse" />
        ) : undefined,
    },
  ];

  return (
    <InstrumentShell
      crumbs={(() => {
        // The parent-study link must NEVER be dropped — it's the only way
        // back to the study workspace. When the round shares the study's
        // name (auto-named single-round studies, the demo study), avoid
        // the duplicated text by labelling the leaf crumb "Interviews"
        // instead of repeating the name.
        const sameName =
          !!project.study_name &&
          project.study_name.trim() === project.name.trim();
        return [
          { label: tProject("shell:instrument.crumbStudies"), to: "/studies" },
          ...(project.study_id
            ? [
                {
                  label:
                    project.study_name ||
                    tProject("shell:instrument.fallbackStudy"),
                  to: `/studies/${project.study_id}`,
                },
              ]
            : []),
          {
            label: sameName
              ? tProject("shell:instrument.crumbInterviewRound")
              : project.name,
          },
        ];
      })()}
      eyebrow={
        project.plan_context
          ? tProject("shell:instrument.eyebrowPlanStep", {
              index: project.plan_context.step_index,
              total: project.plan_context.total_steps,
              plan: project.plan_context.plan_name,
            })
          : tProject("shell:instrument.eyebrowInterviewRound")
      }
      title={
        <input
          type="text"
          className="survey-editor__title-input"
          value={project.name}
          onChange={(e) =>
            setProject((p) => (p ? { ...p, name: e.target.value } : p))
          }
          onBlur={() => {
            if (!id || !project.name.trim()) return;
            patchProjectSettings(id, { name: project.name.trim() }).catch(() =>
              toast(tProject("toasts.roundRenameFailed"), "error"),
            );
          }}
          aria-label={tProject("a11y.roundName")}
          title={project.name}
        />
      }
      status={
        isCollecting
          ? {
              label: tProject("shell:instrument.statusCollecting"),
              tone: "live" as const,
            }
          : {
              label: tProject("shell:instrument.statusPaused"),
              tone: "draft" as const,
            }
      }
      actions={
        <div className="detail-header-actions">
          {/* Desktop: inline actions */}
          <button className="btn btn-ghost btn-sm detail-header-actions__inline" onClick={handleExportCSV}>{tProject("responses.exportCSV")}</button>
          <button className="btn btn-ghost btn-sm detail-header-actions__inline" onClick={handleArchive}>{tProject("detail.archiveProject")}</button>
          {/* Overflow menu: always shown (holds destructive actions), and on
              mobile (<768px) it also absorbs the inline actions above. */}
          <div className="overflow-menu detail-header-actions__overflow" ref={headerMenuRef}>
            <button
              className="overflow-menu__trigger"
              aria-haspopup="menu"
              aria-expanded={headerMenuOpen}
              aria-label={tProject("detail.moreActions")}
              onClick={() => setHeaderMenuOpen((v) => !v)}
            >
              ⋯
            </button>
            {headerMenuOpen && (
              <div className="overflow-menu__dropdown" role="menu">
                <button role="menuitem" className="overflow-menu__item overflow-menu__item--compact-only" onClick={() => { setHeaderMenuOpen(false); handleExportCSV(); }}>
                  {tProject("responses.exportCSV")}
                </button>
                <button role="menuitem" className="overflow-menu__item overflow-menu__item--compact-only" onClick={() => { setHeaderMenuOpen(false); handleArchive(); }}>
                  {tProject("detail.archiveProject")}
                </button>
                <button role="menuitem" className="overflow-menu__item overflow-menu__item--danger" onClick={() => { setHeaderMenuOpen(false); setDeleteProjectTyped(""); setDeleteProjectOpen(true); }}>
                  {tProject("detail.deleteProject")}
                </button>
              </div>
            )}
          </div>
        </div>
      }
      sections={instrumentSections}
      activeSection={tab}
      onSectionChange={(k) => setTab(k as Tab)}
      subNavLabel="Project sections"
    >
      {/* Visually-hidden a11y announcer for inline-edit state */}
      <div aria-live="polite" className="sr-only" role="status">{editAnnouncement}</div>

      <main className="detail-main">

        {/* ── Unsaved-changes banner (replaces blocking confirm dialog) ── */}
        {pendingTab && (
          <div className="unsaved-banner" role="alert" style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
            padding: "12px 16px",
            background: "var(--warning-bg, #fff7ed)",
            border: "1px solid var(--warning, #f59e0b)",
            borderRadius: 8,
            marginBottom: 16,
          }}>
            <span style={{ color: "var(--warning-text, #92400e)", fontSize: 14 }}>
              {tProject("detail.unsavedChanges")}
            </span>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-ghost btn-sm" onClick={() => setPendingTab(null)}>
                {tCommon("cancel")}
              </button>
              <button className="btn btn-primary btn-sm" onClick={confirmDiscardUnsaved}>
                {tProject("transcript.discardContinue")}
              </button>
            </div>
          </div>
        )}

        {/* ── Demo project banner ── */}
        {project.is_demo && (
          <div className="demo-banner">
            <p>{tProject("detail.demoBannerText")}</p>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              style={{ whiteSpace: "nowrap", flexShrink: 0 }}
              onClick={() => {
                const sp = new URLSearchParams(searchParams);
                sp.set("tour", "1");
                setSearchParams(sp);
              }}
            >
              {tProject("tour.replay")}
            </button>
            <Link to="/dashboard" className="btn btn-primary btn-sm" style={{ whiteSpace: "nowrap", textDecoration: "none", flexShrink: 0 }}>
              {tProject("detail.demoBannerCta")}
            </Link>
          </div>
        )}

        {/* ── Guided tour of the demo project. Mounts when the Studies-home
            callout armed it (sessionStorage) or on an explicit ?tour=1
            replay from the demo banner. The user drives it — the tour only
            reacts to their own tab clicks via currentTab. ── */}
        {project.is_demo &&
          (searchParams.get("tour") === "1" ||
            (isDemoTourArmed() && getDemoTourPhase() === "study")) && (
          <DemoTour
            currentTab={tab as "overview" | "setup" | "responses" | "analysis"}
            goToTab={(k) => applyTab(k as Tab)}
            onExit={() => {
              const sp = new URLSearchParams(searchParams);
              sp.delete("tour");
              setSearchParams(sp, { replace: true });
            }}
            onOpenReport={handleExportReport}
            onGoToDashboard={() => navigate("/dashboard")}
          />
        )}

        {/* ══ OVERVIEW ══ */}
        {tab === "overview" && (
          <div className="tab-content" role="tabpanel" id="isection-panel-overview" aria-labelledby="isection-tab-overview">
            {/* Project hero strip — brand band with eyebrow + state */}
            {(() => {
              const isReady = analysis?.status === "ready";
              const isGenerating = analysis?.status === "generating";
              const hasResponses = participants.length > 0;
              let stateClass = "eyebrow-tag eyebrow-tag--info";
              let stateLabel = tProject("hero.stateSetup", { defaultValue: "Setup" });
              if (isReady) {
                stateClass = "eyebrow-tag eyebrow-tag--success pulse-soft";
                stateLabel = tProject("hero.stateAnalysisReady", { defaultValue: "Analysis ready" });
              } else if (isGenerating) {
                stateClass = "eyebrow-tag eyebrow-tag--info";
                stateLabel = tProject("hero.stateAnalysing", { defaultValue: "Analysing…" });
              } else if (hasResponses) {
                stateClass = "eyebrow-tag eyebrow-tag--info";
                stateLabel = tProject("hero.stateCollecting", { defaultValue: "Collecting responses" });
              }
              // Eyebrow reflects link state so it agrees with the breadcrumb's
              // Active/Inactive label rather than always saying "Active study".
              const hasAnyActiveLink = links.some((l) => l.is_active);
              const eyebrowLabel = project.is_demo
                ? tProject("hero.eyebrowDemo", { defaultValue: "Demo project" })
                : hasAnyActiveLink
                  ? tProject("hero.eyebrowActive", { defaultValue: "Active study" })
                  : tProject("hero.eyebrowDraft", { defaultValue: "Study draft" });
              const eyebrowClass = project.is_demo
                ? "eyebrow-tag eyebrow-tag--warning"
                : "eyebrow-tag";
              return (
                <section className="project-hero-strip" aria-label={tProject("hero.aria", { defaultValue: "Study overview" })}>
                  <div className="project-hero-strip__body">
                    <span className={`${eyebrowClass} project-hero-strip__eyebrow`}>{eyebrowLabel}</span>
                    <h2 className="project-hero-strip__title">{project.name}</h2>
                    {project.research_objective && (
                      <p className="project-hero-strip__objective">{project.research_objective}</p>
                    )}
                  </div>
                  <div className="project-hero-strip__state">
                    <span className={stateClass}>{stateLabel}</span>
                  </div>
                </section>
              );
            })()}
            <div className="stats-row">
              <div className="stat-card"><div className="stat-value">{participants.length || "—"}</div><div className="stat-label">{tProject("overview.totalParticipants")}</div></div>
              <div className={`stat-card${completedCount > 0 ? " stat-card--success" : ""}`}><div className="stat-value">{completedCount || "—"}</div><div className="stat-label">{tProject("overview.completed")}</div></div>
              <div className="stat-card">
                <div className="stat-value">{participants.length > 0 ? `${Math.round((completedCount / participants.length) * 100)}%` : "—"}</div>
                <div className="stat-label">{tProject("overview.completionRate")}</div>
              </div>
              <div className={`stat-card${project.questions.length === 0 ? " stat-card--warning" : " stat-card--muted"}`}>
                <div className="stat-value">{project.questions.length}</div>
                <div className="stat-label">{tProject("overview.guideQuestions")}</div>
                {project.questions.length === 0 && (
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4, fontStyle: "italic" }}>{tProject("overview.noQuestionsHint")}</div>
                )}
              </div>
            </div>
            {/* Analysis readiness prompt */}
            {completedCount >= 3 && (!analysis || (analysis.status === "ready" && analysis.participant_count < completedCount)) && (
              <div className="analysis-prompt">
                <span className="analysis-prompt__icon">✦</span>
                <div className="analysis-prompt__body">
                  <div className="analysis-prompt__title">
                    {!analysis
                      ? tProject("overview.readyForAnalysis", { count: completedCount })
                      : tProject("overview.newSinceAnalysis", { count: completedCount - (analysis.participant_count || 0) })}
                  </div>
                  <div className="analysis-prompt__desc">
                    {!analysis
                      ? tProject("overview.readyForAnalysisDesc")
                      : tProject("overview.refreshAnalysisDesc")}
                  </div>
                </div>
                <button className="btn btn-primary btn-sm" onClick={() => setTab("analysis")} style={{ flexShrink: 0 }}>
                  {!analysis ? tProject("overview.generateInsights") : tProject("overview.refreshAnalysis")}
                </button>
              </div>
            )}

            {/* Research Objective — inline edit */}
            <section className="detail-section">
              <div className="section-header-row">
                <h2>{tProject("overview.researchObjective")}</h2>
                {!editingObjective && (
                  <button className="btn btn-ghost btn-sm" onClick={() => {
                    setObjectiveDraft(project.research_objective ?? "");
                    setEditingObjective(true);
                    setEditAnnouncement(tProject("detail.editingFieldAria", { field: tProject("overview.researchObjective") }));
                  }}>{tProject("overview.editObjective", { defaultValue: "Edit objective" })}</button>
                )}
              </div>
              {editingObjective ? (
                <div>
                  <textarea
                    className="field-input"
                    rows={3}
                    value={objectiveDraft}
                    onChange={(e) => setObjectiveDraft(e.target.value)}
                    placeholder={tProject("overview.objectivePlaceholder")}
                    style={{ resize: "vertical" }}
                  />
                  <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                    <button className="btn btn-primary btn-sm" onClick={() => saveProjectMeta({ research_objective: objectiveDraft })} disabled={savingMeta}>{savingMeta ? tCommon("saving") : tCommon("save")}</button>
                    <button className="btn btn-ghost btn-sm" onClick={() => setEditingObjective(false)}>{tCommon("cancel")}</button>
                  </div>
                </div>
              ) : (
                <p className="objective-text" style={{ color: project.research_objective ? undefined : "var(--text-muted)", fontStyle: project.research_objective ? undefined : "italic" }}>
                  {project.research_objective || tProject("overview.noObjective")}
                </p>
              )}
            </section>

            {/* Welcome Message — inline edit */}
            <section className="detail-section">
              <div className="section-header-row">
                <h2>{tProject("overview.welcomeMessageLabel")} <span className="optional-tag">{tProject("overview.welcomeMessageHint")}</span></h2>
                {!editingWelcome && (
                  <button className="btn btn-ghost btn-sm" onClick={() => {
                    setWelcomeDraft(project.welcome_message ?? "");
                    setEditingWelcome(true);
                    setEditAnnouncement(tProject("detail.editingFieldAria", { field: tProject("overview.welcomeMessageLabel") }));
                  }}>{tProject("overview.editWelcome", { defaultValue: "Edit welcome message" })}</button>
                )}
              </div>
              {editingWelcome ? (
                <div>
                  <textarea
                    className="field-input"
                    rows={3}
                    value={welcomeDraft}
                    onChange={(e) => setWelcomeDraft(e.target.value)}
                    placeholder={tProject("overview.welcomePlaceholder")}
                    style={{ resize: "vertical" }}
                  />
                  <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                    <button className="btn btn-primary btn-sm" onClick={() => saveProjectMeta({ welcome_message: welcomeDraft })} disabled={savingMeta}>{savingMeta ? tCommon("saving") : tCommon("save")}</button>
                    <button className="btn btn-ghost btn-sm" onClick={() => setEditingWelcome(false)}>{tCommon("cancel")}</button>
                  </div>
                </div>
              ) : (
                <p className="objective-text" style={{ color: project.welcome_message ? undefined : "var(--text-muted)", fontStyle: project.welcome_message ? undefined : "italic" }}>
                  {project.welcome_message || tProject("overview.noWelcomeMessage")}
                </p>
              )}
            </section>
            <section className="detail-section" data-tour="overview-link">
              <div className="section-header-row">
                <h2>{tProject("overview.interviewLinkTitle")}</h2>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={handleGenerateLink}
                  disabled={project.is_demo || insufficientCredits}
                  title={
                    project.is_demo
                      ? tProject("overview.demoLinkDisabled")
                      : insufficientCredits
                        ? tProject("overview.linkBlockedTitle", { defaultValue: "Not enough credits for your target" })
                        : undefined
                  }
                >{tProject("overview.newLink")}</button>
              </div>
              {insufficientCredits && (
                <div className="credit-gate">
                  <div className="credit-gate__title">
                    {tProject("overview.creditGateTitle", {
                      defaultValue: "Not enough credits to field this study",
                    })}
                  </div>
                  <p className="credit-gate__body">
                    {tProject("overview.creditGateBody", {
                      target: targetParticipants,
                      credits: availableCredits,
                      defaultValue:
                        "Your target is {{target}} interviews, but you have {{credits}} credit(s) — 1 credit = 1 completed interview. Lower your target or get more credits to generate the link.",
                    })}
                    {(availableCredits ?? 0) < 5 && (
                      <> {tProject("overview.creditGateBelowMin", {
                        credits: availableCredits,
                        defaultValue:
                          "Heads up: {{credits}} is below ~5, the minimum for reliable findings — topping up is the better call.",
                      })}</>
                    )}
                  </p>
                  <div className="credit-gate__actions">
                    {/* Only offer the lower-target shortcut when it still
                        lands on a genuine sample (>= 5). Below that we don't
                        nudge an underpowered study — the user can lower it
                        themselves in Setup if they really want to. */}
                    {(availableCredits ?? 0) >= 5 && (
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={async () => {
                        try {
                          setProject(
                            await patchProjectSettings(project.id, {
                              target_participants: availableCredits ?? undefined,
                            }),
                          );
                          toast(
                            tProject("overview.creditGateLowered", {
                              credits: availableCredits,
                              defaultValue: "Target set to {{credits}} — you can generate the link now.",
                            }),
                            "success",
                          );
                        } catch {
                          toast(tProject("setup.warmupSaveError", { defaultValue: "Couldn't save. Please try again." }), "error");
                        }
                      }}
                    >
                      {tProject("overview.creditGateLower", {
                        credits: availableCredits,
                        defaultValue: "Set target to {{credits}} & continue",
                      })}
                    </button>
                    )}
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={() =>
                        setUnlockState({
                          open: true,
                          lockedCount: (targetParticipants ?? 0) - (availableCredits ?? 0),
                          mode: "credits",
                        })
                      }
                    >
                      {tProject("overview.creditGateUpgrade", { defaultValue: "Get more credits" })}
                    </button>
                  </div>
                </div>
              )}
              {links.length === 0 ? (
                <p className="muted-text">{tProject("overview.noLinksHint")}</p>
              ) : (
                <div className="links-list">
                  {links.map((l) => (
                    <div key={l.id} className={`link-row${l.is_active ? "" : " link-row--inactive"}`}>
                      <div className="link-row-main">
                        <span className={`link-status-badge ${l.is_active ? "link-status-badge--active" : "link-status-badge--inactive"}`}>
                          {l.is_active ? tProject("overview.linkActive") : tProject("overview.linkInactive")}
                        </span>
                        <code className="link-url" title={interviewUrl(l.token)}>{interviewUrl(l.token)}</code>
                        <span className="link-cap-summary">
                          {capEditLinkId === l.id ? (
                            <>
                              <input
                                type="number"
                                min={1}
                                className="link-cap-input"
                                value={capDraft}
                                autoFocus
                                aria-label={tProject("overview.capAriaLabel")}
                                placeholder={tProject("overview.capNoLimit")}
                                onChange={(e) => setCapDraft(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") handleSaveCap(l.id);
                                  if (e.key === "Escape") setCapEditLinkId(null);
                                }}
                              />
                              <button className="btn btn-ghost btn-sm" onClick={() => handleSaveCap(l.id)}>
                                {tProject("overview.capSave")}
                              </button>
                              <button className="btn btn-ghost btn-sm" onClick={() => setCapEditLinkId(null)}>
                                {tCommon("cancel")}
                              </button>
                            </>
                          ) : (
                            <button
                              className="link-cap-pill"
                              onClick={() => {
                                setCapEditLinkId(l.id);
                                setCapDraft(l.max_participants ? String(l.max_participants) : "");
                              }}
                            >
                              {l.max_participants
                                ? tProject("overview.capUsage", {
                                    used: l.participant_count,
                                    max: l.max_participants,
                                  })
                                : tProject("overview.capSet")}
                            </button>
                          )}
                        </span>
                      </div>
                      <div className="link-row-actions">
                        {l.is_active && (
                          <button className="btn btn-ghost btn-sm" onClick={() => copyLink(l.token)}>
                            {copiedToken === l.token ? `✓ ${tProject("overview.linkCopied")}` : tProject("overview.copyLink")}
                          </button>
                        )}
                        {l.is_active && (
                          <button
                            className="btn btn-ghost btn-sm"
                            aria-expanded={inviteLinkId === l.id}
                            onClick={() => {
                              setInviteLinkId(inviteLinkId === l.id ? null : l.id);
                              setInviteText("");
                            }}
                          >
                            {tProject("overview.inviteEmails")}
                          </button>
                        )}
                        <button
                          className={`btn btn-sm ${l.is_active ? "btn-ghost" : "btn-secondary"}`}
                          onClick={() => handleToggleLink(l.id)}
                        >
                          {l.is_active ? tProject("overview.deactivateLink") : tProject("overview.activateLink")}
                        </button>
                      </div>
                      {inviteLinkId === l.id && (
                        <div className="link-invite-panel">
                          <label htmlFor={`invite-emails-${l.id}`} className="link-invite-label">
                            {tProject("overview.invitePanelHint")}
                          </label>
                          <textarea
                            id={`invite-emails-${l.id}`}
                            className="link-invite-textarea"
                            rows={3}
                            value={inviteText}
                            autoFocus
                            placeholder={tProject("overview.invitePlaceholder")}
                            onChange={(e) => setInviteText(e.target.value)}
                          />
                          <div className="link-invite-actions">
                            <button
                              className="btn btn-primary btn-sm"
                              disabled={inviteSending || inviteText.trim() === ""}
                              onClick={() => handleSendInvites(l.id)}
                            >
                              {inviteSending ? tProject("overview.inviteSending") : tProject("overview.inviteSend")}
                            </button>
                            <button className="btn btn-ghost btn-sm" onClick={() => setInviteLinkId(null)}>
                              {tCommon("cancel")}
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>
        )}

        {/* ══ SETUP ══ */}
        {tab === "setup" && (
          <div className="tab-content" role="tabpanel" id="isection-panel-setup" aria-labelledby="isection-tab-setup">
            {/* Live-study warning: edits affect future participants */}
            {(() => {
              const hasInProgress = participants.some((p) => p.status === "in_progress");
              const hasActiveLink = links.some((l) => l.is_active);
              const hasCompleted = participants.some((p) => p.status === "completed");
              if (!hasInProgress && !(hasActiveLink && hasCompleted)) return null;
              return (
                <div className="setup-live-warning" role="status">
                  <span className="setup-live-warning__icon" aria-hidden="true">⚠</span>
                  <div>
                    <strong>{tProject("setupLiveWarning.title")}</strong>{" "}
                    <span>{tProject("setupLiveWarning.desc")}</span>
                  </div>
                </div>
              );
            })()}

            {/* PF-3: Conversation style — per-project toggles for the AI moderator's
                opening behaviour. Currently just the warm-up; future flags
                (live-coaching tips, short-answer adaptation, etc.) slot in here. */}
            <section className="detail-section">
              <div className="section-header-row">
                <div>
                  <h2>{tProject("setup.conversationStyleTitle", { defaultValue: "Conversation style" })}</h2>
                  <p className="muted-text" style={{ fontSize: 13, marginTop: 2 }}>
                    {tProject("setup.conversationStyleSubtitle", { defaultValue: "How the AI moderator opens and paces the interview." })}
                  </p>
                </div>
              </div>
              <label className="setting-toggle-row" htmlFor="warmup-toggle">
                <input
                  id="warmup-toggle"
                  type="checkbox"
                  checked={project.warmup_enabled !== false}
                  onChange={async (e) => {
                    const next = e.target.checked;
                    try {
                      const updated = await patchProjectSettings(project.id, { warmup_enabled: next });
                      setProject(updated);
                      toast(
                        tProject(next ? "setup.warmupOnSaved" : "setup.warmupOffSaved", {
                          defaultValue: next ? "Warm-up enabled" : "Warm-up disabled",
                        }),
                        "success"
                      );
                    } catch {
                      toast(tProject("setup.warmupSaveError", { defaultValue: "Couldn't save. Please try again." }), "error");
                    }
                  }}
                />
                <div className="setting-toggle-row__copy">
                  <strong>{tProject("setup.warmupLabel", { defaultValue: "Open with a warm-up question" })}</strong>
                  <span className="muted-text" style={{ fontSize: 12 }}>
                    {tProject("setup.warmupHelp", {
                      defaultValue: "A low-stakes icebreaker before the real research questions. Recommended.",
                    })}
                  </span>
                  <span className="muted-text" style={{ fontSize: 12, fontStyle: "italic" }}>
                    {tProject("setup.warmupExample", {
                      defaultValue:
                        "The AI writes it from your research objective. Example: “Welcome! Before we dive in, what does a typical week look like for you?”",
                    })}
                  </span>
                </div>
              </label>
            </section>

            {/* Interview plan — length + sample-size target. The Research
                Copilot recommends + sets these; surfaced here so they're
                visible and hand-editable. */}
            <section className="detail-section">
              <div className="section-header-row">
                <div>
                  <h2>{tProject("setup.planTitle", { defaultValue: "Interview plan" })}</h2>
                  <p className="muted-text" style={{ fontSize: 13, marginTop: 2 }}>
                    {tProject("setup.planSubtitle", { defaultValue: "How long each interview runs and how many you're aiming to collect." })}
                  </p>
                </div>
              </div>
              <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
                <div>
                  <label className="field-label" htmlFor="plan-duration">
                    {tProject("setup.planDurationLabel", { defaultValue: "Interview length (minutes)" })}
                  </label>
                  <input
                    id="plan-duration"
                    // Re-key on the project value so the uncontrolled input
                    // remounts (and shows the new value) when the Copilot
                    // applies a settings change.
                    key={`dur-${project.interview_duration_minutes}`}
                    className="field-input"
                    type="number"
                    min={5}
                    max={120}
                    style={{ width: 120 }}
                    defaultValue={project.interview_duration_minutes}
                    onBlur={async (e) => {
                      const n = parseInt(e.target.value, 10);
                      if (!Number.isFinite(n) || n === project.interview_duration_minutes) return;
                      try {
                        setProject(await patchProjectSettings(project.id, { interview_duration_minutes: n }));
                        toast(tProject("setup.planSaved", { defaultValue: "Saved" }), "success");
                      } catch {
                        toast(tProject("setup.warmupSaveError", { defaultValue: "Couldn't save. Please try again." }), "error");
                      }
                    }}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="plan-target">
                    {tProject("setup.planTargetLabel", { defaultValue: "Target number of interviews" })}
                  </label>
                  <input
                    id="plan-target"
                    key={`tgt-${project.target_participants ?? ""}`}
                    className="field-input"
                    type="number"
                    min={1}
                    max={1000}
                    style={{ width: 120 }}
                    placeholder={tProject("setup.planTargetPlaceholder", { defaultValue: "e.g. 12" })}
                    defaultValue={project.target_participants ?? ""}
                    onBlur={async (e) => {
                      const raw = e.target.value.trim();
                      const n = raw === "" ? null : parseInt(raw, 10);
                      if (n !== null && !Number.isFinite(n)) return;
                      if (n === (project.target_participants ?? null)) return;
                      try {
                        setProject(await patchProjectSettings(project.id, { target_participants: n ?? undefined }));
                        toast(tProject("setup.planSaved", { defaultValue: "Saved" }), "success");
                      } catch {
                        toast(tProject("setup.warmupSaveError", { defaultValue: "Couldn't save. Please try again." }), "error");
                      }
                    }}
                  />
                  {project.target_participants == null ? (
                    <p className="field-hint" style={{ fontSize: 12, marginTop: 4 }}>
                      {tProject("setup.planTargetHint", { defaultValue: "At least 5 recommended for reliable findings." })}
                    </p>
                  ) : project.target_participants < 5 ? (
                    <p className="field-hint field-hint--warning" style={{ fontSize: 12, marginTop: 4, color: "var(--warning-text)" }}>
                      {tProject("setup.planTargetTooLow", { defaultValue: "Fewer than 5 interviews may not surface reliable patterns." })}
                    </p>
                  ) : null}
                </div>
              </div>
            </section>

            {/* Branding & identity — participant-facing identity policy
                (standard / branded / anonymous) + brand color & font. */}
            <BrandingSettings project={project} onUpdated={setProject} />

            {/* Screening Questions */}
            <section className="detail-section">
              <div className="section-header-row">
                <div>
                  <h2>{tProject("setup.screeningTitle")}</h2>
                  <p className="muted-text" style={{ fontSize: 13, marginTop: 2 }}>{tProject("setup.screeningSubtitle")}</p>
                </div>
                {!editingScreening && (
                  <div style={{ display: "flex", gap: 8 }}>
                    {(project.screening_questions ?? []).length > 0 && (
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={async () => {
                          try {
                            await regenerateScreeningTranslations(project.id);
                            toast(tProject("toasts.translationsRegenerating"), "info");
                          } catch { toast(tProject("toasts.translationsRegenerateFailed"), "error"); }
                        }}
                      >
                        🌐 {tProject("screeningTranslations.regenerateAll")}
                      </button>
                    )}
                    <button className="btn btn-ghost btn-sm" onClick={startEditScreening}>{tCommon("edit")}</button>
                  </div>
                )}
              </div>

              {!editingScreening && (
                (project.screening_questions ?? []).length === 0 ? (
                  <div className="empty-state-inline">
                    <span>{tProject("setup.noScreeningQuestions")}</span>
                    <button className="btn btn-ghost btn-sm" onClick={startEditScreening}>{tProject("setup.addScreeningArrow")}</button>
                  </div>
                ) : (
                  <div className="screening-list">
                    {(project.screening_questions ?? []).map((sq, i) => (
                      <div key={sq.id} className="screening-card">
                        <div className="screening-card-header">
                          <span className="screening-num">Q{i + 1}</span>
                          <span className="screening-question">{sq.question}</span>
                        </div>
                        <div className="screening-options">
                          {sq.options.map((opt) => (
                            <span key={opt} className={`screening-option ${sq.disqualifying_options.includes(opt) ? "disqualifying" : "allowed"}`}>
                              {sq.disqualifying_options.includes(opt) ? "✕" : "✓"} {opt}
                            </span>
                          ))}
                        </div>
                        <ScreeningTranslationsEditor
                          projectId={project.id}
                          screening={sq}
                          sourceLang={project.language || "en"}
                          onSaved={() => loadAll()}
                        />
                      </div>
                    ))}
                  </div>
                )
              )}

              {editingScreening && (
                <div className="screening-editor">
                  {screeningDraft.map((sq, sqIdx) => (
                    <div key={sqIdx} className="guide-editor-question">
                      <div className="guide-editor-header" onClick={() => setExpandedSQ(expandedSQ === sqIdx ? null : sqIdx)}>
                        <span className="guide-editor-num">Q{sqIdx + 1}</span>
                        <span className="guide-editor-preview" style={{ flex: 1, marginLeft: 8 }}>
                          {sq.question || <em className="muted-text">{tProject("setup.emptyQuestion")}</em>}
                        </span>
                        {sq.disqualifying_options.length > 0 && (
                          <span className="badge" style={{ marginRight: 8, background: "var(--danger-bg)", color: "var(--danger)", fontSize: 11 }}>
                            {tProject("setup.disqualifyingCount", { count: sq.disqualifying_options.length })}
                          </span>
                        )}
                        <span className="guide-editor-chevron">{expandedSQ === sqIdx ? "▲" : "▼"}</span>
                      </div>
                      {expandedSQ === sqIdx && (
                        <div className="guide-editor-body">
                          <label className="field-label">{tProject("setup.questionLabel")}</label>
                          <input className="field-input" value={sq.question} onChange={(e) => sqSetQuestion(sqIdx, e.target.value)} placeholder={tProject("setup.questionPlaceholder")} />
                          <label className="field-label" style={{ marginTop: 12 }}>{tProject("setup.optionsLabel")} <span className="optional-tag">{tProject("setup.optionsHint")}</span></label>
                          {sq.options.map((opt, optIdx) => (
                            <div key={optIdx} style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}>
                              <button
                                className={`screening-disq-toggle${sq.disqualifying_options.includes(opt) ? " screening-disq-toggle--active" : ""}`}
                                onClick={() => opt.trim() && sqToggleDisq(sqIdx, opt)}
                                title={sq.disqualifying_options.includes(opt) ? tProject("a11y.disqualifying") : tProject("a11y.allowed")}
                              >
                                {sq.disqualifying_options.includes(opt) ? "✕" : "✓"}
                              </button>
                              <input className="field-input" style={{ flex: 1, marginBottom: 0 }} value={opt} onChange={(e) => sqSetOption(sqIdx, optIdx, e.target.value)} placeholder={tProject("setup.optionNumber", { number: optIdx + 1 })} />
                              {sq.options.length > 1 && <button style={{ background: "none", border: "none", color: "var(--text-disabled)", cursor: "pointer", fontSize: 18, padding: "0 4px" }} onClick={() => sqRemoveOption(sqIdx, optIdx)}>×</button>}
                            </div>
                          ))}
                          <button className="btn btn-ghost btn-sm" onClick={() => sqAddOption(sqIdx)}>{tProject("setup.addOptionBtn")}</button>
                          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}>
                            <button className="btn btn-ghost btn-sm btn-danger-text" onClick={() => sqRemove(sqIdx)}>{tProject("setup.removeQuestion")}</button>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                  <button className="btn btn-ghost btn-sm" onClick={sqAddQuestion} style={{ marginBottom: 16 }}>{tProject("setup.addScreeningQuestion")}</button>
                  <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                    <button className="btn btn-ghost btn-sm" onClick={() => setEditingScreening(false)}>{tCommon("cancel")}</button>
                    <button className="btn btn-primary btn-sm" onClick={saveScreening} disabled={screeningSaving}>{screeningSaving ? tCommon("saving") : tCommon("save")}</button>
                  </div>
                </div>
              )}
            </section>

            <section className="detail-section">
              <div className="section-header-row">
                <div>
                  <h2>{tProject("setup.guideTitle")}</h2>
                  <p className="muted-text" style={{ fontSize: 13, marginTop: 2 }}>
                    {tProject("setup.activeQuestionsCount", { active: project.questions.filter((q) => !q.deprecated_at).length, sections: Object.keys(sections).length })}
                    {project.questions.some((q) => q.deprecated_at) && (
                      <span className="badge" style={{ marginLeft: 8, background: "var(--danger-bg, #fef2f2)", color: "var(--danger, #dc2626)" }}>
                        {tProject("setup.disabledCount", { count: project.questions.filter((q) => q.deprecated_at).length })}
                      </span>
                    )}
                  </p>
                </div>
                <button className="btn btn-ghost btn-sm" onClick={addBlankGuideQuestion}>{tProject("setup.addQuestions")}</button>
              </div>
              {project.questions.length === 0 ? (
                <div className="guide-empty">
                  <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "flex-start" }}>
                    <NextActionChip
                      action={projectNextAction}
                      variant="inline"
                      onRun={() =>
                        document
                          .querySelector<HTMLButtonElement>(".copilot-fab")
                          ?.click()
                      }
                    />
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={addBlankGuideQuestion}
                      style={{ marginTop: 2 }}
                    >
                      {tProject("guideEmpty.writeMyself")}
                    </button>
                  </div>
                  <p style={{ color: "var(--text-tertiary)", fontSize: 13, marginTop: 10 }}>
{tProject("guideEmpty.aiExplainer")}
                  </p>
                </div>
              ) : (
                <>
                  {/* Active questions */}
                  {Object.entries(sections).map(([title, qs]) => {
                    const activeQs = qs.filter((q) => !q.deprecated_at).sort((a, b) => a.question_index - b.question_index);
                    if (activeQs.length === 0) return null;
                    return (
                      <div key={title} className="guide-section">
                        <h3 className="guide-section-title">{title}</h3>
                        <div>
                          {activeQs.map((q) => {
                            const isEditing = editingQuestionId === q.id;
                            const allSorted = [...project.questions].filter((x) => !x.deprecated_at).sort((a, b) => a.section_index - b.section_index || a.question_index - b.question_index);
                            const globalIdx = allSorted.findIndex((x) => x.id === q.id);
                            const isFirst = globalIdx === 0;
                            const isLast = globalIdx === allSorted.length - 1;
                            return (
                              <div
                                key={q.id}
                                className={`guide-question-card${isEditing ? " guide-question-card--editing" : ""}`}
                              >
                                <div className="guide-question-card__layout">
                                  {/* Reorder arrows */}
                                  <div className="guide-question-card__reorder">
                                    <button
                                      className="btn btn-ghost btn-xs"
                                      style={{ padding: "0 4px", fontSize: 10, lineHeight: 1 }}
                                      disabled={isFirst}
                                      onClick={() => moveQuestion(q.id, "up")}
                                      title={tProject("setup.moveUp")}
                                    >▲</button>
                                    <button
                                      className="btn btn-ghost btn-xs"
                                      style={{ padding: "0 4px", fontSize: 10, lineHeight: 1 }}
                                      disabled={isLast}
                                      onClick={() => moveQuestion(q.id, "down")}
                                      title={tProject("setup.moveDown")}
                                    >▼</button>
                                  </div>

                                  {/* Question text — click to edit */}
                                  <div className="guide-question-card__body">
                                    {isEditing ? (
                                      <div>
                                        <textarea
                                          className="field-input"
                                          value={questionDraft}
                                          onChange={(e) => setQuestionDraft(e.target.value)}
                                          rows={2}
                                          style={{ width: "100%", fontSize: 14, marginBottom: 6 }}
                                          autoFocus
                                          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); saveQuestionText(q.id); } if (e.key === "Escape") setEditingQuestionId(null); }}
                                        />
                                        <div style={{ display: "flex", gap: 6 }}>
                                          <button className="btn btn-primary btn-xs" onClick={() => saveQuestionText(q.id)} disabled={savingQuestionId === q.id}>{savingQuestionId === q.id ? tCommon("saving") : tCommon("save")}</button>
                                          <button className="btn btn-ghost btn-xs" onClick={() => setEditingQuestionId(null)}>{tCommon("cancel")}</button>
                                        </div>
                                      </div>
                                    ) : (
                                      <span
                                        className="guide-question-card__text"
                                        onClick={() => { setEditingQuestionId(q.id); setQuestionDraft(q.main_question); }}
                                        title={tProject("setup.clickToEdit")}
                                      >
                                        {/* Continuous numbering across sections (globalIdx), not per-section. */}
                                        <span className="guide-question-card__num">Q{globalIdx + 1}</span>
                                        {q.main_question}
                                      </span>
                                    )}
                                  </div>

                                  {/* Action buttons */}
                                  {!isEditing && (
                                    <div className="guide-question-card__actions">
                                      <button
                                        className="btn btn-ghost btn-xs"
                                        title={q.researcher_notes ? tProject("setup.editNoteTitle") : tProject("setup.addNoteTitle")}
                                        style={{ color: q.researcher_notes ? "var(--warning)" : undefined }}
                                        onClick={() => {
                                          if (editingNoteId === q.id) { setEditingNoteId(null); }
                                          else { setEditingNoteId(q.id); setNoteText(q.researcher_notes ?? ""); }
                                        }}
                                      >
                                        {q.researcher_notes ? "📝" : tProject("setup.noteBtn")}
                                      </button>
                                      <button
                                        className="btn btn-ghost btn-xs"
                                        onClick={() => setExpandedQuestionId(expandedQuestionId === q.id ? null : q.id)}
                                        title={tProject("setup.interviewNotesTip")}
                                      >
                                        {expandedQuestionId === q.id ? "▲" : "▼"}
                                      </button>
                                      <button
                                        className="btn btn-ghost btn-xs"
                                        title={tProject("setup.disableQuestion")}
                                        onClick={() => toggleDeprecateQuestion(q.id, q.deprecated_at)}
                                      >
                                        ✕
                                      </button>
                                    </div>
                                  )}
                                </div>

                                {/* Researcher note display */}
                                {editingNoteId === q.id && (
                                  <div className="guide-question-card__detail" style={{ marginTop: 8 }}>
                                    <textarea className="field-input" value={noteText} onChange={(e) => setNoteText(e.target.value)} placeholder={tProject("setup.notePlaceholder")} rows={2} style={{ width: "100%", marginBottom: 6, fontSize: 13 }} autoFocus />
                                    <div style={{ display: "flex", gap: 6 }}>
                                      <button className="btn btn-primary btn-xs" onClick={() => saveQuestionNote(q.id)}>{tCommon("save")}</button>
                                      <button className="btn btn-ghost btn-xs" onClick={() => setEditingNoteId(null)}>{tCommon("cancel")}</button>
                                    </div>
                                  </div>
                                )}
                                {q.researcher_notes && editingNoteId !== q.id && (
                                  <div className="guide-question-card__note">
                                    📝 {q.researcher_notes}
                                  </div>
                                )}

                                {/* Interview notes + desired learning (expanded) */}
                                {expandedQuestionId === q.id && (
                                  <div className="guide-question-card__detail">
                                    {(["interview_notes", "desired_learning"] as const).map((field) => {
                                      const label = field === "interview_notes" ? tProject("setup.interviewTips") : tProject("setup.desiredLearning");
                                      const isFieldEditing = editingInterviewNotes?.id === q.id && editingInterviewNotes?.field === field;
                                      return (
                                        <div key={field} className="guide-question-card__detail-field">
                                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                                            <span className="guide-question-card__detail-label">{label}</span>
                                            {!isFieldEditing && (
                                              <button className="btn btn-ghost btn-xs" style={{ fontSize: 10 }} onClick={() => { setEditingInterviewNotes({ id: q.id, field }); setInterviewNotesText(q[field] ?? ""); }}>{tCommon("edit")}</button>
                                            )}
                                          </div>
                                          {isFieldEditing ? (
                                            <>
                                              <textarea className="field-input" value={interviewNotesText} onChange={(e) => setInterviewNotesText(e.target.value)} rows={2} style={{ width: "100%", fontSize: 12, marginBottom: 4 }} autoFocus />
                                              <div style={{ display: "flex", gap: 4 }}>
                                                <button className="btn btn-primary btn-xs" onClick={() => saveInterviewNotes(q.id, field)}>{tCommon("save")}</button>
                                                <button className="btn btn-ghost btn-xs" onClick={() => setEditingInterviewNotes(null)}>{tCommon("cancel")}</button>
                                              </div>
                                            </>
                                          ) : (
                                            <p style={{ fontSize: 12, color: "var(--text-secondary, #374151)", margin: 0 }}>{q[field] || <em className="muted-text">{tProject("setup.noneClickEdit")}</em>}</p>
                                          )}
                                        </div>
                                      );
                                    })}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}

                  {/* Disabled questions section */}
                  {project.questions.some((q) => q.deprecated_at) && (
                    <details style={{ marginTop: 16 }}>
                      <summary style={{ cursor: "pointer", fontSize: 13, color: "var(--text-tertiary)", userSelect: "none" }}>
                        {tProject("setup.disabledQuestions", { count: project.questions.filter((q) => q.deprecated_at).length })}
                      </summary>
                      <div style={{ marginTop: 8 }}>
                        {project.questions.filter((q) => q.deprecated_at).sort((a, b) => a.section_index - b.section_index || a.question_index - b.question_index).map((q) => (
                          <div key={q.id} className="guide-question-card__disabled">
                              <s style={{ flex: 1, color: "var(--text-tertiary)", fontSize: 14 }}>{q.main_question}</s>
                              <button
                                className="btn btn-ghost btn-xs"
                                style={{ color: "var(--primary)", flexShrink: 0 }}
                                onClick={() => toggleDeprecateQuestion(q.id, q.deprecated_at)}
                              >
                                {tProject("setup.reEnable")}
                              </button>
                          </div>
                        ))}
                      </div>
                    </details>
                  )}
                </>
              )}
            </section>

            {/* Publication step: link + test drive + invitation templates,
                so a configured study doesn't dead-end before collection. */}
            <RecruitSharePanel project={project} links={links} />

            {/* System prompt accordion removed — hidden from researchers */}
          </div>
        )}

        {/* ══ RESPONSES ══ */}
        {tab === "responses" && (() => {
          const completedCount = participants.filter(p => p.status === "completed").length;
          const inProgressCount = participants.filter(p => p.status !== "completed").length;

          const qualityOrder: Record<string, number> = { strong: 0, good: 1, fair: 2, low: 3 };
          const filtered = participants
            .filter(p => {
              if (responseStatusFilter === "completed") return p.status === "completed";
              if (responseStatusFilter === "in_progress") return p.status !== "completed";
              return true;
            })
            .sort((a, b) => {
              if (responseSortBy === "name") return (a.display_name || "Anonymous").localeCompare(b.display_name || "Anonymous");
              if (responseSortBy === "quality") {
                const qa = qualityOrder[a.quality_label ?? ""] ?? 99;
                const qb = qualityOrder[b.quality_label ?? ""] ?? 99;
                return qa - qb;
              }
              // date: newest first
              return new Date(b.started_at).getTime() - new Date(a.started_at).getTime();
            });

          function relativeDate(iso: string) {
            const diff = Date.now() - new Date(iso).getTime();
            const mins = Math.floor(diff / 60000);
            if (mins < 60) return `${mins}m ago`;
            const hours = Math.floor(mins / 60);
            if (hours < 24) return `${hours}h ago`;
            const days = Math.floor(hours / 24);
            if (days < 7) return `${days}d ago`;
            return new Date(iso).toLocaleDateString(i18n.language, { month: "short", day: "numeric" });
          }

          function avatarInitial(name: string | null | undefined) {
            const n = name?.trim();
            if (!n) return "?";
            return n[0].toUpperCase();
          }

          return (
          <div className="tab-content" role="tabpanel" id="isection-panel-responses" aria-labelledby="isection-tab-responses" style={{ padding: 0 }}>
            <div ref={setResponsesLayoutRef} className={`responses-layout${selectedParticipant && transcript !== null ? " responses-layout--detail-active" : ""}`}>
              {/* ── Left column: filter + list ── */}
              <div className="responses-list-col">
                {/* Header row */}
                <div style={{ marginBottom: 12 }}>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>{tProject("responses.title")}</span>
                </div>

                {/* Status filter pills */}
                <div role="group" aria-label={tProject("a11y.statusFilter")} style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
                  {(["all", "completed", "in_progress"] as const).map(f => {
                    const label = f === "all" ? tProject("responses.allFilter") : f === "completed" ? tProject("responses.doneFilter") : tProject("responses.inProgressFilter");
                    const count = f === "all" ? participants.length : f === "completed" ? completedCount : inProgressCount;
                    const active = responseStatusFilter === f;
                    return (
                      <button
                        key={f}
                        className={`filter-pill ${active ? "filter-pill--active" : ""}`}
                        aria-pressed={active}
                        onClick={() => setResponseStatusFilter(f)}
                      >
                        {label}
                        <span className={`count-badge${active ? " count-badge--active" : ""}`}>{count}</span>
                      </button>
                    );
                  })}
                </div>

                {/* V4 paywall — visibility banner. Shown when any
                 * participants in this project are locked, so the user
                 * sees the unlock CTA without having to click a locked
                 * row first. */}
                {(() => {
                  const lockedCount = participants.filter((p) => p.is_locked).length;
                  if (lockedCount === 0) return null;
                  return (
                    <div className="paywall-banner">
                      <div className="paywall-banner__icon" aria-hidden>🔒</div>
                      <div className="paywall-banner__body">
                        <div className="paywall-banner__title">
                          {tProject("paywall.lockedTranscripts", { count: lockedCount })}
                        </div>
                        <div className="paywall-banner__sub">
                          {tProject("paywall.sub")}
                        </div>
                      </div>
                      <button
                        type="button"
                        className="btn btn-primary btn-sm"
                        onClick={() => setUnlockState({ open: true, lockedCount })}
                      >
                        {tProject("paywall.unlockCta")}
                      </button>
                    </div>
                  );
                })()}

                {/* Sort */}
                <div style={{ marginBottom: 14 }}>
                  <select
                    className="select-compact"
                    value={responseSortBy}
                    onChange={e => setResponseSortBy(e.target.value as "date" | "quality" | "name")}
                  >
                    <option value="date">{tProject("responses.sortNewest")}</option>
                    <option value="quality">{tProject("responses.sortQuality")}</option>
                    <option value="name">{tProject("responses.sortName")}</option>
                  </select>
                </div>

                {loading ? (
                  <SkeletonTable rows={4} />
                ) : participants.length === 0 ? (
                  <div className="empty-state" style={{ padding: "32px 16px" }}>
                    <p style={{ fontWeight: 500 }}>{tProject("responses.noResponsesYet")}</p>
                    <p className="muted-text" style={{ fontSize: 12, marginTop: 4 }}>{tProject("responses.shareLink")}</p>
                    <button className="btn btn-ghost btn-sm" style={{ marginTop: 10 }} onClick={() => setTab("overview")}>{tProject("responses.createLinkCta")} →</button>
                  </div>
                ) : filtered.length === 0 ? (
                  <div style={{ padding: "24px 0", textAlign: "center" }}>
                    <p className="muted-text" style={{ fontSize: 13 }}>{tProject("responses.noFiltered", { status: responseStatusFilter === "completed" ? tProject("responses.doneFilter").toLowerCase() : tProject("responses.inProgressFilter").toLowerCase() })}</p>
                  </div>
                ) : (
                  <div className="participants-list" style={{ gap: 2 }}>
                    {filtered.map((p) => (
                      <div
                        key={p.id}
                        className={`participant-row participant-row--compact ${selectedParticipant?.id === p.id ? "active" : ""} ${p.is_locked ? "participant-row--locked" : ""}`}
                        onClick={() => handleViewTranscript(p)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); handleViewTranscript(p); } }}
                      >
                        <div className="participant-avatar">
                          {p.is_locked ? "🔒" : avatarInitial(p.display_name)}
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            <span className="participant-name" style={{ fontSize: 13, marginRight: 0 }}>{p.display_name || tProject("responses.anonymous")}</span>
                            {p.is_locked && (
                              <span className="status-badge" style={{ fontSize: 10, background: "var(--brand-50, #eef2ff)", color: "var(--brand-700)" }}>
                                Locked
                              </span>
                            )}
                            {p.status !== "completed" && (() => {
                              const ageMs = Date.now() - new Date(p.started_at).getTime();
                              const isRecent = ageMs < 2 * 60 * 60 * 1000; // < 2 hours
                              return (
                                <span className={`status-badge ${isRecent ? "status-progress" : ""}`}
                                  style={{ fontSize: 10, background: isRecent ? undefined : "var(--border-subtle)", color: isRecent ? undefined : "var(--text-tertiary)" }}>
                                  {isRecent ? tProject("responses.live") : tProject("responses.statusInProgress")}
                                </span>
                              );
                            })()}
                          </div>
                          {(p.profession || p.country) && (
                            <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                              {[p.profession, p.country].filter(Boolean).join(" · ")}
                            </div>
                          )}
                          <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 2 }}>
                            <span className="participant-date" style={{ fontSize: 11 }}>{relativeDate(p.started_at)}</span>
                            {p.quality_label && (
                              <span className={`quality-badge quality-badge--${p.quality_label}`} style={{ fontSize: 10, padding: "1px 6px" }}>
                                {tProject(`responses.quality${p.quality_label!.charAt(0).toUpperCase() + p.quality_label!.slice(1)}`)}
                              </span>
                            )}
                            {p.panel_consent && (
                              <span className="status-badge" style={{ fontSize: 10, background: "var(--success-bg, #ecfdf5)", color: "var(--success-text, #047857)" }} title={tProject("responses.followUpOkHint")}>
                                ✓ {tProject("responses.followUpOk")}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* ── Right column: transcript or empty state ── */}
              <div className="responses-transcript-col">
                {transcript !== null && selectedParticipant ? (
                  <>
                    {/* Participant identity card — dark header */}
                    <div className="participant-card">
                      <div className="participant-card__top">
                        <button
                          onClick={() => setSelectedParticipant(null)}
                          className="participant-card__back"
                        >
                          ← {tProject("responses.backToParticipants")}
                        </button>
                        {!project?.is_demo && (
                          <div className="overflow-menu overflow-menu--on-dark" ref={participantMenuRef} style={{ marginLeft: "auto", marginRight: 8 }}>
                            <button
                              className="overflow-menu__trigger"
                              aria-haspopup="menu"
                              aria-expanded={participantMenuOpen}
                              aria-label={tProject("detail.moreActions")}
                              title={tProject("detail.moreActions")}
                              onClick={() => setParticipantMenuOpen((v) => !v)}
                            >
                              ⋯
                            </button>
                            {participantMenuOpen && (
                              <div className="overflow-menu__dropdown" role="menu">
                                <button
                                  role="menuitem"
                                  className="overflow-menu__item overflow-menu__item--danger"
                                  onClick={() => { setParticipantMenuOpen(false); setDeleteParticipantOpen(true); }}
                                >
                                  {tProject("responses.deleteParticipant")}
                                </button>
                              </div>
                            )}
                          </div>
                        )}
                        <button className="participant-card__close" onClick={() => { setTranscript(null); setSelectedParticipant(null); setSelectionInfo(null); }} aria-label={tProject("responses.close")}>✕</button>
                      </div>
                      <div className="participant-card__body">
                        <div className="participant-card__info">
                          <h2 className="participant-card__name">{selectedParticipant.display_name || tProject("responses.anonymous")}</h2>
                          <div className="participant-card__meta">
                            {selectedParticipant.profession && <span className="participant-card__badge">{selectedParticipant.profession}</span>}
                            {selectedParticipant.age_range && <span className="participant-card__badge">{selectedParticipant.age_range}</span>}
                            {selectedParticipant.country && <span className="participant-card__badge">{selectedParticipant.country}</span>}
                            {selectedParticipant.email && <span className="participant-card__badge">{selectedParticipant.email}</span>}
                            {selectedParticipant.panel_consent && (
                              <span className="participant-card__badge" title={tProject("responses.followUpOkHint")}>
                                ✓ {tProject("responses.followUpOk")}
                              </span>
                            )}
                            {(selectedParticipant.screening_answers ?? []).map((a) => (
                              <span key={a.question_id} className="participant-card__badge" title={a.question}>
                                {a.answer}
                              </span>
                            ))}
                          </div>
                          <span className="participant-card__date">{new Date(selectedParticipant.started_at).toLocaleDateString(i18n.language, { day: "numeric", month: "short", year: "numeric" })}</span>
                        </div>
                        {selectedParticipant.quality_label && (
                          <span className={`quality-badge quality-badge--${selectedParticipant.quality_label} quality-badge--lg participant-card__quality`}>
                            {selectedParticipant.quality_label === "low" && `⚠ ${tProject("responses.qualityLowFull")}`}
                            {selectedParticipant.quality_label === "fair" && `◑ ${tProject("responses.qualityFairFull")}`}
                            {selectedParticipant.quality_label === "good" && `● ${tProject("responses.qualityGoodFull")}`}
                            {selectedParticipant.quality_label === "strong" && `★ ${tProject("responses.qualityStrongFull")}`}
                          </span>
                        )}
                      </div>
                      {/* Reading-aid toggle: raw STT / corrected / translated.
                          Shown when the sense-check produced corrections OR the
                          researcher's language differs from the study language. */}
                      {(() => {
                        const hasCleaned = (transcript ?? []).some((t) => t.cleaned_response);
                        const langDiffers = !!project?.language && project.language !== (i18n.language || "en").slice(0, 2).toLowerCase();
                        if (!hasCleaned && !langDiffers) return null;
                        return (
                          <div className="translation-toggle" role="group" aria-label={tProject("responses.translationToggleLabel")}>
                            <button
                              className={`translation-toggle__btn${transcriptViewMode === "original" ? " is-active" : ""}`}
                              onClick={() => setTranscriptViewMode("original")}
                              disabled={translating}
                            >
                              {hasCleaned
                                ? tProject("responses.viewRaw", { defaultValue: "Raw STT" })
                                : tProject("responses.viewOriginal", { lang: (project?.language || "").toUpperCase() })}
                            </button>
                            {hasCleaned && (
                              <button
                                className={`translation-toggle__btn${transcriptViewMode === "cleaned" ? " is-active" : ""}`}
                                onClick={() => setTranscriptViewMode("cleaned")}
                                disabled={translating}
                              >
                                ✨ {tProject("responses.viewCorrected", { defaultValue: "Corrected" })}
                              </button>
                            )}
                            {langDiffers && (
                              <button
                                className={`translation-toggle__btn${transcriptViewMode === "translated" ? " is-active" : ""}`}
                                onClick={handleToggleTranslation}
                                disabled={translating}
                              >
                                {translating
                                  ? tProject("responses.translating")
                                  : tProject("responses.viewTranslated", { lang: (i18n.language || "en").slice(0, 2).toUpperCase() })}
                              </button>
                            )}
                          </div>
                        );
                      })()}
                    </div>

                    {/* Demo transcripts ship without audio files — say so
                        instead of silently omitting the players. */}
                    {project?.is_demo && (
                      <p className="muted-text" style={{ fontSize: 13, margin: "10px 2px 0" }}>
                        🎧 {tProject("responses.demoNoAudio")}
                      </p>
                    )}

                    {/* Two-column: transcript left, tools right */}
                    <div className="transcript-tools-layout">

                    {/* ── Left: Transcript ── */}
                    <div className="transcript-main-col">

                    {/* Transcript turns */}
                    {transcript.length === 0 ? (
                      <p className="muted-text">{tProject("responses.noTranscript")}</p>
                    ) : (
                      <div className="transcript-list" ref={transcriptListRef}>
                        {transcript.map((t) => {
                          const turnTags = tags.filter((tg) => tg.turn_id === t.id);
                          const isHighlighted = highlightTarget?.turnIndex === t.turn_index;
                          return (
                            <div
                              key={t.turn_index}
                              id={`turn-${t.turn_index}`}
                              className={`transcript-turn${isHighlighted ? " transcript-turn--highlighted" : ""}`}
                            >
                              <div className="transcript-q">
                                {transcriptViewMode === "translated" && t.translated_question
                                  ? t.translated_question
                                  : t.question_text}
                                {transcriptViewMode === "translated" && t.translated_question && (
                                  <div className="transcript-q__original">{t.question_text}</div>
                                )}
                                {t.tts_audio_url && (
                                  <AudioClip
                                    src={t.tts_audio_url}
                                    label={`AI question audio — turn ${t.turn_index}`}
                                  />
                                )}
                              </div>
                              {t.response_transcript && editingTurnId === t.id ? (
                                <div style={{ marginTop: 6 }}>
                                  <textarea className="field-input" value={editingText} onChange={(e) => setEditingText(e.target.value)} rows={4} style={{ width: "100%", marginBottom: 6 }} autoFocus />
                                  <div style={{ display: "flex", gap: 6 }}>
                                    <button className="btn btn-primary btn-xs" disabled={savingTurnId === t.id} onClick={() => saveEditTurn(t)}>
                                      {savingTurnId === t.id ? tCommon("saving") : tCommon("save")}
                                    </button>
                                    <button className="btn btn-ghost btn-xs" onClick={() => {
                                      if (editingText !== editingOriginalText && !confirm(tProject("responses.discardChanges"))) return;
                                      setEditingTurnId(null);
                                    }}>{tCommon("cancel")}</button>
                                  </div>
                                </div>
                              ) : t.response_transcript ? (
                                <div
                                  className={`transcript-a${(transcriptViewMode === "translated" && t.translated_response) || (transcriptViewMode === "cleaned" && t.cleaned_response) ? " transcript-a--translated" : ""}`}
                                  onMouseUp={() => transcriptViewMode === "original" && handleTranscriptMouseUp(t.id)}
                                  style={{ userSelect: "text" }}
                                >
                                  {transcriptViewMode === "translated" && t.translated_response ? (
                                    <>
                                      <div className="transcript-a__translated">{t.translated_response}</div>
                                      <div className="transcript-a__original" lang={project?.language || undefined}>
                                        {t.response_transcript}
                                      </div>
                                    </>
                                  ) : transcriptViewMode === "cleaned" && t.cleaned_response ? (
                                    <>
                                      <div className="transcript-a__translated" lang={project?.language || undefined}>
                                        {t.cleaned_response}
                                        <span
                                          className="badge"
                                          style={{ fontSize: 10, marginLeft: 8, background: "var(--info-bg)", color: "var(--info-text)" }}
                                          title={tProject("responses.correctedHint", { defaultValue: "Auto-corrected from the raw transcript (proper nouns, terms). Raw STT shown below." })}
                                        >
                                          ✨ {tProject("responses.autoCorrected", { defaultValue: "Corrected" })}
                                        </span>
                                      </div>
                                      <div className="transcript-a__original" lang={project?.language || undefined}>
                                        {t.response_transcript}
                                      </div>
                                    </>
                                  ) : isHighlighted && highlightTarget
                                    ? renderWithQuoteHighlight(t.response_transcript, highlightTarget.quoteText, t.id)
                                    : t.response_segments && t.response_segments.length > 0
                                      ? renderTranscriptWithSegments(t.response_transcript, t.id, t.response_segments)
                                      : renderTaggedText(t.response_transcript, t.id)}
                                  <span style={{ display: "inline-flex", gap: 4, marginLeft: 8, verticalAlign: "middle", flexWrap: "wrap" }}>
                                    <button className="btn btn-ghost btn-xs" style={{ fontSize: 10 }} onClick={() => startEditTurn(t)}>{tCommon("edit")}</button>
                                    {/* Whole-turn tag. In original view it's the mobile fallback
                                        (text-selection popup is unreliable on touch); in corrected
                                        view it's the only tag path, since precise selection maps to
                                        the raw text. Tags always store against the raw transcript. */}
                                    {(transcriptViewMode === "original" || transcriptViewMode === "cleaned") && t.response_transcript && (
                                      <button
                                        className={`btn btn-ghost btn-xs${transcriptViewMode === "original" ? " turn-tag-btn" : ""}`}
                                        style={{ fontSize: 10 }}
                                        onClick={(e) => {
                                          const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
                                          setSelectionInfo({
                                            turnId: t.id,
                                            text: t.response_transcript || "",
                                            start: 0,
                                            end: (t.response_transcript || "").length,
                                            x: Math.min(rect.left + rect.width / 2, window.innerWidth - 110),
                                            y: rect.top + window.scrollY - 44,
                                            fromTranslation: false,
                                          });
                                          setShowNewCode(false);
                                        }}
                                        title={tProject("responses.tagWholeTurn", { defaultValue: "Tag whole response" })}
                                      >
                                        🏷 {tProject("responses.tagTurn")}
                                      </button>
                                    )}
                                    {transcriptViewMode === "translated" && t.response_transcript && (
                                      <button
                                        className="btn btn-ghost btn-xs"
                                        style={{ fontSize: 10 }}
                                        onClick={(e) => {
                                          const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
                                          setSelectionInfo({
                                            turnId: t.id,
                                            text: t.response_transcript || "",
                                            start: 0,
                                            end: (t.response_transcript || "").length,
                                            x: rect.left + rect.width / 2,
                                            y: rect.top + window.scrollY - 44,
                                            fromTranslation: true,
                                          });
                                          setShowNewCode(false);
                                        }}
                                        title={tProject("responses.tagWholeTurn")}
                                      >
                                        🏷 {tProject("responses.tagTurn")}
                                      </button>
                                    )}
                                    {t.manually_edited && (
                                      <span className="badge" style={{ fontSize: 10, background: "var(--warning-bg)", color: "var(--warning-text)" }}>{tProject("responses.edited")}</span>
                                    )}
                                  </span>
                                  {t.audio_recording_url && (
                                    <AudioClip
                                      ref={(el) => {
                                        recordingAudioRefs.current[t.id] = el;
                                      }}
                                      src={t.audio_recording_url}
                                      label={tProject("a11y.participantRecording", { turn: t.turn_index })}
                                      onTimeUpdate={(e) => {
                                        const segs = t.response_segments;
                                        if (!segs || segs.length === 0) return;
                                        const time = (e.currentTarget as HTMLAudioElement).currentTime;
                                        // Linear scan is fine — typical turn has <30 segments.
                                        let activeIdx = -1;
                                        for (let i = 0; i < segs.length; i++) {
                                          if (time >= segs[i].start && time < segs[i].end) {
                                            activeIdx = i;
                                            break;
                                          }
                                        }
                                        const container = document.querySelector(
                                          `[data-turn-id="${t.id}"]`
                                        );
                                        if (!container) return;
                                        // Toggle is-active only on segments whose state changed.
                                        const desired = String(activeIdx);
                                        const prev = container.querySelectorAll(
                                          ".transcript-segment--active"
                                        );
                                        prev.forEach((el) => {
                                          if (el.getAttribute("data-segment-idx") !== desired) {
                                            el.classList.remove("transcript-segment--active");
                                          }
                                        });
                                        if (activeIdx !== -1) {
                                          const next = container.querySelectorAll(
                                            `[data-segment-idx="${activeIdx}"]`
                                          );
                                          next.forEach((el) =>
                                            el.classList.add("transcript-segment--active")
                                          );
                                        }
                                      }}
                                      onEnded={() => {
                                        document
                                          .querySelectorAll(
                                            `[data-turn-id="${t.id}"] .transcript-segment--active`
                                          )
                                          .forEach((el) =>
                                            el.classList.remove("transcript-segment--active")
                                          );
                                      }}
                                    />
                                  )}
                                </div>
                              ) : null}
                              {turnTags.length > 0 && (
                                <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 6 }}>
                                  {turnTags.map((tg) => (
                                    <span key={tg.id} className="tag-pill" style={{ background: `${tg.code_color || "var(--brand-500)"}22`, border: `1px solid ${tg.code_color || "var(--brand-500)"}` }}>
                                      {tg.code_name}
                                      <button
                                        className="tag-pill-remove"
                                        onClick={(e) => { e.stopPropagation(); handleDeleteTag(tg.id); }}
                                        aria-label={`${tProject("responses.removeTag")} ${tg.code_name}`}
                                        title={tProject("responses.removeTag")}
                                      >×</button>
                                    </span>
                                  ))}
                                </div>
                              )}
                              {(() => {
                                const turnSuggestions = tagSuggestions.filter((s) => s.turn_id === t.id);
                                if (turnSuggestions.length === 0) return null;
                                return (
                                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 6 }}>
                                    {turnSuggestions.map((s) => {
                                      const color = s.code_color || "var(--brand-500)";
                                      const label = s.code_name || s.proposed_code_name || "";
                                      return (
                                        <span
                                          key={s.id}
                                          className="tag-pill tag-pill--suggested"
                                          style={{ border: `1px dashed ${color}` }}
                                          title={`"${s.selected_text}"${s.rationale ? ` (${s.rationale})` : ""}`}
                                        >
                                          {s.proposed_code_name
                                            ? tProject("responses.suggestedNewCode", { name: label })
                                            : label}
                                          <button
                                            className="tag-pill-action"
                                            onClick={(e) => { e.stopPropagation(); handleAcceptSuggestion(s); }}
                                            aria-label={`${tProject("responses.acceptSuggestion")} ${label}`}
                                            title={tProject("responses.acceptSuggestion")}
                                          >✓</button>
                                          <button
                                            className="tag-pill-remove"
                                            onClick={(e) => { e.stopPropagation(); handleRejectSuggestion(s); }}
                                            aria-label={`${tProject("responses.rejectSuggestion")} ${label}`}
                                            title={tProject("responses.rejectSuggestion")}
                                          >×</button>
                                        </span>
                                      );
                                    })}
                                  </div>
                                );
                              })()}
                            </div>
                          );
                        })}
                      </div>
                    )}
                    </div>{/* /transcript-main-col */}

                    {/* ── Right: Tools sidebar ── */}
                    <div className="transcript-sidebar">
                      {/* Interview digest — what the participant said, filled by
                          the same auto-run pass as the quality assessment. */}
                      {((selectedParticipant.key_takeaways?.length ?? 0) > 0 ||
                        (selectedParticipant.notable_quotes?.length ?? 0) > 0) && (
                        <details className="sidebar-panel" open>
                          <summary className="sidebar-panel__header">
                            <span className="sidebar-panel__title">{tProject("responses.keyTakeaways")}</span>
                          </summary>
                          <div className="sidebar-panel__body">
                            {(selectedParticipant.key_takeaways?.length ?? 0) > 0 && (
                              <div className="sidebar-panel__list">
                                <ul>
                                  {selectedParticipant.key_takeaways!.map((s, i) => (
                                    <li key={i}>{s}</li>
                                  ))}
                                </ul>
                              </div>
                            )}
                            {(selectedParticipant.notable_quotes?.length ?? 0) > 0 && (
                              <div className="sidebar-panel__list">
                                <h4 className="sidebar-panel__list-title">{tProject("responses.notableQuotes")}</h4>
                                {selectedParticipant.notable_quotes!.map((q, i) => (
                                  <blockquote key={i} className="sidebar-panel__quote">{q}</blockquote>
                                ))}
                              </div>
                            )}
                          </div>
                        </details>
                      )}

                      {/* Quality Assessment panel — treat the assessment as
                          done once a quality_label exists (that's what the
                          header badge reads). Keying the pending state off
                          quality_summary alone let a blank summary spin
                          "in progress" forever while the badge showed a rating. */}
                      {(selectedParticipant.quality_summary || selectedParticipant.quality_label) ? (
                        <details className="sidebar-panel" open>
                          <summary className="sidebar-panel__header">
                            <span className="sidebar-panel__title">{tProject("responses.qualityAssessment")}</span>
                          </summary>
                          <div className="sidebar-panel__body">
                            {selectedParticipant.quality_summary ? (
                              <p className="sidebar-panel__summary">{selectedParticipant.quality_summary}</p>
                            ) : (
                              <p className="sidebar-panel__summary sidebar-panel__pending">{tProject("responses.qualityNoSummary")}</p>
                            )}
                            {selectedParticipant.avg_response_words != null && (
                              <div className="sidebar-panel__stats">
                                <div className="sidebar-panel__stat">
                                  <span className="sidebar-panel__stat-label">{tProject("responses.avgWords")}</span>
                                  <span className="sidebar-panel__stat-value">{Math.round(selectedParticipant.avg_response_words)}</span>
                                </div>
                                {selectedParticipant.short_answer_pct != null && (
                                  <div className="sidebar-panel__stat">
                                    <span className="sidebar-panel__stat-label">{tProject("responses.shortAnswers")}</span>
                                    <span className="sidebar-panel__stat-value">{Math.round(selectedParticipant.short_answer_pct * 100)}%</span>
                                  </div>
                                )}
                              </div>
                            )}
                            {selectedParticipant.quality_strengths && selectedParticipant.quality_strengths.length > 0 && (
                              <div className="sidebar-panel__list">
                                <h4 className="sidebar-panel__list-title">{tProject("responses.strengths")}</h4>
                                <ul>
                                  {selectedParticipant.quality_strengths.map((s, i) => (
                                    <li key={i}>{s}</li>
                                  ))}
                                </ul>
                              </div>
                            )}
                            {selectedParticipant.quality_issues && selectedParticipant.quality_issues.length > 0 && (
                              <div className="sidebar-panel__list sidebar-panel__list--issues">
                                <h4 className="sidebar-panel__list-title">{tProject("responses.issues")}</h4>
                                <ul>
                                  {selectedParticipant.quality_issues.map((s, i) => (
                                    <li key={i}>{s}</li>
                                  ))}
                                </ul>
                              </div>
                            )}
                          </div>
                        </details>
                      ) : (
                        <div className="sidebar-panel sidebar-panel--pending">
                          <div className="sidebar-panel__header">
                            <span className="sidebar-panel__title">{tProject("responses.qualityAssessment")}</span>
                          </div>
                          <div className="sidebar-panel__body">
                            <p className="sidebar-panel__pending">{tProject("responses.qualityPending")}</p>
                          </div>
                        </div>
                      )}

                      {/* Codebook panel */}
                      <details className="sidebar-panel" open={showCodebook} onToggle={(e) => setShowCodebookPersist((e.target as HTMLDetailsElement).open)}>
                        <summary className="sidebar-panel__header">
                          <span className="sidebar-panel__title">{tProject("responses.codebook")}</span>
                          <span className="sidebar-panel__count">{codes.length}</span>
                        </summary>
                        <div className="sidebar-panel__body">
                          <div className="sidebar-panel__howto" style={{
                            fontSize: 12,
                            color: "var(--text-tertiary)",
                            padding: "8px 10px",
                            marginBottom: 8,
                            background: "var(--bg-subtle, #f8fafc)",
                            borderRadius: 6,
                            lineHeight: 1.5,
                          }}>
                            {tProject("responses.codebookHowTo", { defaultValue: "How to tag: highlight any part of a transcript → pick a code from the popup. Codes you create here appear in every participant's transcript." })}
                          </div>
                          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
                            <button
                              className="btn btn-secondary btn-sm"
                              onClick={handleSuggestTags}
                              disabled={suggestingTags || selectedParticipant.status !== "completed"}
                              title={tProject("responses.suggestTagsHint")}
                            >
                              {suggestingTags ? tProject("responses.suggestingTags") : `✨ ${tProject("responses.suggestTags")}`}
                            </button>
                            {codes.length === 0 && (
                              <button
                                className="btn btn-secondary btn-sm"
                                onClick={handleSuggestCodes}
                                disabled={suggestingCodes}
                              >
                                {suggestingCodes ? tProject("responses.suggestingCodes") : `✨ ${tProject("responses.suggestCodes")}`}
                              </button>
                            )}
                          </div>
                          {codes.length === 0 ? (
                            <p className="sidebar-panel__empty">{tProject("responses.noCodes")}</p>
                          ) : (
                            <div className="sidebar-panel__code-list">
                              {codes.map((c) => (
                                <div key={c.id} className="sidebar-code">
                                  <span className="sidebar-code__dot" style={{ background: c.color }} />
                                  <span className="sidebar-code__name">{c.name}</span>
                                  <span className="sidebar-code__count">{tags.filter((tg) => tg.manual_code_id === c.id).length}</span>
                                  <button className="sidebar-code__delete" onClick={() => handleDeleteCode(c.id)} aria-label={`${tProject("responses.deleteCode")} ${c.name}`}>×</button>
                                </div>
                              ))}
                            </div>
                          )}
                          <p className="sidebar-panel__hint">{tProject("responses.quoteTagInstruction")}</p>
                        </div>
                      </details>
                    </div>{/* /transcript-sidebar */}

                    </div>{/* /transcript-tools-layout */}
                  </>
                ) : (
                  <div className="empty-state" style={{ minHeight: 300, border: "none", background: "transparent" }}>
                    <div className="empty-state-icon">
                      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ color: "var(--text-disabled)" }}>
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /><polyline points="10 9 9 9 8 9" />
                      </svg>
                    </div>
                    <p style={{ fontWeight: 500, fontSize: 14, color: "var(--text-secondary)", margin: 0 }}>{tProject("responses.noSelected")}</p>
                    <p style={{ fontSize: 13, color: "var(--text-tertiary)", margin: 0 }}>{tProject("responses.selectPrompt")}</p>
                  </div>
                )}
              </div>
            </div>

            {/* Floating tag popup. Clamp top so it stays in viewport on touch
                devices where rect.top can be near 0 after scrollIntoView. */}
            {selectionInfo && (
              <div style={{ position: "fixed", left: Math.max(8, Math.min(selectionInfo.x - 90, window.innerWidth - 196)), top: Math.max(8, selectionInfo.y - window.scrollY), zIndex: 1000, background: "var(--bg-surface)", border: "1px solid var(--border-default)", borderRadius: "var(--radius)", boxShadow: "var(--shadow-md)", padding: 8, minWidth: 180, maxWidth: "min(280px, calc(100vw - 16px))" }}>
                {!showNewCode ? (
                  <div>
                    <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 6 }}>{tProject("responses.tagAs")}</div>
                    {codes.map((c) => (
                      <button key={c.id} style={{ display: "flex", alignItems: "center", gap: 6, width: "100%", padding: "4px 8px", border: "none", background: "none", cursor: "pointer", borderRadius: 4, fontSize: 13, textAlign: "left" }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = "var(--border-subtle)")}
                        onMouseLeave={(e) => (e.currentTarget.style.background = "none")}
                        onClick={() => handleTagWithCode(c)}
                      >
                        <span style={{ width: 10, height: 10, borderRadius: "50%", background: c.color, flexShrink: 0 }} />
                        {c.name}
                      </button>
                    ))}
                    <div style={{ borderTop: "1px solid var(--border-subtle)", marginTop: 4, paddingTop: 4 }}>
                      <button className="btn btn-ghost btn-xs" style={{ width: "100%" }} onClick={() => setShowNewCode(true)}>{tProject("responses.newCode")}</button>
                      <button className="btn btn-ghost btn-xs" style={{ width: "100%", color: "var(--text-disabled)" }} onClick={() => { setSelectionInfo(null); window.getSelection()?.removeAllRanges(); }}>{tCommon("cancel")}</button>
                    </div>
                  </div>
                ) : (
                  <div>
                    <input className="field-input" placeholder={tProject("responses.codeName")} value={newCodeName} onChange={(e) => setNewCodeName(e.target.value)} style={{ marginBottom: 6, fontSize: 13 }} autoFocus />
                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 8 }}>
                      {PRESET_COLORS.map((col) => (
                        <div key={col} style={{ width: 20, height: 20, borderRadius: "50%", background: col, cursor: "pointer", border: newCodeColor === col ? "2px solid #111" : "2px solid transparent" }} onClick={() => setNewCodeColor(col)} />
                      ))}
                    </div>
                    <div style={{ display: "flex", gap: 4 }}>
                      <button className="btn btn-primary btn-xs" disabled={!newCodeName.trim() || creatingCode} onClick={handleCreateAndTag}>{creatingCode ? "..." : tProject("responses.createAndTag")}</button>
                      <button className="btn btn-ghost btn-xs" onClick={() => setShowNewCode(false)}>{tCommon("back")}</button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
          );
        })()}

        {/* ══ ANALYSIS ══ */}
        {tab === "analysis" && analysis && (
          <div className="tab-content" role="tabpanel" id="isection-panel-analysis" aria-labelledby="isection-tab-analysis" style={QUAL_BRAND_SCALE}>
            <section className="detail-section">
              {/* Stale banner — above actions so it's seen before clicking Regenerate */}
              {analysis.report && analysis.completed_count > analysis.participant_count && (
                <div className="analysis-stale-banner">
                  ⚠ {tAnalysis("staleWarning", { count: analysis.completed_count - analysis.participant_count })}
                </div>
              )}
              {/* One-time coachmark: surfaces the v1→v2 iteration loop.
                  Only while the latest version is still the AI discovery pass —
                  "This is v1, click Refine for v2" over an already-refined v2
                  reads as a contradiction (the seeded demo ships with v2). */}
              {analysis.status === "ready" && analysis.report &&
                analysis.version_label !== "researcher_refined" &&
                !coachmarkDismissed && (
                <div className="coachmark" role="status">
                  <span className="coachmark__icon" aria-hidden="true">💡</span>
                  <div>
                    <strong>{tAnalysis("iterationCoachmarkTitle")}</strong>{" "}
                    <span>{tAnalysis("iterationCoachmarkDesc")}</span>
                  </div>
                  <button
                    className="coachmark__close"
                    aria-label={tAnalysis("iterationCoachmarkDismiss")}
                    onClick={() => {
                      localStorage.setItem(COACHMARK_KEY, "true");
                      setCoachmarkDismissed(true);
                    }}
                  >
                    ×
                  </button>
                </div>
              )}
              <div className="section-header-row">
                <h2>{tAnalysis("aiAnalysis")}</h2>
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                  {analysis.report && (
                    <button className="btn btn-secondary btn-sm" onClick={handleExportReport} title={tAnalysis("exportReport")}>
                      {tAnalysis("exportPdfBtn")}
                    </button>
                  )}
                  {analysis.report && (
                    <div className="overflow-menu" ref={exportMenuRef}>
                      <button
                        className="overflow-menu__trigger"
                        aria-haspopup="menu"
                        aria-expanded={exportMenuOpen}
                        aria-label={tAnalysis("exportMenuLabel")}
                        onClick={() => setExportMenuOpen((v) => !v)}
                      >
                        ⋯
                      </button>
                      {exportMenuOpen && (
                        <div className="overflow-menu__dropdown" role="menu">
                          <button role="menuitem" className="overflow-menu__item" onClick={() => { setExportMenuOpen(false); handleCopyMarkdown(); }}>
                            {exportCopied ? `✓ ${tCommon("copied")}` : tAnalysis("copyMd")}
                          </button>
                          <button role="menuitem" className="overflow-menu__item" onClick={() => { setExportMenuOpen(false); handleDownloadJSON(); }}>
                            {tAnalysis("downloadJson")}
                          </button>
                          <button role="menuitem" className="overflow-menu__item" onClick={() => { setExportMenuOpen(false); handleShareAnalysis(); }}>
                            🔗 {tAnalysis("shareBtn")}
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                  {analysis.completed_count > 0 && (
                    <button className="btn btn-ai btn-sm" onClick={handleTriggerAnalysis} disabled={analysis.status === "generating"}>
                      {analysis.status === "generating" ? tAnalysis("analysing") : analysis.status === "none" ? `✦ ${tAnalysis("generateBtn")}` : `✦ ${tAnalysis("regenerateBtn")}`}
                    </button>
                  )}
                </div>
              </div>

              {/* Scope line — three report surfaces exist (round analysis /
                  study report / decision memo); each states its scope and
                  links up one level so they stop reading as interchangeable. */}
              <p className="muted-text" style={{ fontSize: 13, margin: "0 0 16px" }}>
                {tAnalysis("scopeNote")}
                {project.study_id && (
                  <>
                    {" "}
                    <Link to={`/studies/${project.study_id}?tab=report`}>
                      {tAnalysis("scopeStudyReportLink")}
                    </Link>
                  </>
                )}
              </p>

              {/* P2: Filter panel */}
              {hasFilterOptions && (
                <div style={{ marginBottom: 16 }}>
                  <button className="btn btn-ghost btn-sm" onClick={() => setFiltersExpanded(!filtersExpanded)} style={{ marginBottom: 6 }}>
                    {filtersExpanded ? "▲" : "▼"} {tAnalysis("filterBySegment")}
                    {activeFilterValues.length > 0 && <span className="badge" style={{ marginLeft: 4 }}>{tAnalysis("activeFilters", { count: activeFilterValues.length })}</span>}
                  </button>
                  {filtersExpanded && (
                    <div style={{ padding: 12, border: "1px solid var(--border-default)", borderRadius: "var(--radius)", background: "var(--bg-base)" }}>
                      {Object.entries(filterOptions).map(([attr, values]) => (
                        <div key={attr} style={{ marginBottom: 10 }}>
                          <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)", marginBottom: 4, textTransform: attr.startsWith("screening:") ? "none" : "capitalize" }}>{filterLabel(attr)}</div>
                          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                            {values.map((val) => {
                              const active = activeFilterBy === attr && activeFilterValues.includes(val);
                              return (
                                <label key={val} style={{ display: "flex", alignItems: "center", gap: 4, padding: "2px 8px", borderRadius: 10, fontSize: 12, border: `1px solid ${active ? "var(--brand-500)" : "var(--border-default)"}`, background: active ? "var(--brand-50)" : "var(--bg-surface)", cursor: "pointer" }}>
                                  <input type="checkbox" checked={active} onChange={() => toggleFilterValue(attr, val)} style={{ width: 12, height: 12 }} />
                                  {val}
                                </label>
                              );
                            })}
                          </div>
                        </div>
                      ))}
                      {activeFilterValues.length > 0 && (
                        <button className="btn btn-ghost btn-xs" onClick={() => { setActiveFilterBy(""); setActiveFilterValues([]); }} style={{ marginTop: 4 }}>{tAnalysis("clearFilters")}</button>
                      )}
                    </div>
                  )}
                  {analysis.filters && (
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8, marginTop: 6 }}>
                      <span style={{ fontSize: 12, color: "var(--text-tertiary)" }}>{tAnalysis("filteredBy")}</span>
                      {analysis.filters.filter_values.map((v) => (
                        <span key={v} className="badge" style={{ background: "var(--brand-50)", color: "var(--brand-700)" }}>{filterLabel(analysis.filters!.filter_by)}: {v}</span>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {analysis.status === "none" && analysis.completed_count === 0 && (
                <div className="empty-state">
                  <p style={{ fontWeight: 500 }}>{tAnalysis("collectFirst")}</p>
                  <p className="muted-text" style={{ fontSize: 13 }}>{tAnalysis("collectFirstDesc")}</p>
                  <button className="btn btn-ghost btn-sm" style={{ marginTop: 10 }} onClick={() => setTab("responses")}>{tAnalysis("goToResponses")}</button>
                </div>
              )}
              {analysis.status === "none" && analysis.completed_count > 0 && (
                <p className="muted-text">{tAnalysis("readyToAnalyse", { count: analysis.completed_count })}</p>
              )}
              {analysis.status === "generating" && (() => {
                const stage = analysis.stage ?? "preparing";
                const withAutoTag = runHadAutoTag || stage === "auto_tagging";
                const stages: string[] = withAutoTag
                  ? ["auto_tagging", "preparing", "synthesizing", "verifying"]
                  : ["preparing", "synthesizing", "verifying"];
                const idx = Math.max(0, stages.indexOf(stage));
                const detail = analysis.stage_detail;
                const label =
                  stage === "auto_tagging" && detail?.total
                    ? tAnalysis("stageAutoTaggingProgress", {
                        done: Math.min((detail.done ?? 0) + 1, detail.total),
                        total: detail.total,
                      })
                    : tAnalysis(`stages.${stage}`, { count: analysis.participant_count });
                return (
                  <div className="analysis-generating" style={{ flexDirection: "column", alignItems: "stretch", gap: 10 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span className="spinner-sm" />
                      <span>{label}</span>
                      <span className="muted-text" style={{ fontSize: 12, marginLeft: "auto", whiteSpace: "nowrap" }}>
                        {tAnalysis("stageStep", { current: idx + 1, total: stages.length })}
                      </span>
                    </div>
                    <div style={{ display: "flex", gap: 4 }} aria-hidden="true">
                      {stages.map((s, i) => (
                        <div
                          key={s}
                          style={{
                            flex: 1,
                            height: 4,
                            borderRadius: 2,
                            background:
                              i < idx ? "var(--brand-500)" : i === idx ? "var(--brand-300)" : "var(--border-default)",
                            transition: "background 0.4s",
                          }}
                        />
                      ))}
                    </div>
                  </div>
                );
              })()}
              {analysis.status === "failed" && (
                <div style={{ padding: "16px", borderRadius: "var(--radius)", background: "var(--danger-bg)", border: "1px solid var(--danger-border)", display: "flex", alignItems: "flex-start", gap: 12 }}>
                  <span style={{ fontSize: 18 }}>⚠</span>
                  <div>
                    <p style={{ fontWeight: 600, color: "var(--danger-text)", marginBottom: 4 }}>{tAnalysis("failedTitle")}</p>
                    <p style={{ color: "var(--danger)", fontSize: 13, marginBottom: 10 }}>
                      {analysis.error?.includes("timed out") ? tAnalysis("failedTimeout") :
                       analysis.error?.includes("No completed") ? tAnalysis("failedNoCompleted") :
                       tAnalysis("failedGeneric")}
                    </p>
                    <button className="btn btn-sm" style={{ background: "var(--danger)", color: "#fff" }} onClick={handleTriggerAnalysis}>
                      {tAnalysis("retryAnalysis")}
                    </button>
                  </div>
                </div>
              )}

              {analysis.status === "ready" && analysis.report && (() => {
                // Determine which report to display — active past version or current
                const isViewingPastVersion = activeVersionNumber !== null && activeVersionReport !== null;
                const displayReport = isViewingPastVersion ? activeVersionReport!.report : analysis.report;
                const r = displayReport!;
                const currentVersionNum = analysis.version ?? (analysisVersions.length > 0 ? analysisVersions[0].version : 1);
                const latestVersionNum = analysisVersions.length > 0 ? analysisVersions[0].version : currentVersionNum;

                // Annotation helpers
                const annotationCount = Object.keys(themeAnnotations).length;
                const actionableAnnotationCount = Object.values(themeAnnotations).filter(
                  (a) => a.status === "disputed" || a.status === "needs_evidence"
                ).length;
                const canRefine = actionableAnnotationCount > 0 || researcherContext.trim().length > 0;

                return (
                  <div className="analysis-report">
                    <h3 style={{ fontSize: "14px", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "8px", textTransform: "uppercase", letterSpacing: "0.5px" }}>{tAnalysis("summary")}</h3>
                    <div className="analysis-summary">{r.summary}</div>
                    <div className="analysis-meta">
                      <span className="badge analysis-ai-badge">
                        {isViewingPastVersion
                          ? (activeVersionReport!.version_label === "researcher_refined" ? `✦ ${tAnalysis("researcherRefinedBadge")}` : `✦ ${tAnalysis("aiGenerated")}`)
                          : (analysis.version_label === "researcher_refined" ? `✦ ${tAnalysis("researcherRefinedBadge")}` : `✦ ${tAnalysis("aiGenerated")}`)}
                      </span>
                      <span className="badge">{tAnalysis("nInterviews", { count: r.participant_count })}</span>
                      <span
                        className={`confidence-badge confidence-badge--${r.confidence || "medium"}`}
                        title={r.confidence_rationale || tAnalysis("sharedReport.confidenceTooltip")}
                        style={{ cursor: "help" }}
                      >
                        {tAnalysis("confidenceBadge", { level: tAnalysis(`confidenceLevel.${r.confidence || "medium"}`) })}
                      </span>
                      {(isViewingPastVersion ? activeVersionReport!.filters : analysis.filters) && (
                        <span className="badge" style={{ background: "var(--brand-50)", color: "var(--brand-700)" }}>
                          {tAnalysis("filteredBadge", { filterBy: (isViewingPastVersion ? activeVersionReport!.filters : analysis.filters)!.filter_by, values: (isViewingPastVersion ? activeVersionReport!.filters : analysis.filters)!.filter_values.join(", ") })}
                        </span>
                      )}
                    </div>

                    {/* Version tabs */}
                    {analysisVersions.length > 1 && (
                      <div className="version-tabs">
                        {[...analysisVersions].reverse().map((v) => {
                          const isCurrent = v.version === latestVersionNum;
                          const isActive = isViewingPastVersion
                            ? v.version === activeVersionNumber
                            : isCurrent;
                          const labelText = v.version_label === "researcher_refined"
                            ? tAnalysis("researcherRefinedBadge")
                            : tAnalysis("aiDiscovery");
                          return (
                            <button
                              key={v.version}
                              className={`version-tab${isActive ? " version-tab--active" : ""}`}
                              onClick={() => {
                                if (isCurrent) {
                                  setActiveVersionNumber(null);
                                  setActiveVersionReport(null);
                                } else {
                                  handleViewVersion(v.version);
                                }
                              }}
                            >
                              v{v.version} · {labelText}
                              {isCurrent && <span style={{ marginLeft: 4, color: "var(--brand-500)" }}>●</span>}
                              {v.annotation_count > 0 && !isCurrent && (
                                <span style={{ marginLeft: 4, fontSize: 10, color: "var(--text-tertiary)" }}>{tAnalysis("annCount", { count: v.annotation_count })}</span>
                              )}
                            </button>
                          );
                        })}
                      </div>
                    )}

                    {/* Past version banner */}
                    {isViewingPastVersion && (
                      <div className="version-banner">
                        {tAnalysis("viewingVersion", { version: activeVersionNumber, label: activeVersionReport!.version_label === "researcher_refined" ? tAnalysis("researcherRefinedBadge") : tAnalysis("aiDiscovery") })}{" "}
                        <button
                          className="btn btn-ghost btn-xs"
                          onClick={() => { setActiveVersionNumber(null); setActiveVersionReport(null); }}
                          style={{ color: "var(--brand-600)", padding: "0 4px" }}
                        >
                          {tAnalysis("switchToLatest", { version: latestVersionNum })}
                        </button>
                      </div>
                    )}

                    {/* ─── Analysis sub-tabs ─── */}
                    <div className="analysis-subtabs" role="tablist" aria-label={tAnalysis("subtabsLabel")}>
                      <button
                        role="tab"
                        aria-selected={analysisSubTab === "overview"}
                        className={`analysis-subtab${analysisSubTab === "overview" ? " analysis-subtab--active" : ""}`}
                        onClick={() => setAnalysisSubTab("overview")}
                      >
                        {tAnalysis("subtabOverview")}
                      </button>
                      <button
                        role="tab"
                        aria-selected={analysisSubTab === "deep"}
                        className={`analysis-subtab${analysisSubTab === "deep" ? " analysis-subtab--active" : ""}`}
                        onClick={() => setAnalysisSubTab("deep")}
                      >
                        {tAnalysis("subtabDeepDive")}
                      </button>
                    </div>

                    {/* ─── OVERVIEW SUB-TAB ─── */}
                    {analysisSubTab === "overview" && (
                      <div className="analysis-overview">
                        {/* KPI strip */}
                        <div className="analysis-kpis">
                          <div className="analysis-kpi">
                            <div className="analysis-kpi__num">{r.themes.length}</div>
                            <div className="analysis-kpi__label">{tAnalysis("kpiThemes")}</div>
                          </div>
                          <div className="analysis-kpi">
                            <div className="analysis-kpi__num">{r.jobs_to_be_done.length}</div>
                            <div className="analysis-kpi__label">{tAnalysis("kpiJtbds")}</div>
                          </div>
                          <div className="analysis-kpi">
                            <div className="analysis-kpi__num">{r.recommendations.length}</div>
                            <div className="analysis-kpi__label">{tAnalysis("kpiRecs")}</div>
                          </div>
                          <div className="analysis-kpi">
                            <div className="analysis-kpi__num analysis-kpi__num--small">
                              {tAnalysis(`confidenceLevel.${r.confidence || "medium"}`)}
                            </div>
                            <div className="analysis-kpi__label">{tAnalysis("kpiConfidence")}</div>
                          </div>
                        </div>

                        {/* Top recommendations — first 3, the answer-in-10-seconds payload */}
                        {r.recommendations.length > 0 && (
                          <div className="analysis-block">
                            <h3>{tAnalysis("topRecommendations")}</h3>
                            <ol className="analysis-recommendations">
                              {r.recommendations.slice(0, 3).map((rec, i) => <li key={i}>{recommendationText(rec)}</li>)}
                            </ol>
                            {r.recommendations.length > 3 && (
                              <button
                                type="button"
                                className="btn btn-ghost btn-sm"
                                style={{ marginTop: 8 }}
                                onClick={() => setAnalysisSubTab("deep")}
                              >
                                {tAnalysis("seeAllRecs", { count: r.recommendations.length })} →
                              </button>
                            )}
                          </div>
                        )}

                        {/* Spotlight: top theme (first one) with one quote */}
                        {r.themes.length > 0 && (
                          <div className="analysis-block">
                            <h3>
                              {tAnalysis("topTheme")}
                              {r.themes.length > 1 && (
                                <span className="muted-text" style={{ fontWeight: 400, fontSize: 13, marginLeft: 8 }}>
                                  {tAnalysis("ofN", { n: r.themes.length })}
                                </span>
                              )}
                            </h3>
                            <div className="analysis-theme analysis-theme--spotlight">
                              <div className="analysis-theme-header" style={{ flexWrap: "wrap" }}>
                                <strong>{r.themes[0].title}</strong>
                                <span className="badge">{r.themes[0].frequency}</span>
                              </div>
                              <p>{r.themes[0].summary}</p>
                              {r.themes[0].quotes.length > 0 && (
                                <div className="analysis-quotes">
                                  {renderAttributedQuote(r.themes[0].quotes[0], 0)}
                                </div>
                              )}
                            </div>
                          </div>
                        )}

                        {/* CTA into deep dive */}
                        <div className="analysis-overview__cta">
                          <button
                            type="button"
                            className="btn btn-primary btn-sm"
                            onClick={() => setAnalysisSubTab("deep")}
                          >
                            {tAnalysis("openDeepDive")} →
                          </button>
                          <span className="muted-text" style={{ fontSize: 12 }}>
                            {tAnalysis("openDeepDiveHint")}
                          </span>
                        </div>
                      </div>
                    )}

                    {/* ─── DEEP DIVE SUB-TAB ─── */}
                    {analysisSubTab === "deep" && (
                      <div className="analysis-deep">
                        {/* Sticky TOC (desktop) — anchors to sections below */}
                        <nav className="analysis-toc" aria-label={tAnalysis("tocLabel")}>
                          <span className="analysis-toc__title">{tAnalysis("tocTitle")}</span>
                          {r.themes.length > 0 && (
                            <a className="analysis-toc__link" href="#analysis-themes">
                              {tAnalysis("tocThemes")} <span className="analysis-toc__count">{r.themes.length}</span>
                            </a>
                          )}
                          {r.jobs_to_be_done.length > 0 && (
                            <a className="analysis-toc__link" href="#analysis-jtbds">
                              {tAnalysis("tocJtbds")} <span className="analysis-toc__count">{r.jobs_to_be_done.length}</span>
                            </a>
                          )}
                          {r.tensions.length > 0 && (
                            <a className="analysis-toc__link" href="#analysis-tensions">
                              {tAnalysis("tocTensions")} <span className="analysis-toc__count">{r.tensions.length}</span>
                            </a>
                          )}
                          {r.recommendations.length > 0 && (
                            <a className="analysis-toc__link" href="#analysis-recommendations">
                              {tAnalysis("tocRecs")} <span className="analysis-toc__count">{r.recommendations.length}</span>
                            </a>
                          )}
                          {r.themes.length > 0 && (
                            <a className="analysis-toc__link" href="#analysis-evidence">{tAnalysis("tocEvidence")}</a>
                          )}
                          <a className="analysis-toc__link" href="#analysis-notes">{tAnalysis("tocNotes")}</a>
                          {!isViewingPastVersion && (
                            <a className="analysis-toc__link" href="#analysis-refine">{tAnalysis("tocRefine")}</a>
                          )}
                          <a className="analysis-toc__link" href="#analysis-heatmap">{tAnalysis("tocHeatmap")}</a>
                        </nav>

                        <div className="analysis-deep__main">

                    {/* Codebook signals — deterministic counts from the
                        researcher's own tags, computed server-side. */}
                    {(r.codebook_stats?.length ?? 0) > 0 && (
                      <div className="analysis-block" id="analysis-codebook-signals">
                        <h3>{tAnalysis("codebookSignals")}</h3>
                        <p className="analysis-codebook-signals__hint">{tAnalysis("codebookSignalsHint")}</p>
                        <div className="analysis-codebook-signals">
                          {r.codebook_stats!.map((s) => (
                            <span key={s.code} className="analysis-codebook-signal" style={{ borderColor: s.color }}>
                              <span className="analysis-codebook-signal__dot" style={{ background: s.color }} />
                              <strong>{s.code}</strong>
                              <span className="analysis-codebook-signal__count">
                                {tAnalysis("codebookSignalCount", { participants: s.participant_count, total: s.participants_total, quotes: s.tag_count })}
                              </span>
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Themes */}
                    {r.themes.length > 0 && (
                      <div className="analysis-block" id="analysis-themes">
                        <h3>{tAnalysis("keyThemesCount", { count: r.themes.length })}</h3>
                        {r.themes.map((t, i) => {
                          const ann = themeAnnotations[t.title];
                          const showNoteInput = !isViewingPastVersion && ann && (ann.status === "disputed" || ann.status === "needs_evidence");
                          return (
                            <div key={i} className="analysis-theme">
                              <div className="analysis-theme-header" style={{ flexWrap: "wrap" }}>
                                <strong>{t.title}{t.quotes.length > 0 && <span className="analysis-quote-count">{tAnalysis("quoteCount", { count: t.quotes.length })}</span>}</strong>
                                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                                  <span className="badge">{t.frequency}</span>
                                  {!isViewingPastVersion && (
                                    <>
                                      <button
                                        className={`annotation-pill${ann?.status === "confirmed" ? " annotation-pill--confirmed" : ""}`}
                                        aria-label={tProject("a11y.annotConfirmed")}
                                        onClick={() => handleAnnotationClick(t.title, "confirmed")}
                                      >✓ {tAnalysis("annotationConfirm")}</button>
                                      <button
                                        className={`annotation-pill${ann?.status === "needs_evidence" ? " annotation-pill--needs_evidence" : ""}`}
                                        aria-label={tProject("a11y.annotNeedsEvidence")}
                                        onClick={() => handleAnnotationClick(t.title, "needs_evidence")}
                                      >? {tAnalysis("annotationEvidence")}</button>
                                      <button
                                        className={`annotation-pill${ann?.status === "disputed" ? " annotation-pill--disputed" : ""}`}
                                        aria-label={tProject("a11y.annotDisputed")}
                                        onClick={() => handleAnnotationClick(t.title, "disputed")}
                                      >✕ {tAnalysis("annotationDispute")}</button>
                                    </>
                                  )}
                                  <button className="btn btn-ghost btn-xs" style={{ color: "var(--warning)" }} onClick={() => { setAddingMemoKey(t.title); setNewMemoContent(""); }}>{tAnalysis("addNote")}</button>
                                </div>
                              </div>
                              <p>{t.summary}</p>
                              {t.researcher_note && (
                                <p style={{ fontSize: 12, color: "var(--text-tertiary)", fontStyle: "italic", borderLeft: "3px solid var(--warning)", paddingLeft: 8, marginTop: 4 }}>
                                  {tAnalysis("researcherNoteLabel")} {t.researcher_note}
                                </p>
                              )}
                              {showNoteInput && (
                                <textarea
                                  className="annotation-note-input"
                                  placeholder={tAnalysis("annotationNotePlaceholder")}
                                  defaultValue={ann?.researcher_note ?? ""}
                                  onBlur={(e) => handleAnnotationNoteBlur(t.title, e.target.value)}
                                />
                              )}
                              {t.quotes.length > 0 && (
                                <div className="analysis-quotes">
                                  {t.quotes.map((q, j) => renderAttributedQuote(q, j))}
                                </div>
                              )}
                              {renderMemoSection("theme_note", t.title)}
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {/* JTBD */}
                    {r.jobs_to_be_done.length > 0 && (
                      <div className="analysis-block" id="analysis-jtbds">
                        <h3>{tAnalysis("jtbdCount", { count: r.jobs_to_be_done.length })}</h3>
                        {r.jobs_to_be_done.map((j, i) => (
                          <div key={i} className="analysis-jtbd">
                            <div className="analysis-jtbd-job">"{j.job}"</div>
                            <p className="analysis-jtbd-insight">{j.insight}</p>
                            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                              <span className="badge">{j.frequency}</span>
                              <button className="btn btn-ghost btn-xs" style={{ color: "var(--warning)" }} onClick={() => { setAddingMemoKey(j.job); setNewMemoContent(""); }}>{tAnalysis("addNote")}</button>
                            </div>
                            {renderMemoSection("jtbd_note", j.job)}
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Tensions */}
                    {r.tensions.length > 0 && (
                      <div className="analysis-block" id="analysis-tensions">
                        <h3>{tAnalysis("tensionsCount", { count: r.tensions.length })}</h3>
                        {r.tensions.map((t, i) => (
                          <div key={i} className="analysis-tension">
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                              <strong>{t.tension}</strong>
                              <button className="btn btn-ghost btn-xs" style={{ color: "var(--warning)", flexShrink: 0 }} onClick={() => { setAddingMemoKey(t.tension); setNewMemoContent(""); }}>{tAnalysis("addNote")}</button>
                            </div>
                            <p>{t.detail}</p>
                            {renderMemoSection("tension_note", t.tension)}
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Recommendations */}
                    {r.recommendations.length > 0 && (
                      <div className="analysis-block" id="analysis-recommendations">
                        <h3>{tAnalysis("recommendations")}</h3>
                        <ol className="analysis-recommendations">
                          {r.recommendations.map((rec, i) => <li key={i}>{recommendationText(rec)}</li>)}
                        </ol>
                      </div>
                    )}

                    {/* General memos */}
                    <div className="analysis-block" id="analysis-notes">
                      <h3>{tAnalysis("generalNotes")}</h3>
                      {memos.filter((m) => m.linked_key === null && m.type === "general").map((m) => (
                        <div key={m.id} className="memo-card">
                          {editingMemoId === m.id ? (
                            <div>
                              <textarea className="field-input" value={editingMemoContent} onChange={(e) => setEditingMemoContent(e.target.value)} rows={3} style={{ width: "100%", marginBottom: 6 }} />
                              <div style={{ display: "flex", gap: 6 }}>
                                <button className="btn btn-primary btn-xs" onClick={() => handleUpdateMemo(m.id)}>{tCommon("save")}</button>
                                <button className="btn btn-ghost btn-xs" onClick={() => setEditingMemoId(null)}>{tCommon("cancel")}</button>
                              </div>
                            </div>
                          ) : (
                            <div>
                              <p style={{ margin: 0, whiteSpace: "pre-wrap", fontSize: 13 }}>{m.content}</p>
                              <div style={{ display: "flex", gap: 6, marginTop: 4, alignItems: "center" }}>
                                <button className="btn btn-ghost btn-xs" onClick={() => { setEditingMemoId(m.id); setEditingMemoContent(m.content); }}>{tCommon("edit")}</button>
                                <button className="btn btn-ghost btn-xs btn-danger-text" onClick={() => handleDeleteMemo(m.id)}>{tCommon("delete")}</button>
                                <span style={{ fontSize: 11, color: "var(--text-tertiary)", marginLeft: "auto" }}>
                                  {timeAgo(m.updated_at || m.created_at)}
                                </span>
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                      {addingMemoKey === "__general__" ? (
                        <div style={{ marginTop: 8 }}>
                          <textarea className="field-input" value={newMemoContent} onChange={(e) => setNewMemoContent(e.target.value)} placeholder={tAnalysis("generalNotePlaceholder")} rows={3} style={{ width: "100%", marginBottom: 6 }} autoFocus />
                          <div style={{ display: "flex", gap: 6 }}>
                            <button className="btn btn-primary btn-xs" onClick={() => handleAddMemo("general", null)}>{tCommon("save")}</button>
                            <button className="btn btn-ghost btn-xs" onClick={() => { setAddingMemoKey(null); setNewMemoContent(""); }}>{tCommon("cancel")}</button>
                          </div>
                        </div>
                      ) : (
                        <button className="btn btn-ghost btn-sm" style={{ marginTop: 8, color: "var(--warning)" }} onClick={() => { setAddingMemoKey("__general__"); setNewMemoContent(""); }}>
                          {tAnalysis("addGeneralNote")}
                        </button>
                      )}
                    </div>

                    {/* Researcher context + Refine */}
                    {!isViewingPastVersion && (
                      <div className="analysis-block" id="analysis-refine">
                        <div className="researcher-context-box">
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                            <h3 style={{ margin: 0 }}>{tAnalysis("researcherContext")}</h3>
                            <span
                              aria-live="polite"
                              style={{
                                fontSize: 12,
                                fontWeight: 500,
                                color: contextSaving === "saved" ? "var(--success-text, #065f46)" : "var(--text-tertiary)",
                                transition: "opacity 0.2s",
                              }}
                            >
                              {contextSaving === "saving"
                                ? `… ${tCommon("saving")}`
                                : contextSaving === "saved"
                                ? `✓ ${tCommon("saved", { defaultValue: "Saved" })}`
                                : ""}
                            </span>
                          </div>
                          <textarea
                            className="field-input"
                            rows={4}
                            value={researcherContext}
                            onChange={(e) => handleResearcherContextChange(e.target.value)}
                            placeholder={tAnalysis("contextPlaceholder")}
                            style={{ width: "100%", fontSize: 13, resize: "vertical" }}
                          />
                        </div>

                        <div style={{ marginTop: 12 }}>
                          {!refineModalOpen ? (
                            <button
                              className="btn btn-ai btn-sm"
                              disabled={!canRefine || refining}
                              onClick={() => setRefineModalOpen(true)}
                              title={!canRefine ? tAnalysis("refineDisabledHint") : undefined}
                            >
                              ✦ {tAnalysis("refineWithAnnotations")}
                            </button>
                          ) : (
                            <div className="refine-confirm-inline">
                              <p style={{ margin: "0 0 8px 0", fontSize: 13 }}>
                                {tAnalysis("refineConfirmText", { version: latestVersionNum + 1, count: annotationCount, current: latestVersionNum })}
                              </p>
                              <div style={{ display: "flex", gap: 8 }}>
                                <button
                                  className="btn btn-primary btn-sm"
                                  disabled={refining}
                                  onClick={handleTriggerRefine}
                                >
                                  {refining ? tAnalysis("starting") : tCommon("confirm")}
                                </button>
                                <button
                                  className="btn btn-ghost btn-sm"
                                  onClick={() => setRefineModalOpen(false)}
                                >
                                  {tCommon("cancel")}
                                </button>
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Evidence map — theme × participant coverage */}
                    {r.themes.length > 0 && (() => {
                      const completed = participants
                        .filter((p) => p.status === "completed")
                        .sort((a, b) => (a.completed_at ?? a.started_at).localeCompare(b.completed_at ?? b.started_at));
                      if (completed.length === 0) return null;
                      const quotedNames = (t: (typeof r.themes)[number]) =>
                        new Set(
                          t.quotes
                            .map((q) => (typeof q === "string" ? "" : q.participant_display_name ?? ""))
                            .filter(Boolean)
                        );
                      return (
                        <div className="analysis-block" id="analysis-evidence">
                          <h3>{tAnalysis("evidenceMap")}</h3>
                          <p className="muted-text" style={{ fontSize: 12, marginBottom: 8 }}>{tAnalysis("evidenceMapHint")}</p>
                          <div style={{ overflowX: "auto" }}>
                            <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 12 }}>
                              <thead>
                                <tr>
                                  <th style={{ padding: "6px 10px", textAlign: "left", background: "var(--bg-base)", borderBottom: "1px solid var(--border-default)", minWidth: 160 }}>{tAnalysis("themeHeader")}</th>
                                  {completed.map((p, i) => (
                                    <th key={p.id} title={p.display_name ?? ""} style={{ padding: "6px 8px", textAlign: "center", background: "var(--bg-base)", borderBottom: "1px solid var(--border-default)", whiteSpace: "nowrap" }}>
                                      P{i + 1}
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {r.themes.map((t, ti) => {
                                  const quoted = quotedNames(t);
                                  return (
                                    <tr key={ti}>
                                      <td style={{ padding: "6px 10px", borderBottom: "1px solid var(--border-subtle)", fontWeight: 500 }}>{t.title}</td>
                                      {completed.map((p) => {
                                        const hit = quoted.has(p.display_name ?? "");
                                        return (
                                          <td key={p.id} title={hit ? `${p.display_name} — ${tAnalysis("evidenceQuoted")}` : undefined} style={{ padding: "6px 8px", textAlign: "center", borderBottom: "1px solid var(--border-subtle)" }}>
                                            <span
                                              aria-label={hit ? tAnalysis("evidenceQuoted") : undefined}
                                              style={{ display: "inline-block", width: hit ? 11 : 7, height: hit ? 11 : 7, borderRadius: "50%", background: hit ? "var(--brand-500)" : "var(--border-default)", opacity: hit ? 1 : 0.6 }}
                                            />
                                          </td>
                                        );
                                      })}
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                          <p className="muted-text" style={{ fontSize: 11, marginTop: 6 }}>
                            {completed.map((p, i) => `P${i + 1} ${p.display_name ?? "—"}`).join(" · ")}
                          </p>
                        </div>
                      );
                    })()}

                    {/* P7: Heatmap */}
                    <div className="analysis-block" id="analysis-heatmap">
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                        <h3 style={{ margin: 0 }}>{tAnalysis("segmentHeatmap")}</h3>
                        <button className="btn btn-ghost btn-sm" onClick={() => { if (!heatmapExpanded) loadHeatmap(); else setHeatmapExpanded(false); }}>
                          {heatmapLoading ? tCommon("loading") : heatmapExpanded ? tAnalysis("hideHeatmap") : tAnalysis("showHeatmap")}
                        </button>
                      </div>
                      {heatmapExpanded && heatmap && (
                        <div style={{ overflowX: "auto" }}>
                          {heatmap.segments.length === 0 ? (
                            <p className="muted-text">{tAnalysis("noSegments")}</p>
                          ) : (
                            <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 12 }}>
                              <thead>
                                <tr>
                                  <th style={{ padding: "6px 10px", textAlign: "left", background: "var(--bg-base)", borderBottom: "1px solid var(--border-default)", minWidth: 160 }}>{tAnalysis("themeHeader")}</th>
                                  {heatmap.segments.map((seg) => (
                                    <th key={seg} style={{ padding: "6px 8px", textAlign: "center", background: "var(--bg-base)", borderBottom: "1px solid var(--border-default)", whiteSpace: "nowrap" }}>
                                      {seg.split(":")[1]}
                                      <div style={{ fontSize: 10, color: "var(--text-disabled)", fontWeight: 400 }}>{seg.split(":")[0].replace("_", " ")}</div>
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {heatmap.themes.map((theme, ti) => (
                                  <tr key={ti}>
                                    <td style={{ padding: "6px 10px", borderBottom: "1px solid var(--border-subtle)", fontWeight: 500 }}>{theme.title}</td>
                                    {heatmap.segments.map((seg) => {
                                      const count = theme.segment_counts[seg] ?? 0;
                                      const segParticipants = heatmap.segment_participants[seg] ?? [];
                                      return (
                                        <td key={seg} style={{ padding: "6px 8px", textAlign: "center", borderBottom: "1px solid var(--border-subtle)", background: heatmapColor(count), cursor: count > 0 ? "help" : "default" }}
                                          title={count > 0 ? tProject("heatmapCell.quotes", { count, participants: segParticipants.join(", ") }) : tProject("heatmapCell.empty")}
                                        >
                                          {count > 0 ? count : ""}
                                        </td>
                                      );
                                    })}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                        </div>
                      )}
                    </div>

                        </div>{/* /.analysis-deep__main */}
                      </div>
                    )}{/* /Deep dive sub-tab */}
                  </div>
                );
              })()}
            </section>
          </div>
        )}
      </main>

      {/* ── Analysis readiness gate (untagged study → offer AI coding) ──── */}
      {gateReadiness && (
        <div
          className="modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="analysis-gate-title"
          onClick={() => setGateReadiness(null)}
        >
          <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 480 }}>
            <button className="modal-close" onClick={() => setGateReadiness(null)} aria-label={tProject("a11y.close")}>×</button>
            <h3 id="analysis-gate-title" style={{ marginTop: 0 }}>{tAnalysis("gate.title")}</h3>
            <p style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.5 }}>
              {tAnalysis("gate.body", { count: gateReadiness.completed_count })}
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 16 }}>
              <button className="btn btn-ai btn-sm" onClick={() => runAnalysisNow(true)}>
                ✨ {tAnalysis("gate.autoTag")}
              </button>
              <p className="muted-text" style={{ fontSize: 12, margin: "0 0 4px" }}>{tAnalysis("gate.autoTagHint")}</p>
              <button className="btn btn-secondary btn-sm" onClick={() => runAnalysisNow(false)}>
                {tAnalysis("gate.runAnyway")}
              </button>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => {
                  setGateReadiness(null);
                  setTab("responses");
                }}
              >
                {tAnalysis("gate.tagFirst")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Delete study confirmation (type-the-name) ───────────────────── */}
      {deleteProjectOpen && project && (
        <div
          className="modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-project-title"
          onClick={() => setDeleteProjectOpen(false)}
        >
          <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 460 }}>
            <button className="modal-close" onClick={() => setDeleteProjectOpen(false)} aria-label={tProject("a11y.close")}>×</button>
            <h3 id="delete-project-title" style={{ marginTop: 0 }}>{tProject("detail.deleteProject")}</h3>
            <p style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.5 }}>
              {tProject("confirms.deleteProjectPrompt", { name: project.name })}
            </p>
            <input
              type="text"
              className="input"
              autoFocus
              value={deleteProjectTyped}
              placeholder={project.name}
              aria-label={tProject("detail.deleteProject")}
              onChange={(e) => setDeleteProjectTyped(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && deleteProjectTyped.trim() === project.name) confirmDeleteProject(); }}
              style={{ width: "100%", marginBottom: 16 }}
            />
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
              <button className="btn btn-ghost btn-sm" onClick={() => setDeleteProjectOpen(false)}>{tCommon("cancel")}</button>
              <button
                className="btn btn-sm btn-danger"
                disabled={deleteProjectTyped.trim() !== project.name}
                onClick={confirmDeleteProject}
              >
                {tCommon("delete")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Delete participant confirmation ─────────────────────────────── */}
      {deleteParticipantOpen && selectedParticipant && (
        <div
          className="modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-participant-title"
          onClick={() => setDeleteParticipantOpen(false)}
        >
          <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 460 }}>
            <button className="modal-close" onClick={() => setDeleteParticipantOpen(false)} aria-label={tProject("a11y.close")}>×</button>
            <h3 id="delete-participant-title" style={{ marginTop: 0 }}>{tProject("responses.deleteParticipant")}</h3>
            <p style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.5 }}>
              {tProject("confirms.deleteParticipant")}
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
              <button className="btn btn-ghost btn-sm" onClick={() => setDeleteParticipantOpen(false)}>{tCommon("cancel")}</button>
              <button className="btn btn-sm btn-danger" onClick={confirmDeleteParticipant}>{tCommon("delete")}</button>
            </div>
          </div>
        </div>
      )}

      {/* ── AI starter-codebook proposal modal ─────────────────────────── */}
      {suggestedCodes && (
        <div
          className="modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="suggested-codes-title"
          onClick={() => setSuggestedCodes(null)}
        >
          <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 480 }}>
            <button className="modal-close" onClick={() => setSuggestedCodes(null)} aria-label={tProject("a11y.close")}>×</button>
            <h3 id="suggested-codes-title" style={{ marginTop: 0 }}>{tProject("responses.suggestedCodesTitle")}</h3>
            <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>{tProject("responses.suggestedCodesIntro")}</p>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, margin: "12px 0" }}>
              {suggestedCodes.map((c) => (
                <label key={c.name} style={{ display: "flex", alignItems: "flex-start", gap: 8, cursor: "pointer" }}>
                  <input
                    type="checkbox"
                    checked={!!suggestedCodesChecked[c.name]}
                    onChange={(e) => setSuggestedCodesChecked((prev) => ({ ...prev, [c.name]: e.target.checked }))}
                    style={{ marginTop: 3 }}
                  />
                  <span>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontWeight: 600, fontSize: 13 }}>
                      <span style={{ width: 10, height: 10, borderRadius: "50%", background: c.color, display: "inline-block" }} />
                      {c.name}
                    </span>
                    {c.description && (
                      <span style={{ display: "block", fontSize: 12, color: "var(--text-tertiary)", lineHeight: 1.4 }}>{c.description}</span>
                    )}
                  </span>
                </label>
              ))}
            </div>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button className="btn btn-secondary btn-sm" onClick={() => setSuggestedCodes(null)}>
                {tProject("responses.suggestedCodesCancel")}
              </button>
              <button
                className="btn btn-primary btn-sm"
                onClick={handleAddSuggestedCodes}
                disabled={addingSuggestedCodes || suggestedCodes.every((c) => !suggestedCodesChecked[c.name])}
              >
                {addingSuggestedCodes
                  ? tProject("responses.suggestedCodesAdding")
                  : tProject("responses.suggestedCodesAdd", { count: suggestedCodes.filter((c) => suggestedCodesChecked[c.name]).length })}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Welcome / first-participant modal ─────────────────────────── */}
      {welcomeOpen && (() => {
        const activeLink = links.find((l) => l.is_active) ?? links[0];
        const shareUrl = activeLink ? interviewUrl(activeLink.token) : "";
        const closeWelcome = () => {
          setWelcomeOpen(false);
          // Remove ?created=1 so a reload won't re-open the modal
          searchParams.delete("created");
          setSearchParams(searchParams, { replace: true });
        };
        const copyShareUrl = async () => {
          if (!shareUrl) return;
          try {
            await navigator.clipboard.writeText(shareUrl);
            setWelcomeCopied(true);
            setTimeout(() => setWelcomeCopied(false), 2000);
          } catch {
            toast(tProject("toasts.clipboardCopyFailed"), "error");
          }
        };
        const subject = encodeURIComponent(tProject("share.emailSubject", { projectName: project?.name ?? "" }));
        const bodyText = encodeURIComponent(
          tProject("share.emailBody", { url: shareUrl })
        );
        const mailtoLink = `mailto:?subject=${subject}&body=${bodyText}`;
        return (
          <div
            className="modal-overlay"
            role="dialog"
            aria-modal="true"
            aria-labelledby="welcome-modal-title"
            onClick={closeWelcome}
          >
            <div className="modal-content welcome-modal" onClick={(e) => e.stopPropagation()}>
              <button className="modal-close" onClick={closeWelcome} aria-label={tProject("a11y.close")}>×</button>
              <div className="welcome-modal-icon" aria-hidden="true">🎉</div>
              <h2 id="welcome-modal-title" className="welcome-modal-title">
                {tProject("detail.welcomeModalTitle")}
              </h2>
              <p className="welcome-modal-subtitle">
                {tProject("detail.welcomeModalSubtitle")}
              </p>

              {activeLink ? (
                <>
                  <div className="welcome-modal-link">
                    <input
                      type="text"
                      readOnly
                      value={shareUrl}
                      onFocus={(e) => e.currentTarget.select()}
                      className="field-input welcome-modal-link-input"
                      aria-label={tProject("a11y.interviewLink")}
                    />
                    <button
                      className="btn btn-primary"
                      onClick={copyShareUrl}
                      type="button"
                    >
                      {welcomeCopied ? `✓ ${tCommon("copied")}` : tProject("detail.copyLink")}
                    </button>
                  </div>

                  <div className="welcome-modal-share">
                    <a
                      href={mailtoLink}
                      className="btn btn-ghost welcome-modal-share-btn"
                    >
                      ✉ {tProject("detail.sendViaEmail")}
                    </a>
                    <button
                      className="btn btn-ghost welcome-modal-share-btn"
                      type="button"
                      onClick={() => {
                        window.open(shareUrl, "_blank");
                      }}
                    >
                      ▶ {tProject("detail.previewInterview")}
                    </button>
                  </div>

                  <div className="welcome-modal-tips">
                    <strong>Pro tip:</strong> {tProject("detail.proTip")}
                  </div>

                  <ol className="welcome-modal-nextsteps" style={{
                    margin: "16px 0 0",
                    padding: "12px 16px 12px 32px",
                    background: "var(--bg-subtle, #f8fafc)",
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    fontSize: 13,
                    lineHeight: 1.6,
                    color: "var(--text-secondary)",
                  }}>
                    <li>{tProject("detail.nextStep1", { defaultValue: "Share the link with participants" })}</li>
                    <li>{tProject("detail.nextStep2", { defaultValue: "Monitor replies in the Responses tab" })}</li>
                    <li>{tProject("detail.nextStep3", { defaultValue: "Run AI Analysis once you have 3+ completed interviews" })}</li>
                  </ol>
                </>
              ) : (
                <div className="welcome-modal-tips">
                  {tProject("detail.noAutoLink")}
                </div>
              )}

              <div className="welcome-modal-footer">
                <button className="btn btn-ghost" onClick={closeWelcome}>
                  {tProject("detail.shareLater")}
                </button>
                <button
                  className="btn btn-primary"
                  onClick={() => {
                    setTab("overview");
                    closeWelcome();
                  }}
                >
                  {tProject("detail.goToProject")}
                </button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* In-context AI assistant. Accepted proposals are applied via the
          real interview-guide API, then we reload the project. */}
      <ResearchCopilotPanel
        target={{
          id: project.id,
          runTurn: (m, h) =>
            runCopilot(
              "projects",
              project.id,
              m,
              instrumentSections.find((s) => s.key === tab)?.label,
              projectMission,
              h,
            ),
          loadConversation: () => getConversation("projects", project.id),
          saveConversation: (t, v) => saveConversation("projects", project.id, t, v),
          applyAction: async (action) => {
            if (action.type === "edit_objective" && action.new_objective) {
              await patchProjectSettings(project.id, {
                research_objective: action.new_objective,
              });
            } else if (action.type === "add_guide_question" && action.question) {
              const q = action.question as ProposedGuideQuestion;
              await createGuideQuestion(project.id, {
                section_title: q.section_title,
                main_question: q.main_question,
                desired_learning: q.desired_learning,
                // Persist the Copilot's "why" as the question's note so the
                // reasoning survives the accept (it used to be dropped).
                researcher_notes: q.rationale || undefined,
              });
            } else if (action.type === "edit_settings" && action.settings) {
              await patchProjectSettings(project.id, action.settings);
            } else if (action.type === "add_screening_question" && action.screening) {
              await createScreeningQuestion(project.id, {
                question: action.screening.question,
                options: action.screening.options,
                disqualifying_options: action.screening.disqualifying_options,
              });
            } else if (
              action.type === "edit_guide_question" &&
              action.question_id
            ) {
              const payload: {
                main_question?: string;
                desired_learning?: string;
              } = {};
              if (action.new_main_question)
                payload.main_question = action.new_main_question;
              if (action.new_desired_learning)
                payload.desired_learning = action.new_desired_learning;
              await patchQuestion(project.id, action.question_id, payload);
            } else if (
              action.type === "remove_guide_question" &&
              action.question_id
            ) {
              await patchQuestion(project.id, action.question_id, {
                deprecated_at: new Date().toISOString(),
              });
            } else if (action.type === "run_analysis") {
              await triggerAnalysis(project.id);
            } else if (action.type === "refine_analysis") {
              await triggerRefinedAnalysis(project.id);
            }
          },
        }}
        onApplied={() => {
          if (!id) return;
          getProject(id)
            .then(setProject)
            .catch(() => undefined);
        }}
        mission={projectMission}
        nextAction={projectNextAction}
        nudges={nudges}
        onDismissNudge={(nid) => {
          dismissNudge(nid);
          if (project) setNudges(activeNudgesFor(project.id));
        }}
      />

      {/* V4 paywall — opens when a locked transcript is clicked or
       *  the analysis trigger returns 402. */}
      <UnlockModal
        open={unlockState.open}
        onClose={() => setUnlockState({ open: false, lockedCount: 0 })}
        lockedCount={unlockState.lockedCount}
        mode={unlockState.mode}
      />
    </InstrumentShell>
  );
}
