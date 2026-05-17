import { Fragment, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import {
  CopilotMessage,
  ProposedAction,
  runCopilot,
} from "../api/copilot";
import { createQuestion, deprecateQuestion, patchQuestion } from "../api/surveys";
import { useToast } from "./Toast";

/**
 * ResearchCopilotPanel — the in-context AI assistant for the survey builder.
 *
 * A collapsible slide-over (zero footprint when closed). The copilot reads
 * the live survey server-side, asks clarifying questions, and PROPOSES
 * question changes. Each proposal renders as a card the researcher accepts
 * (applied via the real survey API) or rejects. See api/copilot.ts and
 * backend services/copilot.py.
 *
 * One copilot, every surface: this same component will later mount on the
 * interview guide and the homescreen — only the API target changes.
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
  "Help me start a survey from scratch",
  "Review my questions for methodology issues",
  "Suggest a screener question",
];

/**
 * Lightweight inline renderer for the copilot's replies — turns `**bold**`
 * into <strong>. Newlines and lists are preserved by the `white-space:
 * pre-wrap` on .copilot-msg__text, so this only handles bold. Dependency-free.
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
  surveyId,
  onApplied,
}: {
  surveyId: string;
  onApplied: () => void;
}) {
  const { toast } = useToast();
  const [open, setOpen] = useState(false);
  const [thread, setThread] = useState<ThreadItem[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const threadRef = useRef<HTMLDivElement>(null);
  const prevCount = useRef(0);

  // Auto-scroll only when a NEW message arrives (or the copilot starts
  // thinking) — never when an existing proposal's status changes, or
  // accepting a proposal higher up would yank the view to the bottom.
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
      const resp = await runCopilot(surveyId, toMessages(next));
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
        { kind: "assistant", text: "Sorry — I couldn't respond. Please try again.", actions: [] },
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
      if (action.type === "add_question" && action.question) {
        await createQuestion(surveyId, {
          type: action.question.type,
          prompt: action.question.prompt,
          config: action.question.config,
          is_required: false,
        });
      } else if (action.type === "edit_question" && action.question_id) {
        const payload: { prompt?: string; config?: Record<string, unknown> } = {};
        if (action.new_prompt) payload.prompt = action.new_prompt;
        if (action.new_config) payload.config = action.new_config;
        await patchQuestion(surveyId, action.question_id, payload);
      } else if (action.type === "remove_question" && action.question_id) {
        await deprecateQuestion(surveyId, action.question_id);
      }
      setStatus(action.id, "accepted");
      onApplied();
    } catch {
      toast("Couldn't apply that change", "error");
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        className="copilot-fab"
        onClick={() => setOpen(true)}
        aria-label="Open the Research Copilot"
      >
        ✦ Ask AI
      </button>
    );
  }

  return (
    <aside className="copilot-panel" aria-label="Research Copilot">
      <header className="copilot-panel__header">
        <span className="copilot-panel__title">✦ Research Copilot</span>
        <button
          type="button"
          className="copilot-panel__close"
          onClick={() => setOpen(false)}
          aria-label="Close"
        >
          ✕
        </button>
      </header>

      <div className="copilot-thread" ref={threadRef}>
        {thread.length === 0 && (
          <div className="copilot-empty">
            <p className="copilot-empty__lead">
              I can draft questions, fix methodology issues, and shape your
              survey. Tell me what you want to learn.
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
                <ProposalCard key={a.id} action={a} onAccept={() => accept(a)} onReject={() => setStatus(a.id, "rejected")} />
              ))}
            </div>
          ),
        )}

        {busy && <div className="copilot-msg copilot-msg--thinking">Thinking…</div>}
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
  const heading =
    action.type === "add_question"
      ? `Add — ${TYPE_LABEL[action.question?.type ?? ""] ?? action.question?.type}`
      : action.type === "edit_question"
        ? "Edit question"
        : "Remove question";
  const body =
    action.type === "add_question"
      ? action.question?.prompt
      : action.type === "edit_question"
        ? action.new_prompt ?? "Update this question"
        : "Remove this question from the survey";
  const rationale =
    action.type === "add_question"
      ? action.question?.rationale
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
          <button type="button" className="btn btn-primary btn-sm" onClick={onAccept}>
            Accept
          </button>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onReject}>
            Dismiss
          </button>
        </div>
      ) : (
        <div className="copilot-proposal__status">
          {action.status === "accepted" ? "✓ Added to your survey" : "Dismissed"}
        </div>
      )}
    </div>
  );
}
