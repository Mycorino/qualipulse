import { Fragment, ReactNode, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  getMe,
  completeOnboarding,
  resendVerification,
  analyseWebsite,
  type CompanyResponse,
} from "../api/auth";
import {
  runOnboardingCopilot,
  getOnboardingMemory,
  type CopilotMessage,
  type ProposedAction,
  type ProposedGuideQuestion,
} from "../api/copilot";
import {
  createProject,
  patchProjectSettings,
  createGuideQuestion,
} from "../api/projects";
import { setCachedOnboarded } from "../hooks/useAuth";
import { useToast } from "../components/Toast";

/**
 * Welcome — the conversational onboarding.
 *
 * The new researcher's first conversation with the Research Copilot.
 * Instead of a 4-step form, the agent asks what they want to learn and
 * drafts a real first study. The opening greeting is canned (instant, no
 * API); the model is only called once the researcher answers.
 */

type ThreadItem = {
  role: "user" | "assistant";
  text: string;
  /** Attached to an assistant turn that proposed the first study. */
  study?: ProposedAction;
  /** Tap-to-answer chips the agent attached to this turn. */
  replies?: { context?: string; options: string[] };
  /** Website-lookup card the agent attached to this turn. */
  website?: { prompt: string };
  /** True once the user has used the chips/website card on this turn —
   *  prevents re-use after the conversation moves on. */
  consumed?: boolean;
};

type Phase = "profile" | "frame" | "launch";

/**
 * Lightweight inline markdown renderer — handles `**bold**` and `*italic*`.
 * Newlines/lists are preserved by `white-space: pre-wrap` on
 * `.onboarding-msg__text`. Dependency-free, same pattern as the copilot panel.
 */
function renderRich(text: string): ReactNode {
  // Split on **bold** first so single-asterisk italics inside survive.
  const parts: ReactNode[] = [];
  text.split("**").forEach((chunk, i) => {
    const node = i % 2 === 1 ? (
      <strong key={`b-${i}`}>{renderItalics(chunk, i)}</strong>
    ) : (
      <Fragment key={`p-${i}`}>{renderItalics(chunk, i)}</Fragment>
    );
    parts.push(node);
  });
  return parts;
}

function renderItalics(text: string, parentKey: number): ReactNode {
  return text.split(/(\*[^*\n]+\*)/g).map((seg, j) => {
    if (seg.startsWith("*") && seg.endsWith("*") && seg.length > 2) {
      return <em key={`i-${parentKey}-${j}`}>{seg.slice(1, -1)}</em>;
    }
    return <Fragment key={`t-${parentKey}-${j}`}>{seg}</Fragment>;
  });
}

const greeting = (firstName: string): string =>
  `Hi ${firstName} — I'm your Research Copilot. I help you run interviews ` +
  `and surveys without the scheduling-and-synthesis grind.\n\n` +
  `To start: what's the one thing you most need to learn about your users ` +
  `right now?`;

