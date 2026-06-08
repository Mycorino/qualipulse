import { Fragment, ReactNode, useEffect, useRef, useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import {
  getMe,
  completeOnboarding,
  resendVerification,
  analyseWebsite,
  saveOnboardingProfile,
  type CompanyResponse,
} from "../api/auth";
import {
  runOnboardingCopilot,
  getOnboardingMemory,
  getOnboardingConversation,
  saveOnboardingConversation,
  transcribeDemoAudio,
  prepWelcomeGreeting,
  getStarterSuggestions,
  getDemoBundle,
  getDemoOpeningQuestion,
  createResearchPlan,
  createOnboardingStudy,
  type CopilotMessage,
  type DemoTranscribeResponse,
  type ProposedAction,
  type ProposedGuideQuestion,
  type DemoBundle,
  type DemoBundleExample,
  type DemoBundleTheme,
} from "../api/copilot";
// Project-level APIs no longer needed here — study creation uses the
// atomic /onboarding/study endpoint via createOnboardingStudy.
import { useAudioRecorder } from "../hooks/useAudioRecorder";
import { setCachedOnboarded } from "../hooks/useAuth";
import { useToast } from "../components/Toast";
import client from "../api/client";
import WelcomeSetup, { ROLES, TEAM_SIZES, USE_CASES } from "./WelcomeSetup";

// Direction #1 (free-first PLG): the paid plan a user clicked on the pricing
// page is stashed in localStorage at signup. On the completion screen we offer
// a one-click upgrade so the strongest purchase signal isn't lost to a hunt
// for the billing page. Display names map plan id → label.
const SIGNUP_PLAN_LABELS: Record<string, string> = {
  exploration: "Exploration",
  team: "Team",
  agency: "Agency",
};

function readSignupUpgrade(): { planId: string; interval: string; label: string } | null {
  try {
    const planId = (localStorage.getItem("qp_signup_plan") || "").toLowerCase();
    const label = SIGNUP_PLAN_LABELS[planId];
    if (!label) return null;
    const interval = localStorage.getItem("qp_signup_interval") === "annual" ? "annual" : "monthly";
    return { planId, interval, label };
  } catch {
    return null;
  }
}

// Per-key canonical option sets — when the user clicks one of these
// sidebar rows we render a chip picker rather than a free-text input,
// because the agent + plan-recommendation logic both key off these
// exact strings.
const CANONICAL_BY_FIELD: Partial<Record<keyof CompanyResponse, string[]>> = {
  role: ROLES,
  company_size: TEAM_SIZES,
  use_case: USE_CASES,
};

/**
 * Welcome — the conversational onboarding.
 *
 * The new researcher's first conversation with the Research Copilot.
 * Instead of a 4-step form, the agent asks what they want to learn and
 * drafts a real first study. The opening greeting is canned (instant, no
 * API); the model is only called once the researcher answers.
 */

let _threadItemId = 0;
function nextThreadId(): string {
  return `ti-${++_threadItemId}-${Date.now()}`;
}

type ThreadItem = {
  id: string;
  role: "user" | "assistant";
  text: string;
  /** Attached to an assistant turn that proposed the first study. */
  study?: ProposedAction;
  /** Attached when the agent proposed a multi-step research plan (Wave E). */
  plan?: ProposedAction;
  /** Tap-to-answer chips the agent attached to this turn. */
  replies?: { context?: string; options: string[] };
  /** Website-lookup card the agent attached to this turn. */
  website?: { prompt: string };
  /** Participant-experience demo card the agent attached to this turn. */
  participantDemo?: { intro: string };
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
  const { t, i18n } = useTranslation("onboarding");

  const [me, setMe] = useState<CompanyResponse | null>(null);
  const [thread, setThread] = useState<ThreadItem[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  /** Live narration of which tool the agent is running ("Drafting your
   *  study", "Lining up some options"). Shown in the thinking bubble in
   *  place of the generic "Drafting…" string. Cleared between turns. */
  const [statusLabel, setStatusLabel] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  // Direction #1 — paid-plan upgrade offered on the completion screen.
  const [upgrading, setUpgrading] = useState(false);
  const signupUpgrade = readSignupUpgrade();
  const [done, setDone] = useState<{
    projectId: string;
    studyName: string;
    memory: string;
    profileSummary: string;
    interviewToken: string | null;
  } | null>(null);
  // V2 — controls the "see a sample study first" preview overlay.
  // Lets evaluators look at what a finished study card looks like
  // without committing to drafting their own.
  const [showSamplePreview, setShowSamplePreview] = useState(false);

  // V3 — participant-experience demo modal. Opened from the inline
  // demo card the agent posts after the user's first message.
  const [showParticipantDemo, setShowParticipantDemo] = useState(false);
  // Track whether the user opened the demo at least once — after
  // closing, we fire a synthetic "continue" message so the agent
  // proceeds to the plan proposal without the user having to nudge.
  const demoOpenedRef = useRef(false);

  // W3.5 — controls the "want a recap by email?" verify modal on the
  // completion screen. Initial value reads localStorage so a refresh
  // doesn't re-pop the modal once the user dismissed it.
  // Key is scoped to company ID so multi-account browsers don't cross-leak.
  const verifyDismissKey = me ? `verify_modal_dismissed_${me.id}` : "verify_modal_dismissed";
  const [verifyModalDismissed, setVerifyModalDismissed] = useState<boolean>(
    () => {
      try {
        // Check both legacy (unscoped) and scoped keys for backwards compat.
        return (
          localStorage.getItem("verify_modal_dismissed") === "1" ||
          localStorage.getItem(verifyDismissKey) === "1"
        );
      } catch {
        return false;
      }
    },
  );
  const threadRef = useRef<HTMLDivElement>(null);
  // Auto-scroll bookkeeping. We only yank the thread to the bottom when
  // the user is already near the bottom — otherwise they're reading
  // earlier in the conversation and we must not steal their scroll.
  const isAtBottomRef = useRef(true);
  const prevThreadLenRef = useRef(0);
  // Server-side conversation version (Wave A Fix 4). Held in a ref
  // because writes are fire-and-forget — a stale read just clobbers
  // the version cheaply.
  const convoVersionRef = useRef<number>(0);
  // Latch the wizard-vs-chat decision on the first render where `me` is
  // loaded. Without this, step 1/2 saving a profile field (role,
  // company_size, use_case) flips `phase1Complete` to true mid-wizard,
  // which unmounts WelcomeSetup BEFORE step 3 ("Le deal") can render —
  // making the deal screen dead code. Once the wizard owns the screen it
  // keeps it until the user finishes or skips (via onComplete).
  const wizardLatchRef = useRef<boolean | null>(null);
  const [wizardFinished, setWizardFinished] = useState(false);

  // Load the researcher, redirect out if already onboarded, hydrate the
  // persisted conversation thread when present, and otherwise seed the
  // instant canned greeting.
  useEffect(() => {
    getMe()
      .then(async (m) => {
        if (m.onboarding_completed) {
          navigate("/dashboard", { replace: true });
          return;
        }
        setMe(m);
        // Wave A Fix 4 — hydrate any prior turns first. If the fetch
        // succeeds and returns turns, render them as the seed (drop
        // attachments — restoring `study` / `replies` / `website` /
        // `participantDemo` from history is a separate task). If empty
        // or failing, fall back to the canned greeting.
        let hydrated: ThreadItem[] | null = null;
        try {
          const convo = await getOnboardingConversation();
          convoVersionRef.current = convo.version || 0;
          if (Array.isArray(convo.thread) && convo.thread.length > 0) {
            hydrated = (convo.thread as Array<Record<string, unknown>>)
              .map((raw) => {
                const role = raw.role === "user" ? "user" : "assistant";
                // Tolerate either `text` or `content` — different writers
                // may have used either shape.
                const text =
                  typeof raw.text === "string"
                    ? (raw.text as string)
                    : typeof raw.content === "string"
                      ? (raw.content as string)
                      : "";
                return text ? ({ id: nextThreadId(), role, text } as ThreadItem) : null;
              })
              .filter((x): x is ThreadItem => x !== null);
            if (hydrated.length === 0) hydrated = null;
          }
        } catch {
          // Silent fallback — never block onboarding on a hydration miss.
          hydrated = null;
        }
        if (hydrated) {
          setThread(hydrated);
          return;
        }
        // If the user came through the structured wizard, the agent's
        // canned greeting acknowledges what we already know rather
        // than re-asking. Different greeting key, same shape.
        const greetingKey =
          m.role && m.company_size && m.use_case
            ? "greeting_post_wizard"
            : "greeting";
        setThread([
          {
            id: nextThreadId(),
            role: "assistant",
            text: t(greetingKey, {
              firstName: m.first_name || "there",
              role: m.role || "",
              useCase: (m.use_case || "").toLowerCase(),
            }),
          },
        ]);
        // If the wizard was completed, ask the backend for a Haiku-
        // personalised greeting. Replaces the canned greeting in-
        // place when it lands. Fails silent.
        //
        // Race: for freemail signups, the company-name backfill runs
        // async after the wizard completes — business_summary may not
        // yet exist when this fires. Poll a few times before giving up.
        const wizardComplete =
          !!m.role && !!m.company_size && !!m.use_case;
        if (wizardComplete) {
          let attempt = 0;
          const maxAttempts = 3;
          const tryGreeting = () => {
            attempt += 1;
            prepWelcomeGreeting()
              .then((text) => {
                if (text) {
                  setThread((prev) =>
                    prev.length === 1 && prev[0].role === "assistant"
                      ? [{ ...prev[0], text }]
                      : prev,
                  );
                  // Also refresh `me` so the sidebar picks up the
                  // backfilled business_summary + industry.
                  getMe().then(setMe).catch(() => undefined);
                  return;
                }
                if (attempt < maxAttempts) {
                  // 3s, 6s back-off — covers the typical Haiku +
                  // backfill round-trip without polling forever.
                  setTimeout(tryGreeting, 3000 * attempt);
                }
              })
              .catch(() => undefined);
          };
          tryGreeting();
        }
      })
      .catch(() => navigate("/login", { replace: true }));
    // eslint-disable-next-line react-hooks/exhaustive-deps — `t` swap would
    // rewrite the greeting in-place after a language toggle, but the
    // canned greeting is meant to stay in the language captured at first
    // load (matches the user's chosen account language at signup).
  }, [navigate]);

  // Track whether the thread is currently scrolled to (within 50px of)
  // the bottom — used to gate auto-scroll on new content.
  useEffect(() => {
    const el = threadRef.current;
    if (!el) return;
    const onScroll = () => {
      const slack = el.scrollHeight - el.scrollTop - el.clientHeight;
      isAtBottomRef.current = slack < 50;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  // Auto-scroll on new content — but only when the user was already at
  // the bottom. Smooth when a brand-new turn is added; instant during
  // token-by-token streaming deltas (smooth would be jittery at ~30 fps).
  useEffect(() => {
    const el = threadRef.current;
    if (!el) return;
    if (!isAtBottomRef.current) {
      prevThreadLenRef.current = thread.length;
      return;
    }
    const newTurnAdded = thread.length > prevThreadLenRef.current;
    prevThreadLenRef.current = thread.length;
    el.scrollTo({
      top: el.scrollHeight,
      behavior: newTurnAdded ? "smooth" : "auto",
    });
  }, [thread, busy]);

  const send = async (raw: string) => {
    const text = raw.trim();
    if (!text || busy) return;
    const next: ThreadItem[] = [...thread, { id: nextThreadId(), role: "user", text }];
    // Push the user turn AND an empty assistant draft — streaming deltas
    // fill it in, the final `done` event finalises with the study proposal.
    setThread([...next, { id: nextThreadId(), role: "assistant", text: "" }]);
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
      const plan = resp.proposed_actions.find(
        (a) => a.type === "create_research_plan",
      );
      const repliesAction = resp.proposed_actions.find(
        (a) => a.type === "suggest_replies",
      );
      const websiteAction = resp.proposed_actions.find(
        (a) => a.type === "request_website",
      );
      const demoAction = resp.proposed_actions.find(
        (a) => a.type === "propose_participant_demo",
      );
      const replies = repliesAction?.options?.length
        ? { context: repliesAction.context, options: repliesAction.options }
        : undefined;
      const website = websiteAction
        ? { prompt: websiteAction.prompt || "Paste your company URL." }
        : undefined;
      const participantDemo = demoAction
        ? {
            intro:
              demoAction.intro ||
              "Want to see what your participants will experience?",
          }
        : undefined;
      setThread((prev) => {
        const updated = prev.map((it, i) =>
          i === prev.length - 1 && it.role === "assistant"
            ? {
                ...it,
                text: resp.reply,
                study,
                plan,
                replies,
                website,
                participantDemo,
              }
            : it,
        );
        // Wave A Fix 4 — persist the conversation so a router round-trip
        // (verify-email, sample modal, etc.) doesn't wipe the thread.
        // Drop attachments — only role + plain text survives to the
        // server. Fire-and-forget; never block the UI.
        const plain = updated
          .filter((it) => (it.text || "").trim().length > 0)
          .map((it) => ({ role: it.role, text: it.text }));
        saveOnboardingConversation(plain, convoVersionRef.current)
          .then((v) => {
            convoVersionRef.current = v;
          })
          .catch(() => {
            /* swallow — persistence is best-effort */
          });
        return updated;
      });
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

  const acceptPlan = async (plan: ProposedAction) => {
    if (creating) return;
    setCreating(true);
    try {
      const result = await createResearchPlan({
        plan_name: plan.plan_name || "Research plan",
        rationale: plan.rationale || "",
        steps: (plan.steps || []).map((s) => ({
          order_index: s.order_index,
          method: s.method,
          title: s.title,
          purpose: s.purpose,
          deliverable: s.deliverable,
          n_participants: s.n_participants,
          duration_weeks: s.duration_weeks,
        })),
        decision_to_inform: plan.decision_to_inform,
        timeline: plan.timeline,
        success_criteria: plan.success_criteria,
        target_customer_description: plan.target_customer_description,
        language: i18n.language || "en",
      });
      await completeOnboarding({});
      setCachedOnboarded(true);
      const recap = await getOnboardingMemory().catch(() => ({
        memory: "",
        profile_summary: "",
      }));
      if (result.project_id) {
        // Step 1 was a voice interview — Project was drafted. Land on
        // the same "your study is ready" completion screen as today.
        setDone({
          projectId: result.project_id,
          studyName: result.study_name || plan.plan_name || "Your study",
          memory: recap.memory,
          profileSummary: recap.profile_summary,
          interviewToken: result.interview_token,
        });
      } else {
        // Step 1 wasn't a voice_interview — no Project drafted yet. Land
        // them on the dashboard; their plan is saved and step 1 awaits
        // activation. (v1 limitation — other methods come later.)
        navigate("/dashboard", { replace: true });
      }
      setCreating(false);
    } catch {
      toast(t("toast.study_setup_failed"), "error");
      setCreating(false);
    }
  };

  const acceptStudy = async (study: ProposedAction) => {
    if (creating) return;
    setCreating(true);
    try {
      const result = await createOnboardingStudy({
        study_name: study.study_name || "My first study",
        language: i18n.language || "en",
        objective: study.objective,
        decision_to_inform: study.decision_to_inform,
        timeline: study.timeline,
        success_criteria: study.success_criteria,
        target_customer_description: study.target_customer_description,
        questions: ((study.questions ?? []) as ProposedGuideQuestion[]).map((q) => ({
          section_title: q.section_title,
          main_question: q.main_question,
          desired_learning: q.desired_learning,
        })),
      });
      await completeOnboarding({});
      setCachedOnboarded(true);
      const recap = await getOnboardingMemory().catch(() => ({
        memory: "",
        profile_summary: "",
      }));
      setDone({
        projectId: result.project_id,
        studyName: result.study_name || "Your study",
        memory: recap.memory,
        profileSummary: recap.profile_summary,
        interviewToken: result.interview_token,
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

  // Hybrid Phase 1 → Phase 2 handoff. Show the structured 3-step
  // wizard FIRST (unless the user has skipped it, already completed
  // the qualification fields, or made chat progress on a refresh).
  //
  // Bumped the skip-flag key to _v2 so anyone who saw the original v1
  // wizard (and then never again, because the v1 key was sticky) sees
  // the new design. Server-side check: even if the v2 skip flag is
  // set, force the wizard back on if the qualification fields are
  // ALL empty — that means the user almost certainly never finished
  // it on this account.
  const wizardSkipped = (() => {
    try {
      return localStorage.getItem("qp_welcome_setup_skipped_v2") === "1";
    } catch {
      return false;
    }
  })();
  const profileEmpty = !me.role && !me.company_size && !me.use_case;
  const phase1Complete = !!me.role && !!me.company_size && !!me.use_case;
  const hasChatProgress = thread.length > 1;
  // The skip flag only suppresses when there's evidence the user
  // genuinely engaged — at least one captured field — otherwise we
  // assume the flag is stale and re-show the wizard.
  const skipRespected = wizardSkipped && !profileEmpty;
  // First-render decision, latched (see wizardLatchRef above): once the
  // wizard owns the screen it keeps it through all 3 steps even as the
  // profile fields fill in, until the user finishes or skips.
  if (wizardLatchRef.current === null) {
    wizardLatchRef.current =
      !done && !skipRespected && !phase1Complete && !hasChatProgress;
  }
  const showSetupWizard = !wizardFinished && wizardLatchRef.current === true;
  if (showSetupWizard) {
    return (
      <WelcomeSetup
        me={me}
        onProfileSaved={setMe}
        onComplete={() => {
          try {
            localStorage.setItem("qp_welcome_setup_skipped_v2", "1");
          } catch {
            /* private-mode no-op */
          }
          setWizardFinished(true);
          getMe().then(setMe).catch(() => undefined);
        }}
      />
    );
  }

  // Phase: tell-me-about-your-work until 2+ profile fields are set; frame
  // your study until the agent has proposed one; launch once accepted.
  const profileFields: { key: keyof CompanyResponse; label: string }[] = [
    { key: "role", label: t("sidebar.role") },
    { key: "company_size", label: t("sidebar.team_size") },
    { key: "industry", label: t("sidebar.industry") },
    { key: "use_case", label: t("sidebar.use_case") },
    // V2: shown only once captured — keep the sidebar tidy for the
    // first few exchanges.
    ...(me.current_tool
      ? [
          {
            key: "current_tool" as keyof CompanyResponse,
            label: t("sidebar.current_tool"),
          },
        ]
      : []),
    ...(me.referral_source
      ? [
          {
            key: "referral_source" as keyof CompanyResponse,
            label: t("sidebar.referral_source"),
          },
        ]
      : []),
    ...(me.research_experience
      ? [
          {
            key: "research_experience" as keyof CompanyResponse,
            label: t("sidebar.research_experience"),
          },
        ]
      : []),
    ...(me.decision_role
      ? [
          {
            key: "decision_role" as keyof CompanyResponse,
            label: t("sidebar.decision_role"),
          },
        ]
      : []),
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
    const handleUpgradeFromSignup = async () => {
      if (!signupUpgrade) return;
      setUpgrading(true);
      try {
        const { data } = await client.post("/billing/checkout", {
          plan_id: signupUpgrade.planId,
          billing_interval: signupUpgrade.interval,
          success_url: window.location.origin + "/account/billing?upgraded=true",
          cancel_url: window.location.origin + "/account/billing",
        });
        // Decision made — clear the stash so we don't keep nudging.
        localStorage.removeItem("qp_signup_plan");
        localStorage.removeItem("qp_signup_interval");
        window.location.href = data.checkout_url;
      } catch {
        setUpgrading(false);
        toast(
          t("toast.upgrade_failed", {
            defaultValue: "Couldn't start checkout — you can upgrade anytime from Billing.",
          }),
          "error",
        );
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
        localStorage.setItem(verifyDismissKey, "1");
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
            {/* Wave A Fix 1c — primary CTA is "Open your study" because
             *  that's the natural next action after onboarding. The
             *  test-interview button is demoted to a tertiary ghost
             *  with its hint underneath. */}
            <button
              type="button"
              className="btn btn-primary onboarding-done__cta--primary"
              onClick={() =>
                navigate(`/projects/${done.projectId}`, { replace: true })
              }
            >
              <span className="onboarding-done__cta-label">
                {t("done.cta_open_study")}
              </span>
            </button>

            {/* Direction #1: one-click upgrade for users who arrived via a
             *  paid plan card. They still started free; this just makes the
             *  buy button reachable without hunting for /account/billing. */}
            {signupUpgrade && (
              <button
                type="button"
                className="btn btn-secondary"
                disabled={upgrading}
                onClick={handleUpgradeFromSignup}
              >
                {upgrading
                  ? t("common:loading", { defaultValue: "Loading…" })
                  : t("done.cta_upgrade", {
                      defaultValue: "Upgrade to {{plan}} →",
                      plan: signupUpgrade.label,
                    })}
              </button>
            )}

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
              className="btn btn-ghost onboarding-done__cta--tertiary"
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
        <ProfileSidebar
          me={me}
          profileFields={profileFields}
          onChange={async (key, value) => {
            // Optimistic UI — sidebar shows the new value immediately, then
            // the network call confirms. PATCH /auth/onboarding accepts
            // partial profile updates.
            setMe((prev) => (prev ? { ...prev, [key]: value } : prev));
            try {
              await saveOnboardingProfile({ [key]: value });
            } catch {
              // Roll back on failure + surface a toast.
              toast(t("toast.skip_failed"), "error");
              const fresh = await getMe().catch(() => null);
              if (fresh) setMe(fresh);
            }
          }}
        />

        <div className="onboarding__main">
          <div className="onboarding__thread" ref={threadRef}>
            {thread.map((it, i) => {
              const lastTurn = i === thread.length - 1;
              const showAttachments = lastTurn && !it.consumed && !busy;
              return (
                <div
                  key={it.id}
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
                  {it.plan && (
                    <ResearchPlanCard
                      plan={it.plan}
                      onAccept={() => acceptPlan(it.plan!)}
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
                  {showAttachments && it.participantDemo && (
                    <ParticipantDemoInvite
                      intro={it.participantDemo.intro}
                      disabled={busy || creating}
                      onOpen={() => {
                        // Wave A Fix 3 — engaging with the card either
                        // way removes it. Without consuming on Open the
                        // invite re-renders after the modal closes.
                        consumeAttachment(i);
                        demoOpenedRef.current = true;
                        setShowParticipantDemo(true);
                      }}
                      onSkip={() => {
                        consumeAttachment(i);
                        demoOpenedRef.current = true;
                        // User skipped — fire the auto-continue now so
                        // the agent moves to the plan proposal without
                        // requiring a manual nudge.
                        if (!busy && !creating) {
                          send(t("participant_demo.auto_continue", "Ok, ready for the plan"));
                        }
                      }}
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
                  {/* V2: when this is the canned greeting (first
                   *  assistant turn, no user reply yet), surface three
                   *  example research-goal chips that PREFILL the
                   *  textarea — kills the cold-start hesitation. Tapping
                   *  doesn't send; the user can still edit before Send. */}
                  {i === 0 &&
                    it.role === "assistant" &&
                    thread.length === 1 &&
                    !busy && (
                      <>
                        <GoalSuggestionChips
                          disabled={busy || creating}
                          onPick={(text) => setInput(text)}
                        />
                        <button
                          type="button"
                          className="onboarding-see-sample"
                          onClick={() => setShowSamplePreview(true)}
                          disabled={creating}
                        >
                          {t("see_sample_link")}
                        </button>
                      </>
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

      {showSamplePreview && (
        <SampleStudyPreview
          industry={me?.industry || ""}
          useCase={me?.use_case || ""}
          onClose={() => setShowSamplePreview(false)}
        />
      )}

      {showParticipantDemo && (
        <ParticipantDemoModal
          firstName={me.first_name || "there"}
          onClose={() => {
            setShowParticipantDemo(false);
            // Auto-continue: once the demo modal closes (completed or
            // bailed), nudge the agent to proceed to the plan
            // proposal. The agent's methodology says to pick up where
            // it left off after the demo — but it has no signal that
            // the demo was dismissed, so we send a synthetic user
            // message. Guard against double-fire if user types in the
            // textarea before close.
            if (demoOpenedRef.current && !busy && !creating) {
              demoOpenedRef.current = false;
              send(t("participant_demo.auto_continue", "Ok, ready for the plan"));
            }
          }}
        />
      )}
    </div>
  );
}

/**
 * V3 — modal preview of what a finished study DELIVERS, not just what
 * questions it asks. Three tabs:
 *   Synthesis (default)  — theme cards with quote pull-outs
 *   Quotes               — verbatims with highlight + code tag
 *   Guide                — the interview question list
 *
 * Demoted the question list from "the demo" to "the appendix", and
 * led with the synthesis — what the researcher actually pays for.
 */
type SampleTab = "synthesis" | "quotes" | "guide";

/**
 * Maps an industry / use-case signal onto a sample-study variant key.
 * Each variant has its own example block in onboarding.json under
 * `sample_modal.variants.<key>.{example,themes,quotes}`. Unknown
 * industries fall through to the default SaaS-flavoured variant.
 */
function pickSampleVariant(industry: string, useCase: string): string {
  const haystack = `${industry} ${useCase}`.toLowerCase();
  if (/(construct|real estate|proptech|bâtiment|immobilier|btp)/.test(haystack)) {
    return "b2b_specifier";
  }
  if (/(retail|ecommerce|e-commerce|consumer|d2c|grande conso)/.test(haystack)) {
    return "consumer";
  }
  return "saas";
}

function SampleStudyPreview({
  industry,
  useCase,
  onClose,
}: {
  industry: string;
  useCase: string;
  onClose: () => void;
}) {
  const { t } = useTranslation("onboarding");
  const [tab, setTab] = useState<SampleTab>("synthesis");
  const variant = pickSampleVariant(industry, useCase) as
    | "saas"
    | "b2b_specifier"
    | "consumer";
  // Wave D — fetch the demo bundle from the backend. The bundle is
  // structured to match what real ProjectAnalysis + QuoteTags look
  // like, paving the way for a future swap to the real ProjectDetail
  // subviews (file as follow-up).
  const [bundle, setBundle] = useState<DemoBundle | null>(null);
  useEffect(() => {
    let cancelled = false;
    getDemoBundle(variant)
      .then((b) => {
        if (!cancelled && b) setBundle(b);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [variant]);

  // Fallback to i18n strings until the bundle arrives (and if it
  // never arrives — offline / API error — the i18n path still works).
  const k = (suffix: string): string => {
    if (bundle && suffix.startsWith("example.")) {
      const key = suffix.slice("example.".length) as keyof DemoBundleExample;
      const value = bundle.example[key];
      if (typeof value === "string" && value) return value;
    }
    return t(`sample_modal.variants.${variant}.${suffix}`, {
      defaultValue: t(`sample_modal.variants.saas.${suffix}`),
    });
  };

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  // Themes + quotes from the backend bundle when available, with
  // graceful i18n fallback. Normalise to the camelCase shape the
  // existing render expects.
  const readI18nArray = <T,>(suffix: string): T[] => {
    const chosen = t(`sample_modal.variants.${variant}.${suffix}`, {
      returnObjects: true,
    }) as unknown;
    if (Array.isArray(chosen) && chosen.length > 0) return chosen as T[];
    const fallback = t(`sample_modal.variants.saas.${suffix}`, {
      returnObjects: true,
    }) as unknown;
    return Array.isArray(fallback) ? (fallback as T[]) : [];
  };
  const themes: DemoBundleTheme[] = bundle?.themes ?? readI18nArray("themes");
  const quotes: Array<{
    speaker: string;
    text: string;
    highlight: string;
    code: string;
    codeColor: string;
  }> = bundle
    ? bundle.quotes.map((q) => ({
        speaker: q.speaker,
        text: q.text,
        highlight: q.highlight,
        code: q.code,
        codeColor: q.code_color,
      }))
    : readI18nArray("quotes");

  return (
    <div
      className="onboarding-sample-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="sample-modal-title"
      onClick={(e) => {
        if (e.currentTarget === e.target) onClose();
      }}
    >
      <div className="onboarding-sample-modal__card onboarding-sample-modal__card--v3">
        <button
          type="button"
          className="onboarding-sample-modal__close"
          onClick={onClose}
          aria-label={t("sample_modal.close")}
        >
          ×
        </button>
        <div className="onboarding-sample-modal__eyebrow">
          ✦ {t("sample_modal.eyebrow")}
        </div>
        <h2
          id="sample-modal-title"
          className="onboarding-sample-modal__title"
        >
          {t("sample_modal.title")}
        </h2>
        <p className="onboarding-sample-modal__body">
          {t("sample_modal.body")}
        </p>

        <div className="onboarding-sample-modal__study-head">
          <div className="onboarding-sample-modal__study-name">
            {k("example.name")}
          </div>
          <div className="onboarding-sample-modal__meta">
            <span>{t("sample_modal.meta_participants", { count: 25 })}</span>
            <span aria-hidden>·</span>
            <span>{t("sample_modal.meta_completed")}</span>
          </div>
        </div>

        <div
          className="onboarding-sample-modal__tabs"
          role="tablist"
          aria-label={t("sample_modal.tabs_aria")}
        >
          {(
            [
              { id: "synthesis", label: t("sample_modal.tab_synthesis") },
              { id: "quotes", label: t("sample_modal.tab_quotes") },
              { id: "guide", label: t("sample_modal.tab_guide") },
            ] as { id: SampleTab; label: string }[]
          ).map((tabDef) => (
            <button
              key={tabDef.id}
              type="button"
              role="tab"
              aria-selected={tab === tabDef.id}
              className={`onboarding-sample-modal__tab ${
                tab === tabDef.id
                  ? "onboarding-sample-modal__tab--active"
                  : ""
              }`}
              onClick={() => setTab(tabDef.id)}
            >
              {tabDef.label}
            </button>
          ))}
        </div>

        <div className="onboarding-sample-modal__pane">
          {tab === "synthesis" && (
            <div className="onboarding-sample-modal__synthesis">
              <p className="onboarding-sample-modal__objective">
                {k("example.objective")}
              </p>
              <div className="onboarding-sample-modal__themes">
                {themes.map((th, i) => (
                  <article
                    key={i}
                    className="onboarding-sample-theme"
                  >
                    <div className="onboarding-sample-theme__rank">
                      {i + 1}
                    </div>
                    <div className="onboarding-sample-theme__body">
                      <h3 className="onboarding-sample-theme__title">
                        {th.title}
                      </h3>
                      <p className="onboarding-sample-theme__finding">
                        {th.finding}
                      </p>
                      <blockquote className="onboarding-sample-theme__quote">
                        “{th.quote}”
                        <cite>— {th.speaker}</cite>
                      </blockquote>
                    </div>
                  </article>
                ))}
              </div>
            </div>
          )}

          {tab === "quotes" && (
            <div className="onboarding-sample-modal__quotes">
              {quotes.map((q, i) => {
                const idx = q.text.indexOf(q.highlight);
                const before = idx >= 0 ? q.text.slice(0, idx) : q.text;
                const hl = idx >= 0 ? q.highlight : "";
                const after =
                  idx >= 0 ? q.text.slice(idx + q.highlight.length) : "";
                return (
                  <article
                    key={i}
                    className="onboarding-sample-quote"
                    style={
                      {
                        ["--quote-code-color" as string]: q.codeColor,
                      } as Record<string, string>
                    }
                  >
                    <div className="onboarding-sample-quote__speaker">
                      {q.speaker}
                    </div>
                    <p className="onboarding-sample-quote__text">
                      {before}
                      {hl && (
                        <mark className="onboarding-sample-quote__highlight">
                          {hl}
                        </mark>
                      )}
                      {after}
                    </p>
                    <span className="onboarding-sample-quote__code">
                      <span
                        className="onboarding-sample-quote__code-dot"
                        aria-hidden
                      />
                      {q.code}
                    </span>
                  </article>
                );
              })}
            </div>
          )}

          {tab === "guide" && (
            <ol className="onboarding-study__questions onboarding-study__questions--in-modal">
              <li>
                <span className="onboarding-study__section">
                  {k("example.q1_section")}
                </span>
                {k("example.q1_question")}
              </li>
              <li>
                <span className="onboarding-study__section">
                  {k("example.q2_section")}
                </span>
                {k("example.q2_question")}
              </li>
              <li>
                <span className="onboarding-study__section">
                  {k("example.q3_section")}
                </span>
                {k("example.q3_question")}
              </li>
            </ol>
          )}
        </div>

        <div className="onboarding-sample-modal__actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={onClose}
          >
            {t("sample_modal.cta")}
          </button>
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
  onChange,
}: {
  me: CompanyResponse;
  profileFields: { key: keyof CompanyResponse; label: string }[];
  onChange: (key: keyof CompanyResponse, value: string) => Promise<void>;
}) {
  const { t } = useTranslation("onboarding");
  const summary = (me.business_summary || "").trim();
  const [editing, setEditing] = useState<keyof CompanyResponse | null>(null);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);

  const startEdit = (key: keyof CompanyResponse, currentValue: string) => {
    setEditing(key);
    setDraft(currentValue);
  };
  const cancelEdit = () => {
    setEditing(null);
    setDraft("");
  };
  const commitEdit = async () => {
    if (editing === null) return;
    const trimmed = draft.trim();
    setSaving(true);
    try {
      await onChange(editing, trimmed);
    } finally {
      setSaving(false);
      setEditing(null);
      setDraft("");
    }
  };
  // Chip-picker commit path — bypass the draft text state and write the
  // canonical option directly. Used by the canonical-options popover.
  const commitValue = async (key: keyof CompanyResponse, value: string) => {
    setSaving(true);
    try {
      await onChange(key, value);
    } finally {
      setSaving(false);
      setEditing(null);
      setDraft("");
    }
  };

  // Identity rows seeded from the signup form. Always visible — sells
  // "the system already knows you" from the very first render, instead
  // of an empty checkmark list.
  const identityRows: { label: string; value: string }[] = [];
  const fullName = [me.first_name, me.last_name]
    .filter(Boolean)
    .join(" ")
    .trim();
  if (fullName) {
    identityRows.push({ label: t("sidebar.name", "You"), value: fullName });
  }
  if (me.name) {
    identityRows.push({ label: t("sidebar.company"), value: me.name });
  }

  // Only render captured-during-chat rows when they have a value.
  // Hollow circles for un-captured fields read as a chore list — we
  // surface those inline in the chat instead (via `suggest_replies`).
  const filledFields = profileFields.filter(
    (f) => !!(me[f.key] as string | null | undefined),
  );

  return (
    <aside className="onboarding-sidebar" aria-label={t("sidebar.eyebrow")}>
      <div className="onboarding-sidebar__eyebrow">{t("sidebar.eyebrow")}</div>
      <ul className="onboarding-sidebar__list">
        {identityRows.map((r) => (
          <li
            key={r.label}
            className="onboarding-sidebar__row onboarding-sidebar__row--filled onboarding-sidebar__row--identity"
          >
            <span className="onboarding-sidebar__check" aria-hidden>✓</span>
            <span className="onboarding-sidebar__label">{r.label}</span>
            <span
              className="onboarding-sidebar__value"
              title={r.value}
            >
              {r.value}
            </span>
          </li>
        ))}
        {filledFields.map((f) => {
          const value = (me[f.key] as string | null | undefined) || "";
          const isEditing = editing === f.key;
          return (
            <li
              key={String(f.key)}
              className={`onboarding-sidebar__row onboarding-sidebar__row--filled ${isEditing ? "onboarding-sidebar__row--editing" : ""}`}
            >
              <span className="onboarding-sidebar__check" aria-hidden>
                ✓
              </span>
              <span className="onboarding-sidebar__label">{f.label}</span>
              {isEditing ? (
                CANONICAL_BY_FIELD[f.key] ? (
                  // Canonical option set — render a chip popover so we
                  // never write a free-text value the agent / plan logic
                  // wouldn't recognise. Esc closes, click commits.
                  //
                  // If the saved value is NOT in the canonical list
                  // (user picked "Other" + typed a custom string in the
                  // wizard), surface it as a "Custom" chip + a free-text
                  // input so the value can be kept or edited without
                  // losing it.
                  (() => {
                    const opts = CANONICAL_BY_FIELD[f.key]!;
                    const isCustom = !!value && !opts.includes(value);
                    return (
                      <span
                        className="onboarding-sidebar__editor onboarding-sidebar__chip-picker"
                        role="radiogroup"
                        aria-label={f.label}
                        onKeyDown={(e) => {
                          if (e.key === "Escape") {
                            e.preventDefault();
                            cancelEdit();
                          }
                        }}
                      >
                        {isCustom && (
                          <>
                            <button
                              type="button"
                              role="radio"
                              aria-checked={true}
                              className="onboarding-sidebar__chip onboarding-sidebar__chip--active onboarding-sidebar__chip--custom"
                              title={value}
                              disabled={saving}
                              autoFocus
                            >
                              ✓ {value}
                            </button>
                            <input
                              type="text"
                              className="onboarding-sidebar__custom-input"
                              defaultValue={value}
                              placeholder={value}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") {
                                  e.preventDefault();
                                  const v = (e.target as HTMLInputElement)
                                    .value
                                    .trim();
                                  if (!v) return;
                                  // Auto-snap to canonical if the typed
                                  // string matches case-insensitive.
                                  const snap = opts.find(
                                    (o) => o.toLowerCase() === v.toLowerCase(),
                                  );
                                  commitValue(f.key, snap || v);
                                } else if (e.key === "Escape") {
                                  e.preventDefault();
                                  cancelEdit();
                                }
                              }}
                              onBlur={(e) => {
                                const v = e.target.value.trim();
                                if (v && v !== value) {
                                  const snap = opts.find(
                                    (o) => o.toLowerCase() === v.toLowerCase(),
                                  );
                                  commitValue(f.key, snap || v);
                                }
                              }}
                              disabled={saving}
                              aria-label={f.label}
                            />
                          </>
                        )}
                        {opts.map((opt) => (
                          <button
                            key={opt}
                            type="button"
                            role="radio"
                            aria-checked={value === opt}
                            className={`onboarding-sidebar__chip ${
                              value === opt
                                ? "onboarding-sidebar__chip--active"
                                : ""
                            }`}
                            onClick={() => commitValue(f.key, opt)}
                            disabled={saving}
                            autoFocus={!isCustom && value === opt}
                          >
                            {opt}
                          </button>
                        ))}
                      </span>
                    );
                  })()
                ) : (
                  <span className="onboarding-sidebar__editor">
                    <input
                      type="text"
                      autoFocus
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          commitEdit();
                        } else if (e.key === "Escape") {
                          e.preventDefault();
                          cancelEdit();
                        }
                      }}
                      disabled={saving}
                      aria-label={f.label}
                    />
                  </span>
                )
              ) : value ? (
                <button
                  type="button"
                  className="onboarding-sidebar__value onboarding-sidebar__value--clickable"
                  onClick={() => startEdit(f.key, value)}
                  title={value}
                >
                  {value}
                </button>
              ) : null}
            </li>
          );
        })}
        {identityRows.length === 0 && filledFields.length === 0 && (
          <li className="onboarding-sidebar__empty">
            {t("sidebar.empty_hint")}
          </li>
        )}
      </ul>
      {summary && (
        <div className="onboarding-sidebar__summary">
          <div className="onboarding-sidebar__summary-label">
            {t("sidebar.business_summary_label", "Business")}
          </div>
          <p className="onboarding-sidebar__summary-text">{summary}</p>
        </div>
      )}
    </aside>
  );
}

/**
 * V2 — pre-suggested research-goal chips rendered under the canned
 * greeting BEFORE the user has sent anything. Tap PREFILLS the
 * textarea (not Send) so the user can edit. Kills the cold-start
 * blank-textarea hesitation. Translation key is plural: t("goal_suggestions",
 * { returnObjects: true }) returns a string[] which we render directly.
 */
function GoalSuggestionChips({
  disabled,
  onPick,
}: {
  disabled: boolean;
  onPick: (text: string) => void;
}) {
  const { t } = useTranslation("onboarding");
  const fallback = t("goal_suggestions", { returnObjects: true }) as unknown;
  const [dynamic, setDynamic] = useState<string[] | null>(null);

  useEffect(() => {
    // Fetch personalised starter chips. Cached server-side for 24h;
    // returns null when the wizard wasn't completed enough to support
    // a sensible Haiku call. Race: for freemail signups, the company-
    // name backfill runs async — business_summary may land 3-15s
    // after wizard completion. Retry a couple of times before
    // giving up to the static fallback.
    let cancelled = false;
    let attempt = 0;
    const maxAttempts = 3;
    const tryFetch = () => {
      attempt += 1;
      getStarterSuggestions()
        .then((arr) => {
          if (cancelled) return;
          if (arr && arr.length >= 1) {
            setDynamic(arr);
            return;
          }
          if (attempt < maxAttempts) {
            setTimeout(tryFetch, 3000 * attempt);
          }
        })
        .catch(() => undefined);
    };
    tryFetch();
    return () => {
      cancelled = true;
    };
  }, []);

  const suggestions =
    dynamic ??
    (Array.isArray(fallback) ? (fallback as string[]) : []);
  if (suggestions.length === 0) return null;
  return (
    <div
      className="onboarding-goal-chips"
      role="group"
      aria-label={t("goal_suggestions_label")}
    >
      <span className="onboarding-goal-chips__hint">
        {t("goal_suggestions_label")}
      </span>
      <div className="onboarding-goal-chips__row">
        {(suggestions as string[]).map((s) => (
          <button
            key={s}
            type="button"
            className="onboarding-goal-chip"
            disabled={disabled}
            onClick={() => onPick(s)}
          >
            {s}
          </button>
        ))}
      </div>
    </div>
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
  // V2 progressive disclosure: questions collapsed by default so the
  // CTA stays above the fold. The strategic context (decision /
  // timeline / success criteria / who they'll interview) the agent
  // captured is also surfaced as a compact summary.
  const [showQuestions, setShowQuestions] = useState(false);
  const decision = (study.decision_to_inform || "").trim();
  const timeline = (study.timeline || "").trim();
  const success = (study.success_criteria || "").trim();
  const audience = (study.target_customer_description || "").trim();
  const hasContext = decision || timeline || success || audience;

  return (
    <div className="onboarding-study">
      <div className="onboarding-study__eyebrow">
        ✦ {t("study.eyebrow")}
      </div>
      <div className="onboarding-study__name">{study.study_name}</div>
      {study.objective && (
        <p className="onboarding-study__objective">{study.objective}</p>
      )}

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

      {hasContext && (
        <dl className="onboarding-study__context">
          {decision && (
            <>
              <dt>{t("study.context_decision")}</dt>
              <dd>{decision}</dd>
            </>
          )}
          {timeline && (
            <>
              <dt>{t("study.context_timeline")}</dt>
              <dd>{timeline}</dd>
            </>
          )}
          {audience && (
            <>
              <dt>{t("study.context_audience")}</dt>
              <dd>{audience}</dd>
            </>
          )}
          {success && (
            <>
              <dt>{t("study.context_success")}</dt>
              <dd>{success}</dd>
            </>
          )}
        </dl>
      )}

      <button
        type="button"
        className="onboarding-study__expand"
        aria-expanded={showQuestions}
        onClick={() => setShowQuestions((v) => !v)}
      >
        {showQuestions
          ? t("study.hide_questions", { count: questions.length })
          : t("study.show_questions", { count: questions.length })}
      </button>
      {showQuestions && (
        <ol className="onboarding-study__questions">
          {questions.map((q, i) => (
            <li key={i}>
              <span className="onboarding-study__section">
                {q.section_title}
              </span>
              {q.main_question}
            </li>
          ))}
        </ol>
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
        <span className="onboarding-study__hint">{t("study.hint")}</span>
      </div>
    </div>
  );
}

/**
 * Wave E — research-plan proposal card. A 2-3 step timeline that the
 * researcher accepts as a whole. Step 1 (if voice_interview) gets
 * drafted as a real Project immediately; later steps stay pending
 * placeholders the user activates from the dashboard.
 */
function ResearchPlanCard({
  plan,
  onAccept,
  disabled,
}: {
  plan: ProposedAction;
  onAccept: () => void;
  disabled: boolean;
}) {
  const { t } = useTranslation("onboarding");
  const steps = plan.steps ?? [];
  const decision = (plan.decision_to_inform || "").trim();
  const timeline = (plan.timeline || "").trim();
  const success = (plan.success_criteria || "").trim();
  const audience = (plan.target_customer_description || "").trim();
  const hasContext = decision || timeline || success || audience;

  return (
    <div className="onboarding-plan">
      <div className="onboarding-plan__eyebrow">
        ✦ {t("plan.eyebrow", "Your research plan")}
      </div>
      <div className="onboarding-plan__name">{plan.plan_name}</div>
      {plan.rationale && (
        <p className="onboarding-plan__rationale">{plan.rationale}</p>
      )}

      <ol className="onboarding-plan__steps">
        {steps.map((s) => (
          <li key={s.order_index} className="onboarding-plan-step">
            <span className="onboarding-plan-step__num">{s.order_index}</span>
            <div className="onboarding-plan-step__body">
              <div className="onboarding-plan-step__head">
                <span className="onboarding-plan-step__title">{s.title}</span>
                <span className="onboarding-plan-step__method">
                  {t(`plan.method.${s.method}`, { defaultValue: s.method })}
                </span>
              </div>
              {s.purpose && (
                <p className="onboarding-plan-step__purpose">{s.purpose}</p>
              )}
              <div className="onboarding-plan-step__meta">
                {typeof s.n_participants === "number" && s.n_participants > 0 && (
                  <span>
                    {t("plan.meta_participants", "{{count}} participants", {
                      count: s.n_participants,
                    })}
                  </span>
                )}
                {typeof s.duration_weeks === "number" && s.duration_weeks > 0 && (
                  <span>
                    {t("plan.meta_duration", {
                      count: s.duration_weeks,
                      defaultValue: "{{count}} weeks",
                    })}
                  </span>
                )}
                {s.deliverable && (
                  <span className="onboarding-plan-step__deliverable">
                    → {s.deliverable}
                  </span>
                )}
              </div>
            </div>
          </li>
        ))}
      </ol>

      {hasContext && (
        <dl className="onboarding-study__context">
          {decision && (
            <>
              <dt>{t("study.context_decision")}</dt>
              <dd>{decision}</dd>
            </>
          )}
          {timeline && (
            <>
              <dt>{t("study.context_timeline")}</dt>
              <dd>{timeline}</dd>
            </>
          )}
          {audience && (
            <>
              <dt>{t("study.context_audience")}</dt>
              <dd>{audience}</dd>
            </>
          )}
          {success && (
            <>
              <dt>{t("study.context_success")}</dt>
              <dd>{success}</dd>
            </>
          )}
        </dl>
      )}

      <div className="onboarding-plan__actions">
        <button
          type="button"
          className="btn btn-primary"
          onClick={onAccept}
          disabled={disabled}
        >
          {t("plan.accept_cta", "Accept this plan & draft step 1")}
        </button>
        <span className="onboarding-study__hint">
          {t("plan.hint", "Step 1 becomes your first study now — later steps wait for your go-ahead.")}
        </span>
      </div>
    </div>
  );
}

/* ── V3 — Participant-experience demo (iPhone-framed embedded interview) ──
 *
 * Two components:
 *   1. <ParticipantDemoInvite> — the inline chat card the agent posts.
 *      Just an intro line + two buttons (Open / Skip).
 *   2. <ParticipantDemoModal>  — the full-screen overlay with the
 *      iPhone frame, mic recording, transcribe round-trip, and the
 *      analysis-view reveal.
 */

function ParticipantDemoInvite({
  intro,
  disabled,
  onOpen,
  onSkip,
}: {
  intro: string;
  disabled: boolean;
  onOpen: () => void;
  onSkip: () => void;
}) {
  const { t } = useTranslation("onboarding");
  return (
    <div className="onboarding-demo-invite">
      <div className="onboarding-demo-invite__eyebrow">
        ✦ {t("participant_demo.invite_eyebrow")}
      </div>
      <p className="onboarding-demo-invite__intro">{intro}</p>
      <div className="onboarding-demo-invite__actions">
        <button
          type="button"
          className="btn btn-primary btn-sm"
          onClick={onOpen}
          disabled={disabled}
        >
          {t("participant_demo.invite_open")}
        </button>
        <button
          type="button"
          className="onboarding-demo-invite__skip"
          onClick={onSkip}
          disabled={disabled}
        >
          {t("participant_demo.invite_skip")}
        </button>
      </div>
    </div>
  );
}

type DemoPhase =
  | "intro"        // Bot question on screen, mic not yet engaged
  | "permission"   // Awaiting mic permission
  | "recording"    // User holding/talking
  | "uploading"    // Whisper round trip
  | "reveal"       // Transcript + highlight + code shown
  | "error";

function ParticipantDemoModal({
  firstName,
  onClose,
}: {
  firstName: string;
  onClose: () => void;
}) {
  const { t } = useTranslation("onboarding");
  const [phase, setPhase] = useState<DemoPhase>("intro");
  const [result, setResult] = useState<DemoTranscribeResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string>("");
  // Haiku-personalised mid-conversation question, fetched on mount.
  // Falls back to the static i18n question when null (wizard skipped
  // / API failure / sparse context).
  const [personalisedQuestion, setPersonalisedQuestion] = useState<
    string | null
  >(null);
  useEffect(() => {
    let cancelled = false;
    getDemoOpeningQuestion()
      .then((q) => {
        if (!cancelled && q) setPersonalisedQuestion(q);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);
  const { isRecording, error: recorderError, startRecording, stopRecording } =
    useAudioRecorder();

  // Escape closes the modal at any phase except mid-upload (don't
  // strand the user if Whisper is mid-call).
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && phase !== "uploading") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose, phase]);

  // Mirror the recorder hook's error state into our local error
  // phase so the UI can render a clear message.
  useEffect(() => {
    if (recorderError) {
      setErrorMsg(
        recorderError === "PERMISSION_DENIED"
          ? t("participant_demo.error_mic_denied")
          : recorderError,
      );
      setPhase("error");
    }
  }, [recorderError, t]);

  const handleStart = async () => {
    setPhase("permission");
    await startRecording();
    // If permission was denied the hook will surface via recorderError;
    // otherwise it flips isRecording on. Let the effect catch errors.
    setPhase((prev) => (prev === "permission" ? "recording" : prev));
  };

  const handleStop = async () => {
    setPhase("uploading");
    try {
      const blob = await stopRecording();
      const res = await transcribeDemoAudio(blob);
      setResult(res);
      setPhase("reveal");
    } catch (err: unknown) {
      setErrorMsg(
        err instanceof Error
          ? err.message
          : t("participant_demo.error_generic"),
      );
      setPhase("error");
    }
  };

  // Canned fallback shown on Skip (no recording needed). Renders a
  // hand-crafted transcript + highlight + code that matches what the
  // real flow would produce — keeps the wow moment for users who
  // decline mic permission.
  const cannedResult: DemoTranscribeResponse = {
    transcript: t("participant_demo.canned_transcript"),
    highlight: {
      start: 0,
      end: 0,
      text: t("participant_demo.canned_highlight"),
    },
    code: {
      label: t("participant_demo.canned_code"),
      color: "#4f46e5",
    },
  };
  const handleSkipToReveal = () => {
    setResult(cannedResult);
    setPhase("reveal");
  };

  return (
    <div
      className="onboarding-demo-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="demo-modal-title"
      onClick={(e) => {
        if (e.currentTarget === e.target && phase !== "uploading") onClose();
      }}
    >
      <div className="onboarding-demo-modal__card">
        <button
          type="button"
          className="onboarding-demo-modal__close"
          onClick={onClose}
          disabled={phase === "uploading"}
          aria-label={t("participant_demo.close")}
        >
          ×
        </button>
        <div className="onboarding-demo-modal__header">
          <div className="onboarding-demo-modal__eyebrow">
            ✦ {t("participant_demo.modal_eyebrow")}
          </div>
          <h2
            id="demo-modal-title"
            className="onboarding-demo-modal__title"
          >
            {phase === "reveal"
              ? t("participant_demo.modal_title_reveal")
              : t("participant_demo.modal_title")}
          </h2>
          <p className="onboarding-demo-modal__body">
            {phase === "reveal"
              ? t("participant_demo.modal_body_reveal")
              : t("participant_demo.modal_body")}
          </p>
        </div>

        {phase !== "reveal" ? (
          <DemoPhoneFrame>
            <div className="onboarding-demo-phone__bot-question">
              {personalisedQuestion ||
                t("participant_demo.question", { firstName })}
            </div>
            <div className="onboarding-demo-phone__controls">
              {phase === "intro" && (
                <button
                  type="button"
                  className="onboarding-demo-phone__record-button"
                  onClick={handleStart}
                  aria-label={t("participant_demo.start_recording")}
                >
                  <span className="onboarding-demo-phone__mic-icon">🎤</span>
                  <span className="onboarding-demo-phone__record-label">
                    {t("participant_demo.tap_to_speak")}
                  </span>
                </button>
              )}
              {phase === "permission" && (
                <p className="onboarding-demo-phone__hint">
                  {t("participant_demo.requesting_mic")}
                </p>
              )}
              {phase === "recording" && isRecording && (
                <button
                  type="button"
                  className="onboarding-demo-phone__record-button onboarding-demo-phone__record-button--active"
                  onClick={handleStop}
                  aria-label={t("participant_demo.stop_recording")}
                >
                  <span className="onboarding-demo-phone__pulse" aria-hidden />
                  <span className="onboarding-demo-phone__record-label">
                    {t("participant_demo.tap_to_stop")}
                  </span>
                </button>
              )}
              {phase === "uploading" && (
                <p className="onboarding-demo-phone__hint">
                  {t("participant_demo.transcribing")}
                </p>
              )}
              {phase === "error" && (
                <div className="onboarding-demo-phone__error">
                  <p>{errorMsg}</p>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => {
                      setErrorMsg("");
                      setPhase("intro");
                    }}
                  >
                    {t("participant_demo.try_again")}
                  </button>
                </div>
              )}
            </div>
          </DemoPhoneFrame>
        ) : (
          result && <DemoRevealView result={result} />
        )}

        <div className="onboarding-demo-modal__footer">
          {phase !== "reveal" && phase !== "uploading" && (
            <button
              type="button"
              className="onboarding-demo-modal__skip"
              onClick={handleSkipToReveal}
            >
              {t("participant_demo.skip_to_example")}
            </button>
          )}
          {phase === "reveal" && (
            <button
              type="button"
              className="btn btn-primary"
              onClick={onClose}
            >
              {t("participant_demo.reveal_cta")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/** Pure-CSS iPhone frame around its children. Cosmetic — collapses
 *  to a phone-shaped rounded card on narrow viewports to avoid
 *  the nested-phone weirdness on mobile devices. */
function DemoPhoneFrame({ children }: { children: ReactNode }) {
  return (
    <div className="onboarding-demo-phone" aria-hidden={false}>
      <div className="onboarding-demo-phone__notch" aria-hidden />
      <div className="onboarding-demo-phone__screen">{children}</div>
      <div className="onboarding-demo-phone__home-indicator" aria-hidden />
    </div>
  );
}

/** Reveal phase — show the user's transcript with a highlighted
 *  span and the code tag the server picked. Mimics what the real
 *  researcher analysis view will look like. */
function DemoRevealView({
  result,
}: {
  result: DemoTranscribeResponse;
}) {
  const { t } = useTranslation("onboarding");
  const transcript = result.transcript || "";
  const highlight = result.highlight;
  // Render transcript with the highlighted span wrapped in a tagged
  // <mark>. If no highlight, render plain transcript.
  let pre = "";
  let mid = "";
  let post = "";
  if (highlight && highlight.text && transcript) {
    // Find the highlight text in the transcript (case-insensitive,
    // tolerant of whitespace). Server returns char offsets but the
    // transcript may have been normalised, so we re-search here for
    // safety.
    const idx = transcript.indexOf(highlight.text);
    if (idx >= 0) {
      pre = transcript.slice(0, idx);
      mid = highlight.text;
      post = transcript.slice(idx + highlight.text.length);
    } else {
      pre = transcript;
    }
  } else {
    pre = transcript;
  }

  return (
    <div className="onboarding-demo-reveal">
      <div className="onboarding-demo-reveal__label">
        {t("participant_demo.your_answer")}
      </div>
      <p className="onboarding-demo-reveal__transcript">
        {pre}
        {mid && (
          <mark
            className="onboarding-demo-reveal__highlight"
            style={{ ["--highlight-color" as string]: result.code.color } as Record<string, string>}
          >
            {mid}
          </mark>
        )}
        {post}
      </p>
      <div
        className="onboarding-demo-reveal__code"
        style={{ ["--code-color" as string]: result.code.color } as Record<string, string>}
      >
        <span className="onboarding-demo-reveal__code-dot" aria-hidden />
        <span className="onboarding-demo-reveal__code-label">
          {result.code.label}
        </span>
      </div>
      <p className="onboarding-demo-reveal__caption">
        {t("participant_demo.reveal_caption")}
      </p>
    </div>
  );
}
