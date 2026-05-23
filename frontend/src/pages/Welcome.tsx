import { Fragment, ReactNode, useEffect, useRef, useState } from "react";
import { Trans, useTranslation } from "react-i18next";
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
  createLink,
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

/**
 * Compute "Day X of Y" for the trial chip on the completion screen.
 * Returns null when the trial has ended or no trial_ends_at is set.
 */
function trialDayInfo(trialEndsAt: string | null | undefined): {
  day: number;
  total: number;
} | null {
  if (!trialEndsAt) return null;
  const end = new Date(trialEndsAt).getTime();
  if (!Number.isFinite(end)) return null;
  const now = Date.now();
  // Assume a 14-day trial (matches backend bootstrap); start = end - 14d.
  const total = 14;
  const start = end - total * 24 * 60 * 60 * 1000;
  if (now < start || now > end) return null;
  const elapsed = Math.floor((now - start) / (24 * 60 * 60 * 1000));
  return { day: Math.max(1, Math.min(total, elapsed + 1)), total };
}

/**
 * W3.6 — soft plan suggestion. Maps captured `company_size` to the
 * plan that fits, so the completion screen plants the price anchor
 * the user will eventually see. No CTA — just a quiet line.
 * Returns null when we don't have enough signal to suggest.
 */
function planSuggestion(companySize: string | null | undefined): {
  name: string;
  monthly: string;
} | null {
  const size = (companySize || "").trim();
  if (!size) return null;
  if (size === "1–10" || size === "1-10") {
    return { name: "Exploration", monthly: "€89" };
  }
  if (size === "11–50" || size === "11-50" || size === "51–200" || size === "51-200") {
    return { name: "Team", monthly: "€299" };
  }
  if (size === "201–1000" || size === "201-1000" || size === "1000+") {
    return { name: "Agency", monthly: "€799" };
  }
  return null;
}

// The canned greeting is i18n'd — the actual string lives in
// frontend/src/locales/{en,fr}/onboarding.json under "greeting" and
// interpolates {{firstName}}.

