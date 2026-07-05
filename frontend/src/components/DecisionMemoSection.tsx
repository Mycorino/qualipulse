import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { StudySummary } from "../api/studies";
import {
  SynthesisSummary,
  createSynthesis,
  deleteSynthesis,
  fetchSynthesisMemoHtml,
  listSyntheses,
} from "../api/synthesis";
import { useToast } from "./Toast";

/**
 * DecisionMemoSection — cross-study synthesis on the Studies home.
 *
 * Shown once the workspace has ≥2 studies: the researcher picks the studies
 * (each needs a ready analysis — the server validates and names offenders),
 * optionally states the decision to inform, and gets a print-ready decision
 * memo synthesised across those studies' final analyses.
 */

const POLL_MS = 5000;

export function DecisionMemoSection({ studies }: { studies: StudySummary[] }) {
  const { t, i18n } = useTranslation("dashboard");
  const { toast } = useToast();
  const [memos, setMemos] = useState<SynthesisSummary[] | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [name, setName] = useState("");
  const [question, setQuestion] = useState("");
  const [creating, setCreating] = useState(false);
  const pollRef = useRef<number | null>(null);

  const refresh = useCallback(() => {
    listSyntheses()
      .then(setMemos)
      .catch(() => toast(t("decisionMemos.loadError"), "error"));
  }, [toast, t]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Poll while any memo is generating; stop as soon as none are.
  useEffect(() => {
    const anyGenerating = (memos ?? []).some((m) => m.status === "generating");
    if (anyGenerating && pollRef.current === null) {
      pollRef.current = window.setInterval(refresh, POLL_MS);
    } else if (!anyGenerating && pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current !== null) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [memos, refresh]);

  async function handleCreate() {
    if (selected.size < 2) return;
    setCreating(true);
    try {
      await createSynthesis({
        study_ids: Array.from(selected),
        name: name.trim() || undefined,
        decision_question: question.trim() || undefined,
      });
      setModalOpen(false);
      setSelected(new Set());
      setName("");
      setQuestion("");
      toast(t("decisionMemos.createdToast"), "success");
      refresh();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: { code?: string; studies?: string[] } } } })
        ?.response?.data?.detail;
      if (detail?.code === "studies_not_ready") {
        toast(t("decisionMemos.notReadyError", { studies: (detail.studies ?? []).join(", ") }), "error");
      } else {
        toast(t("decisionMemos.createError"), "error");
      }
    } finally {
      setCreating(false);
    }
  }

  async function handleOpen(id: string) {
    try {
      const data = await fetchSynthesisMemoHtml(id);
      const url = URL.createObjectURL(new Blob([data], { type: "text/html" }));
      window.open(url, "_blank", "noopener");
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch {
      toast(t("decisionMemos.openError"), "error");
    }
  }

  async function handleDelete(id: string) {
    try {
      await deleteSynthesis(id);
      setMemos((ms) => (ms ?? []).filter((m) => m.id !== id));
    } catch {
      toast(t("decisionMemos.deleteError"), "error");
    }
  }

  const eligible = studies.filter((s) => s.project_count > 0 || s.survey_count > 0);
  if (studies.length < 2) return null;

  return (
    <section className="quanti-showcase__section">
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: "var(--space-4)", flexWrap: "wrap", marginBottom: "var(--space-4)" }}>
        <div>
          <div className="quanti-showcase__eyebrow">{t("decisionMemos.eyebrow")}</div>
          <h2 style={{ fontSize: "var(--text-xl)", fontWeight: 700, margin: 0 }}>{t("decisionMemos.title")}</h2>
          <p style={{ color: "var(--text-tertiary)", fontSize: "var(--text-sm)", margin: "4px 0 0" }}>{t("decisionMemos.sub")}</p>
        </div>
        <button type="button" className="btn btn-primary btn-sm" onClick={() => setModalOpen(true)}>
          {t("decisionMemos.newMemo")}
        </button>
      </div>

      {memos !== null && memos.length === 0 && (
        <p style={{ color: "var(--text-tertiary)", fontSize: "var(--text-sm)" }}>{t("decisionMemos.empty")}</p>
      )}

      {memos !== null && memos.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
          {memos.map((m) => (
            <div
              key={m.id}
              style={{
                display: "flex", alignItems: "center", gap: "var(--space-4)", flexWrap: "wrap",
                background: "var(--bg-surface)", border: "1px solid var(--border-default)",
                borderRadius: "var(--radius-md)", padding: "var(--space-3) var(--space-4)",
              }}
            >
              <div style={{ flex: 1, minWidth: 220 }}>
                <div style={{ fontWeight: 600 }}>{m.name}</div>
                <div style={{ fontSize: "var(--text-xs)", color: "var(--text-tertiary)" }}>
                  {t("decisionMemos.studyCount", { count: m.study_count })}
                  {m.generated_at ? ` · ${new Date(m.generated_at).toLocaleDateString(i18n.language)}` : ""}
                </div>
              </div>
              {m.status === "generating" && (
                <span className="badge">{t("decisionMemos.statusGenerating")}</span>
              )}
              {m.status === "failed" && (
                <span className="badge" style={{ background: "var(--danger-bg)", color: "var(--danger-text)" }} title={m.error ?? undefined}>
                  {t("decisionMemos.statusFailed")}
                </span>
              )}
              {m.status === "ready" && (
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => handleOpen(m.id)}>
                  📄 {t("decisionMemos.open")}
                </button>
              )}
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                aria-label={t("decisionMemos.delete")}
                onClick={() => handleDelete(m.id)}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      {modalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={t("decisionMemos.modalTitle")}
          className="new-study-modal__overlay"
          onClick={() => setModalOpen(false)}
        >
          <div className="new-study-modal" onClick={(e) => e.stopPropagation()}>
            <button
              type="button"
              className="new-study-modal__close"
              onClick={() => setModalOpen(false)}
              aria-label={t("decisionMemos.close")}
            >
              ✕
            </button>
            <div className="new-study-modal__eyebrow">{t("decisionMemos.eyebrow")}</div>
            <h2 className="new-study-modal__title">{t("decisionMemos.modalTitle")}</h2>
            <p className="new-study-modal__sub">{t("decisionMemos.modalSub")}</p>

            <label style={{ display: "block", fontSize: "var(--text-sm)", fontWeight: 600, margin: "var(--space-4) 0 var(--space-1)" }}>
              {t("decisionMemos.studiesLabel")}
            </label>
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-1)", maxHeight: 220, overflowY: "auto", border: "1px solid var(--border-default)", borderRadius: "var(--radius)", padding: "var(--space-2)" }}>
              {eligible.map((s) => (
                <label key={s.id} style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", fontSize: "var(--text-sm)", cursor: "pointer", padding: "4px 6px" }}>
                  <input
                    type="checkbox"
                    checked={selected.has(s.id)}
                    onChange={(e) => {
                      setSelected((prev) => {
                        const next = new Set(prev);
                        if (e.target.checked) next.add(s.id);
                        else next.delete(s.id);
                        return next;
                      });
                    }}
                  />
                  <span>{s.name}</span>
                </label>
              ))}
            </div>

            <label style={{ display: "block", fontSize: "var(--text-sm)", fontWeight: 600, margin: "var(--space-4) 0 var(--space-1)" }}>
              {t("decisionMemos.questionLabel")}
            </label>
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder={t("decisionMemos.questionPlaceholder")}
              rows={2}
              style={{ width: "100%", resize: "vertical" }}
            />

            <label style={{ display: "block", fontSize: "var(--text-sm)", fontWeight: 600, margin: "var(--space-3) 0 var(--space-1)" }}>
              {t("decisionMemos.nameLabel")}
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("decisionMemos.namePlaceholder")}
              style={{ width: "100%" }}
            />

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "var(--space-2)", marginTop: "var(--space-5)" }}>
              <button type="button" className="btn btn-ghost" onClick={() => setModalOpen(false)}>
                {t("decisionMemos.cancel")}
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={selected.size < 2 || creating}
                onClick={handleCreate}
              >
                {creating ? t("decisionMemos.creating") : t("decisionMemos.create", { count: selected.size })}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