export default function Welcome() {
  const navigate = useNavigate();
  const { toast } = useToast();

  const [me, setMe] = useState<CompanyResponse | null>(null);
  const [thread, setThread] = useState<ThreadItem[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [creating, setCreating] = useState(false);
  const [done, setDone] = useState<{
    projectId: string;
    studyName: string;
    memory: string;
  } | null>(null);
  const threadRef = useRef<HTMLDivElement>(null);

  // Load the researcher, redirect out if already onboarded, and seed the
  // instant canned greeting.
  useEffect(() => {
    getMe()
      .then((m) => {
        if (m.onboarding_completed) {
          navigate("/dashboard", { replace: true });
          return;
        }
        setMe(m);
        setThread([
          { role: "assistant", text: greeting(m.first_name || "there") },
        ]);
      })
      .catch(() => navigate("/login", { replace: true }));
  }, [navigate]);

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight });
  }, [thread, busy]);

  const send = async (raw: string) => {
    const text = raw.trim();
    if (!text || busy) return;
    const next: ThreadItem[] = [...thread, { role: "user", text }];
    // Push the user turn AND an empty assistant draft — streaming deltas
    // fill it in, the final `done` event finalises with the study proposal.
    setThread([...next, { role: "assistant", text: "" }]);
    setInput("");
    setBusy(true);
    try {
      // The API conversation must start with a user turn — drop the
      // canned assistant greeting that opens the thread.
      const msgs: CopilotMessage[] = next.map((t) => ({
        role: t.role,
        content: t.text,
      }));
      while (msgs.length && msgs[0].role === "assistant") msgs.shift();

      const resp = await runOnboardingCopilot(msgs, {
        onDelta: (chunk) =>
          setThread((t) =>
            t.map((it, i) =>
              i === t.length - 1 && it.role === "assistant"
                ? { ...it, text: it.text + chunk }
                : it,
            ),
          ),
      });
      const study = resp.proposed_actions.find(
        (a) => a.type === "create_first_study",
      );
      const repliesAction = resp.proposed_actions.find(
        (a) => a.type === "suggest_replies",
      );
      const websiteAction = resp.proposed_actions.find(
        (a) => a.type === "request_website",
      );
      const replies = repliesAction?.options?.length
        ? { context: repliesAction.context, options: repliesAction.options }
        : undefined;
      const website = websiteAction
        ? { prompt: websiteAction.prompt || "Paste your company URL." }
        : undefined;
      setThread((t) =>
        t.map((it, i) =>
          i === t.length - 1 && it.role === "assistant"
            ? { ...it, text: resp.reply, study, replies, website }
            : it,
        ),
      );
      // Profile fields may have been written by `save_profile` —
      // refresh `me` so the "What I know about you" panel updates.
      getMe().then(setMe).catch(() => undefined);
    } catch {
      setThread((t) =>
        t.map((it, i) =>
          i === t.length - 1 && it.role === "assistant"
            ? { ...it, text: "Sorry — I couldn't respond just now. Please try again." }
            : it,
        ),
      );
    } finally {
      setBusy(false);
    }
  };

  const acceptStudy = async (study: ProposedAction) => {
    if (creating) return;
    setCreating(true);
    try {
      const project = await createProject({
        name: study.study_name || "My first study",
        language: "en",
        questions: [],
      });
      if (study.objective) {
        await patchProjectSettings(project.id, {
          research_objective: study.objective,
        });
      }
      for (const q of (study.questions ?? []) as ProposedGuideQuestion[]) {
        await createGuideQuestion(project.id, {
          section_title: q.section_title,
          main_question: q.main_question,
          desired_learning: q.desired_learning,
        });
      }
      await completeOnboarding({});
      setCachedOnboarded(true);
      const memory = await getOnboardingMemory().catch(() => "");
      setDone({
        projectId: project.id,
        studyName: study.study_name || "Your study",
        memory,
      });
      setCreating(false);
    } catch {
      toast("Couldn't set up your study — please try again.", "error");
      setCreating(false);
    }
  };

  // Mark a turn's chip/website attachment as consumed once the user has
  // acted on it — keeps the chips from re-appearing alongside later turns.
  const consumeAttachment = (turnIndex: number) => {
    setThread((t) =>
      t.map((it, i) => (i === turnIndex ? { ...it, consumed: true } : it)),
    );
  };

  // After a website lookup, drop the resulting summary into the conversation
  // as the user's next message so the agent can incorporate it.
  const handleWebsiteLookup = async (turnIndex: number, url: string) => {
    if (!url || busy) return;
    consumeAttachment(turnIndex);
    try {
      const res = await analyseWebsite(url);
      const summary = (res.business_summary || "").trim();
      if (!summary) {
        toast("Couldn't read that site — try a different URL.", "error");
        return;
      }
      // Refresh `me` — backend will have saved website_url + business_summary.
      getMe().then(setMe).catch(() => undefined);
      await send(`Our company: ${url}\n\n${summary}`);
    } catch {
      toast("Couldn't read that site — try a different URL.", "error");
    }
  };

  const skip = async () => {
    if (creating) return;
    setCreating(true);
    try {
      await completeOnboarding({});
      setCachedOnboarded(true);
      navigate("/dashboard", { replace: true });
    } catch {
      toast("Something went wrong — please try again.", "error");
      setCreating(false);
    }
  };

  if (!me) return null;

  // Phase: tell-me-about-your-work until 2+ profile fields are set; frame
  // your study until the agent has proposed one; launch once accepted.
  const profileFields: { key: keyof CompanyResponse; label: string }[] = [
    { key: "role", label: "Role" },
    { key: "company_size", label: "Team size" },
    { key: "industry", label: "Industry" },
    { key: "use_case", label: "Use case" },
  ];
  const profileFilled = profileFields.filter((f) => !!me[f.key]).length;
  const studyProposed = thread.some((t) => !!t.study);
  const phase: Phase = done
    ? "launch"
    : studyProposed
      ? "frame"
      : profileFilled >= 2
        ? "frame"
        : "profile";

  if (done) {
    return (
      <div className="onboarding">
        <header className="onboarding__bar">
          <span className="onboarding__brand">QualiPulse</span>
        </header>
        <div className="onboarding-done">
          <div className="onboarding-done__eyebrow">✦ You're all set</div>
          <h1 className="onboarding-done__title">{done.studyName}</h1>
          <p className="onboarding-done__sub">
            Your first study is ready — build it out and launch when you are.
          </p>
          <div className="onboarding-done__memory">
            <div className="onboarding-done__memory-label">
              Here's what I'll remember about your research
            </div>
            <p className="onboarding-done__memory-text">
              {done.memory.trim() ||
                "I'll learn more about your research as we work together."}
            </p>
          </div>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() =>
              navigate(`/projects/${done.projectId}`, { replace: true })
            }
          >
            Open your study →
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="onboarding">
      {creating && (
        <div className="onboarding__overlay">
          <p>Setting up your study…</p>
        </div>
      )}

      <header className="onboarding__bar">
        <span className="onboarding__brand">QualiPulse</span>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={skip}
          disabled={creating}
        >
          Skip — just take me in
        </button>
      </header>

      {!me.email_verified && (
        <div className="onboarding__verify">
          Verify your email when you get a moment — check your inbox.{" "}
          <button
            type="button"
            className="onboarding__verify-resend"
            onClick={() =>
              resendVerification()
                .then(() => toast("Verification email sent.", "success"))
                .catch(() => toast("Couldn't resend right now.", "error"))
            }
          >
            Resend
          </button>
        </div>
      )}

      <MilestoneBar phase={phase} />

      <div className="onboarding__layout">
        <ProfileSidebar me={me} profileFields={profileFields} />

        <div className="onboarding__main">
          <div className="onboarding__thread" ref={threadRef}>
            {thread.map((it, i) => {
              const lastTurn = i === thread.length - 1;
              const showAttachments = lastTurn && !it.consumed && !busy;
              return (
                <div
                  key={i}
                  className={`onboarding-msg onboarding-msg--${it.role}`}
                >
                  {it.text && (
                    <div className="onboarding-msg__text">
                      {renderRich(it.text)}
                    </div>
                  )}
                  {it.study && (
                    <StudyCard
                      study={it.study}
                      onAccept={() => acceptStudy(it.study!)}
                      disabled={creating}
                    />
                  )}
                  {showAttachments && it.website && (
                    <WebsiteCard
                      prompt={it.website.prompt}
                      disabled={busy || creating}
                      onLookup={(url) => handleWebsiteLookup(i, url)}
                      onSkip={() => consumeAttachment(i)}
                    />
                  )}
                  {showAttachments && it.replies && (
                    <ReplyChips
                      options={it.replies.options}
                      disabled={busy || creating}
                      onPick={(text) => {
                        consumeAttachment(i);
                        send(text);
                      }}
                    />
                  )}
                </div>
              );
            })}
            {busy && (
              <div className="onboarding-msg onboarding-msg--assistant">
                <div className="onboarding-msg__text onboarding-msg__text--thinking">
                  Drafting…
                </div>
              </div>
            )}
          </div>

          <div className="onboarding__input">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(input);
            }
          }}
          placeholder="Tell the copilot what you want to learn…"
          rows={2}
          disabled={busy || creating}
        />
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => send(input)}
          disabled={busy || creating || !input.trim()}
        >
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function MilestoneBar({ phase }: { phase: Phase }) {
  const steps: { id: Phase; label: string }[] = [
    { id: "profile", label: "Tell me about your work" },
    { id: "frame", label: "Frame your study" },
    { id: "launch", label: "Launch" },
  ];
  const order: Phase[] = ["profile", "frame", "launch"];
  const currentIdx = order.indexOf(phase);
  return (
    <ol className="onboarding-milestones" aria-label="Onboarding progress">
      {steps.map((s, i) => {
        const state = i < currentIdx ? "done" : i === currentIdx ? "active" : "todo";
        return (
          <li
            key={s.id}
            className={`onboarding-milestones__step onboarding-milestones__step--${state}`}
          >
            <span className="onboarding-milestones__dot" aria-hidden>
              {state === "done" ? "✓" : i + 1}
            </span>
            <span className="onboarding-milestones__label">{s.label}</span>
          </li>
        );
      })}
    </ol>
  );
}

