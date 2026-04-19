import React, { useState, useEffect, useRef } from "react";
import { useParams, useNavigate, useSearchParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useToast } from "../components/Toast";
import { SkeletonTable } from "../components/Skeleton";
import LanguageSwitcher from "../components/LanguageSwitcher";
import { useAuth } from "../hooks/useAuth";
import {
  getProject,
  listProjects,
  getLinks,
  getParticipants,
  createLink,
  toggleLink,
  updateProject,
  exportCSV,
  archiveProject,
  getAnalysis,
  triggerAnalysis,
  updateTurn,
  patchQuestion,
  getCodes,
  createCode,
  updateCode,
  deleteCode,
  getTags,
  createTag,
  deleteTag,
  getMemos,
  createMemo,
  updateMemo,
  deleteMemo,
  getHeatmap,
  shareAnalysis,
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
import { getTranscript, translateTranscript } from "../api/projects";

type Tab = "overview" | "setup" | "responses" | "analysis";

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
  const { logout } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  // ── First-run welcome modal (shown after project creation) ──────────────
  const [welcomeOpen, setWelcomeOpen] = useState(() => searchParams.get("created") === "1");
  const [welcomeCopied, setWelcomeCopied] = useState(false);

  // ── Core state ─────────────────────────────────────────────────────────────
  const [project, setProject] = useState<ProjectResponse | null>(null);
  const [links, setLinks] = useState<InterviewLink[]>([]);
  const [participants, setParticipants] = useState<ParticipantResponse[]>([]);
  const [transcript, setTranscript] = useState<TranscriptTurn[] | null>(null);
  const [selectedParticipant, setSelectedParticipant] = useState<ParticipantResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [copiedToken, setCopiedToken] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [analysisPolling, setAnalysisPolling] = useState(false);
  const [tab, setTabRaw] = useState<Tab>("overview");
  // advancedPromptOpen removed — system prompt hidden from researchers
  const [projects, setProjects] = useState<import("../api/projects").ProjectListItem[]>([]);

  // ── Responses tab filters/sort ─────────────────────────────────────────────
  const [responseStatusFilter, setResponseStatusFilter] = useState<"all" | "completed" | "in_progress">("all");
  const [responseSortBy, setResponseSortBy] = useState<"date" | "quality" | "name">("date");

  // ── Analysis version history ───────────────────────────────────────────────
  const [analysisVersions, setAnalysisVersions] = useState<AnalysisVersionMeta[]>([]);
  const [versionHistoryOpen, setVersionHistoryOpen] = useState(false);

  // ── Transcript highlight target (from "View transcript →" in analysis) ───────
  const [highlightTarget, setHighlightTarget] = useState<{ turnIndex: number; quoteText: string } | null>(null);
  const transcriptListRef = useRef<HTMLDivElement>(null);

  // ── Transcript translation (reading aid) ──────────────────────────────────
  const [transcriptViewMode, setTranscriptViewMode] = useState<"original" | "translated">("original");
  const [translating, setTranslating] = useState(false);

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

  // Guard tab switches when there are unsaved edits in Setup
  function hasUnsavedSetupEdits(): boolean {
    return editingScreening || editingQuestionId !== null || editingNoteId !== null || editingInterviewNotes !== null;
  }

  function setTab(next: Tab) {
    if (next !== tab && tab === "setup" && hasUnsavedSetupEdits()) {
      if (!window.confirm(tProject("detail.unsavedChanges"))) return;
      setEditingScreening(false);
      setEditingQuestionId(null);
      setEditingNoteId(null);
      setEditingInterviewNotes(null);
    }
    setTabRaw(next);
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
      if (parts.length > 0) setTab("responses");
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
      listProjects().then(setProjects).catch(() => {}),
      getAnalysisHistory(id!).then(setAnalysisVersions).catch(() => {}),
    ]);
  }

  function startPolling() {
    if (analysisPolling) return;
    setAnalysisPolling(true);
    const iv = setInterval(async () => {
      const ana = await getAnalysis(id!);
      setAnalysis(ana);
      if (ana.status !== "generating") {
        clearInterval(iv);
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
  }

  async function handleTriggerAnalysis() {
    if (analysis?.report) {
      const ok = window.confirm(tAnalysis("regenerateConfirm"));
      if (!ok) return;
    }
    const filters =
      activeFilterBy && activeFilterValues.length > 0
        ? { filter_by: activeFilterBy, filter_values: activeFilterValues }
        : undefined;
    await triggerAnalysis(id!, filters);
    setAnalysis((prev) => prev ? { ...prev, status: "generating" } : null);
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
      r.recommendations.forEach((rec) => lines.push(`- ${rec}`));
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

  async function handleShareAnalysis() {
    try {
      const res = await shareAnalysis(id!);
      const url = `${window.location.origin}/reports/${res.share_token}`;
      await navigator.clipboard.writeText(url);
      toast("Share link copied to clipboard ✓", "success");
    } catch {
      toast("Could not generate share link — make sure analysis is ready.", "error");
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
        toast("Failed to remove annotation", "error");
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
      toast("Failed to save annotation", "error");
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
      toast("Failed to save note", "error");
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
        toast("Failed to save context", "error");
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
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed to start refined analysis";
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
      toast("Failed to load version", "error");
    }
  }

  async function handleGenerateLink() {
    try {
      const link = await createLink(id!);
      setLinks((prev) => [...prev, link]);
    } catch {
      toast("Failed to generate link", "error");
    }
  }

  async function handleToggleLink(linkId: string) {
    try {
      const updated = await toggleLink(linkId);
      setLinks((prev) => prev.map((l) => (l.id === linkId ? updated : l)));
    } catch {
      toast("Failed to update link", "error");
    }
  }

  function interviewUrl(token: string) {
    return `${window.location.origin}/i/${token}`;
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
    if (editingTurnId && editingText !== editingOriginalText) {
      if (!confirm("You have unsaved transcript changes. Discard them?")) return;
    }
    setSelectedParticipant(p);
    setTranscript(null);
    setEditingTurnId(null);
    setSelectionInfo(null);
    setTranscriptViewMode("original");
    if (highlight) setHighlightTarget(highlight);
    else setHighlightTarget(null);
    try {
      const result = await getTranscript(id!, p.id);
      setSelectedParticipant(result.participant);
      setTranscript(result.turns);
    } catch {
      setTranscript([]);
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
      toast("Failed to export CSV", "error");
    }
  }

  async function handleArchive() {
    if (!confirm("Archive this project? You can restore it any time from the dashboard.")) return;
    try {
      await archiveProject(id!);
      toast("Project archived", "success");
      navigate("/dashboard");
    } catch {
      toast("Failed to archive project", "error");
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
      toast("Failed to save transcript edit", "error");
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
    const start = fullText.indexOf(text);
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
      toast("Failed to tag quote", "error");
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
      toast("Failed to create code", "error");
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
    if (!confirm("Delete this code? All tagged quotes will also be removed.")) return;
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
      toast("Failed to rename code", "error");
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
      toast("Failed to save notes", "error");
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
      toast("Failed to save question", "error");
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
      toast("Failed to reorder", "error");
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
      toast("Failed to save note", "error");
    }
  }

  async function toggleDeprecateQuestion(questionId: string, currentDeprecatedAt: string | null | undefined) {
    const inProgress = participants.some((p) => p.status === "in_progress");
    if (!currentDeprecatedAt && inProgress) {
      if (!confirm("There are interviews in progress. Deprecating will skip this question for new responses. Continue?")) return;
    }
    const newDeprecatedAt = currentDeprecatedAt ? null : new Date().toISOString();
    try {
      const updated = await patchQuestion(id!, questionId, { deprecated_at: newDeprecatedAt });
      setProject((prev) =>
        prev ? { ...prev, questions: prev.questions.map((q) => q.id === questionId ? { ...q, deprecated_at: updated.deprecated_at } : q) } : prev
      );
    } catch {
      toast("Failed to update question", "error");
    }
  }

  // ── P6: Memos ──────────────────────────────────────────────────────────────

  function timeAgo(dateStr: string): string {
    const now = new Date();
    const date = new Date(dateStr);
    const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);
    if (seconds < 60) return "just now";
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}d ago`;
    return date.toLocaleDateString();
  }

  async function handleAddMemo(type: string, linkedKey: string | null) {
    if (!newMemoContent.trim()) return;
    try {
      const memo = await createMemo(id!, { type, linked_key: linkedKey, content: newMemoContent });
      setMemos((prev) => [...prev, memo]);
      setNewMemoContent("");
      setAddingMemoKey(null);
    } catch {
      toast("Failed to save memo", "error");
    }
  }

  async function handleUpdateMemo(memoId: string) {
    try {
      const updated = await updateMemo(id!, memoId, editingMemoContent);
      setMemos((prev) => prev.map((m) => m.id === memoId ? updated : m));
      setEditingMemoId(null);
    } catch {
      toast("Failed to update memo", "error");
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
      toast("No ready analysis available — generate one first.", "error");
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
    }
    return Object.fromEntries(Object.entries(opts).map(([k, v]) => [k, Array.from(v)]));
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
            onClick={(e) => { e.stopPropagation(); if (confirm(`Remove "${tag.code_name}" tag?`)) handleDeleteTag(tag.id); }}
            aria-label={`Remove tag ${tag.code_name}`}
            title="Remove tag"
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
            <textarea className="field-input" value={newMemoContent} onChange={(e) => setNewMemoContent(e.target.value)} placeholder="Research note..." rows={3} style={{ width: "100%", marginBottom: 6 }} autoFocus />
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

  if (loading) return <div className="page-center"><p className="muted-text">Loading project...</p></div>;
  if (!project) return <div className="page-center"><p>Project not found.</p></div>;

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
    } catch { toast("Failed to save screening questions", "error"); }
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

  return (
    <div className="detail-layout">

      {/* ── Branded header (matches Dashboard) ── */}
      <header className="dashboard-header" style={{ flexWrap: "wrap" }}>
        <span className="logo">QualiPulse</span>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <LanguageSwitcher variant="light" />
          <button className="btn btn-ghost" style={{ minHeight: 44 }} onClick={() => navigate("/account")}>
            {tCommon("account")}
          </button>
          <button className="btn btn-ghost" style={{ minHeight: 44 }} onClick={logout}>
            {tCommon("signOut")}
          </button>
        </div>
      </header>

      {/* ── Breadcrumb + actions ── */}
      <div className="detail-header">
        <div className="detail-header-left">
          <div className="detail-breadcrumb">
            <a href="/dashboard">{tProject("detail.backToDashboard").replace("← ", "")}</a>
            <span className="detail-breadcrumb-sep">/</span>
            <span>{project.name}</span>
            {projects.length > 1 && (
              <select
                style={{ marginLeft: 8, fontSize: "0.8rem", color: "var(--text-tertiary)", background: "none", border: "none", cursor: "pointer" }}
                value={id}
                onChange={(e) => navigate(`/projects/${e.target.value}`)}
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            )}
          </div>
        </div>
        <div className="detail-header-actions">
          <button className="btn btn-ghost btn-sm" onClick={handleExportCSV}>{tProject("responses.exportCSV")}</button>
          <button className="btn btn-ghost btn-sm" onClick={handleArchive}>{tProject("detail.archiveProject")}</button>
        </div>
      </div>

      {/* ── Tabs — ordered by researcher workflow ── */}
      <div className="detail-tabs" role="tablist">
        {(["overview", "setup", "responses", "analysis"] as Tab[]).map((tabKey) => (
          <button
            key={tabKey}
            role="tab"
            aria-selected={tab === tabKey}
            className={`detail-tab ${tab === tabKey ? "active" : ""}`}
            onClick={() => setTab(tabKey)}
          >
            {tabKey === "responses" && (<>{tProject("detail.tabResponses")} {participants.length > 0 && <span className="tab-count">{completedCount}/{participants.length}</span>}</>)}
            {tabKey === "analysis" && (<>{tProject("detail.tabAnalysis")} {analysis?.status === "generating" && <span className="tab-dot tab-dot-pulse" />}</>)}
            {tabKey === "overview" && tProject("detail.tabOverview")}
            {tabKey === "setup" && tProject("detail.tabSetup")}
          </button>
        ))}
      </div>

      <main className="detail-main">

        {/* ── Demo project banner ── */}
        {project.is_demo && (
          <div className="demo-banner">
            <p>{tProject("detail.demoBannerText")}</p>
            <Link to="/projects/new" className="btn btn-primary btn-sm" style={{ whiteSpace: "nowrap", textDecoration: "none", flexShrink: 0 }}>
              {tProject("detail.demoBannerCta")}
            </Link>
          </div>
        )}

        {/* ══ OVERVIEW ══ */}
        {tab === "overview" && (
          <div className="tab-content">
            <div className="stats-row">
              <div className="stat-card"><div className="stat-value">{participants.length}</div><div className="stat-label">{tProject("overview.totalParticipants")}</div></div>
              <div className="stat-card stat-card--success"><div className="stat-value">{completedCount}</div><div className="stat-label">{tProject("overview.completed")}</div></div>
              <div className="stat-card">
                <div className="stat-value">{participants.length > 0 ? Math.round((completedCount / participants.length) * 100) : 0}%</div>
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
                  <button className="btn btn-ghost btn-sm" onClick={() => { setObjectiveDraft(project.research_objective ?? ""); setEditingObjective(true); }}>{tCommon("edit")}</button>
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
                  <button className="btn btn-ghost btn-sm" onClick={() => { setWelcomeDraft(project.welcome_message ?? ""); setEditingWelcome(true); }}>{tCommon("edit")}</button>
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
            <section className="detail-section">
              <div className="section-header-row">
                <h2>{tProject("overview.interviewLinkTitle")}</h2>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={handleGenerateLink}
                  disabled={project.is_demo}
                  title={project.is_demo ? tProject("overview.demoLinkDisabled") : undefined}
                >{tProject("overview.newLink")}</button>
              </div>
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
                      </div>
                      <div className="link-row-actions">
                        {l.is_active && (
                          <button className="btn btn-ghost btn-sm" onClick={() => copyLink(l.token)}>
                            {copiedToken === l.token ? `✓ ${tProject("overview.linkCopied")}` : tProject("overview.copyLink")}
                          </button>
                        )}
                        <button
                          className={`btn btn-sm ${l.is_active ? "btn-ghost" : "btn-secondary"}`}
                          onClick={() => handleToggleLink(l.id)}
                        >
                          {l.is_active ? tProject("overview.deactivateLink") : tProject("overview.activateLink")}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>
        )}

        {/* ══ SETUP ══ */}
        {tab === "setup" && (
          <div className="tab-content">

            {/* Screening Questions */}
            <section className="detail-section">
              <div className="section-header-row">
                <div>
                  <h2>{tProject("setup.screeningTitle")}</h2>
                  <p className="muted-text" style={{ fontSize: 13, marginTop: 2 }}>{tProject("setup.screeningSubtitle")}</p>
                </div>
                {!editingScreening && <button className="btn btn-ghost btn-sm" onClick={startEditScreening}>{tCommon("edit")}</button>}
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
                                title={sq.disqualifying_options.includes(opt) ? "Disqualifying" : "Allowed"}
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
                <button className="btn btn-ghost btn-sm" onClick={() => navigate(`/projects/${id}/edit`)}>{tProject("setup.addQuestions")}</button>
              </div>
              {project.questions.length === 0 ? (
                <p className="muted-text">{tProject("setup.noQuestionsYet")} <button className="btn btn-primary btn-sm" onClick={() => navigate(`/projects/${id}/edit`)}>{tProject("setup.createGuide")}</button></p>
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
                          {activeQs.map((q, qi) => {
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
                                        <span className="guide-question-card__num">Q{qi + 1}</span>
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
            return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
          }

          function avatarInitial(name: string | null | undefined) {
            const n = name?.trim();
            if (!n) return "?";
            return n[0].toUpperCase();
          }

          return (
          <div className="tab-content" style={{ padding: 0 }}>
            <div className="responses-layout">
              {/* ── Left column: filter + list ── */}
              <div className="responses-list-col">
                {/* Header row */}
                <div style={{ marginBottom: 12 }}>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>{tProject("responses.title")}</span>
                </div>

                {/* Status filter pills */}
                <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
                  {(["all", "completed", "in_progress"] as const).map(f => {
                    const label = f === "all" ? `${tProject("responses.allFilter")} (${participants.length})` : f === "completed" ? `${tProject("responses.doneFilter")} (${completedCount})` : `${tProject("responses.inProgressFilter")} (${inProgressCount})`;
                    return (
                      <button
                        key={f}
                        className={`filter-pill ${responseStatusFilter === f ? "filter-pill--active" : ""}`}
                        onClick={() => setResponseStatusFilter(f)}
                      >{label}</button>
                    );
                  })}
                </div>

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
                        className={`participant-row participant-row--compact ${selectedParticipant?.id === p.id ? "active" : ""}`}
                        onClick={() => handleViewTranscript(p)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); handleViewTranscript(p); } }}
                      >
                        <div className="participant-avatar">{avatarInitial(p.display_name)}</div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            <span className="participant-name" style={{ fontSize: 13, marginRight: 0 }}>{p.display_name || tProject("responses.anonymous")}</span>
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
                        <button className="participant-card__close" onClick={() => { setTranscript(null); setSelectedParticipant(null); setSelectionInfo(null); }} aria-label={tProject("responses.close")}>✕</button>
                      </div>
                      <div className="participant-card__body">
                        <div className="participant-card__info">
                          <h2 className="participant-card__name">{selectedParticipant.display_name || tProject("responses.anonymous")}</h2>
                          <div className="participant-card__meta">
                            {selectedParticipant.profession && <span className="participant-card__badge">{selectedParticipant.profession}</span>}
                            {selectedParticipant.age_range && <span className="participant-card__badge">{selectedParticipant.age_range}</span>}
                            {selectedParticipant.country && <span className="participant-card__badge">{selectedParticipant.country}</span>}
                          </div>
                          <span className="participant-card__date">{new Date(selectedParticipant.started_at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}</span>
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
                      {/* Translation toggle (reading aid) */}
                      {project?.language && project.language !== (i18n.language || "en").slice(0, 2).toLowerCase() && (
                        <div className="translation-toggle" role="group" aria-label={tProject("responses.translationToggleLabel")}>
                          <button
                            className={`translation-toggle__btn${transcriptViewMode === "original" ? " is-active" : ""}`}
                            onClick={() => setTranscriptViewMode("original")}
                            disabled={translating}
                          >
                            {tProject("responses.viewOriginal", { lang: project.language.toUpperCase() })}
                          </button>
                          <button
                            className={`translation-toggle__btn${transcriptViewMode === "translated" ? " is-active" : ""}`}
                            onClick={handleToggleTranslation}
                            disabled={translating}
                          >
                            {translating
                              ? tProject("responses.translating")
                              : tProject("responses.viewTranslated", { lang: (i18n.language || "en").slice(0, 2).toUpperCase() })}
                          </button>
                        </div>
                      )}
                    </div>

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
                                  <audio controls src={t.tts_audio_url} className="transcript-audio" aria-label={`AI question audio — turn ${t.turn_index}`} />
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
                                  className={`transcript-a${transcriptViewMode === "translated" && t.translated_response ? " transcript-a--translated" : ""}`}
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
                                  ) : isHighlighted && highlightTarget
                                    ? renderWithQuoteHighlight(t.response_transcript, highlightTarget.quoteText, t.id)
                                    : renderTaggedText(t.response_transcript, t.id)}
                                  <span style={{ display: "inline-flex", gap: 4, marginLeft: 8, verticalAlign: "middle" }}>
                                    <button className="btn btn-ghost btn-xs" style={{ fontSize: 10 }} onClick={() => startEditTurn(t)}>{tCommon("edit")}</button>
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
                                    <audio controls src={t.audio_recording_url} className="transcript-audio" aria-label={`Participant recording — turn ${t.turn_index}`} />
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
                            </div>
                          );
                        })}
                      </div>
                    )}
                    </div>{/* /transcript-main-col */}

                    {/* ── Right: Tools sidebar ── */}
                    <div className="transcript-sidebar">
                      {/* Quality Assessment panel */}
                      {selectedParticipant.quality_summary ? (
                        <details className="sidebar-panel" open>
                          <summary className="sidebar-panel__header">
                            <span className="sidebar-panel__title">{tProject("responses.qualityAssessment")}</span>
                          </summary>
                          <div className="sidebar-panel__body">
                            <p className="sidebar-panel__summary">{selectedParticipant.quality_summary}</p>
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
                            <p className="sidebar-panel__pending">{tProject("qualityPending")}</p>
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

            {/* Floating tag popup */}
            {selectionInfo && (
              <div style={{ position: "fixed", left: selectionInfo.x - 90, top: selectionInfo.y, zIndex: 1000, background: "var(--bg-surface)", border: "1px solid var(--border-default)", borderRadius: "var(--radius)", boxShadow: "var(--shadow-md)", padding: 8, minWidth: 180 }}>
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
          <div className="tab-content">
            <section className="detail-section">
              {/* Stale banner — above actions so it's seen before clicking Regenerate */}
              {analysis.report && analysis.completed_count > analysis.participant_count && (
                <div className="analysis-stale-banner">
                  ⚠ {tAnalysis("staleWarning", { count: analysis.completed_count - analysis.participant_count })}
                </div>
              )}
              <div className="section-header-row">
                <h2>{tAnalysis("aiAnalysis")}</h2>
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                  {analysis.report && (
                    <>
                      <button className="btn btn-ghost btn-sm" onClick={handleCopyMarkdown}>
                        {exportCopied ? `✓ ${tCommon("copied")}` : tAnalysis("copyMd")}
                      </button>
                      <button className="btn btn-ghost btn-sm" onClick={handleDownloadJSON}>
                        {tAnalysis("downloadJson")}
                      </button>
                      <button className="btn btn-ghost btn-sm" onClick={handleShareAnalysis}>
                        🔗 {tAnalysis("shareBtn")}
                      </button>
                    </>
                  )}
                  {analysis.completed_count > 0 && (
                    <button className="btn btn-ai btn-sm" onClick={handleTriggerAnalysis} disabled={analysis.status === "generating"}>
                      {analysis.status === "generating" ? tAnalysis("analysing") : analysis.status === "none" ? `✦ ${tAnalysis("generateBtn")}` : `✦ ${tAnalysis("regenerateBtn")}`}
                    </button>
                  )}
                </div>
              </div>

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
                          <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)", marginBottom: 4, textTransform: "capitalize" }}>{attr.replace("_", " ")}</div>
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
                        <span key={v} className="badge" style={{ background: "var(--brand-50)", color: "var(--brand-700)" }}>{analysis.filters!.filter_by}: {v}</span>
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
              {analysis.status === "generating" && (
                <div className="analysis-generating"><span className="spinner-sm" /><span>{tAnalysis("claudeReading", { count: analysis.participant_count })}</span></div>
              )}
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
                        {tAnalysis("confidenceBadge", { level: r.confidence })}
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

                    {/* Themes */}
                    {r.themes.length > 0 && (
                      <div className="analysis-block">
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
                                        aria-label="Confirmed"
                                        onClick={() => handleAnnotationClick(t.title, "confirmed")}
                                      >✓ {tAnalysis("annotationConfirm")}</button>
                                      <button
                                        className={`annotation-pill${ann?.status === "needs_evidence" ? " annotation-pill--needs_evidence" : ""}`}
                                        aria-label="Needs evidence"
                                        onClick={() => handleAnnotationClick(t.title, "needs_evidence")}
                                      >? {tAnalysis("annotationEvidence")}</button>
                                      <button
                                        className={`annotation-pill${ann?.status === "disputed" ? " annotation-pill--disputed" : ""}`}
                                        aria-label="Disputed"
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
                      <div className="analysis-block">
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
                      <div className="analysis-block">
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
                      <div className="analysis-block">
                        <h3>{tAnalysis("recommendations")}</h3>
                        <ol className="analysis-recommendations">
                          {r.recommendations.map((rec, i) => <li key={i}>{rec}</li>)}
                        </ol>
                      </div>
                    )}

                    {/* General memos */}
                    <div className="analysis-block">
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
                      <div className="analysis-block">
                        <div className="researcher-context-box">
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                            <h3 style={{ margin: 0 }}>{tAnalysis("researcherContext")}</h3>
                            <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
                              {contextSaving === "saving" ? tCommon("saving") : contextSaving === "saved" ? `${tCommon("save")} ✓` : ""}
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

                    {/* P7: Heatmap */}
                    <div className="analysis-block">
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
                                          title={count > 0 ? `${count} quote(s) — ${segParticipants.join(", ")}` : "No quotes from this segment"}
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
                  </div>
                );
              })()}
            </section>
          </div>
        )}
      </main>

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
            toast("Could not copy to clipboard", "error");
          }
        };
        const subject = encodeURIComponent(`Quick research interview — ${project?.name ?? ""}`);
        const bodyText = encodeURIComponent(
          `Hi,\n\nI'd love your input on a short research study I'm running.\n` +
            `It's a 10–20 minute voice interview you can do right from your browser, at your own pace.\n\n` +
            `Start here: ${shareUrl}\n\nThanks so much!`
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
              <button className="modal-close" onClick={closeWelcome} aria-label="Close">×</button>
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
                      aria-label="Interview link"
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
    </div>
  );
}
