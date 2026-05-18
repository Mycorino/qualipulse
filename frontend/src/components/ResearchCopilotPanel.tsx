import { Fragment, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import type {
  CopilotMessage,
  CopilotTarget,
  ProposedAction,
  ProposedGuideQuestion,
  ProposedSurveyQuestion,
} from "../api/copilot";
import type { NextAction } from "../copilot/nextAction";
import type { Nudge } from "../copilot/signals";
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

const TYPE_LABEL: Record<string, string> = {
  likert: "Likert scale",
  mc_single: "Multiple choice",
  mc_multi: "Multi-select",
  nps: "NPS",
  open_text: "Open text",
  short_text: "Short text",
};

type PendingAction = ProposedAction & {
  id: string;
  status: "pending" | "accepted" | "rejected";
};

type ThreadItem =
  | { kind: "user"; text: string }
  | { kind: "assistant"; text: string; actions: PendingAction[] };

const STARTERS = [
  "Help me start from scratch",
  "Review this for methodology issues",
  "Suggest the next question",
];

/**
 * Lightweight inline renderer for the copilot's replies — turns `**bold**`
 * into <strong>. Newlines/lists are preserved by `white-space: pre-wrap`
 * on .copilot-msg__text, so this only handles bold. Dependency-free.
 */
function renderRich(text: string): ReactNode {
  return text.split("**").map((part, i) =>
    i % 2 === 1 ? (
      <strong key={i}>{part}</strong>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  );
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
  const { toast } = useToast();
  const [open, setOpen] = useState(false);
  const [thread, setThread] = useState<ThreadItem[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const threadRef = useRef<HTMLDivElement>(null);
  const prevCount = useRef(0);
  const loaded = useRef(false);

  // Restore the persisted conversation for this instrument on mount, so the
  // chat resumes instead of being lost when the researcher navigates away.
  useEffect(() => {
    let cancelled = false;
    loaded.current = false;
    setThread([]);
    prevCount.current = 0;
    target
      .loadConversation()
      .then((items) => {
        if (cancelled) return;
        if (Array.isArray(items) && items.length > 0) {
          setThread(items as ThreadItem[]);
          prevCount.current = items.length;
        }
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
  // the initial load has settled.
  useEffect(() => {
    if (!loaded.current) return;
    target.saveConversation(thread).catch(() => undefined);
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
    setThread(next);
    setInput("");
    setBusy(true);
    try {
      const resp = await target.runTurn(toMessages(next));
      setThread((t) => [
        ...t,
        {
          kind: "assistant",
          text: resp.reply,
          actions: resp.proposed_actions.map((a, i) => ({
            ...a,
            id: `${Date.now()}-${i}`,
            status: "pending" as const,
          })),
        },
      ]);
    } catch {
      toast("The copilot is unavailable right now", "error");
      setThread((t) => [
        ...t,
        {
          kind: "assistant",
          text: "Sorry — I couldn't respond. Please try again.",
          actions: [],
        },
      ]);
    } finally {
      setBusy(false);
    }
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
      toast("Couldn't apply that change", "error");
    }
  };

  if (!open) {
    // Collapsed dock — the FAB, plus the live next-best-action when there
    // is one. A soft dot signals an unseen nudge. Either opens the copilot.
    const hasNudge = (nudges?.length ?? 0) > 0;
    return (
      <div className="copilot-dock">
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
            hasNudge
              ? "Open the Research Copilot — new updates"
              : "Open the Research Copilot"
          }
        >
          ✦ Ask AI
          {hasNudge && (
            <span className="copilot-fab__dot" aria-hidden="true" />
          )}
        </button>
      </div>
    );
  }

  return (
    <aside className="copilot-panel" aria-label="Research Copilot">
      <header className="copilot-panel__header">
        <div className="copilot-panel__heading">
          <span className="copilot-panel__title">✦ Research Copilot</span>
          {mission && (
            <span className="copilot-panel__mission">Here to: {mission}</span>
          )}
        </div>
        <button
          type="button"
          className="copilot-panel__close"
          onClick={() => setOpen(false)}
          aria-label="Close"
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
                aria-label="Dismiss update"
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
            {nextAction && nextAction.kind === "do" && (
              <button
                type="button"
                className="copilot-nba-starter"
                onClick={() => send(`Help me: ${nextAction.label}`)}
              >
                <span className="copilot-nba-starter__eyebrow">
                  ✦ Suggested next step
                </span>
                <span className="copilot-nba-starter__label">
                  {nextAction.label}
                </span>
                <span className="copilot-nba-starter__reason">
                  {nextAction.reason}
                </span>
              </button>
            )}
            <p className="copilot-empty__lead">
              I can draft questions, fix methodology issues, and shape your
              study. Tell me what you want to learn.
            </p>
            {STARTERS.map((s) => (
              <button
                key={s}
                type="button"
                className="copilot-starter"
                onClick={() => send(s)}
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {thread.map((it, idx) =>
          it.kind === "user" ? (
            <div key={idx} className="copilot-msg copilot-msg--user">
              {it.text}
            </div>
          ) : (
            <div key={idx} className="copilot-msg copilot-msg--assistant">
              <div className="copilot-msg__text">{renderRich(it.text)}</div>
              {it.actions.map((a) => (
                <ProposalCard
                  key={a.id}
                  action={a}
                  onAccept={() => accept(a)}
                  onReject={() => setStatus(a.id, "rejected")}
                />
              ))}
            </div>
          ),
        )}

        {busy && (
          <div className="copilot-msg copilot-msg--thinking">Thinking…</div>
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
          placeholder="Ask the copilot…"
          rows={2}
          disabled={busy}
        />
        <button
          type="button"
          className="btn btn-primary btn-sm"
          onClick={() => send(input)}
          disabled={busy || !input.trim()}
        >
          Send
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
  let heading: string;
  let body: string | undefined;

  if (action.type === "add_question") {
    const q = action.question as ProposedSurveyQuestion | undefined;
    heading = `Add — ${TYPE_LABEL[q?.type ?? ""] ?? q?.type ?? "question"}`;
    body = q?.prompt;
  } else if (action.type === "add_guide_question") {
    const q = action.question as ProposedGuideQuestion | undefined;
    heading = "Add — Interview question";
    body = q?.main_question;
  } else if (action.type === "edit_question") {
    heading = "Edit question";
    body = action.new_prompt ?? "Update this question";
  } else if (action.type === "edit_guide_question") {
    heading = "Edit question";
    body = action.new_main_question ?? "Update this question";
  } else if (action.type === "edit_objective") {
    heading = "Set the research objective";
    body = action.new_objective;
  } else if (action.type === "run_analysis") {
    heading = "Run AI analysis";
    body = "Synthesise themes, JTBDs, and tensions from the interviews";
  } else if (action.type === "refine_analysis") {
    heading = "Refine the analysis";
    body = "Re-synthesise using your theme annotations and context";
  } else {
    heading = "Remove question";
    body = "Remove this question";
  }

  const rationale =
    action.question && "rationale" in action.question
      ? (action.question as { rationale?: string }).rationale
      : action.rationale;

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
            Accept
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={onReject}
          >
            Dismiss
          </button>
        </div>
      ) : (
        <div className="copilot-proposal__status">
          {action.status === "accepted" ? "✓ Applied" : "Dismissed"}
        </div>
      )}
    </div>
  );
}
