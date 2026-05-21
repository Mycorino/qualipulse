import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  getMe,
  completeOnboarding,
  resendVerification,
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
};

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
      setThread((t) =>
        t.map((it, i) =>
          i === t.length - 1 && it.role === "assistant"
            ? { ...it, text: resp.reply, study }
            : it,
        ),
      );
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

      <div className="onboarding__thread" ref={threadRef}>
        {thread.map((it, i) => (
          <div key={i} className={`onboarding-msg onboarding-msg--${it.role}`}>
            {it.text && (
              <div className="onboarding-msg__text">{it.text}</div>
            )}
            {it.study && (
              <StudyCard
                study={it.study}
                onAccept={() => acceptStudy(it.study!)}
                disabled={creating}
              />
            )}
          </div>
        ))}
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
