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
  | {
      kind: "assistant";
      text: string;
      actions: PendingAction[];
      /** The turn failed — text may be a partial stream. Never replayed
       * to the model; renders an inline notice + retry. */
      error?: boolean;
    };

/** Server JSON → ThreadItem[], defensively. A malformed persisted item
 * (missing `actions`, unknown kind) must not crash the whole panel. */
function sanitizeThread(raw: unknown[]): ThreadItem[] {
  const items: ThreadItem[] = [];
  for (const entry of raw) {
    if (!entry || typeof entry !== "object") continue;
    const it = entry as Record<string, unknown>;
    const text = typeof it.text === "string" ? it.text : "";
    if (it.kind === "user") {
      items.push({ kind: "user", text });
    } else if (it.kind === "assistant") {
      items.push({
        kind: "assistant",
        text,
        actions: Array.isArray(it.actions)
          ? (it.actions as PendingAction[])
          : [],
        error: it.error === true,
      });
    }
  }
  return items;
}

/** i18n key suffixes under dashboard:copilot.starters */
const STARTER_KEYS = ["scratch", "methodology", "nextQuestion"];

/**
 * Targets we've already auto-opened during THIS page load. Survives React
 * StrictMode's dev mount/unmount/remount (which resets component state), so
 * the panel still opens once even though the localStorage guard is written
 * on the first invoke. A genuine later page load starts with an empty set.
 */