function ProfileSidebar({
  me,
  profileFields,
}: {
  me: CompanyResponse;
  profileFields: { key: keyof CompanyResponse; label: string }[];
}) {
  const summary = (me.business_summary || "").trim();
  return (
    <aside className="onboarding-sidebar" aria-label="What the copilot knows">
      <div className="onboarding-sidebar__eyebrow">What I know about you</div>
      <ul className="onboarding-sidebar__list">
        {profileFields.map((f) => {
          const value = (me[f.key] as string | null | undefined) || "";
          return (
            <li
              key={String(f.key)}
              className={`onboarding-sidebar__row onboarding-sidebar__row--${value ? "filled" : "empty"}`}
            >
              <span className="onboarding-sidebar__check" aria-hidden>
                {value ? "✓" : "○"}
              </span>
              <span className="onboarding-sidebar__label">{f.label}</span>
              {value && (
                <span className="onboarding-sidebar__value">{value}</span>
              )}
            </li>
          );
        })}
      </ul>
      {summary && (
        <div className="onboarding-sidebar__summary">
          <div className="onboarding-sidebar__summary-label">
            Your company
          </div>
          <p className="onboarding-sidebar__summary-text">{summary}</p>
        </div>
      )}
    </aside>
  );
}

function ReplyChips({
  options,
  disabled,
  onPick,
}: {
  options: string[];
  disabled: boolean;
  onPick: (text: string) => void;
}) {
  return (
    <div className="onboarding-chips" role="group" aria-label="Quick replies">
      {options.map((opt) => (
        <button
          key={opt}
          type="button"
          className="onboarding-chip"
          disabled={disabled}
          onClick={() => onPick(opt)}
        >
          {opt}
        </button>
      ))}
    </div>
  );
}

