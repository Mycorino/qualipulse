import { Fragment, useEffect, useLayoutEffect, useRef, useState } from "react";
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
import {
  hasOpenedCopilot,
  markCopilotOpened,
  markTeaserSeen,
  teaserSeen,
} from "../copilot/teaser";
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

/** Proposal types whose primary text can be rewritten before accepting. */
const EDITABLE_TYPES = new Set([
  "add_guide_question",
  "add_question",
  "edit_guide_question",
  "edit_question",
  "edit_objective",
  "add_screening_question",
]);

/** The proactive dock popup — a fresh nudge wins over the static NBA. */
type Teaser =
  | { key: string; kind: "nudge"; nudge: Nudge }
  | { key: string; kind: "nba"; action: NextAction };

/** How long the collapsed dock waits before popping the teaser — it should
 * read as "the copilot noticed something", not a page-load banner. */
const TEASER_SHOW_DELAY_MS = 2500;
/** After this, the teaser folds away; the dock chip keeps the suggestion. */
const TEASER_AUTO_HIDE_MS = 15000;

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
  intro,
  disableInput,
  suppressTeaser,
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
   * A deterministic intro shown in the empty thread instead of the generic
   * lead + instrument starters. The CTA fires `onCta` directly (no chat
   * turn) — used on surfaces with no chat backend, to explain and point the
   * user at the real next action.
   */
  intro?: { lead: string; ctaLabel?: string; onCta?: () => void };
  /** Hide the free-text input (surfaces with no chat backend). */
  disableInput?: boolean;
  /** Never pop the proactive teaser (e.g. while the demo tour is guiding
   * the user — two competing popups would fight for attention). */
  suppressTeaser?: boolean;
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
  // Auto-grow the composer with its content (capped by CSS max-height so
  // a long paste scrolls inside the box instead of eating the thread).
  useLayoutEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [input]);
  // True while the user is scrolled to (near) the bottom — auto-scroll
  // only then, so reading an earlier proposal mid-stream isn't yanked.
  const isAtBottom = useRef(true);
  // ── Proactive teaser (collapsed dock popup) ──
  const [teaser, setTeaser] = useState<Teaser | null>(null);
  // First-run explainer is decided when the teaser pops (reading it at
  // render time would flip mid-display once the panel gets opened).
  const [teaserFirstRun, setTeaserFirstRun] = useState(false);
  // At most one teaser per surface mount — a nudge landing later must not
  // pop a second bubble in the same visit.
  const teaserShownFor = useRef<string | null>(null);
  // Prompt queued by the teaser CTA — sent once the panel is open AND the
  // persisted conversation finished hydrating (sending earlier would race
  // the thread restore).
  const pendingPromptRef = useRef<string | null>(null);
  const [hydrated, setHydrated] = useState(false);

  /** Open the panel; optionally queue a prompt to auto-send once hydrated. */
  const openPanel = (prompt?: string) => {
    markCopilotOpened();
    if (prompt && !disableInput) pendingPromptRef.current = prompt;
    setTeaser(null);
    setOpen(true);
  };

  const updateThread = (updater: (cur: ThreadItem[]) => ThreadItem[]) => {
    threadData.current = updater(threadData.current);
    setThread(threadData.current);
  };

  // Restore the persisted conversation for this instrument on mount, so the
  // chat resumes instead of being lost when the researcher navigates away.
  useEffect(() => {
    let cancelled = false;
    loaded.current = false;
    setHydrated(false);
    pendingPromptRef.current = null;
    setTeaser(null);
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
        if (!cancelled) {
          loaded.current = true;
          setHydrated(true);
        }
      });
    return () => {
      cancelled = true;
      // Unmount / target switch: stop any live stream (releases the HTTP
      // connection; the server stops generating).
      abortRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target.id]);

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

  // ── Teaser: pick + pop ──
  // A fresh nudge (event-driven, "your analysis just finished") beats the
  // static NBA. Each candidate teases once ever (persisted); the surface
  // pops at most one bubble per mount; the delay makes it read as noticed,
  // not preloaded.
  const nudgeIdsKey = (nudges ?? []).map((n) => n.id).join(",");
  useEffect(() => {
    if (open || suppressTeaser) return;
    if (teaserShownFor.current === target.id) return;
    let candidate: Teaser | null = null;
    const freshNudge = (nudges ?? []).find(
      (n) => !teaserSeen(`${target.id}:nudge:${n.id}`),
    );
    if (freshNudge) {
      candidate = {
        key: `${target.id}:nudge:${freshNudge.id}`,
        kind: "nudge",
        nudge: freshNudge,
      };
    } else if (
      nextAction &&
      nextAction.kind === "do" &&
      !teaserSeen(`${target.id}:nba:${nextAction.id}`)
    ) {
      candidate = {
        key: `${target.id}:nba:${nextAction.id}`,
        kind: "nba",
        action: nextAction,
      };
    }
    if (!candidate) return;
    const picked = candidate;
    const timer = setTimeout(() => {
      teaserShownFor.current = target.id;
      markTeaserSeen(picked.key);
      setTeaserFirstRun(!hasOpenedCopilot());
      setTeaser(picked);
    }, TEASER_SHOW_DELAY_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, suppressTeaser, target.id, nextAction?.id, nudgeIdsKey]);

  // Teaser: fold away on its own — the dock chip keeps the suggestion, so
  // an ignored bubble never lingers (and never pops again).
  useEffect(() => {
    if (!teaser) return;
    const timer = setTimeout(() => setTeaser(null), TEASER_AUTO_HIDE_MS);
    return () => clearTimeout(timer);
  }, [teaser]);

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

  // Fire the teaser's queued prompt once the panel is open and the persisted
  // conversation has hydrated — the copilot starts working immediately, so
  // one click on the popup demonstrates what the agent actually does.
  useEffect(() => {
    if (!open || !hydrated || busy || disableInput) return;
    const prompt = pendingPromptRef.current;
    if (!prompt) return;
    pendingPromptRef.current = null;
    send(prompt);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, hydrated, busy]);

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

  const setStatus = (
    actionId: string,
    status: PendingAction["status"],
    patch: Partial<PendingAction> = {},
  ) => {
    updateThread((t) =>
      t.map((it) =>
        it.kind === "assistant"
          ? {
              ...it,
              actions: it.actions.map((a) =>
                a.id === actionId ? ({ ...a, ...patch, status } as PendingAction) : a,
              ),
            }
          : it,
      ),
    );
  };

  // Resolving a staged proposal should move the conversation to the next
  // step instead of leaving it idle — the Copilot reads the updated
  // snapshot and proposes whatever comes next (objective -> screener ->
  // guide -> launch). Analysis triggers and removals are one-off actions
  // with nothing staged after them, so they deliberately do NOT continue.
  const AUTO_CONTINUE_AFTER = new Set([
    "edit_objective",
    "edit_settings",
    "add_screening_question",
    "add_guide_question",
    "edit_guide_question",
    "add_question",
    "edit_question",
  ]);

  // A proposal turn often stages a BATCH of cards. Fire the "what's next"
  // turn once — after the last card in the batch is resolved — never once
  // per card. Reads the synchronous thread ref, so resolving several cards
  // fast can't fire it twice or miss on a stale closure. When everything
  // was dismissed the conversation must still move on, so a different
  // prompt asks for an alternative instead of stalling.
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
    // …and only for the LAST assistant turn: resolving an old card after
    // the conversation already moved on must not inject a stray prompt.
    const lastAssistant = [...threadData.current]
      .reverse()
      .find((it) => it.kind === "assistant");
    if (lastAssistant !== turn) return;
    send(
      proposals.some((a) => a.status === "accepted")
        ? t("copilot.continueAfterAccept")
        : t("copilot.continueAfterReject"),
    );
  };

  /** Return a copy of the proposal with its editable text replaced. */
  const withEditedText = (action: PendingAction, text: string): PendingAction => {
    switch (action.type) {
      case "add_guide_question":
        return { ...action, question: { ...(action.question ?? {}), main_question: text } as ProposedGuideQuestion };
      case "add_question":
        return { ...action, question: { ...(action.question ?? {}), prompt: text } as ProposedSurveyQuestion };
      case "edit_guide_question":
        return { ...action, new_main_question: text };
      case "edit_question":
        return { ...action, new_prompt: text };
      case "edit_objective":
        return { ...action, new_objective: text };
      case "add_screening_question":
        return action.screening
          ? { ...action, screening: { ...action.screening, question: text } }
          : action;
      default:
        return action;
    }
  };

  const accept = async (action: PendingAction, editedText?: string) => {
    const trimmed = editedText?.trim();
    const effective = trimmed ? withEditedText(action, trimmed) : action;
    try {
      await target.applyAction(effective);
      setStatus(action.id, "accepted", effective);
      onApplied();
      maybeAutoContinue(effective);
    } catch {
      toast(t("copilot.applyError"), "error");
    }
  };

  const reject = (action: PendingAction) => {
    setStatus(action.id, "rejected");
    // Rejecting the last pending card in a batch still advances the flow —
    // otherwise the conversation stalls after "accept 2, reject 1" (or
    // after dismissing everything).
    maybeAutoContinue(action);
  };

  if (!open) {
    // Collapsed dock — the FAB, plus the live next-best-action when there
    // is one. A soft dot signals an unseen nudge. Either opens the copilot.
    // A freshly-picked teaser pops as a speech bubble above the FAB; while
    // it's up the chip hides (both would repeat the same suggestion).
    const hasNudge = (nudges?.length ?? 0) > 0;
    return (
      <div className="copilot-dock">
        <div className="sr-only" aria-live="polite" role="status">
          {announce}
        </div>
        {teaser && (
          <div className="copilot-teaser" role="status" aria-live="polite">
            <button
              type="button"
              className="copilot-teaser__dismiss"
              onClick={() => setTeaser(null)}
              aria-label={t("copilot.teaser.dismiss")}
            >
              ✕
            </button>
            <span className="copilot-teaser__eyebrow">
              {t("copilot.teaser.eyebrow")}
            </span>
            {teaserFirstRun && (
              <p className="copilot-teaser__intro">
                {t("copilot.teaser.firstRun")}
              </p>
            )}
            {teaser.kind === "nudge" ? (
              <>
                <p className="copilot-teaser__body">
                  {teaser.nudge.textKey
                    ? t(teaser.nudge.textKey, teaser.nudge.textParams)
                    : teaser.nudge.text}
                </p>
                <button
                  type="button"
                  className="btn btn-primary btn-sm copilot-teaser__cta"
                  onClick={() => openPanel()}
                >
                  {t("copilot.teaser.ctaNudge")}
                </button>
              </>
            ) : (
              <>
                <p className="copilot-teaser__body">
                  {t(teaser.action.labelKey, teaser.action.params)}
                </p>
                <p className="copilot-teaser__reason">
                  {t(teaser.action.reasonKey, teaser.action.params)}
                </p>
                <button
                  type="button"
                  className="btn btn-primary btn-sm copilot-teaser__cta"
                  onClick={() =>
                    openPanel(
                      t("copilot.helpMePrefix", {
                        label: t(teaser.action.labelKey, teaser.action.params),
                      }),
                    )
                  }
                >
                  {t("copilot.teaser.cta")}
                </button>
              </>
            )}
          </div>
        )}
        {!teaser && nextAction && nextAction.kind === "do" && (
          <NextActionChip
            action={nextAction}
            variant="dock"
            onRun={() => openPanel()}
          />
        )}
        <button
          type="button"
          className="copilot-fab"
          onClick={() => openPanel()}
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
                    onAccept={(text) => accept(a, text)}
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
          rows={1}
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
  onAccept: (editedText?: string) => void;
  onReject: () => void;
}) {
  const { t } = useTranslation("dashboard");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
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

  // Proposals whose main text the researcher can rewrite before applying.
  const editable =
    action.status === "pending" &&
    EDITABLE_TYPES.has(action.type) &&
    typeof body === "string";

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
      {editing ? (
        <textarea
          className="copilot-proposal__edit"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={3}
          autoFocus
          aria-label={t("copilot.proposal.editLabel")}
        />
      ) : (
        <div className="copilot-proposal__body">{body}</div>
      )}
      {rationale && !editing && (
        <div className="copilot-proposal__rationale">{rationale}</div>
      )}
      {action.status === "pending" ? (
        <div className="copilot-proposal__actions">
          {editing ? (
            <>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => onAccept(draft)}
                disabled={!draft.trim()}
              >
                {t("copilot.proposal.applyEdit")}
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setEditing(false)}
              >
                {t("copilot.proposal.cancelEdit")}
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => onAccept()}
              >
                {t("copilot.proposal.accept")}
              </button>
              {editable && (
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => {
                    setDraft(body ?? "");
                    setEditing(true);
                  }}
                >
                  {t("copilot.proposal.edit")}
                </button>
              )}
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={onReject}
              >
                {t("copilot.proposal.dismiss")}
              </button>
            </>
          )}
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
