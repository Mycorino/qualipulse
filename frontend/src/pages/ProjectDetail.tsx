import React, { useState, useEffect, useRef } from "react";
import { useParams, useNavigate, useSearchParams, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useToast } from "../components/Toast";
import { SkeletonTable } from "../components/Skeleton";
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
  assessQuality,
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
import { getTranscript, patchProjectSettings } from "../api/projects";

type Tab = "overview" | "setup" | "responses" | "analysis";

const PRESET_COLORS = [
  "#6366f1", "#ec4899", "#f59e0b", "#10b981",
  "#3b82f6", "#8b5cf6", "#ef4444", "#14b8a6",
];

export default function ProjectDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const { t: tAnalysis } = useTranslation("analysis");
  const { t: tProject } = useTranslation("project");
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
  const [advancedPromptOpen, setAdvancedPromptOpen] = useState(false);
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
  const codebookInitial = localStorage.getItem(codebookPrefKey) === "true";
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

  // ── System prompt editor ────────────────────────────────────────────────────
  const [editingSystemPrompt, setEditingSystemPrompt] = useState(false);
  const [systemPromptDraft, setSystemPromptDraft] = useState("");
  const [savingSystemPrompt, setSavingSystemPrompt] = useState(false);

  // ── Panel settings ─────────────────────────────────────────────────────────
  const [savingPanelToggle, setSavingPanelToggle] = useState(false);

  async function handlePanelToggle(enabled: boolean) {
    if (!id || !project) return;
    setSavingPanelToggle(true);
    try {
      const updated = await patchProjectSettings(id, { panel_collection_enabled: enabled });
      setProject(updated);
      toast(enabled ? "Panel collection enabled" : "Panel collection disabled", "success");
    } catch {
      toast("Failed to update setting", "error");
    } finally {
      setSavingPanelToggle(false);
    }
  }

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
    turnId: string; text: string; start: number; end: number; x: number; y: number;
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

  // ── P8: AI Quality assessment ───────────────────────────────────────────────
  const [qualityAssessment, setQualityAssessment] = useState<import("../api/projects").QualityAssessment | null>(null);
  const [loadingQuality, setLoadingQuality] = useState(false);

  // Guard tab switches when there are unsaved edits in Setup
  function hasUnsavedSetupEdits(): boolean {
    return editingScreening || editingQuestionId !== null || editingNoteId !== null || editingInterviewNotes !== null;
  }

  function setTab(next: Tab) {
    if (next !== tab && tab === "setup" && hasUnsavedSetupEdits()) {
      if (!window.confirm("You have unsaved changes in the Setup tab. Discard them?")) return;
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
    lines.push(`\n*Based on ${r.participant_count} participant(s) · ${r.confidence} confidence*\n`);
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
          await fetch(`/api/projects/${id}/analysis/annotations/${existing.id}`, { method: "DELETE", headers: { Authorization: `Bearer ${localStorage.getItem("access_token")}` } });
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
    setQualityAssessment(null);
    setSelectionInfo(null);
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

  async function handleAssessQuality() {
    if (!selectedParticipant) return;
    setLoadingQuality(true);
    setQualityAssessment(null);
    try {
      const result = await assessQuality(id!, selectedParticipant.id);
      setQualityAssessment(result);
    } catch {
      toast("Failed to assess quality", "error");
    } finally {
      setLoadingQuality(false);
    }
  }

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
          style={{ borderBottom: `2.5px solid ${color}`, background: `${color}22`, borderRadius: 2, cursor: "pointer" }}
          title={`[${tag.code_name}] — click to remove`}
          onClick={() => handleDeleteTag(tag.id)}
        >
          {text.slice(tag.start_index, tag.end_index)}
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
        <div style={{ fontSize: 12, color: "#6b7280", marginTop: 4, display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontWeight: 600, color: "#374151" }}>{q.participant_display_name || q.participant_identifier}</span>
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

  async function saveSystemPrompt() {
    if (!project) return;
    setSavingSystemPrompt(true);
    try {
      const updated = await updateProject(id!, {
        name: project.name,
        language: project.language,
        interview_duration_minutes: project.interview_duration_minutes,
        research_objective: project.research_objective,
        welcome_message: project.welcome_message,
        system_prompt: systemPromptDraft,
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
      setEditingSystemPrompt(false);
    } finally {
      setSavingSystemPrompt(false);
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

      {/* ── Header ── */}
      <header className="detail-header">
        <div className="detail-header-left">
          <div className="detail-breadcrumb">
            <a href="/dashboard">Projects</a>
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
          <button className="btn btn-ghost btn-sm" onClick={handleExportCSV}>Export CSV</button>
          <button className="btn btn-ghost btn-sm" onClick={handleArchive} title="Archive this project (recoverable from the dashboard)">Archive</button>
        </div>
      </header>

      {/* ── Tabs — ordered by researcher workflow ── */}
      <div className="detail-tabs" role="tablist">
        {(["overview", "setup", "responses", "analysis"] as Tab[]).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            className={`detail-tab ${tab === t ? "active" : ""}`}
            onClick={() => setTab(t)}
          >
            {t === "responses" && (<>Responses {participants.length > 0 && <span className="tab-count">{completedCount}/{participants.length}</span>}</>)}
            {t === "analysis" && (<>Analysis {analysis?.status === "generating" && <span className="tab-dot tab-dot-pulse" />}</>)}
            {t === "overview" && "Overview"}
            {t === "setup" && "Setup"}
          </button>
        ))}
      </div>

      <main className="detail-main">

        {/* ── Demo project banner ── */}
        {project.is_demo && (
          <div style={{
            background: "var(--brand-50, #eef2ff)",
            border: "1px solid var(--brand-200, #c7d2fe)",
            borderRadius: 10,
            padding: "16px 20px",
            marginBottom: 20,
            display: "flex",
            alignItems: "center",
            gap: 16,
            flexWrap: "wrap",
          }}>
            <p style={{ flex: 1, margin: 0, fontSize: 14, color: "var(--text-primary)", lineHeight: 1.5 }}>
              {tProject("detail.demoBannerText")}
            </p>
            <Link
              to="/projects/new"
              className="btn btn-primary btn-sm"
              style={{ whiteSpace: "nowrap", textDecoration: "none", flexShrink: 0 }}
            >
              {tProject("detail.demoBannerCta")}
            </Link>
          </div>
        )}

        {/* ══ OVERVIEW ══ */}
        {tab === "overview" && (
          <div className="tab-content">
            <div className="stats-row">
              <div className="stat-card"><div className="stat-value">{participants.length}</div><div className="stat-label">Participants</div></div>
              <div className="stat-card"><div className="stat-value">{completedCount}</div><div className="stat-label">Completed</div></div>
              <div className="stat-card">
                <div className="stat-value">{participants.length > 0 ? Math.round((completedCount / participants.length) * 100) : 0}%</div>
                <div className="stat-label">Completion rate</div>
              </div>
              <div className="stat-card">
                <div className="stat-value">{project.questions.length}</div>
                <div className="stat-label">Guide questions</div>
                {project.questions.length === 0 && (
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4, fontStyle: "italic" }}>No questions yet — add in Setup tab</div>
                )}
              </div>
            </div>
            {/* Analysis readiness prompt */}
            {completedCount >= 3 && (!analysis || (analysis.status === "ready" && analysis.participant_count < completedCount)) && (
              <div
                style={{
                  background: "var(--success-bg, #f0fdf4)",
                  border: "1px solid var(--success-border, #bbf7d0)",
                  borderRadius: 10,
                  padding: "14px 18px",
                  marginBottom: 16,
                  display: "flex",
                  alignItems: "center",
                  gap: 14,
                  flexWrap: "wrap",
                }}
              >
                <span style={{ fontSize: 20 }}>✦</span>
                <div style={{ flex: 1, minWidth: 200 }}>
                  <div style={{ fontWeight: 600, fontSize: 14, color: "var(--text-primary)" }}>
                    {!analysis
                      ? `${completedCount} interviews completed — ready for AI analysis`
                      : `${completedCount - (analysis.participant_count || 0)} new interview${completedCount - (analysis.participant_count || 0) !== 1 ? "s" : ""} since last analysis`}
                  </div>
                  <div style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 2 }}>
                    {!analysis
                      ? "Generate themes, insights, and recommendations from your data."
                      : "Refresh to include the latest responses in your analysis."}
                  </div>
                </div>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => setTab("analysis")}
                  style={{ flexShrink: 0 }}
                >
                  {!analysis ? "Generate insights →" : "Refresh analysis →"}
                </button>
              </div>
            )}

            {/* Research Objective — inline edit */}
            <section className="detail-section">
              <div className="section-header-row">
                <h2>Research Objective</h2>
                {!editingObjective && (
                  <button className="btn btn-ghost btn-sm" onClick={() => { setObjectiveDraft(project.research_objective ?? ""); setEditingObjective(true); }}>Edit</button>
                )}
              </div>
              {editingObjective ? (
                <div>
                  <textarea
                    className="field-input"
                    rows={3}
                    value={objectiveDraft}
                    onChange={(e) => setObjectiveDraft(e.target.value)}
                    placeholder="What are you trying to learn from this research?"
                    style={{ resize: "vertical" }}
                  />
                  <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                    <button className="btn btn-primary btn-sm" onClick={() => saveProjectMeta({ research_objective: objectiveDraft })} disabled={savingMeta}>{savingMeta ? "Saving…" : "Save"}</button>
                    <button className="btn btn-ghost btn-sm" onClick={() => setEditingObjective(false)}>Cancel</button>
                  </div>
                </div>
              ) : (
                <p className="objective-text" style={{ color: project.research_objective ? undefined : "var(--text-muted)", fontStyle: project.research_objective ? undefined : "italic" }}>
                  {project.research_objective || "No objective set — click Edit to add one."}
                </p>
              )}
            </section>

            {/* Welcome Message — inline edit */}
            <section className="detail-section">
              <div className="section-header-row">
                <h2>Welcome Message <span className="optional-tag">(shown to participants)</span></h2>
                {!editingWelcome && (
                  <button className="btn btn-ghost btn-sm" onClick={() => { setWelcomeDraft(project.welcome_message ?? ""); setEditingWelcome(true); }}>Edit</button>
                )}
              </div>
              {editingWelcome ? (
                <div>
                  <textarea
                    className="field-input"
                    rows={3}
                    value={welcomeDraft}
                    onChange={(e) => setWelcomeDraft(e.target.value)}
                    placeholder="e.g. Thank you for taking part in this study. Your answers will help us improve our product."
                    style={{ resize: "vertical" }}
                  />
                  <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                    <button className="btn btn-primary btn-sm" onClick={() => saveProjectMeta({ welcome_message: welcomeDraft })} disabled={savingMeta}>{savingMeta ? "Saving…" : "Save"}</button>
                    <button className="btn btn-ghost btn-sm" onClick={() => setEditingWelcome(false)}>Cancel</button>
                  </div>
                </div>
              ) : (
                <p className="objective-text" style={{ color: project.welcome_message ? undefined : "var(--text-muted)", fontStyle: project.welcome_message ? undefined : "italic" }}>
                  {project.welcome_message || "No welcome message — click Edit to add one."}
                </p>
              )}
            </section>
            <section className="detail-section">
              <div className="section-header-row">
                <h2>Interview Link</h2>
                <button className="btn btn-primary btn-sm" onClick={handleGenerateLink}>+ New Link</button>
              </div>
              {links.length === 0 ? (
                <p className="muted-text">No links yet. Generate one to share with participants.</p>
              ) : (
                <div className="links-list">
                  {links.map((l) => (
                    <div key={l.id} className={`link-row${l.is_active ? "" : " link-row--inactive"}`}>
                      <div className="link-row-main">
                        <span className={`link-status-badge ${l.is_active ? "link-status-badge--active" : "link-status-badge--inactive"}`}>
                          {l.is_active ? "Active" : "Inactive"}
                        </span>
                        <code className="link-url" style={{ wordBreak: "break-all" }}>{interviewUrl(l.token)}</code>
                      </div>
                      <div className="link-row-actions">
                        {l.is_active && (
                          <button className="btn btn-ghost btn-sm" onClick={() => copyLink(l.token)}>
                            {copiedToken === l.token ? "✓ Copied!" : "Copy"}
                          </button>
                        )}
                        <button
                          className={`btn btn-sm ${l.is_active ? "btn-ghost" : "btn-secondary"}`}
                          onClick={() => handleToggleLink(l.id)}
                        >
                          {l.is_active ? "Deactivate" : "Activate"}
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
                  <h2>Screening Questions</h2>
                  <p className="muted-text" style={{ fontSize: 13, marginTop: 2 }}>Asked before the interview — disqualifying answers block access.</p>
                </div>
                {!editingScreening && <button className="btn btn-ghost btn-sm" onClick={startEditScreening}>Edit</button>}
              </div>

              {!editingScreening && (
                (project.screening_questions ?? []).length === 0 ? (
                  <div className="empty-state-inline">
                    <span>No screening questions.</span>
                    <button className="btn btn-ghost btn-sm" onClick={startEditScreening}>Add one →</button>
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
                          {sq.question || <em className="muted-text">Empty question</em>}
                        </span>
                        {sq.disqualifying_options.length > 0 && (
                          <span className="badge" style={{ marginRight: 8, background: "#fef2f2", color: "#dc2626", fontSize: 11 }}>
                            {sq.disqualifying_options.length} disqualifying
                          </span>
                        )}
                        <span className="guide-editor-chevron">{expandedSQ === sqIdx ? "▲" : "▼"}</span>
                      </div>
                      {expandedSQ === sqIdx && (
                        <div className="guide-editor-body">
                          <label className="field-label">Question</label>
                          <input className="field-input" value={sq.question} onChange={(e) => sqSetQuestion(sqIdx, e.target.value)} placeholder="e.g. Do you shop online at least once a month?" />
                          <label className="field-label" style={{ marginTop: 12 }}>Options <span className="optional-tag">— click ✕/✓ to mark disqualifying</span></label>
                          {sq.options.map((opt, optIdx) => (
                            <div key={optIdx} style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}>
                              <button style={{ width: 28, height: 28, flexShrink: 0, borderRadius: 6, border: "1.5px solid", borderColor: sq.disqualifying_options.includes(opt) ? "#dc2626" : "#d1d5db", background: sq.disqualifying_options.includes(opt) ? "#fef2f2" : "#fff", color: sq.disqualifying_options.includes(opt) ? "#dc2626" : "#9ca3af", cursor: "pointer", fontWeight: 700, fontSize: 14 }} onClick={() => opt.trim() && sqToggleDisq(sqIdx, opt)}>
                                {sq.disqualifying_options.includes(opt) ? "✕" : "✓"}
                              </button>
                              <input className="field-input" style={{ flex: 1, marginBottom: 0 }} value={opt} onChange={(e) => sqSetOption(sqIdx, optIdx, e.target.value)} placeholder={`Option ${optIdx + 1}`} />
                              {sq.options.length > 1 && <button style={{ background: "none", border: "none", color: "#9ca3af", cursor: "pointer", fontSize: 18, padding: "0 4px" }} onClick={() => sqRemoveOption(sqIdx, optIdx)}>×</button>}
                            </div>
                          ))}
                          <button className="btn btn-ghost btn-sm" onClick={() => sqAddOption(sqIdx)}>+ Add option</button>
                          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}>
                            <button className="btn btn-ghost btn-sm btn-danger-text" onClick={() => sqRemove(sqIdx)}>Remove question</button>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                  <button className="btn btn-ghost btn-sm" onClick={sqAddQuestion} style={{ marginBottom: 16 }}>+ Add screening question</button>
                  <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                    <button className="btn btn-ghost btn-sm" onClick={() => setEditingScreening(false)}>Cancel</button>
                    <button className="btn btn-primary btn-sm" onClick={saveScreening} disabled={screeningSaving}>{screeningSaving ? "Saving..." : "Save"}</button>
                  </div>
                </div>
              )}
            </section>

            {/* Panel Collection */}
            <section className="detail-section">
              <div className="section-header-row" style={{ alignItems: "center" }}>
                <div>
                  <h2>Participant panel collection</h2>
                  <p className="muted-text" style={{ fontSize: 13, marginTop: 2 }}>
                    When enabled, verified participants are invited to join the QualiPulse research community after their interview.
                  </p>
                </div>
                <label
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    cursor: savingPanelToggle ? "not-allowed" : "pointer",
                    flexShrink: 0,
                  }}
                >
                  <div
                    role="switch"
                    aria-checked={(project?.panel_collection_enabled ?? true)}
                    tabIndex={0}
                    style={{
                      position: "relative",
                      width: 40,
                      height: 22,
                      borderRadius: 11,
                      background: (project?.panel_collection_enabled ?? true) ? "#4f46e5" : "#d1d5db",
                      transition: "background 0.2s",
                      opacity: savingPanelToggle ? 0.6 : 1,
                      cursor: savingPanelToggle ? "not-allowed" : "pointer",
                    }}
                    onClick={() => !savingPanelToggle && handlePanelToggle(!(project?.panel_collection_enabled ?? true))}
                    onKeyDown={(e) => { if ((e.key === "Enter" || e.key === " ") && !savingPanelToggle) { e.preventDefault(); handlePanelToggle(!(project?.panel_collection_enabled ?? true)); } }}
                  >
                    <div
                      style={{
                        position: "absolute",
                        top: 3,
                        left: (project?.panel_collection_enabled ?? true) ? 21 : 3,
                        width: 16,
                        height: 16,
                        borderRadius: "50%",
                        background: "#fff",
                        transition: "left 0.2s",
                        boxShadow: "0 1px 3px rgba(0,0,0,0.2)",
                      }}
                    />
                  </div>
                  <span style={{ fontSize: 13, color: "var(--text-secondary, #6b7280)" }}>
                    {(project?.panel_collection_enabled ?? true) ? "On" : "Off"}
                  </span>
                </label>
              </div>
            </section>

            <section className="detail-section">
              <div className="section-header-row">
                <div>
                  <h2>Interview Guide</h2>
                  <p className="muted-text" style={{ fontSize: 13, marginTop: 2 }}>
                    {project.questions.filter((q) => !q.deprecated_at).length} active question{project.questions.filter((q) => !q.deprecated_at).length !== 1 ? "s" : ""} across {Object.keys(sections).length} section{Object.keys(sections).length !== 1 ? "s" : ""}
                    {project.questions.some((q) => q.deprecated_at) && (
                      <span className="badge" style={{ marginLeft: 8, background: "var(--danger-bg, #fef2f2)", color: "var(--danger, #dc2626)" }}>
                        {project.questions.filter((q) => q.deprecated_at).length} disabled
                      </span>
                    )}
                  </p>
                </div>
                <button className="btn btn-ghost btn-sm" onClick={() => navigate(`/projects/${id}/edit`)}>Add Questions</button>
              </div>
              {project.questions.length === 0 ? (
                <p className="muted-text">No questions defined yet. <button className="btn btn-primary btn-sm" onClick={() => navigate(`/projects/${id}/edit`)}>Create interview guide</button></p>
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
                                className="guide-question-card"
                                style={{
                                  padding: "12px 14px",
                                  marginBottom: 8,
                                  borderRadius: 8,
                                  border: isEditing ? "1.5px solid var(--primary, #6366f1)" : "1px solid var(--border, #e5e7eb)",
                                  background: isEditing ? "var(--bg-surface-hover, #f8f9fc)" : "white",
                                  transition: "border-color 0.15s, background 0.15s",
                                }}
                              >
                                <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
                                  {/* Reorder arrows */}
                                  <div style={{ display: "flex", flexDirection: "column", gap: 2, flexShrink: 0, marginTop: 2 }}>
                                    <button
                                      className="btn btn-ghost btn-xs"
                                      style={{ padding: "0 4px", fontSize: 10, color: isFirst ? "var(--border, #e5e7eb)" : "var(--text-muted, #9ca3af)", lineHeight: 1 }}
                                      disabled={isFirst}
                                      onClick={() => moveQuestion(q.id, "up")}
                                      title="Move up"
                                    >▲</button>
                                    <button
                                      className="btn btn-ghost btn-xs"
                                      style={{ padding: "0 4px", fontSize: 10, color: isLast ? "var(--border, #e5e7eb)" : "var(--text-muted, #9ca3af)", lineHeight: 1 }}
                                      disabled={isLast}
                                      onClick={() => moveQuestion(q.id, "down")}
                                      title="Move down"
                                    >▼</button>
                                  </div>

                                  {/* Question text — click to edit */}
                                  <div style={{ flex: 1, minWidth: 0 }}>
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
                                          <button className="btn btn-primary btn-xs" onClick={() => saveQuestionText(q.id)} disabled={savingQuestionId === q.id}>{savingQuestionId === q.id ? "Saving..." : "Save"}</button>
                                          <button className="btn btn-ghost btn-xs" onClick={() => setEditingQuestionId(null)}>Cancel</button>
                                        </div>
                                      </div>
                                    ) : (
                                      <span
                                        style={{ color: "var(--text, #111827)", cursor: "pointer", display: "block" }}
                                        onClick={() => { setEditingQuestionId(q.id); setQuestionDraft(q.main_question); }}
                                        title="Click to edit"
                                      >
                                        <span style={{ color: "var(--text-muted, #9ca3af)", fontSize: 12, marginRight: 6 }}>Q{qi + 1}</span>
                                        {q.main_question}
                                      </span>
                                    )}
                                  </div>

                                  {/* Action buttons */}
                                  {!isEditing && (
                                    <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
                                      <button
                                        className="btn btn-ghost btn-xs"
                                        title={q.researcher_notes ? "Edit note" : "Add note"}
                                        style={{ color: q.researcher_notes ? "#d97706" : "var(--text-muted, #9ca3af)" }}
                                        onClick={() => {
                                          if (editingNoteId === q.id) { setEditingNoteId(null); }
                                          else { setEditingNoteId(q.id); setNoteText(q.researcher_notes ?? ""); }
                                        }}
                                      >
                                        {q.researcher_notes ? "📝" : "Note"}
                                      </button>
                                      <button
                                        className="btn btn-ghost btn-xs"
                                        style={{ color: "var(--text-muted, #9ca3af)" }}
                                        onClick={() => setExpandedQuestionId(expandedQuestionId === q.id ? null : q.id)}
                                        title="Interview notes & desired learning"
                                      >
                                        {expandedQuestionId === q.id ? "▲" : "▼"}
                                      </button>
                                      <button
                                        className="btn btn-ghost btn-xs"
                                        title="Disable question"
                                        style={{ color: "var(--text-muted, #9ca3af)" }}
                                        onClick={() => toggleDeprecateQuestion(q.id, q.deprecated_at)}
                                      >
                                        ✕
                                      </button>
                                    </div>
                                  )}
                                </div>

                                {/* Researcher note display */}
                                {editingNoteId === q.id && (
                                  <div style={{ marginTop: 8, marginLeft: 28 }}>
                                    <textarea
                                      className="field-input"
                                      value={noteText}
                                      onChange={(e) => setNoteText(e.target.value)}
                                      placeholder="Research notes, reminders, observations..."
                                      rows={2}
                                      style={{ width: "100%", marginBottom: 6, fontSize: 13 }}
                                      autoFocus
                                    />
                                    <div style={{ display: "flex", gap: 6 }}>
                                      <button className="btn btn-primary btn-xs" onClick={() => saveQuestionNote(q.id)}>Save</button>
                                      <button className="btn btn-ghost btn-xs" onClick={() => setEditingNoteId(null)}>Cancel</button>
                                    </div>
                                  </div>
                                )}
                                {q.researcher_notes && editingNoteId !== q.id && (
                                  <div style={{ marginTop: 6, marginLeft: 28, padding: "4px 8px", background: "#fffbeb", borderRadius: 4, fontSize: 12, color: "#92400e" }}>
                                    📝 {q.researcher_notes}
                                  </div>
                                )}

                                {/* Interview notes + desired learning (expanded) */}
                                {expandedQuestionId === q.id && (
                                  <div style={{ marginTop: 8, marginLeft: 28, display: "flex", flexDirection: "column", gap: 8 }}>
                                    {(["interview_notes", "desired_learning"] as const).map((field) => {
                                      const label = field === "interview_notes" ? "Interview Tips" : "Desired Learning";
                                      const isFieldEditing = editingInterviewNotes?.id === q.id && editingInterviewNotes?.field === field;
                                      return (
                                        <div key={field} style={{ background: "var(--bg-surface, #f9fafb)", borderRadius: 6, padding: "8px 10px", border: "1px solid var(--border, #e5e7eb)" }}>
                                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                                            <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted, #6b7280)", textTransform: "uppercase" }}>{label}</span>
                                            {!isFieldEditing && (
                                              <button className="btn btn-ghost btn-xs" style={{ fontSize: 10 }} onClick={() => { setEditingInterviewNotes({ id: q.id, field }); setInterviewNotesText(q[field] ?? ""); }}>Edit</button>
                                            )}
                                          </div>
                                          {isFieldEditing ? (
                                            <>
                                              <textarea className="field-input" value={interviewNotesText} onChange={(e) => setInterviewNotesText(e.target.value)} rows={2} style={{ width: "100%", fontSize: 12, marginBottom: 4 }} autoFocus />
                                              <div style={{ display: "flex", gap: 4 }}>
                                                <button className="btn btn-primary btn-xs" onClick={() => saveInterviewNotes(q.id, field)}>Save</button>
                                                <button className="btn btn-ghost btn-xs" onClick={() => setEditingInterviewNotes(null)}>Cancel</button>
                                              </div>
                                            </>
                                          ) : (
                                            <p style={{ fontSize: 12, color: "var(--text-secondary, #374151)", margin: 0 }}>{q[field] || <em className="muted-text">None — click Edit to add</em>}</p>
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
                      <summary style={{ cursor: "pointer", fontSize: 13, color: "var(--text-muted, #6b7280)", userSelect: "none" }}>
                        {project.questions.filter((q) => q.deprecated_at).length} disabled question{project.questions.filter((q) => q.deprecated_at).length !== 1 ? "s" : ""}
                      </summary>
                      <div style={{ marginTop: 8 }}>
                        {project.questions.filter((q) => q.deprecated_at).sort((a, b) => a.section_index - b.section_index || a.question_index - b.question_index).map((q) => (
                          <div key={q.id} style={{ padding: "8px 12px", marginBottom: 6, borderRadius: 6, border: "1px solid var(--border, #e5e7eb)", background: "var(--bg-surface, #f9fafb)", opacity: 0.7 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                              <s style={{ flex: 1, color: "var(--text-muted, #9ca3af)", fontSize: 14 }}>{q.main_question}</s>
                              <button
                                className="btn btn-ghost btn-xs"
                                style={{ color: "var(--primary, #6366f1)", flexShrink: 0 }}
                                onClick={() => toggleDeprecateQuestion(q.id, q.deprecated_at)}
                              >
                                Re-enable
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </details>
                  )}
                </>
              )}
            </section>

            {/* System Prompt — Advanced accordion */}
            <section className="detail-section">
              <div className="advanced-accordion">
                <button
                  className="advanced-accordion-toggle"
                  onClick={() => setAdvancedPromptOpen((o) => !o)}
                  aria-expanded={advancedPromptOpen}
                >
                  <span>⚙ Advanced — AI Interviewer Prompt</span>
                  <span style={{ fontSize: "0.8rem" }}>{advancedPromptOpen ? "▲" : "▼"}</span>
                </button>
                {advancedPromptOpen && (
                  <div className="advanced-accordion-body">
                    <div className="advanced-warning">
                      ⚠ Changes here affect all future interviews on this project and cannot be applied retroactively to completed sessions.
                    </div>
                    <p className="muted-text" style={{ fontSize: 13, marginBottom: 8 }}>
                      Customize how the AI interviewer behaves. Leave blank to use the default prompt.{" "}
                      {!editingSystemPrompt && !project.system_prompt && (
                        <span style={{ color: "var(--text-tertiary)" }}>Currently using default.</span>
                      )}
                    </p>
                    <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
                      {!editingSystemPrompt && (
                        <button className="btn btn-ghost btn-sm" onClick={() => { setSystemPromptDraft(project.system_prompt ?? ""); setEditingSystemPrompt(true); }}>Edit</button>
                      )}
                    </div>
                    {editingSystemPrompt ? (
                      <>
                        <textarea
                          className="field-input"
                          value={systemPromptDraft}
                          onChange={(e) => setSystemPromptDraft(e.target.value)}
                          rows={8}
                          style={{ width: "100%", fontFamily: "monospace", fontSize: 13, marginBottom: 8 }}
                        />
                        <div style={{ display: "flex", gap: 6 }}>
                          <button className="btn btn-primary btn-sm" onClick={saveSystemPrompt} disabled={savingSystemPrompt}>{savingSystemPrompt ? "Saving…" : "Save"}</button>
                          <button className="btn btn-ghost btn-sm" onClick={() => setEditingSystemPrompt(false)}>Cancel</button>
                        </div>
                      </>
                    ) : (
                      <pre className="system-prompt-preview">{project.system_prompt || <em className="muted-text">No custom prompt — using default.</em>}</pre>
                    )}
                  </div>
                )}
              </div>
            </section>
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
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>Responses</span>
                </div>

                {/* Status filter pills */}
                <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
                  {(["all", "completed", "in_progress"] as const).map(f => {
                    const label = f === "all" ? `All (${participants.length})` : f === "completed" ? `Done (${completedCount})` : `In progress (${inProgressCount})`;
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
                    className="field-input"
                    value={responseSortBy}
                    onChange={e => setResponseSortBy(e.target.value as "date" | "quality" | "name")}
                    style={{ fontSize: 12, padding: "4px 8px", height: 30 }}
                  >
                    <option value="date">Newest first</option>
                    <option value="quality">By quality</option>
                    <option value="name">By name</option>
                  </select>
                </div>

                {loading ? (
                  <SkeletonTable rows={4} />
                ) : participants.length === 0 ? (
                  <div className="empty-state" style={{ padding: "32px 16px" }}>
                    <p style={{ fontWeight: 500 }}>No responses yet</p>
                    <p className="muted-text" style={{ fontSize: 12, marginTop: 4 }}>Share an interview link to get started.</p>
                    <button className="btn btn-ghost btn-sm" style={{ marginTop: 10 }} onClick={() => setTab("overview")}>Create interview link →</button>
                  </div>
                ) : filtered.length === 0 ? (
                  <div style={{ padding: "24px 0", textAlign: "center" }}>
                    <p className="muted-text" style={{ fontSize: 13 }}>No {responseStatusFilter === "completed" ? "completed" : "in-progress"} responses.</p>
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
                            <span className="participant-name" style={{ fontSize: 13, marginRight: 0 }}>{p.display_name || "Anonymous"}</span>
                            {p.status !== "completed" && (() => {
                              const ageMs = Date.now() - new Date(p.started_at).getTime();
                              const isRecent = ageMs < 2 * 60 * 60 * 1000; // < 2 hours
                              return (
                                <span className={`status-badge ${isRecent ? "status-progress" : ""}`}
                                  style={{ fontSize: 10, background: isRecent ? undefined : "var(--border-subtle)", color: isRecent ? undefined : "var(--text-tertiary)" }}>
                                  {isRecent ? "Live" : "In progress"}
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
                                {p.quality_label === "low" && "Low"}
                                {p.quality_label === "fair" && "Fair"}
                                {p.quality_label === "good" && "Good"}
                                {p.quality_label === "strong" && "Strong"}
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
                    {/* Back button — useful on mobile, also handy on desktop */}
                    <button
                      onClick={() => setSelectedParticipant(null)}
                      style={{
                        background: "none",
                        border: "none",
                        color: "var(--primary)",
                        fontSize: "14px",
                        cursor: "pointer",
                        padding: "8px 0",
                        marginBottom: "8px",
                      }}
                      className="responses-back-btn"
                    >
                      ← Back to participants
                    </button>

                    {/* Transcript header */}
                    <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 16, position: "sticky", top: 0, zIndex: 10, background: "var(--bg-surface)", paddingBottom: "12px", borderBottom: "1px solid var(--border)" }}>
                      <div>
                        <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>{selectedParticipant.display_name || "Anonymous"}</h2>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                          {selectedParticipant.profession && <span className="badge">{selectedParticipant.profession}</span>}
                          {selectedParticipant.age_range && <span className="badge">{selectedParticipant.age_range}</span>}
                          {selectedParticipant.country && <span className="badge">{selectedParticipant.country}</span>}
                          <span className="participant-date" style={{ fontSize: 12 }}>{new Date(selectedParticipant.started_at).toLocaleString()}</span>
                        </div>
                      </div>
                      <button className="btn btn-ghost btn-sm" onClick={() => { setTranscript(null); setSelectedParticipant(null); setSelectionInfo(null); }}>Close</button>
                    </div>

                    {/* AI Quality Assessment */}
                    <div style={{ marginBottom: 16 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: qualityAssessment ? 12 : 0 }}>
                        {selectedParticipant.quality_label && (
                          <span className={`quality-badge quality-badge--${selectedParticipant.quality_label}`}>
                            {selectedParticipant.quality_label === "low" && "⚠ Low quality"}
                            {selectedParticipant.quality_label === "fair" && "◑ Fair quality"}
                            {selectedParticipant.quality_label === "good" && "● Good quality"}
                            {selectedParticipant.quality_label === "strong" && "★ Strong quality"}
                          </span>
                        )}
                        <button className="btn btn-ai btn-sm" onClick={handleAssessQuality} disabled={loadingQuality}>
                          {loadingQuality ? "Assessing…" : qualityAssessment ? "✦ Re-assess" : "✦ AI Quality Check"}
                        </button>
                        {qualityAssessment && (
                          <button className="btn btn-ghost btn-xs" onClick={() => setQualityAssessment(null)}>Hide</button>
                        )}
                      </div>
                      {qualityAssessment && (
                        <div className="quality-panel">
                          <div className="quality-panel-header">
                            <span className={`quality-badge quality-badge--${qualityAssessment.quality_label} quality-badge--lg`}>
                              {qualityAssessment.quality_label === "low" && "⚠ Low quality"}
                              {qualityAssessment.quality_label === "fair" && "◑ Fair quality"}
                              {qualityAssessment.quality_label === "good" && "● Good quality"}
                              {qualityAssessment.quality_label === "strong" && "★ Strong quality"}
                            </span>
                            <div className="quality-stats">
                              <span>~{qualityAssessment.avg_response_words} words/answer</span>
                              <span>{qualityAssessment.short_answer_pct}% short answers</span>
                            </div>
                          </div>
                          <p className="quality-summary">{qualityAssessment.summary}</p>
                          {qualityAssessment.strengths.length > 0 && (
                            <div className="quality-points quality-points--good">
                              <strong>Strengths</strong>
                              <ul>{qualityAssessment.strengths.map((s, i) => <li key={i}>{s}</li>)}</ul>
                            </div>
                          )}
                          {qualityAssessment.issues.length > 0 && (
                            <div className="quality-points quality-points--warn">
                              <strong>Issues</strong>
                              <ul>{qualityAssessment.issues.map((s, i) => <li key={i}>{s}</li>)}</ul>
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Codebook (inline, collapsible) */}
                    <div style={{ marginBottom: 16 }}>
                      <button className="btn btn-ghost btn-xs" onClick={() => setShowCodebookPersist(!showCodebook)} style={{ marginBottom: showCodebook ? 8 : 0 }}>
                        {showCodebook ? "▲" : "▼"} Codebook ({codes.length})
                      </button>
                      {showCodebook && (
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                          {codes.length === 0 ? (
                            <p className="muted-text" style={{ fontSize: 12 }}>No codes yet. Select text to create one.</p>
                          ) : codes.map((c) => (
                            <div key={c.id} style={{ display: "flex", alignItems: "center", gap: 5, padding: "3px 10px", borderRadius: 20, background: `${c.color}22`, border: `1.5px solid ${c.color}`, fontSize: 12 }}>
                              <span style={{ width: 8, height: 8, borderRadius: "50%", background: c.color, display: "inline-block", flexShrink: 0 }} />
                              {renamingCodeId === c.id ? (
                                <>
                                  <input autoFocus value={renameText} onChange={(e) => setRenameText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") handleRenameCode(c.id); if (e.key === "Escape") setRenamingCodeId(null); }} style={{ border: "none", background: "transparent", outline: "none", fontSize: 12, width: Math.max(60, renameText.length * 8) }} />
                                  <button style={{ background: "none", border: "none", cursor: "pointer", color: "#6366f1", padding: 0, fontSize: 11 }} onClick={() => handleRenameCode(c.id)} title="Save">✓</button>
                                  <button style={{ background: "none", border: "none", cursor: "pointer", color: "#9ca3af", padding: 0, fontSize: 11 }} onClick={() => setRenamingCodeId(null)} title="Cancel">✕</button>
                                </>
                              ) : (
                                <>
                                  <span title="Double-click to rename" onDoubleClick={() => { setRenamingCodeId(c.id); setRenameText(c.name); }} style={{ cursor: "text" }}>{c.name}</span>
                                  <span className="muted-text" style={{ fontSize: 10 }}>({c.tag_count})</span>
                                  <button style={{ background: "none", border: "none", cursor: "pointer", color: "#9ca3af", padding: 0, fontSize: 10 }} onClick={() => { setRenamingCodeId(c.id); setRenameText(c.name); }} title="Rename">✎</button>
                                  <button style={{ background: "none", border: "none", cursor: "pointer", color: "#9ca3af", padding: 0, fontSize: 13 }} onClick={() => handleDeleteCode(c.id)} title="Delete code">×</button>
                                </>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Quote tagging instruction */}
                    <div className="quote-tag-instruction" style={{ marginBottom: 16 }}>
                      <span>💬</span>
                      <span>Select any text in an answer to tag it with a code.</span>
                    </div>

                    {/* Transcript turns */}
                    {transcript.length === 0 ? (
                      <p className="muted-text">No transcript available.</p>
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
                                <strong>Q:</strong> {t.question_text}
                                {t.tts_audio_url && (
                                  <audio controls src={t.tts_audio_url} className="transcript-audio" aria-label={`AI question audio — turn ${t.turn_index}`} />
                                )}
                              </div>
                              {t.response_transcript && editingTurnId === t.id ? (
                                <div style={{ marginTop: 6 }}>
                                  <textarea className="field-input" value={editingText} onChange={(e) => setEditingText(e.target.value)} rows={4} style={{ width: "100%", marginBottom: 6 }} autoFocus />
                                  <div style={{ display: "flex", gap: 6 }}>
                                    <button className="btn btn-primary btn-xs" disabled={savingTurnId === t.id} onClick={() => saveEditTurn(t)}>
                                      {savingTurnId === t.id ? "Saving..." : "Save"}
                                    </button>
                                    <button className="btn btn-ghost btn-xs" onClick={() => {
                                      if (editingText !== editingOriginalText && !confirm("Discard changes?")) return;
                                      setEditingTurnId(null);
                                    }}>Cancel</button>
                                  </div>
                                </div>
                              ) : t.response_transcript ? (
                                <div className="transcript-a" onMouseUp={() => handleTranscriptMouseUp(t.id)} style={{ userSelect: "text" }}>
                                  <strong>A:</strong>{" "}
                                  {isHighlighted && highlightTarget
                                    ? renderWithQuoteHighlight(t.response_transcript, highlightTarget.quoteText, t.id)
                                    : renderTaggedText(t.response_transcript, t.id)}
                                  <span style={{ display: "inline-flex", gap: 4, marginLeft: 8, verticalAlign: "middle" }}>
                                    <button className="btn btn-ghost btn-xs" style={{ fontSize: 10 }} onClick={() => startEditTurn(t)}>Edit</button>
                                    {t.manually_edited && (
                                      <span className="badge" style={{ fontSize: 10, background: "#fef9c3", color: "#854d0e" }}>edited</span>
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
                                    <span key={tg.id} style={{ padding: "2px 8px", borderRadius: 10, fontSize: 11, background: `${tg.code_color || "#6366f1"}22`, border: `1px solid ${tg.code_color || "#6366f1"}`, cursor: "pointer" }} title="Click to remove tag" onClick={() => handleDeleteTag(tg.id)}>
                                      {tg.code_name}
                                    </span>
                                  ))}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", minHeight: 300, color: "var(--text-tertiary)" }}>
                    <div style={{ fontSize: 40, marginBottom: 12, opacity: 0.25 }}>📋</div>
                    <p style={{ fontWeight: 500, fontSize: 14, marginBottom: 4, color: "var(--text-secondary)" }}>No response selected</p>
                    <p style={{ fontSize: 13 }}>Choose a participant from the list to view their transcript</p>
                  </div>
                )}
              </div>
            </div>

            {/* Floating tag popup */}
            {selectionInfo && (
              <div style={{ position: "fixed", left: selectionInfo.x - 90, top: selectionInfo.y, zIndex: 1000, background: "white", border: "1px solid #e5e7eb", borderRadius: 8, boxShadow: "0 4px 12px rgba(0,0,0,0.15)", padding: 8, minWidth: 180 }}>
                {!showNewCode ? (
                  <div>
                    <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 6 }}>Tag as:</div>
                    {codes.map((c) => (
                      <button key={c.id} style={{ display: "flex", alignItems: "center", gap: 6, width: "100%", padding: "4px 8px", border: "none", background: "none", cursor: "pointer", borderRadius: 4, fontSize: 13, textAlign: "left" }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = "#f3f4f6")}
                        onMouseLeave={(e) => (e.currentTarget.style.background = "none")}
                        onClick={() => handleTagWithCode(c)}
                      >
                        <span style={{ width: 10, height: 10, borderRadius: "50%", background: c.color, flexShrink: 0 }} />
                        {c.name}
                      </button>
                    ))}
                    <div style={{ borderTop: "1px solid #f3f4f6", marginTop: 4, paddingTop: 4 }}>
                      <button className="btn btn-ghost btn-xs" style={{ width: "100%" }} onClick={() => setShowNewCode(true)}>+ New code</button>
                      <button className="btn btn-ghost btn-xs" style={{ width: "100%", color: "#9ca3af" }} onClick={() => { setSelectionInfo(null); window.getSelection()?.removeAllRanges(); }}>Cancel</button>
                    </div>
                  </div>
                ) : (
                  <div>
                    <input className="field-input" placeholder="Code name" value={newCodeName} onChange={(e) => setNewCodeName(e.target.value)} style={{ marginBottom: 6, fontSize: 13 }} autoFocus />
                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 8 }}>
                      {PRESET_COLORS.map((col) => (
                        <div key={col} style={{ width: 20, height: 20, borderRadius: "50%", background: col, cursor: "pointer", border: newCodeColor === col ? "2px solid #111" : "2px solid transparent" }} onClick={() => setNewCodeColor(col)} />
                      ))}
                    </div>
                    <div style={{ display: "flex", gap: 4 }}>
                      <button className="btn btn-primary btn-xs" disabled={!newCodeName.trim() || creatingCode} onClick={handleCreateAndTag}>{creatingCode ? "..." : "Create & Tag"}</button>
                      <button className="btn btn-ghost btn-xs" onClick={() => setShowNewCode(false)}>Back</button>
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
                  ⚠ {analysis.completed_count - analysis.participant_count} new response{analysis.completed_count - analysis.participant_count > 1 ? "s" : ""} since last analysis — regenerate to include them.
                </div>
              )}
              <div className="section-header-row">
                <h2>AI Analysis</h2>
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                  {analysis.report && (
                    <>
                      <button className="btn btn-ghost btn-sm" onClick={handleCopyMarkdown}>
                        {exportCopied ? "✓ Copied" : "Copy MD"}
                      </button>
                      <button className="btn btn-ghost btn-sm" onClick={handleDownloadJSON}>
                        ↓ JSON
                      </button>
                      <button className="btn btn-ghost btn-sm" onClick={handleShareAnalysis}>
                        🔗 Share
                      </button>
                    </>
                  )}
                  {analysis.completed_count > 0 && (
                    <button className="btn btn-ai btn-sm" onClick={handleTriggerAnalysis} disabled={analysis.status === "generating"}>
                      {analysis.status === "generating" ? "Analysing..." : analysis.status === "none" ? "✦ Generate" : "✦ Regenerate"}
                    </button>
                  )}
                </div>
              </div>

              {/* P2: Filter panel */}
              {hasFilterOptions && (
                <div style={{ marginBottom: 16 }}>
                  <button className="btn btn-ghost btn-sm" onClick={() => setFiltersExpanded(!filtersExpanded)} style={{ marginBottom: 6 }}>
                    {filtersExpanded ? "▲" : "▼"} Filter by segment
                    {activeFilterValues.length > 0 && <span className="badge" style={{ marginLeft: 4 }}>{activeFilterValues.length} active</span>}
                  </button>
                  {filtersExpanded && (
                    <div style={{ padding: 12, border: "1px solid #e5e7eb", borderRadius: 8, background: "#f9fafb" }}>
                      {Object.entries(filterOptions).map(([attr, values]) => (
                        <div key={attr} style={{ marginBottom: 10 }}>
                          <div style={{ fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 4, textTransform: "capitalize" }}>{attr.replace("_", " ")}</div>
                          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                            {values.map((val) => {
                              const active = activeFilterBy === attr && activeFilterValues.includes(val);
                              return (
                                <label key={val} style={{ display: "flex", alignItems: "center", gap: 4, padding: "2px 8px", borderRadius: 10, fontSize: 12, border: `1px solid ${active ? "#6366f1" : "#e5e7eb"}`, background: active ? "#eef2ff" : "white", cursor: "pointer" }}>
                                  <input type="checkbox" checked={active} onChange={() => toggleFilterValue(attr, val)} style={{ width: 12, height: 12 }} />
                                  {val}
                                </label>
                              );
                            })}
                          </div>
                        </div>
                      ))}
                      {activeFilterValues.length > 0 && (
                        <button className="btn btn-ghost btn-xs" onClick={() => { setActiveFilterBy(""); setActiveFilterValues([]); }} style={{ marginTop: 4 }}>Clear filters</button>
                      )}
                    </div>
                  )}
                  {analysis.filters && (
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8, marginTop: 6 }}>
                      <span style={{ fontSize: 12, color: "#6b7280" }}>Filtered by:</span>
                      {analysis.filters.filter_values.map((v) => (
                        <span key={v} className="badge" style={{ background: "#eef2ff", color: "#4338ca" }}>{analysis.filters!.filter_by}: {v}</span>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {analysis.status === "none" && analysis.completed_count === 0 && (
                <div className="empty-state">
                  <p style={{ fontWeight: 500 }}>Collect responses first</p>
                  <p className="muted-text" style={{ fontSize: 13 }}>Complete at least one interview to generate an analysis.</p>
                  <button className="btn btn-ghost btn-sm" style={{ marginTop: 10 }} onClick={() => setTab("responses")}>Go to Responses →</button>
                </div>
              )}
              {analysis.status === "none" && analysis.completed_count > 0 && (
                <p className="muted-text">{analysis.completed_count} completed interview{analysis.completed_count > 1 ? "s" : ""} ready to analyse.</p>
              )}
              {analysis.status === "generating" && (
                <div className="analysis-generating"><span className="spinner-sm" /><span>Claude is reading {analysis.participant_count} interview{analysis.participant_count !== 1 ? "s" : ""}...</span></div>
              )}
              {analysis.status === "failed" && (
                <div style={{ padding: "16px", borderRadius: 8, background: "#fef2f2", border: "1px solid #fecaca", display: "flex", alignItems: "flex-start", gap: 12 }}>
                  <span style={{ fontSize: 18 }}>⚠</span>
                  <div>
                    <p style={{ fontWeight: 600, color: "#991b1b", marginBottom: 4 }}>Analysis couldn't complete</p>
                    <p style={{ color: "#b91c1c", fontSize: 13, marginBottom: 10 }}>
                      {analysis.error?.includes("timed out") ? "The analysis timed out — your dataset may be too large. Try filtering to a smaller group first." :
                       analysis.error?.includes("No completed") ? "No completed interviews to analyse yet." :
                       "Something went wrong on our end. Please try again."}
                    </p>
                    <button className="btn btn-sm" style={{ background: "#991b1b", color: "#fff" }} onClick={handleTriggerAnalysis}>
                      Retry analysis
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
                    <h3 style={{ fontSize: "14px", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "8px", textTransform: "uppercase", letterSpacing: "0.5px" }}>Summary</h3>
                    <div className="analysis-summary">{r.summary}</div>
                    <div className="analysis-meta">
                      <span className="badge analysis-ai-badge">
                        {isViewingPastVersion
                          ? (activeVersionReport!.version_label === "researcher_refined" ? "✦ Researcher-refined" : "✦ AI-generated")
                          : (analysis.version_label === "researcher_refined" ? "✦ Researcher-refined" : "✦ AI-generated")}
                      </span>
                      <span className="badge">n={r.participant_count} interview{r.participant_count !== 1 ? "s" : ""}</span>
                      <span
                        className="badge"
                        title="Confidence reflects sample size, response depth, and thematic saturation. Low = &lt;5 interviews or very short responses. High = 10+ rich interviews with consistent themes."
                        style={{ cursor: "help", textDecoration: "underline dotted" }}
                      >
                        {r.confidence} confidence
                      </span>
                      {(isViewingPastVersion ? activeVersionReport!.filters : analysis.filters) && (
                        <span className="badge" style={{ background: "#eef2ff", color: "#4338ca" }}>
                          Filtered: {(isViewingPastVersion ? activeVersionReport!.filters : analysis.filters)!.filter_by} ({(isViewingPastVersion ? activeVersionReport!.filters : analysis.filters)!.filter_values.join(", ")})
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
                            ? "Researcher-refined"
                            : "AI Discovery";
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
                                <span style={{ marginLeft: 4, fontSize: 10, color: "var(--text-tertiary)" }}>{v.annotation_count} ann.</span>
                              )}
                            </button>
                          );
                        })}
                      </div>
                    )}

                    {/* Past version banner */}
                    {isViewingPastVersion && (
                      <div className="version-banner">
                        Viewing v{activeVersionNumber} — {activeVersionReport!.version_label === "researcher_refined" ? "Researcher-refined" : "AI Discovery"}.{" "}
                        <button
                          className="btn btn-ghost btn-xs"
                          onClick={() => { setActiveVersionNumber(null); setActiveVersionReport(null); }}
                          style={{ color: "var(--brand-600)", padding: "0 4px" }}
                        >
                          Switch to v{latestVersionNum} (latest)
                        </button>
                      </div>
                    )}

                    {/* Themes */}
                    {r.themes.length > 0 && (
                      <div className="analysis-block">
                        <h3>Key Themes ({r.themes.length})</h3>
                        {r.themes.map((t, i) => {
                          const ann = themeAnnotations[t.title];
                          const showNoteInput = !isViewingPastVersion && ann && (ann.status === "disputed" || ann.status === "needs_evidence");
                          return (
                            <div key={i} className="analysis-theme">
                              <div className="analysis-theme-header" style={{ flexWrap: "wrap" }}>
                                <strong>{t.title}{t.quotes.length > 0 && <span className="analysis-quote-count">{t.quotes.length} quote{t.quotes.length !== 1 ? "s" : ""}</span>}</strong>
                                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                                  <span className="badge">{t.frequency}</span>
                                  {!isViewingPastVersion && (
                                    <>
                                      <button
                                        className={`annotation-btn annotation-btn--confirmed${ann?.status === "confirmed" ? " annotation-btn--active" : ""}`}
                                        title="Confirmed"
                                        aria-label="Confirmed"
                                        onClick={() => handleAnnotationClick(t.title, "confirmed")}
                                      >✓</button>
                                      <button
                                        className={`annotation-btn annotation-btn--needs-evidence${ann?.status === "needs_evidence" ? " annotation-btn--active" : ""}`}
                                        title="Needs evidence"
                                        aria-label="Needs evidence"
                                        onClick={() => handleAnnotationClick(t.title, "needs_evidence")}
                                      >−</button>
                                      <button
                                        className={`annotation-btn annotation-btn--disputed${ann?.status === "disputed" ? " annotation-btn--active" : ""}`}
                                        title="Disputed"
                                        aria-label="Disputed"
                                        onClick={() => handleAnnotationClick(t.title, "disputed")}
                                      >✕</button>
                                    </>
                                  )}
                                  <button className="btn btn-ghost btn-xs" style={{ color: "#d97706" }} onClick={() => { setAddingMemoKey(t.title); setNewMemoContent(""); }}>+ Note</button>
                                </div>
                              </div>
                              <p>{t.summary}</p>
                              {t.researcher_note && (
                                <p style={{ fontSize: 12, color: "var(--text-tertiary)", fontStyle: "italic", borderLeft: "3px solid var(--warning)", paddingLeft: 8, marginTop: 4 }}>
                                  Researcher note: {t.researcher_note}
                                </p>
                              )}
                              {showNoteInput && (
                                <textarea
                                  className="annotation-note-input"
                                  placeholder="Add a note for Claude (optional)"
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
                        <h3>Jobs to be Done ({r.jobs_to_be_done.length})</h3>
                        {r.jobs_to_be_done.map((j, i) => (
                          <div key={i} className="analysis-jtbd">
                            <div className="analysis-jtbd-job">"{j.job}"</div>
                            <p className="analysis-jtbd-insight">{j.insight}</p>
                            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                              <span className="badge">{j.frequency}</span>
                              <button className="btn btn-ghost btn-xs" style={{ color: "#d97706" }} onClick={() => { setAddingMemoKey(j.job); setNewMemoContent(""); }}>+ Note</button>
                            </div>
                            {renderMemoSection("jtbd_note", j.job)}
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Tensions */}
                    {r.tensions.length > 0 && (
                      <div className="analysis-block">
                        <h3>Tensions & Contradictions ({r.tensions.length})</h3>
                        {r.tensions.map((t, i) => (
                          <div key={i} className="analysis-tension">
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                              <strong>{t.tension}</strong>
                              <button className="btn btn-ghost btn-xs" style={{ color: "#d97706", flexShrink: 0 }} onClick={() => { setAddingMemoKey(t.tension); setNewMemoContent(""); }}>+ Note</button>
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
                        <h3>Recommendations</h3>
                        <ol className="analysis-recommendations">
                          {r.recommendations.map((rec, i) => <li key={i}>{rec}</li>)}
                        </ol>
                      </div>
                    )}

                    {/* General memos */}
                    <div className="analysis-block">
                      <h3>General Notes</h3>
                      {memos.filter((m) => m.linked_key === null && m.type === "general").map((m) => (
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
                      {addingMemoKey === "__general__" ? (
                        <div style={{ marginTop: 8 }}>
                          <textarea className="field-input" value={newMemoContent} onChange={(e) => setNewMemoContent(e.target.value)} placeholder="Add a project-wide note..." rows={3} style={{ width: "100%", marginBottom: 6 }} autoFocus />
                          <div style={{ display: "flex", gap: 6 }}>
                            <button className="btn btn-primary btn-xs" onClick={() => handleAddMemo("general", null)}>Save</button>
                            <button className="btn btn-ghost btn-xs" onClick={() => { setAddingMemoKey(null); setNewMemoContent(""); }}>Cancel</button>
                          </div>
                        </div>
                      ) : (
                        <button className="btn btn-ghost btn-sm" style={{ marginTop: 8, color: "#d97706" }} onClick={() => { setAddingMemoKey("__general__"); setNewMemoContent(""); }}>
                          + Add General Note
                        </button>
                      )}
                    </div>

                    {/* Researcher context + Refine */}
                    {!isViewingPastVersion && (
                      <div className="analysis-block">
                        <div className="researcher-context-box">
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                            <h3 style={{ margin: 0 }}>Researcher Context</h3>
                            <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
                              {contextSaving === "saving" ? "Saving…" : contextSaving === "saved" ? "Saved ✓" : ""}
                            </span>
                          </div>
                          <textarea
                            className="field-input"
                            rows={4}
                            value={researcherContext}
                            onChange={(e) => handleResearcherContextChange(e.target.value)}
                            placeholder="Add context Claude doesn't have from transcripts — industry norms, prior research, hypotheses, things to look for or avoid."
                            style={{ width: "100%", fontSize: 13, resize: "vertical" }}
                          />
                        </div>

                        <div style={{ marginTop: 12 }}>
                          {!refineModalOpen ? (
                            <button
                              className="btn btn-ai btn-sm"
                              disabled={!canRefine || refining}
                              onClick={() => setRefineModalOpen(true)}
                              title={!canRefine ? "Add disputed/needs-evidence annotations or researcher context first" : undefined}
                            >
                              ✦ Refine with my annotations
                            </button>
                          ) : (
                            <div className="refine-confirm-inline">
                              <p style={{ margin: "0 0 8px 0", fontSize: 13 }}>
                                Generate v{latestVersionNum + 1} based on your {annotationCount} annotation{annotationCount !== 1 ? "s" : ""}?
                                This won't overwrite v{latestVersionNum}.
                              </p>
                              <div style={{ display: "flex", gap: 8 }}>
                                <button
                                  className="btn btn-primary btn-sm"
                                  disabled={refining}
                                  onClick={handleTriggerRefine}
                                >
                                  {refining ? "Starting…" : "Confirm"}
                                </button>
                                <button
                                  className="btn btn-ghost btn-sm"
                                  onClick={() => setRefineModalOpen(false)}
                                >
                                  Cancel
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
                        <h3 style={{ margin: 0 }}>Segment Heatmap</h3>
                        <button className="btn btn-ghost btn-sm" onClick={() => { if (!heatmapExpanded) loadHeatmap(); else setHeatmapExpanded(false); }}>
                          {heatmapLoading ? "Loading..." : heatmapExpanded ? "Hide" : "Show"}
                        </button>
                      </div>
                      {heatmapExpanded && heatmap && (
                        <div style={{ overflowX: "auto" }}>
                          {heatmap.segments.length === 0 ? (
                            <p className="muted-text">No demographic segments found. Collect profession, age, or country data from participants to populate this view.</p>
                          ) : (
                            <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 12 }}>
                              <thead>
                                <tr>
                                  <th style={{ padding: "6px 10px", textAlign: "left", background: "#f9fafb", borderBottom: "1px solid #e5e7eb", minWidth: 160 }}>Theme</th>
                                  {heatmap.segments.map((seg) => (
                                    <th key={seg} style={{ padding: "6px 8px", textAlign: "center", background: "#f9fafb", borderBottom: "1px solid #e5e7eb", whiteSpace: "nowrap" }}>
                                      {seg.split(":")[1]}
                                      <div style={{ fontSize: 10, color: "#9ca3af", fontWeight: 400 }}>{seg.split(":")[0].replace("_", " ")}</div>
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {heatmap.themes.map((theme, ti) => (
                                  <tr key={ti}>
                                    <td style={{ padding: "6px 10px", borderBottom: "1px solid #f3f4f6", fontWeight: 500 }}>{theme.title}</td>
                                    {heatmap.segments.map((seg) => {
                                      const count = theme.segment_counts[seg] ?? 0;
                                      const segParticipants = heatmap.segment_participants[seg] ?? [];
                                      return (
                                        <td key={seg} style={{ padding: "6px 8px", textAlign: "center", borderBottom: "1px solid #f3f4f6", background: heatmapColor(count), cursor: count > 0 ? "help" : "default" }}
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
                Your project is live!
              </h2>
              <p className="welcome-modal-subtitle">
                Share this link and start collecting responses — your first insights could be in as soon as an hour.
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
                      {welcomeCopied ? "✓ Copied" : "Copy link"}
                    </button>
                  </div>

                  <div className="welcome-modal-share">
                    <a
                      href={mailtoLink}
                      className="btn btn-ghost welcome-modal-share-btn"
                    >
                      ✉ Send via email
                    </a>
                    <button
                      className="btn btn-ghost welcome-modal-share-btn"
                      type="button"
                      onClick={() => {
                        window.open(shareUrl, "_blank");
                      }}
                    >
                      ▶ Preview interview
                    </button>
                  </div>

                  <div className="welcome-modal-tips">
                    <strong>Pro tip:</strong> The first 3 participants are the most valuable. Aim to recruit from inside your existing network — teammates, recent customers, or community members — rather than cold outreach.
                  </div>
                </>
              ) : (
                <div className="welcome-modal-tips">
                  We couldn't auto-generate an interview link. Head to the Overview tab to create one manually.
                </div>
              )}

              <div className="welcome-modal-footer">
                <button className="btn btn-ghost" onClick={closeWelcome}>
                  I'll share later
                </button>
                <button
                  className="btn btn-primary"
                  onClick={() => {
                    setTab("overview");
                    closeWelcome();
                  }}
                >
                  Go to project
                </button>
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
}