function WebsiteCard({
  prompt,
  disabled,
  onLookup,
  onSkip,
}: {
  prompt: string;
  disabled: boolean;
  onLookup: (url: string) => void;
  onSkip: () => void;
}) {
  const [url, setUrl] = useState("");
  const [working, setWorking] = useState(false);
  const submit = async () => {
    const v = url.trim();
    if (!v || working) return;
    setWorking(true);
    await onLookup(v);
    setWorking(false);
  };
  return (
    <div className="onboarding-website">
      <div className="onboarding-website__eyebrow">✦ Quick lookup</div>
      <p className="onboarding-website__prompt">{prompt}</p>
      <div className="onboarding-website__row">
        <input
          type="url"
          inputMode="url"
          autoComplete="url"
          placeholder="https://yourcompany.com"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              submit();
            }
          }}
          disabled={disabled || working}
        />
        <button
          type="button"
          className="btn btn-primary btn-sm"
          onClick={submit}
          disabled={disabled || working || !url.trim()}
        >
          {working ? "Reading…" : "Look it up"}
        </button>
      </div>
      <button
        type="button"
        className="onboarding-website__skip"
        onClick={onSkip}
        disabled={disabled || working}
      >
        I'd rather just tell you
      </button>
    </div>
  );
}

function StudyCard({
  study,
  onAccept,
  disabled,
}: {
  study: ProposedAction;
  onAccept: () => void;
  disabled: boolean;
}) {
  const questions = (study.questions ?? []) as ProposedGuideQuestion[];
  return (
    <div className="onboarding-study">
      <div className="onboarding-study__eyebrow">✦ Your first study</div>
      <div className="onboarding-study__name">{study.study_name}</div>
      {study.objective && (
        <p className="onboarding-study__objective">{study.objective}</p>
      )}
      <ol className="onboarding-study__questions">
        {questions.map((q, i) => (
          <li key={i}>
            <span className="onboarding-study__section">{q.section_title}</span>
            {q.main_question}
          </li>
        ))}
      </ol>
      <div className="onboarding-study__actions">
        <button
          type="button"
          className="btn btn-primary btn-sm"
          onClick={onAccept}
          disabled={disabled}
        >
          Create this study
        </button>
        <span className="onboarding-study__hint">
          or keep chatting to refine it
        </span>
      </div>
    </div>
  );
}
