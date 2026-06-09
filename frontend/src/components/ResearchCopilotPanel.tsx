import { Fragment, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import type {
  CopilotMessage,
  CopilotTarget,
  ProposedAction,
  ProposedGuideQuestion,
  ProposedSurveyQuestion,
} from "../api/copilot";
import type { NextAction } from "../copilot/nextAction";
import type { Nudge } from "../copilot/signals";
import { useNudgeAnnounce } from "../copilot/useNudgeAnnounce";
import { NextActionChip } from "./NextActionChip";
import { useToast } from "./Toast";

/**
 * ResearchCopilotPanel — the in-context AI assistant.
 *
 * A collapsible slide-over (zero footprint when closed). The copilot reads
 * the live instrument server-side, asks clarifying questions, and PROPOSES
 * changes. Each proposal renders as a card the researcher accepts (applied
 * via the real instrument API) or rejects.
 *
 * One copilot, every surface: the panel is generic over a `CopilotTarget`.
 * The survey editor and the interview-guide builder each build a target;
 * later surfaces do the same.
 */

type PendingAction = ProposedAction & {
  id: string;
  status: "pending" | "accepted" | "rejected";
};

type ThreadItem =
  | { kind: "user"; text: string }
  | { kind: "assistant"; text: string; actions: PendingAction[] };

/** i18n key suffixes under dashboard:copilot.starters */
const STARTER_KEYS = ["scratch", "methodology", "nextQuestion"];

/**
 * Lightweight inline renderer for the copilot's replies — turns
 * `**bold**`, `*italic*`, and `` `code` `` into the matching elements.
 * Newlines/lists are preserved by `white-space: pre-wrap` on
 * .copilot-msg__text, so this only handles inline emphasis.
 * Dependency-free. Bold is matched before italic so `**x**` never
 * degrades into stray single-asterisk italics.
 */
const _RICH_TOKEN = /(\*\*[^*]+\*\*|\*[^*\n]+\*|`[^`]+`)/g;

function renderRich(text: string): ReactNode {
  return text.split(_RICH_TOKEN).map((part, i) => {
    if (!part) return null;
    if (part.length >= 4 && part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    if (part.length >= 2 && part.startsWith("*") && part.endsWith("*")) {
      return <em key={i}>{part.slice(1, -1)}</em>;
    }
    if (part.length >= 2 && part.startsWith("`") && part.endsWith("`")) {
      return <code key={i}>{part.slice(1, -1)}</code>;
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
}

export function ResearchCopilotPanel({
  target,
  onApplied,
  mission,
  nextAction,
  nudges,
  onDismissNudge,
}: {
  target: CopilotTarget;
  onApplied: () => void;
  /** The one-line job the copilot helps with on this surface. */
  mission?: string;
  /** The deterministic next-best-action for this surface, if any. */
  nextAction?: NextAction;
  /** Event-driven nudges — "something changed while you were away." */
  nudges?: Nudge[];
  onDismissNudge?: (id: string) => void;
}) {
  const { t } = useTranslation("dashboard");
  const { toast } = useToast();
  const announce = useNudgeAnnounce(nudges);
  const [open, setOpen] = useState(false);
  const [thread, setThread] = useState<ThreadItem[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  // Free-form draft per suggest_replies group (keyed by action id) — the
  // editable field is always shown alongside the option buttons.
  const [replyDrafts, setReplyDrafts] = useState<Record<string, string>>({});
  // Live narration of the agent's current step ("Reading your interviews…")
  // while busy. Falls back to a generic "Thinking…" between status events.
  const [statusLabel, setStatusLabel] = useState<string | null>(null);
  const threadRef = useRef<HTMLDivElement>(null);
  const prevCount = useRef(0);
  const loaded = useRef(false);
  const versionRef = useRef(0);
  const saveInFlight = useRef(false);

  // Restore the persisted conversation for this instrument on mount, so the
  // chat resumes instead of being lost when the researcher navigates away.
  useEffect(() => {
    let cancelled = false;
    loaded.current = false;
    setThread([]);
    prevCount.current = 0;
    versionRef.current = 0;
    target
      .loadConversation()
      .then((snapshot) => {
        if (cancelled) return;
        if (Array.isArray(snapshot.thread) && snapshot.thread.length > 0) {
          setThread(snapshot.thread as ThreadItem[]);
          prevCount.current = snapshot.thread.length;
        }
        versionRef.current = snapshot.version;
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) loaded.current = true;
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target.id]);

  // Persist the thread after every change (turns, accepts, rejects) once
  // the initial load has settled. Serialized to avoid concurrent writes
  // racing on the version counter.
  useEffect(() => {
    if (!loaded.current) return;
    if (saveInFlight.current) return;
    saveInFlight.current = true;
    target
      .saveConversation(thread, versionRef.current)
      .then((newVersion) => {
        versionRef.current = newVersion;
      })
      .catch(() => undefined)
      .finally(() => {
        saveInFlight.current = false;
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [thread, target.id]);

  // Auto-scroll only when a NEW message arrives (or the copilot starts
  // thinking) — never when an existing proposal's status changes.
  useEffect(() => {
    if (thread.length > prevCount.current || busy) {
      threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight });
    }
    prevCount.current = thread.length;
  }, [thread, busy]);

  const toMessages = (items: ThreadItem[]): CopilotMessage[] =>
    items.map((it) => ({ role: it.kind, content: it.text }));

  const send = async (raw: string) => {
    const text = raw.trim();
    if (!text || busy) return;
    const next: ThreadItem[] = [...thread, { kind: "user", text }];
    // Push the user turn AND an empty assistant draft. Streaming deltas
    // fill the draft; the final `done` event finalises it with the
    // authoritative reply + proposed actions.
    setThread([...next, { kind: "assistant", text: "", actions: [] }]);
    setInput("");
    setStatusLabel(null);
    setBusy(true);
    try {
      const resp = await target.runTurn(toMessages(next), {
        onStatus: (label) => setStatusLabel(label),
        onDelta: (chunk) =>
          setThread((t) =>
            t.map((it, i) =>
              i === t.length - 1 && it.kind === "assistant"
                ? { ...it, text: it.text + chunk }
                : it,
            ),
          ),
      });
      setThread((t) =>
        t.map((it, i) =>
          i === t.length - 1 && it.kind === "assistant"
            ? {
                ...it,
                text: resp.reply,
                actions: resp.proposed_actions.map((a, j) => ({
                  ...a,
                  id: `${Date.now()}-${j}`,
                  status: "pending" as const,
                })),
              }
            : it,
        ),
      );
    } catch {
      toast(t("copilot.unavailable"), "error");
      const errorReply = t("copilot.errorReply");
      setThread((items) =>
        items.map((it, i) =>
          i === items.length - 1 && it.kind === "assistant"
            ? {
                ...it,
                text: errorReply,
              }
            : it,
        ),
      );
    } finally {
      setStatusLabel(null);
      setBusy(false);
    }
  };

  const submitFreeReply = (actionId: string) => {
    const v = (replyDrafts[actionId] ?? "").trim();
    if (!v || busy) return;
    setReplyDrafts((d) => ({ ...d, [actionId]: "" }));
    send(v);
  };

  const setStatus = (actionId: string, status: PendingAction["status"]) => {
    setThread((t) =>
      t.map((it) =>
        it.kind === "assistant"
          ? {
              ...it,
              actions: it.actions.map((a) =>
                a.id === actionId ? { ...a, status } : a,
              ),
            }
          : it,
      ),
    );
  };

  const accept = async (action: PendingAction) => {
    try {
      await target.applyAction(action);
      setStatus(action.id, "accepted");
      onApplied();
    } catch {
      toast(t("copilot.applyError"), "error");
    }
  };

  if (!open) {
    // Collapsed dock — the FAB, plus the live next-best-action when there
    // is one. A soft dot signals an unseen nudge. Either opens the copilot.
    const hasNudge = (nudges?.length ?? 0) > 0;
    return (
      <div className="copilot-dock">
        <div className="sr-only" aria-live="polite" role="status">
          {announce}
        </div>
        {nextAction && nextAction.kind === "do" && (
          <NextActionChip
            action={nextAction}
            variant="dock"
            onRun={() => setOpen(true)}
          />
        )}
        <button
          type="button"
          className="copilot-fab"
          onClick={() => setOpen(true)}
          aria-label={
            hasNudge ? t("copilot.openWithUpdates") : t("copilot.open")
          }
        >
          {t("copilot.fab")}
          {hasNudge && (
            <span className="copilot-fab__dot" aria-hidden="true" />
          )}
        </button>
      </div>
    );
  }

  return (
    <aside className="copilot-panel" aria-label={t("copilot.ariaPanel")}>
      <div className="sr-only" aria-live="polite" role="status">
        {announce}
      </div>
      <header className="copilot-panel__header">
        <div className="copilot-panel__heading">
          <span className="copilot-panel__title">{t("copilot.title")}</span>
          {mission && (
            <span className="copilot-panel__mission">{t("copilot.missionPrefix", { mission })}</span>
          )}
        </div>
        <button
          type="button"
          className="copilot-panel__close"
          onClick={() => setOpen(false)}
          aria-label={t("copilot.close")}
        >
          ✕
        </button>
      </header>

      {nudges && nudges.length > 0 && (
        <div className="copilot-nudges">
          {nudges.map((n) => (
            <div
              key={n.id}
              className={`copilot-nudge copilot-nudge--${n.tone}`}
            >
              <span className="copilot-nudge__text">{n.text}</span>
              <button
                type="button"
                className="copilot-nudge__dismiss"
                onClick={() => onDismissNudge?.(n.id)}
                aria-label={t("copilot.dismissUpdate")}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="copilot-thread" ref={threadRef}>
        {thread.length === 0 && (
          <div className="copilot-empty">
            {nextAction && nextAction.kind === "do" && (() => {
              const nbaLabel = t(nextAction.labelKey, nextAction.params);
              const nbaReason = t(nextAction.reasonKey, nextAction.params);
              return (
                <button
                  type="button"
                  className="copilot-nba-starter"
                  onClick={() => send(t("copilot.helpMePrefix", { label: nbaLabel }))}
                >
                  <span className="copilot-nba-starter__eyebrow">
                    {t("copilot.suggestedNextStep")}
                  </span>
                  <span className="copilot-nba-starter__label">{nbaLabel}</span>
                  <span className="copilot-nba-starter__reason">{nbaReason}</span>
                </button>
              );
            })()}
            <p className="copilot-empty__lead">{t("copilot.emptyLead")}</p>
            {STARTER_KEYS.map((key) => {
              const label = t(`copilot.starters.${key}`);
              return (
                <button
                  key={key}
                  type="button"
                  className="copilot-starter"
                  onClick={() => send(label)}
                >
                  {label}
                </button>
              );
            })}
          </div>
        )}

        {thread.map((it, idx) =>
          it.kind === "user" ? (
            <div key={idx} className="copilot-msg copilot-msg--user">
              {it.text}
            </div>
          ) : (
            <div key={idx} className="copilot-msg copilot-msg--assistant">
              {it.text && (
                <div className="copilot-msg__text">{renderRich(it.text)}</div>
              )}
              {it.actions
                .filter((a) => a.type !== "suggest_replies")
                .map((a) => (
                  <ProposalCard
                    key={a.id}
                    action={a}
                    onAccept={() => accept(a)}
                    onReject={() => setStatus(a.id, "rejected")}
                  />
                ))}
              {/* Clarifying-question chips — one click answers, or the
                  researcher can still type a custom reply below. */}
              {it.actions
                .filter(
                  (a) =>
                    a.type === "suggest_replies" && (a.options?.length ?? 0) > 0,
                )
                .map((a) => (
                  <div key={a.id} className="copilot-replies" role="group">
                    <div className="copilot-replies__eyebrow">
                      {t("copilot.replyEyebrow")}
                    </div>
                    <div className="copilot-replies__options">
                      {(a.options ?? []).map((opt, k) => (
                        <button
                          key={k}
                          type="button"
                          className="copilot-reply-option"
                          onClick={() => send(opt)}
                          disabled={busy}
                        >
                          {opt}
                        </button>
                      ))}
                    </div>
                    <div className="copilot-replies__or">
                      {t("copilot.replyOr")}
                    </div>
                    <div className="copilot-reply-freeform">
                      <input
                        className="copilot-reply-freeform__field"
                        value={replyDrafts[a.id] ?? ""}
                        onChange={(e) =>
                          setReplyDrafts((d) => ({ ...d, [a.id]: e.target.value }))
                        }
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            e.preventDefault();
                            submitFreeReply(a.id);
                          }
                        }}
                        placeholder={t("copilot.freeReplyPlaceholder")}
                        disabled={busy}
                      />
                      <button
                        type="button"
                        className="btn btn-primary btn-sm"
                        onClick={() => submitFreeReply(a.id)}
                        disabled={busy || !(replyDrafts[a.id] ?? "").trim()}
                      >
                        {t("copilot.send")}
                      </button>
                    </div>
                  </div>
                ))}
            </div>
          ),
        )}

        {busy && (
          <div className="copilot-msg copilot-msg--thinking">
            {statusLabel ?? t("copilot.thinking")}
          </div>
        )}
      </div>

      <div className="copilot-input">
        <textarea
          className="copilot-input__field"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(input);
            }
          }}
          placeholder={t("copilot.inputPlaceholder")}
          rows={2}
          disabled={busy}
        />
        <button
          type="button"
          className="btn btn-primary btn-sm"
          onClick={() => send(input)}
          disabled={busy || !input.trim()}
        >
          {t("copilot.send")}
        </button>
      </div>
    </aside>
  );
}

function ProposalCard({
  action,
  onAccept,
  onReject,
}: {
  action: PendingAction;
  onAccept: () => void;
  onReject: () => void;
}) {
  const { t } = useTranslation("dashboard");
  let heading: string;
  let body: string | undefined;

  if (action.type === "add_question") {
    const q = action.question as ProposedSurveyQuestion | undefined;
    const typeLabel = q?.type
      ? t(`copilot.type.${q.type}`, { defaultValue: q.type })
      : t("copilot.proposal.fallbackQuestion");
    heading = t("copilot.proposal.addQuestion", { type: typeLabel });
    body = q?.prompt;
  } else if (action.type === "add_guide_question") {
    const q = action.question as ProposedGuideQuestion | undefined;
    heading = t("copilot.proposal.addGuideQuestion");
    body = q?.main_question;
  } else if (action.type === "edit_question") {
    heading = t("copilot.proposal.editQuestion");
    body = action.new_prompt ?? t("copilot.proposal.updateThisQuestion");
  } else if (action.type === "edit_guide_question") {
    heading = t("copilot.proposal.editQuestion");
    body = action.new_main_question ?? t("copilot.proposal.updateThisQuestion");
  } else if (action.type === "edit_objective") {
    heading = t("copilot.proposal.setObjective");
    body = action.new_objective;
  } else if (action.type === "edit_settings") {
    heading = t("copilot.proposal.editSettings");
    const s = action.settings ?? {};
    const parts: string[] = [];
    if (s.interview_duration_minutes != null)
      parts.push(
        t("copilot.proposal.settingsDuration", { n: s.interview_duration_minutes }),
      );
    if (s.target_participants != null)
      parts.push(
        t("copilot.proposal.settingsSample", { n: s.target_participants }),
      );
    if (s.warmup_enabled != null)
      parts.push(
        s.warmup_enabled
          ? t("copilot.proposal.settingsWarmupOn")
          : t("copilot.proposal.settingsWarmupOff"),
      );
    body = parts.join(" · ");
  } else if (action.type === "add_screening_question") {
    heading = t("copilot.proposal.addScreening");
    body = action.screening?.question;
  } else if (action.type === "run_analysis") {
    heading = t("copilot.proposal.runAnalysis");
    body = t("copilot.proposal.runAnalysisBody");
  } else if (action.type === "refine_analysis") {
    heading = t("copilot.proposal.refineAnalysis");
    body = t("copilot.proposal.refineAnalysisBody");
  } else {
    heading = t("copilot.proposal.removeQuestion");
    body = t("copilot.proposal.removeThisQuestion");
  }

  const rationale =
    action.question && "rationale" in action.question
      ? (action.question as { rationale?: string }).rationale
      : action.screening?.rationale ?? action.rationale;

  return (
    <div
      className={`copilot-proposal copilot-proposal--${action.status}`}
      data-action={action.type}
    >
      <div className="copilot-proposal__eyebrow">{heading}</div>
      <div className="copilot-proposal__body">{body}</div>
      {rationale && (
        <div className="copilot-proposal__rationale">{rationale}</div>
      )}
      {action.status === "pending" ? (
        <div className="copilot-proposal__actions">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={onAccept}
          >
            {t("copilot.proposal.accept")}
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={onReject}
          >
            {t("copilot.proposal.dismiss")}
          </button>
        </div>
      ) : (
        <div className="copilot-proposal__status">
          {action.status === "accepted"
            ? t("copilot.proposal.applied")
            : t("copilot.proposal.dismissed")}
        </div>
      )}
    </div>
  );
}