const _autoOpenedThisLoad = new Set<string>();

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
  autoOpen,
  intro,
  disableInput,
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
  /**
   * Open the panel automatically the FIRST time it's seen on this surface
   * (guarded per `target.id` via localStorage). Used to greet first-run
   * users — e.g. the empty studies screen.
   */
  autoOpen?: boolean;
  /**
   * A deterministic intro shown in the empty thread instead of the generic
   * lead + instrument starters. The CTA fires `onCta` directly (no chat
   * turn) — used on surfaces with no chat backend, to explain and point the
   * user at the real next action.
   */
  intro?: { lead: string; ctaLabel?: string; onCta?: () => void };
  /** Hide the free-text input (surfaces with no chat backend). */
  disableInput?: boolean;
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
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const prevCount = useRef(0);
  const loaded = useRef(false);
  const versionRef = useRef(0);
  const saveInFlight = useRef(false);
  const saveDirty = useRef(false);
  const lastSavedJson = useRef("");
  // Single synchronous source of truth for the thread. Every mutation goes
  // through updateThread so async handlers (stream deltas, accepts, saves)
  // never race a stale closure. `thread` state mirrors it for rendering.
  const threadData = useRef<ThreadItem[]>([]);
  // Monotonic token identifying the CURRENT turn/target. Any async handler
  // from an older turn (a stream still running after navigating from
  // project A to project B) sees a mismatch and no-ops instead of writing
  // A's reply into B's conversation.
  const turnToken = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  // True while the user is scrolled to (near) the bottom — auto-scroll
  // only then, so reading an earlier proposal mid-stream isn't yanked.
  const isAtBottom = useRef(true);

  const updateThread = (updater: (cur: ThreadItem[]) => ThreadItem[]) => {
    threadData.current = updater(threadData.current);
    setThread(threadData.current);
  };

  // Restore the persisted conversation for this instrument on mount, so the
  // chat resumes instead of being lost when the researcher navigates away.
  useEffect(() => {
    let cancelled = false;
    loaded.current = false;
    turnToken.current += 1; // invalidate any in-flight turn for the old target
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
    setStatusLabel(null);
    threadData.current = [];
    setThread([]);
    prevCount.current = 0;
    versionRef.current = 0;
    lastSavedJson.current = "";
    target
      .loadConversation()
      .then((snapshot) => {
        if (cancelled) return;
        if (Array.isArray(snapshot.thread) && snapshot.thread.length > 0) {
          const items = sanitizeThread(snapshot.thread);
          threadData.current = items;
          setThread(items);
          prevCount.current = items.length;
          lastSavedJson.current = JSON.stringify(items);
        }
        versionRef.current = snapshot.version;
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) loaded.current = true;
      });
    return () => {
      cancelled = true;
      // Unmount / target switch: stop any live stream (releases the HTTP
      // connection; the server stops generating).
      abortRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target.id]);

  // Auto-open the panel the first time it's seen on this surface. Guarded
  // per target.id via localStorage so a repeat visit doesn't re-pop it.
  // `_autoOpenedThisLoad` lets the StrictMode dev remount re-open even though
  // the localStorage guard was already written on the first invoke.
  useEffect(() => {
    if (!autoOpen) return;
    if (_autoOpenedThisLoad.has(target.id)) {
      setOpen(true);
      return;
    }
    const key = `copilot_autoopen_${target.id}`;
    try {
      if (localStorage.getItem(key)) return;
      localStorage.setItem(key, "1");
    } catch {
      // localStorage unavailable (private mode) — open anyway, it's harmless.
    }
    _autoOpenedThisLoad.add(target.id);
    setOpen(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoOpen, target.id]);

  // Persist on TURN BOUNDARIES (turn finished, accepts, rejects) — never
  // per streamed token. A save landing while one is already in flight
  // marks a dirty flag and re-runs when it settles, so the final state
  // is never silently dropped.
  const persist = () => {
    if (!loaded.current) return;
    const items = threadData.current;
    const json = JSON.stringify(items);
    if (json === lastSavedJson.current) return; // e.g. hydration echo
    if (saveInFlight.current) {
      saveDirty.current = true;
      return;
    }
    saveInFlight.current = true;
    target
      .saveConversation(items, versionRef.current)
      .then((newVersion) => {
        versionRef.current = newVersion;
        lastSavedJson.current = json;
      })
      .catch(() => undefined)
      .finally(() => {
        saveInFlight.current = false;
        if (saveDirty.current) {
          saveDirty.current = false;
          persist();
        }
      });
  };

  useEffect(() => {
    if (busy) return; // mid-stream states are transient — don't persist them
    persist();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [thread, busy, target.id]);

  // Auto-scroll on new messages / streaming — but only while the user is
  // already at the bottom. Scrolling up to re-read is never yanked back.
  const handleThreadScroll = () => {
    const el = threadRef.current;
    if (!el) return;
    isAtBottom.current =
      el.scrollHeight - el.scrollTop - el.clientHeight < 48;
  };

  useEffect(() => {
    if (!isAtBottom.current) {
      prevCount.current = thread.length;
      return;
    }
    if (thread.length > prevCount.current || busy) {
      threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight });
    }
    prevCount.current = thread.length;
  }, [thread, busy]);

  // Restore focus to the input when a turn ends — the browser drops focus
  // if the field was disabled/blurred during the stream.
  useEffect(() => {
    if (!busy && open && !disableInput) inputRef.current?.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busy]);

  // Error bubbles (and empty drafts) are UI artifacts — never replay them
  // to the model as real assistant turns.
  const toMessages = (items: ThreadItem[]): CopilotMessage[] =>
    items
      .filter(
        (it) =>
          it.kind === "user" ||
          (it.text.trim().length > 0 && !(it.kind === "assistant" && it.error)),
      )
      .map((it) => ({ role: it.kind, content: it.text }));

  const stop = () => {
    abortRef.current?.abort();
  };

  const runTurnWith = async (baseItems: ThreadItem[]) => {
    const token = ++turnToken.current;
    const controller = new AbortController();
    abortRef.current = controller;
    const fresh = () => turnToken.current === token;

    setStatusLabel(null);
    setBusy(true);
    try {
      const resp = await target.runTurn(toMessages(baseItems), {
        signal: controller.signal,
        onStatus: (label) => {
          if (fresh()) setStatusLabel(label);
        },
        onDelta: (chunk) => {
          if (!fresh()) return;
          updateThread((items) =>
            items.map((it, i) =>
              i === items.length - 1 && it.kind === "assistant"
                ? { ...it, text: it.text + chunk }
                : it,
            ),
          );
        },
      });
      if (!fresh()) return;
      updateThread((items) =>
        items.map((it, i) =>
          i === items.length - 1 && it.kind === "assistant"
            ? {
                ...it,
                text: resp.reply,
                error: resp.error === true,
                actions: resp.proposed_actions.map((a, j) => ({
                  ...a,
                  id: `${token}-${j}`,
                  status: "pending" as const,
                })),
              }
            : it,
        ),
      );
      if (resp.error) toast(t("copilot.unavailable"), "error");
    } catch (err) {
      if (!fresh()) return;
      const aborted = (err as Error | undefined)?.name === "AbortError";
      if (!aborted) toast(t("copilot.unavailable"), "error");
      // KEEP any streamed partial text — a reply that died at 95% is still
      // useful. Flag the bubble so it renders the notice + retry and is
      // excluded from future model input.
      updateThread((items) =>
        items.map((it, i) =>
          i === items.length - 1 && it.kind === "assistant"
            ? { ...it, error: !aborted, text: it.text }
            : it,
        ),
      );
      if (aborted) {
        // User stop (or navigation): drop a trailing EMPTY draft entirely.
        updateThread((items) => {
          const last = items[items.length - 1];
          if (last && last.kind === "assistant" && !last.text.trim() && last.actions.length === 0) {
            return items.slice(0, -1);
          }
          return items;
        });
      }
    } finally {
      if (turnToken.current === token) {
        abortRef.current = null;
        setStatusLabel(null);
        setBusy(false);
      }
    }
  };

  const send = async (raw: string) => {
    const text = raw.trim();
    if (!text || busy) return;
    // Push the user turn AND an empty assistant draft. Streaming deltas
    // fill the draft; the final `done` event finalises it with the
    // authoritative reply + proposed actions.
    updateThread((cur) => [
      ...cur,
      { kind: "user", text },
      { kind: "assistant", text: "", actions: [] },
    ]);
    const baseItems = threadData.current.slice(0, -1); // without the draft
    setInput("");
    await runTurnWith(baseItems);
  };

  /** Re-run the turn behind a failed assistant bubble, in place. */
  const retryLast = async () => {
    if (busy) return;
    const items = threadData.current;
    const last = items[items.length - 1];
    if (!last || last.kind !== "assistant" || !last.error) return;
    updateThread((cur) => [
      ...cur.slice(0, -1),
      { kind: "assistant", text: "", actions: [] },
    ]);
    await runTurnWith(threadData.current.slice(0, -1));
  };

  const submitFreeReply = (actionId: string) => {
    const v = (replyDrafts[actionId] ?? "").trim();
    if (!v || busy) return;
    setReplyDrafts((d) => ({ ...d, [actionId]: "" }));
    send(v);
  };

  const setStatus = (actionId: string, status: PendingAction["status"]) => {
    updateThread((t) =>
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

  // Resolving a staged proposal should move the conversation to the next
  // step instead of leaving it idle — the Copilot reads the updated
  // snapshot and proposes whatever comes next (objective -> screener ->
  // guide). These proposal types advance the staged flow; the guide is
  // the terminal stage, so it deliberately does NOT auto-continue.
  const AUTO_CONTINUE_AFTER = new Set([
    "edit_objective",
    "edit_settings",
    "add_screening_question",
  ]);

  // A screener proposal stages a BATCH of add_screening_question cards.
  // Fire the "what's next" turn once — after the last card in the batch is
  // resolved and at least one was accepted — never once per card. Reads
  // the synchronous thread ref, so accepting several cards fast can't fire
  // it twice or miss on a stale closure.
  const maybeAutoContinue = (action: PendingAction) => {
    if (!AUTO_CONTINUE_AFTER.has(action.type)) return;
    const turn = threadData.current.find(
      (it) =>
        it.kind === "assistant" &&
        it.actions.some((a) => a.id === action.id),
    );
    if (!turn || turn.kind !== "assistant") return;
    const proposals = turn.actions.filter((a) => a.type !== "suggest_replies");
    // Wait until every proposal card in this turn is resolved…
    if (proposals.some((a) => a.status === "pending")) return;
    // …and only continue if the user actually accepted something.
    if (!proposals.some((a) => a.status === "accepted")) return;
    send(t("copilot.continueAfterAccept"));
  };

  const accept = async (action: PendingAction) => {
    try {
      await target.applyAction(action);
      setStatus(action.id, "accepted");
      onApplied();
      maybeAutoContinue(action);
    } catch {
      toast(t("copilot.applyError"), "error");
    }
  };

  const reject = (action: PendingAction) => {
    setStatus(action.id, "rejected");
    // Rejecting the last pending card in a batch where others were
    // accepted still advances the flow — otherwise the conversation
    // stalls after "accept 2, reject 1".
    maybeAutoContinue(action);
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
              <span className="copilot-nudge__text">
                {n.textKey ? t(n.textKey, n.textParams) : n.text}
              </span>
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

      <div
        className="copilot-thread"
        ref={threadRef}
        onScroll={handleThreadScroll}
        role="log"
      >
        {thread.length === 0 && intro && (
          <div className="copilot-empty">
            <p className="copilot-empty__lead">{intro.lead}</p>
            {intro.ctaLabel && intro.onCta && (
              <button
                type="button"
                className="btn btn-primary copilot-intro-cta"
                onClick={intro.onCta}
              >
                {intro.ctaLabel}
              </button>
            )}
          </div>
        )}

        {thread.length === 0 && !intro && !disableInput && (
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
              {it.error && (
                <div className="copilot-msg__error">
                  <span>{t("copilot.errorInline")}</span>
                  {idx === thread.length - 1 && (
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={retryLast}
                      disabled={busy}
                    >
                      {t("copilot.retry")}
                    </button>
                  )}
                </div>
              )}
              {it.actions
                .filter((a) => a.type !== "suggest_replies")
                .map((a) => (
                  <ProposalCard
                    key={a.id}
                    action={a}
                    onAccept={() => accept(a)}
                    onReject={() => reject(a)}
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

      {!disableInput && (
      <div className="copilot-input">
        <textarea
          ref={inputRef}
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
        />
        {busy ? (
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={stop}
          >
            {t("copilot.stop")}
          </button>
        ) : (
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={() => send(input)}
            disabled={!input.trim()}
          >
            {t("copilot.send")}
          </button>
        )}
      </div>
      )}
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
    if (s.branding_mode === "anonymous")
      parts.push(t("copilot.proposal.settingsBrandingAnonymous", { defaultValue: "Anonymous study" }));
    else if (s.branding_mode === "branded")
      parts.push(t("copilot.proposal.settingsBrandingBranded", { defaultValue: "Branded interview" }));
    else if (s.branding_mode === "standard")
      parts.push(t("copilot.proposal.settingsBrandingStandard", { defaultValue: "Standard identity" }));
    if (s.brand_primary_color)
      parts.push(t("copilot.proposal.settingsBrandColor", { color: s.brand_primary_color, defaultValue: "Color {{color}}" }));
    if (s.brand_font)
      parts.push(t("copilot.proposal.settingsBrandFont", { font: s.brand_font, defaultValue: "Font: {{font}}" }));
    if (s.researcher_name)
      parts.push(t("copilot.proposal.settingsResearcherName", { name: s.researcher_name, defaultValue: "Shown as {{name}}" }));
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
  } else if (
    action.type === "remove_question" ||
    action.type === "remove_guide_question"
  ) {
    heading = t("copilot.proposal.removeQuestion");
    body = t("copilot.proposal.removeThisQuestion");
  } else {
    // Forward compatibility: an action type this build doesn't know MUST
    // NOT fall into the remove branch (a dangerous mislabel) — render a
    // neutral card with no Accept.
    return (
      <div className="copilot-proposal copilot-proposal--rejected">
        <div className="copilot-proposal__eyebrow">
          {t("copilot.proposal.unsupported")}
        </div>
      </div>
    );
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