export default function Welcome() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { t } = useTranslation("onboarding");

  const [me, setMe] = useState<CompanyResponse | null>(null);
  const [thread, setThread] = useState<ThreadItem[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  /** Live narration of which tool the agent is running ("Drafting your
   *  study", "Lining up some options"). Shown in the thinking bubble in
   *  place of the generic "Drafting…" string. Cleared between turns. */
  const [statusLabel, setStatusLabel] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [done, setDone] = useState<{
    projectId: string;
    studyName: string;
    memory: string;
    profileSummary: string;
    interviewToken: string | null;
  } | null>(null);
  // W3.5 — controls the "want a recap by email?" verify modal on the
  // completion screen. Initial value reads localStorage so a refresh
  // doesn't re-pop the modal once the user dismissed it.
  const [verifyModalDismissed, setVerifyModalDismissed] = useState<boolean>(
    () => {
      try {
        return localStorage.getItem("verify_modal_dismissed") === "1";
      } catch {
        return false;
      }
    },
  );
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
          {
            role: "assistant",
            text: t("greeting", { firstName: m.first_name || "there" }),
          },
        ]);
      })
      .catch(() => navigate("/login", { replace: true }));
    // eslint-disable-next-line react-hooks/exhaustive-deps — `t` swap would
    // rewrite the greeting in-place after a language toggle, but the
    // canned greeting is meant to stay in the language captured at first
    // load (matches the user's chosen account language at signup).
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

      setStatusLabel(null);
      const resp = await runOnboardingCopilot(msgs, {
        onStatus: (label) => setStatusLabel(label),
        onDelta: (chunk) =>
          setThread((prev) =>
            prev.map((it, i) =>
              i === prev.length - 1 && it.role === "assistant"
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
      setThread((prev) =>
        prev.map((it, i) =>
          i === prev.length - 1 && it.role === "assistant"
            ? { ...it, text: resp.reply, study, replies, website }
            : it,
        ),
      );
      // Profile fields may have been written by `save_profile` —
      // refresh `me` so the "What I know about you" panel updates.
      getMe().then(setMe).catch(() => undefined);
    } catch {
      setThread((prev) =>
        prev.map((it, i) =>
          i === prev.length - 1 && it.role === "assistant"
            ? { ...it, text: t("chat_error") }
            : it,
        ),
      );
    } finally {
      setBusy(false);
      setStatusLabel(null);
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
      // Auto-create the first interview link so the completion screen's
      // "Take your own interview" + "Share your link" CTAs are usable
      // immediately — no extra click. If link creation fails the user
      // can still create one from the project page, so we don't block.
      let interviewToken: string | null = null;
      try {
        const link = await createLink(project.id);
        interviewToken = link.token;
      } catch {
        interviewToken = null;
      }
      await completeOnboarding({});
      setCachedOnboarded(true);
      const recap = await getOnboardingMemory().catch(() => ({
        memory: "",
        profile_summary: "",
      }));
      setDone({
        projectId: project.id,
        studyName: study.study_name || "Your study",
        memory: recap.memory,
        profileSummary: recap.profile_summary,
        interviewToken,
      });
      setCreating(false);
    } catch {
      toast(t("toast.study_setup_failed"), "error");
      setCreating(false);
    }
  };

  // Mark a turn's chip/website attachment as consumed once the user has
  // acted on it — keeps the chips from re-appearing alongside later turns.
  const consumeAttachment = (turnIndex: number) => {
    setThread((prev) =>
      prev.map((it, i) => (i === turnIndex ? { ...it, consumed: true } : it)),
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
        toast(t("toast.website_unreadable"), "error");
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
      toast(t("toast.skip_failed"), "error");
      setCreating(false);
    }
  };

  if (!me) return null;

  // Phase: tell-me-about-your-work until 2+ profile fields are set; frame
  // your study until the agent has proposed one; launch once accepted.
  const profileFields: { key: keyof CompanyResponse; label: string }[] = [
    { key: "role", label: t("sidebar.role") },
    { key: "company_size", label: t("sidebar.team_size") },
    { key: "industry", label: t("sidebar.industry") },
    { key: "use_case", label: t("sidebar.use_case") },
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
    const trial = trialDayInfo(me.trial_ends_at);
    const interviewUrl = done.interviewToken
      ? `${window.location.origin}/interview/${done.interviewToken}`
      : null;
    const handleShareLink = async () => {
      if (!interviewUrl) {
        toast(t("toast.no_link"), "error");
        return;
      }
      try {
        await navigator.clipboard.writeText(interviewUrl);
        toast(t("toast.link_copied"), "success");
      } catch {
        toast(t("toast.link_copy_failed"), "error");
      }
    };
    // Prefer the deterministic profile summary (concrete facts the
    // server built from captured fields) over the agent's free-form
    // memory note. Fall back gracefully.
    const recapText =
      done.profileSummary.trim() ||
      done.memory.trim() ||
      t("done.memory_fallback");

    // W3.6 — soft plan line, only when we have signal.
    const plan = planSuggestion(me.company_size);

    // W3.5 — only show the recap-by-email modal once per browser and
    // only when an unverified email is the actual obstacle.
    const showVerifyModal = !me.email_verified && !verifyModalDismissed;
    const dismissVerifyModal = () => {
      try {
        localStorage.setItem("verify_modal_dismissed", "1");
      } catch {
        /* no-op — sessionStorage / private mode */
      }
      setVerifyModalDismissed(true);
    };
    const acceptVerifyModal = () => {
      resendVerification()
        .then(() => toast(t("toast.verify_sent"), "success"))
        .catch(() => toast(t("toast.resend_error"), "error"));
      dismissVerifyModal();
    };

    return (
      <div className="onboarding">
        <header className="onboarding__bar">
          <span className="onboarding__brand">QualiPulse</span>
          {trial && (
            <span
              className="onboarding-trial-chip"
              title={t("done.trial_chip", { day: trial.day, total: trial.total })}
            >
              {t("done.trial_chip", { day: trial.day, total: trial.total })}
            </span>
          )}
        </header>
        <div className="onboarding-done">
          <div className="onboarding-done__eyebrow">
            ✦ {t("done.eyebrow")}
          </div>
          <h1 className="onboarding-done__title">{done.studyName}</h1>
          <p className="onboarding-done__sub">{t("done.sub")}</p>

          <div className="onboarding-done__memory">
            <div className="onboarding-done__memory-label">
              {t("done.memory_label")}
            </div>
            <p className="onboarding-done__memory-text">{recapText}</p>
          </div>

          {plan && (
            <p className="onboarding-done__plan-hint">
              <Trans
                ns="onboarding"
                i18nKey="done.plan_hint"
                values={{ planName: plan.name, monthly: plan.monthly }}
                components={{ strong: <strong /> }}
              />
            </p>
          )}

          <div className="onboarding-done__actions">
            <button
              type="button"
              className="btn btn-primary onboarding-done__cta--primary"
              disabled={!interviewUrl}
              onClick={() => {
                if (!interviewUrl) {
                  toast(t("toast.no_link_short"), "error");
                  return;
                }
                window.open(interviewUrl, "_blank", "noopener");
              }}
            >
              <span className="onboarding-done__cta-label">
                {t("done.cta_take_interview")}
              </span>
              <span className="onboarding-done__cta-hint">
                {t("done.cta_take_interview_hint")}
              </span>
            </button>

            <div className="onboarding-done__cta-row">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleShareLink}
                disabled={!interviewUrl}
              >
                {t("done.cta_copy_link")}
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() =>
                  navigate(`/projects/${done.projectId}`, { replace: true })
                }
              >
                {t("done.cta_open_study")}
              </button>
            </div>
          </div>
        </div>

        {showVerifyModal && (
          <div
            className="onboarding-verify-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="verify-modal-title"
          >
            <div className="onboarding-verify-modal__card">
              <div className="onboarding-verify-modal__eyebrow">
                ✦ {t("verify_modal.eyebrow")}
              </div>
              <h2
                id="verify-modal-title"
                className="onboarding-verify-modal__title"
              >
                {t("verify_modal.title")}
              </h2>
              <p className="onboarding-verify-modal__body">
                {t("verify_modal.body")}
              </p>
              <div className="onboarding-verify-modal__actions">
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={acceptVerifyModal}
                >
                  {t("verify_modal.accept")}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={dismissVerifyModal}
                >
                  {t("verify_modal.dismiss")}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="onboarding">
      {creating && (
        <div className="onboarding__overlay">
          <p>{t("setting_up")}</p>
        </div>
      )}

      <header className="onboarding__bar">
        <span className="onboarding__brand">QualiPulse</span>
        <button
          type="button"
          className="onboarding__skip"
          onClick={skip}
          disabled={creating}
        >
          {t("skip")}
        </button>
      </header>

      {!me.email_verified && (
        <div className="onboarding__verify">
          {t("verify_banner")}{" "}
          <button
            type="button"
            className="onboarding__verify-resend"
            onClick={() =>
              resendVerification()
                .then(() => toast(t("toast.resend_success"), "success"))
                .catch(() => toast(t("toast.resend_error"), "error"))
            }
          >
            {t("verify_resend")}
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
              <div
                className="onboarding-msg onboarding-msg--assistant"
                aria-live="polite"
              >
                <div className="onboarding-msg__text onboarding-msg__text--thinking">
                  {statusLabel ? `${statusLabel}…` : t("thinking_fallback")}
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
          placeholder={t("input_placeholder")}
          rows={2}
          disabled={busy || creating}
        />
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => send(input)}
          disabled={busy || creating || !input.trim()}
        >
              {t("send")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function MilestoneBar({ phase }: { phase: Phase }) {
  const { t } = useTranslation("onboarding");
  const steps: { id: Phase; label: string }[] = [
    { id: "profile", label: t("phase.profile") },
    { id: "frame", label: t("phase.frame") },
    { id: "launch", label: t("phase.launch") },
  ];
  const order: Phase[] = ["profile", "frame", "launch"];
  const currentIdx = order.indexOf(phase);
  return (
    <ol className="onboarding-milestones" aria-label={t("phase.profile")}>
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
  const { t } = useTranslation("onboarding");
  const summary = (me.business_summary || "").trim();
  return (
    <aside className="onboarding-sidebar" aria-label={t("sidebar.eyebrow")}>
      <div className="onboarding-sidebar__eyebrow">{t("sidebar.eyebrow")}</div>
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
            {t("sidebar.company")}
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
  const { t } = useTranslation("onboarding");
  return (
    <div
      className="onboarding-chips"
      role="group"
      aria-label={t("sidebar.eyebrow")}
    >
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
  const { t } = useTranslation("onboarding");
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
      <div className="onboarding-website__eyebrow">
        ✦ {t("website.eyebrow")}
      </div>
      <p className="onboarding-website__prompt">
        {prompt || t("website.default_prompt")}
      </p>
      <div className="onboarding-website__row">
        <input
          type="url"
          inputMode="url"
          autoComplete="url"
          placeholder={t("website.url_placeholder")}
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
          {working ? t("website.reading") : t("website.lookup_cta")}
        </button>
      </div>
      <button
        type="button"
        className="onboarding-website__skip"
        onClick={onSkip}
        disabled={disabled || working}
      >
        {t("website.skip")}
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
  const { t } = useTranslation("onboarding");
  const questions = (study.questions ?? []) as ProposedGuideQuestion[];
  return (
    <div className="onboarding-study">
      <div className="onboarding-study__eyebrow">
        ✦ {t("study.eyebrow")}
      </div>
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
      {typeof study.recommended_participants === "number" && (
        <div className="onboarding-study__recommend">
          <span className="onboarding-study__recommend-label">
            {t("study.recommended_label")}
          </span>
          <span className="onboarding-study__recommend-value">
            {t("study.recommended_value", {
              count: study.recommended_participants,
            })}
          </span>
        </div>
      )}
      <div className="onboarding-study__actions">
        <button
          type="button"
          className="btn btn-primary btn-sm"
          onClick={onAccept}
          disabled={disabled}
        >
          {t("study.create_cta")}
        </button>
        <span className="onboarding-study__hint">
          {t("study.hint")}
        </span>
      </div>
    </div>
  );
}
