import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

import {
  getInterviewInfo,
  getDemoLink,
  getScreeningQuestions,
  submitScreening,
  startInterview,
  submitAudio,
  checkResume,
  getResumeSummary,
  claimHandoff,
  finishInterview,
  getTurnAudio,
  getInterviewStatus,
  requestVerification,
  verifyInterviewCode,
  savePanelProfile,
  RECORDING_TOO_LARGE,
  InterviewInfo,
  VerifyTokenResponse,
  ScreeningQuestion,
  ResumeCheck,
  ResumeSummary,
  SubmitAudioResponse,
  TurnMismatchDetail,
  Stimulus,
} from "../api/interviews";
import StimulusCard from "../components/StimulusCard";
import {
  useAudioRecorder,
  RECORDING_TOO_SHORT,
  SILENT_RECORDING,
  RecordingInterruptReason,
} from "../hooks/useAudioRecorder";
import DeviceHandoff from "../components/DeviceHandoff";
import LanguagePicker from "../components/LanguagePicker";
import RealtimeInterview from "../components/RealtimeInterview";
import ParticipantQuestionnaire, { QuestionnaireResult } from "../components/ParticipantQuestionnaire";
import PanelEnrichment from "../components/PanelEnrichment";
import { SUPPORTED_LANGUAGES } from "../i18n";
import { applyParticipantBranding } from "../utils/branding";
import { detectInAppBrowser, androidChromeIntentUrl } from "../utils/inAppBrowser";
import { useHead } from "../hooks/useHead";

// A tiny valid silent WAV. Playing this from within a user gesture (the
// "enable microphone" tap) "unlocks" the audio element on iOS Safari, so the
// first question's TTS — which fires from a useEffect, not a tap — is allowed
// to autoplay afterwards instead of being silently blocked.
const SILENT_AUDIO =
  "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YQAAAAA=";

type Phase =
  | "email_entry"
  | "email_sent"
  | "consent"
  | "profile"
  | "screening"
  | "disqualified"
  | "study_unavailable"
  | "link_full"
  | "already_completed"
  | "interview"
  | "complete";

interface ProfileState {
  firstName: string;
  ageRange: string;
  gender: string;
  employment: string;
  jobFunction: string;
  industry: string;
  companySize: string;
  seniority: string;
  city: string;
  selectedTagIds: number[];
}

const EMPTY_PROFILE: ProfileState = {
  firstName: "",
  ageRange: "",
  gender: "",
  employment: "",
  jobFunction: "",
  industry: "",
  companySize: "",
  seniority: "",
  city: "",
  selectedTagIds: [],
};

/** Returning-participant hints carried by both verification routes. */
interface ProfileMeta {
  profile_complete?: boolean;
  panel_consent?: boolean;
  first_name?: string | null;
  preferred_language?: string | null;
}

/** The distinct outcomes of submitting a six-digit code. */
type CodeErrorKind = "code_invalid" | "code_expired" | "too_many_attempts" | "generic";

/** Map the backend's structured `detail: { code, message }` onto a localizable kind. */
function codeErrorKind(err: unknown): CodeErrorKind {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  const raw =
    detail && typeof detail === "object" && !Array.isArray(detail)
      ? (detail as { code?: unknown }).code
      : undefined;
  if (raw === "code_invalid" || raw === "code_expired" || raw === "too_many_attempts") return raw;
  return "generic";
}

function parseJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = atob(parts[1].replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(payload);
  } catch {
    return null;
  }
}

/** Line icons for the participant flow.
 *  Emoji were rendering inconsistently across platforms (Apple's colour
 *  glyphs next to a flat blue UI) and are not resizable or themeable, so
 *  the display icons are inline SVG on currentColor instead. */
function Icon({ path, size = 48, stroke = 1.5 }: { path: React.ReactNode; size?: number; stroke?: number }) {
  return (
    <svg
      width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true" focusable="false"
    >
      {path}
    </svg>
  );
}

const IconMail = (p: { size?: number }) => (
  <Icon {...p} path={<><rect x="2" y="4" width="20" height="16" rx="2" /><path d="m2 7 10 6 10-6" /></>} />
);
const IconMic = (p: { size?: number }) => (
  <Icon {...p} path={<><rect x="9" y="2" width="6" height="12" rx="3" /><path d="M5 10a7 7 0 0 0 14 0" /><path d="M12 17v5" /></>} />
);
const IconCompass = (p: { size?: number }) => (
  <Icon {...p} path={<><circle cx="12" cy="12" r="9" /><path d="m15.5 8.5-2 5.5-5.5 2 2-5.5z" /></>} />
);
const IconLink = (p: { size?: number }) => (
  <Icon {...p} path={<><path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1" /><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1" /></>} />
);
const IconHeart = (p: { size?: number }) => (
  <Icon {...p} path={<path d="M12 20s-7-4.4-7-9.3A4 4 0 0 1 12 8a4 4 0 0 1 7 2.7c0 4.9-7 9.3-7 9.3z" />} />
);
const IconSpeaker = (p: { size?: number }) => (
  <Icon {...p} size={p.size ?? 16} path={<><path d="M11 5 6 9H3v6h3l5 4z" /><path d="M16 9a4 4 0 0 1 0 6" /></>} />
);
const IconBulb = (p: { size?: number }) => (
  <Icon {...p} size={p.size ?? 16} path={<><path d="M9 18h6" /><path d="M10 21h4" /><path d="M12 3a6 6 0 0 0-3.6 10.8c.4.3.6.8.6 1.2h6c0-.4.2-.9.6-1.2A6 6 0 0 0 12 3z" /></>} />
);
const IconGift = (p: { size?: number }) => (
  <Icon {...p} size={p.size ?? 16} path={<><rect x="3" y="8" width="18" height="4" rx="1" /><path d="M5 12v8h14v-8" /><path d="M12 8v12" /><path d="M12 8S9.5 3 7.5 4.5 9 8 12 8zM12 8s2.5-5 4.5-3.5S15 8 12 8z" /></>} />
);

export default function Interview() {
  const { t, i18n } = useTranslation("interview");
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const location = useLocation();

  const [phase, setPhase] = useState<Phase>("email_entry");
  const [info, setInfo] = useState<InterviewInfo | null>(null);
  const [infoLoading, setInfoLoading] = useState(true);
  const [error, setError] = useState("");
  // Stable mirror of `info` for callbacks that must not re-create on load.
  const infoRef = useRef<InterviewInfo | null>(null);
  useEffect(() => { infoRef.current = info; }, [info]);
  // Realtime beta: set when the live transport failed and the participant
  // chose to continue in the classic flow. Sticky for the session so a
  // flaky network doesn't bounce them between the two experiences.
  const [realtimeFallback, setRealtimeFallback] = useState(false);
  const realtimeFallbackRef = useRef(false);

  // Participant-facing head: the static index.html tags sell the product to
  // researchers. Link unfurlers never get here (nginx routes them to the
  // backend preview, see services/interview_preview.py), this is for the
  // browser tab and for keeping the token URL out of search indexes.
  useHead({
    title: info?.project_name || t("meta.title"),
    metas: [
      { name: "description", content: t("meta.description") },
      { name: "robots", content: "noindex, nofollow" },
    ],
  });

  // Verification / session
  const [verificationEmail, setVerificationEmail] = useState("");
  const [sendingVerification, setSendingVerification] = useState(false);
  const [resendCountdown, setResendCountdown] = useState(0);
  const [sessionToken, setSessionToken] = useState<string | null>(null);
  const [email, setEmail] = useState(""); // from verified session
  // Six-digit code entry. The code is the primary route: typing it keeps the
  // participant in the tab they already opened, where the microphone works.
  const [verificationCode, setVerificationCode] = useState("");
  const [verifyingCode, setVerifyingCode] = useState(false);
  const [codeError, setCodeError] = useState<CodeErrorKind | null>(null);
  const [codeResent, setCodeResent] = useState(false);
  const codeInputRef = useRef<HTMLInputElement | null>(null);

  // Consent
  const [consentGiven, setConsentGiven] = useState(false);
  const [consentDeclined, setConsentDeclined] = useState(false);
  // Two-tap decline: declining is terminal (no way back to the study), so an
  // accidental tap shouldn't end it. First tap arms an inline confirmation.
  const [declineConfirming, setDeclineConfirming] = useState(false);

  // Panel profile
  const [profile, setProfile] = useState<ProfileState>(EMPTY_PROFILE);
  // Returning-participant recognition: set from the magic-link verify response
  // (stashed in sessionStorage by InterviewVerify). When the profile is already
  // complete we skip the questionnaire entirely.
  const [profileComplete, setProfileComplete] = useState(false);
  // Whether the participant opted into the research panel during the
  // questionnaire — drives the gentler post-interview re-prompt for decliners.
  const [panelConsentGiven, setPanelConsentGiven] = useState(false);
  // Set when /start is blocked by the workspace billing gate (403). Shows a
  // calm terminal message instead of a scary "Something went wrong" + retry.
  const [studyUnavailableMsg, setStudyUnavailableMsg] = useState<string | null>(null);
  // In-app webview escape hatch (Instagram/FB/TikTok can't grant the mic).
  // Bypass is only offered when the recording APIs are actually present.
  const [webviewBypass, setWebviewBypass] = useState(false);
  const [linkCopied, setLinkCopied] = useState(false);
  // Post-interview panel re-prompt state for participants who declined earlier.
  const [repromptState, setRepromptState] = useState<"idle" | "saving" | "done" | "dismissed">("idle");
  // Inline panel-enrichment ("add more details, get more studies") on the
  // completion screen for consented panelists.
  const [showEnrichment, setShowEnrichment] = useState(false);
  // Post-interview "a minute about you" questionnaire (optional). Lives on the
  // completion screen so the pre-interview path stays near-frictionless.
  const [showPostQuestionnaire, setShowPostQuestionnaire] = useState(false);
  // Studies that opt into profiling BEFORE the interview run the same
  // questionnaire component up front instead of on the completion screen.
  const [showPreQuestionnaire, setShowPreQuestionnaire] = useState(false);
  const [didPreQuestionnaire, setDidPreQuestionnaire] = useState(false);
  const [postProfileState, setPostProfileState] = useState<"idle" | "done" | "skipped">("idle");

  // Interview state
  const [displayName, setDisplayName] = useState("");
  const [profession, setProfession] = useState("");
  const [ageRange, setAgeRange] = useState("");
  const [country, setCountry] = useState("");
  const [participantId, setParticipantId] = useState("");
  const [currentQuestion, setCurrentQuestion] = useState("");
  // The artefact shown alongside the current question (concept test,
  // pack shot, ad creative). Always assigned wholesale on a turn change,
  // never merged: a question without a stimulus must clear the previous one.
  const [stimulus, setStimulus] = useState<Stimulus | null>(null);
  const [processing, setProcessing] = useState(false);
  const [starting, setStarting] = useState(false);
  // Mute preference survives reloads/resume — an unexpected replay of TTS
  // after a refresh is jarring for someone who explicitly muted it.
  const [muted, setMuted] = useState(
    () => typeof window !== "undefined" && localStorage.getItem("qp_interview_muted") === "1"
  );
  const [turnCount, setTurnCount] = useState(0);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [isFollowUp, setIsFollowUp] = useState(false);
  // True while the current prompt is the warm-up (not a guide question):
  // the progress label must not claim "Q1 of N" during it.
  const [isWarmup, setIsWarmup] = useState(false);
  // Index of the pending interviewer turn, echoed back on /respond and /skip
  // so a retried upload can never be applied to the wrong question. Null when
  // unknown (resume paths that predate the field).
  const [turnIndex, setTurnIndex] = useState<number | null>(null);
  // Pause / finish-here controls.
  const [paused, setPaused] = useState(false);
  const pausedTtsRef = useRef(false);
  const [finishConfirming, setFinishConfirming] = useState(false);
  const [finishing, setFinishing] = useState(false);
  // Neutral, non-error notices (turn resync, recording interrupted).
  const [notice, setNotice] = useState<string | null>(null);
  // PF-3: live coaching tip surfaced when the engine detects a short-answer
  // run. Persists between turns until the user dismisses or the engine clears
  // it because the participant elaborated again.
  const [coachingHint, setCoachingHint] = useState<string | null>(null);
  const [coachingHintDismissed, setCoachingHintDismissed] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [totalSeconds, setTotalSeconds] = useState(0);
  const [resumeCheck, setResumeCheck] = useState<ResumeCheck | null>(null);
  const [resumeSummary, setResumeSummary] = useState<ResumeSummary | null>(null);
  const [loadingResumeSummary, setLoadingResumeSummary] = useState(false);

  // Screening
  const [screeningQuestions, setScreeningQuestions] = useState<ScreeningQuestion[]>([]);
  const [screeningStep, setScreeningStep] = useState(0);
  const [screeningAnswers, setScreeningAnswers] = useState<Record<string, string>>({});
  const [screeningLoading, setScreeningLoading] = useState(false);
  const [disqualifiedOn, setDisqualifiedOn] = useState("");
  const [screeningError, setScreeningError] = useState("");

  // Recording UX
  const lastBlobRef = useRef<Blob | null>(null);
  const [pendingBlob, setPendingBlob] = useState<Blob | null>(null);
  // Accessibility text fallback: participants without a working microphone
  // can type their answer instead. `textMode` swaps the record controls for a
  // textarea; the typed value stays in state until a submit succeeds, so a
  // transport failure retries the same answer (the lastBlobRef equivalent).
  const [textMode, setTextMode] = useState(false);
  const [typedAnswer, setTypedAnswer] = useState("");
  const MAX_TYPED_ANSWER_CHARS = 5000;
  const [ttsPlaying, setTtsPlaying] = useState(false);
  const [ttsEnded, setTtsEnded] = useState(true);
  // Honest processing state: one calm label, plus a patience hint after 8s.
  const [processingLong, setProcessingLong] = useState(false);
  // One-tap answering: after tap-to-stop the take auto-sends in 2.5s unless
  // the participant taps Undo (which drops them into a playable preview).
  const [autoSending, setAutoSending] = useState(false);
  const autoSendTimerRef = useRef<number | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  // Single polite live region for screen readers (question, then processing).
  const [liveMessage, setLiveMessage] = useState("");
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const recordingStartTimeRef = useRef<number | null>(null);
  const MAX_RECORDING_SECONDS = 240;
  const [micTestDone, setMicTestDone] = useState(false);
  // A mid-interview mic failure (flat-line take, or repeated "we didn't hear
  // you" server rejections) sends the participant back to the mic test with
  // an explanatory banner; the interview resumes on the same question.
  const [micRecheck, setMicRecheck] = useState(false);
  const emptyStreakRef = useRef(0);
  // An expired/invalid ?handoff= claim: shown once on the landing screen.
  const [handoffClaimError, setHandoffClaimError] = useState(false);
  const [micLevel, setMicLevel] = useState(0);
  const micStreamRef = useRef<MediaStream | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const micAnimRef = useRef<number | null>(null);
  const [micPermissionRequested, setMicPermissionRequested] = useState(false);

  const [ttsFailedWarning, setTtsFailedWarning] = useState(false);
  // Autoplay was blocked before ANY clip has played (iOS Safari when the
  // unlock trick didn't take). Distinct from ttsFailedWarning: instead of a
  // scary banner we show a "Play question" button — a user gesture always
  // satisfies the autoplay policy.
  const [ttsBlocked, setTtsBlocked] = useState(false);
  // Has any audio successfully played in this session? Until then, an
  // onerror/play-rejection is almost always a transient autoplay-policy
  // glitch on the very first <audio> element rather than a real failure
  // — we suppress the warning until we've heard at least one full clip.
  const hasEverPlayedRef = useRef(false);

  // Audit-fix UI state
  const [whyEmailOpen, setWhyEmailOpen] = useState(false);
  const [screeningErrorKind, setScreeningErrorKind] = useState<"network" | "server" | "ratelimit" | null>(null);
  const [screeningRetryCount, setScreeningRetryCount] = useState(0);
  const beepFiredRef = useRef(false);
  const [showFutureStudies, setShowFutureStudies] = useState(false);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const pendingFirstTtsRef = useRef<string | null>(null);
  const { isRecording, error: recError, startRecording, stopRecording } =
    useAudioRecorder({
      onInterrupted: (blob: Blob | null, reason: RecordingInterruptReason) => {
        if (blob) {
          lastBlobRef.current = blob;
          setPendingBlob(blob);
          setTtsEnded(false);
        }
        setNotice(
          reason === "hidden"
            ? t("recording.interruptedHidden")
            : t("recording.interruptedDevice")
        );
      },
    });

  // Object URL for the preview player; revoked whenever the blob changes.
  useEffect(() => {
    if (!pendingBlob) { setPreviewUrl(null); return; }
    const url = URL.createObjectURL(pendingBlob);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [pendingBlob]);

  // Clear the auto-send timer on unmount so a late fire can't hit a dead page.
  useEffect(() => () => {
    if (autoSendTimerRef.current) window.clearTimeout(autoSendTimerRef.current);
  }, []);

  // Patience hint after 8s of processing (no fake step progression).
  useEffect(() => {
    if (!processing) { setProcessingLong(false); return; }
    const timer = window.setTimeout(() => setProcessingLong(true), 8000);
    return () => window.clearTimeout(timer);
  }, [processing]);

  // Feed the single live region: the new question text first, then processing
  // state changes. Plain text only, never emoji.
  useEffect(() => {
    if (phase !== "interview") return;
    if (processing) {
      setLiveMessage(processingLong ? t("interview.processing.stillWorking") : t("interview.processing.listening"));
    } else if (currentQuestion) {
      setLiveMessage(currentQuestion);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, processing, processingLong, currentQuestion]);

  // ── Session / URL handling on load ──────────────────────────────────────

  // Apply the returning-participant meta (profile_complete / first_name /
  // preferred_language). Shared by both verification routes: the magic link
  // (which stashes it in sessionStorage before redirecting here) and the
  // six-digit code (which gets it straight off the verify-code response).
  function applyProfileMeta(meta: ProfileMeta) {
    if (meta.profile_complete) setProfileComplete(true);
    // Seed from the server so a returning panelist who already joined is not
    // re-asked, and one who declined last time IS asked (see the reprompt).
    if (meta.panel_consent) setPanelConsentGiven(true);
    if (meta.first_name) setProfile((p) => ({ ...p, firstName: meta.first_name as string }));
    const ml = (meta.preferred_language || "").slice(0, 2);
    if (ml && (SUPPORTED_LANGUAGES as readonly string[]).includes(ml)) {
      localStorage.setItem("qp_interview_lang", ml);
      i18n.changeLanguage(ml);
    }
  }

  /** The one path a verified participant takes, whichever route verified them. */
  function applyVerifiedSession(res: VerifyTokenResponse) {
    const linkToken = res.link_token || token || "";
    sessionStorage.setItem(`interview_session_${linkToken}`, res.session_token);
    sessionStorage.setItem(
      `interview_profile_meta_${linkToken}`,
      JSON.stringify({
        profile_complete: res.profile_complete,
        first_name: res.first_name,
        preferred_language: res.preferred_language,
      })
    );
    setEmail(res.email);
    setSessionToken(res.session_token);
    applyProfileMeta(res);
    setPhase("consent");
  }

  useEffect(() => {
    if (!token) return;

    // Check URL for ?session param (from InterviewVerify redirect)
    const params = new URLSearchParams(location.search);
    const sessionParam = params.get("session");

    // ?handoff param: this device is adopting an in-progress interview
    // started elsewhere (QR code / link from the "continue on another
    // device" panel). Claim it, then drop into the normal interview flow;
    // the mic prompt + mic test run on THIS device before recording.
    const handoffParam = params.get("handoff");
    if (handoffParam) {
      (async () => {
        try {
          const claim = await claimHandoff(token, handoffParam);
          if (claim.email) setEmail(claim.email);
          if (claim.session_token) {
            setSessionToken(claim.session_token);
            sessionStorage.setItem(`interview_session_${token}`, claim.session_token);
          }
          let summary: ResumeSummary | null = null;
          try {
            summary = await getResumeSummary(token, claim.participant_id);
          } catch { /* summary is best-effort; the next turn resyncs the clock */ }
          let duration = 0;
          try {
            duration = (await getInterviewInfo(token)).interview_duration_minutes ?? 0;
          } catch { /* ditto */ }
          lockInterviewLanguage(summary?.language);
          setParticipantId(claim.participant_id);
          setCurrentQuestion(claim.last_question ?? "");
          setStimulus(claim.last_stimulus ?? null);
          setTurnCount(claim.turn_count ?? 1);
          setQuestionIndex(claim.question_index ?? 0);
          setTurnIndex(null);
          const total = duration * 60;
          setTotalSeconds(total);
          setElapsedSeconds(Math.min((summary?.elapsed_minutes ?? 0) * 60, total));
          saveSession(
            claim.participant_id,
            claim.last_question ?? "",
            claim.turn_count ?? 1,
            null,
            claim.question_index ?? 0,
          );
          navigate(`/i/${token}`, { replace: true });
          setPhase("interview");
        } catch {
          setHandoffClaimError(true);
          navigate(`/i/${token}`, { replace: true });
          setPhase("email_entry");
        }
      })();
      return;
    }

    // Read the returning-participant meta that InterviewVerify stashed
    // alongside the session.
    const applyStoredProfileMeta = () => {
      try {
        const raw = sessionStorage.getItem(`interview_profile_meta_${token}`);
        if (!raw) return;
        applyProfileMeta(JSON.parse(raw) as ProfileMeta);
      } catch { /* meta is best-effort */ }
    };

    if (sessionParam) {
      const payload = parseJwtPayload(sessionParam);
      if (payload?.email) {
        const emailVal = String(payload.email);
        setEmail(emailVal);
        setSessionToken(sessionParam);
        sessionStorage.setItem(`interview_session_${token}`, sessionParam);
        navigate(`/i/${token}`, { replace: true });
        applyStoredProfileMeta();
        setPhase("consent");
        return;
      }
    }

    // Check sessionStorage for existing session
    const saved = sessionStorage.getItem(`interview_session_${token}`);
    if (saved) {
      const payload = parseJwtPayload(saved);
      if (payload?.email) {
        setEmail(String(payload.email));
        setSessionToken(saved);
        applyStoredProfileMeta();
        setPhase("consent");
        return;
      }
      // Stale/invalid session — clear it
      sessionStorage.removeItem(`interview_session_${token}`);
    }

    setPhase("email_entry");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // ── Load interview info ──────────────────────────────────────────────────

  useEffect(() => {
    if (!token) return;
    // Special "demo" token: look up the real active demo link and redirect to it
    if (token === "demo") {
      getDemoLink()
        .then(({ redirect_token }) => navigate(`/i/${redirect_token}`, { replace: true }))
        .catch(() => {
          setError(t("linkInactive.title"));
          setInfoLoading(false);
        });
      return;
    }
    // Best-guess language we already know before the round-trip (explicit pick
    // or browser) so the study name comes back localized on the first fetch.
    const supported = SUPPORTED_LANGUAGES as readonly string[];
    const manual = localStorage.getItem("qp_interview_lang") || "";
    const browser = (i18n.language || "en").slice(0, 2);
    const guess = supported.includes(manual) ? manual : supported.includes(browser) ? browser : "";
    getInterviewInfo(token, guess || undefined)
      .then((data) => {
        setInfo(data);
        // Language precedence (participant choice wins, per the redesign):
        //   1. an explicit pick the participant made via the language picker
        //   2. their browser/detected language (if we support it)
        //   3. the study's configured language (if we support it)
        //   4. English
        let target = "en";
        if (supported.includes(manual)) target = manual;
        else if (supported.includes(browser)) target = browser;
        else if (data.language && supported.includes(data.language)) target = data.language;
        if (target !== i18n.language) i18n.changeLanguage(target);
        // If the resolved language differs from our pre-fetch guess (e.g. it
        // came from the study's default), refetch so the name is localized.
        if (target !== guess && target !== "en") {
          getInterviewInfo(token, target).then(setInfo).catch(() => {});
        }
      })
      .catch(() => setError(t("linkInactive.title")))
      .finally(() => setInfoLoading(false));
  }, [token]);

  // Branded studies re-theme the whole participant experience (accent color
  // + font) by overriding the design-system CSS variables; cleanup restores
  // them so the theme never leaks past this page.
  useEffect(() => applyParticipantBranding(info?.branding), [info?.branding]);

  // Resend countdown
  useEffect(() => {
    if (resendCountdown <= 0) return;
    const t = setTimeout(() => setResendCountdown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [resendCountdown]);

  // ── Live countdown during interview ──────────────────────────────────────
  // This local ticker is only a between-turns *estimate*. The server paces on
  // an active-time clock (per-gap capped at 5 minutes, so pauses and locked
  // screens don't burn the budget) and its elapsed_seconds / total_seconds are
  // authoritative: every TurnResponse resyncs us via syncClockFromServer, so
  // local drift can never accumulate across turns.
  //
  // While paused the ticker stops entirely and does NOT back-fill the gap on
  // resume, which is what keeps the UI honest with the server's clock.
  useEffect(() => {
    if (phase !== "interview" || totalSeconds === 0 || paused) return;
    const interval = setInterval(() => {
      setElapsedSeconds((s) => Math.min(s + 1, totalSeconds));
    }, 1000);
    return () => clearInterval(interval);
  }, [phase, totalSeconds, paused]);

  // ── beforeunload warning during active interview ─────────────────────
  useEffect(() => {
    if (phase !== "interview" || !participantId || paused) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [phase, participantId, paused]);

  // Lock both the live i18n language AND the persisted interview-language key
  // to the backend-authoritative value so the UI never drifts from the AI, and
  // so a mid-interview remount re-resolves to the same language.
  const lockInterviewLanguage = useCallback(
    (lang?: string | null) => {
      const code = (lang || "").slice(0, 2);
      if (!code || !(SUPPORTED_LANGUAGES as readonly string[]).includes(code)) return;
      localStorage.setItem("qp_interview_lang", code);
      if (i18n.language?.slice(0, 2) !== code) i18n.changeLanguage(code);
      // Refetch study info in the locked language so participant-facing copy
      // (the study name on the completion screen, etc.) is localized too.
      if (token) {
        getInterviewInfo(token, code)
          .then((data) => setInfo(data))
          .catch(() => { /* keep canonical name on failure */ });
      }
    },
    [i18n, token]
  );

  // ── TTS ────────────────────────────────────────────────────────────────

  // Reuse ONE audio element for the whole interview. iOS Safari only reliably
  // allows programmatic playback on an element it has already played once from
  // a user gesture; creating a fresh `new Audio()` per turn re-triggers the
  // autoplay block. `unlockAudio()` (called from the mic-enable tap) primes it.
  const getAudioEl = useCallback(() => {
    if (!audioRef.current) audioRef.current = new Audio();
    return audioRef.current;
  }, []);

  const unlockAudio = useCallback(() => {
    try {
      const audio = getAudioEl();
      audio.muted = true;
      audio.src = SILENT_AUDIO;
      const p = audio.play();
      if (p && typeof p.then === "function") {
        p.then(() => {
          audio.pause();
          audio.currentTime = 0;
          audio.muted = false;
        }).catch(() => { audio.muted = false; });
      }
    } catch {
      /* best-effort unlock — playback still has the manual Replay fallback */
    }
  }, [getAudioEl]);

  const playTTS = useCallback(
    (url: string) => {
      const audio = getAudioEl();
      audio.onended = null;
      audio.onerror = null;
      try { audio.pause(); } catch { /* not yet playing */ }
      setTtsFailedWarning(false);
      setTtsBlocked(false);
      if (muted) {
        // Nothing to hear — unblock the record button immediately.
        setTtsEnded(true);
        return;
      }
      audio.muted = false;
      audio.src = url;
      setTtsPlaying(true);
      setTtsEnded(false);
      audio.onended = () => {
        setTtsPlaying(false);
        setTtsEnded(true);
        hasEverPlayedRef.current = true;
      };
      audio.onerror = () => {
        setTtsPlaying(false);
        setTtsEnded(true);
        // Only surface the warning once we've successfully played at least
        // one clip — first-mount races / autoplay quirks shouldn't startle
        // the participant with a yellow banner before the interview starts.
        if (hasEverPlayedRef.current) setTtsFailedWarning(true);
      };
      audio.play()
        .then(() => { hasEverPlayedRef.current = true; })
        .catch(() => {
          setTtsPlaying(false);
          setTtsEnded(true);
          if (hasEverPlayedRef.current) setTtsFailedWarning(true);
          // First clip rejected → almost certainly the autoplay policy.
          // Offer a tap-to-play fallback so the question isn't silently lost.
          else setTtsBlocked(true);
        });
    },
    [muted, getAudioEl]
  );

  // ── Deferred voice synthesis (item 13) ──────────────────────────────────
  // The backend now usually returns tts_audio_url: null so the question text
  // renders sooner; the voice is fetched separately, once per turn. The
  // record button is never gated on audio that has not arrived.
  const ttsFetchSeqRef = useRef(0);
  const micTestDoneRef = useRef(false);
  useEffect(() => { micTestDoneRef.current = micTestDone; }, [micTestDone]);
  const answeringRef = useRef(false);
  useEffect(() => {
    answeringRef.current = isRecording || !!pendingBlob || processing || paused;
  }, [isRecording, pendingBlob, processing, paused]);

  const fetchDeferredTts = useCallback(
    async (pid: string, turnIdx: number | null | undefined) => {
      if (!token || !pid || turnIdx === null || turnIdx === undefined) return;
      // Realtime beta: the live model speaks; fetching deferred TTS would
      // pointlessly synthesize a server-side mp3 for a question the
      // participant already heard. After a fallback to classic, the voice
      // comes from deferred TTS again.
      if (infoRef.current?.interview_mode === "realtime_beta" && !realtimeFallbackRef.current) return;
      const seq = ++ttsFetchSeqRef.current;
      const startedAt = Date.now();
      let url: string | null = null;
      try {
        url = await getTurnAudio(token, pid, turnIdx);
      } catch {
        return; // stay text-only, the supported degradation
      }
      if (seq !== ttsFetchSeqRef.current || !url) return; // superseded / failed
      if (!micTestDoneRef.current) {
        // First question, mic check still on screen: park it like a direct
        // first-turn URL; the existing effect plays it once the check ends.
        pendingFirstTtsRef.current = url;
        return;
      }
      if (answeringRef.current) return; // never talk over the participant
      if (Date.now() - startedAt > 10_000 && ttsFetchSeqRef.current > 1) {
        // Arrived late: offer tap-to-play instead of surprising autoplay.
        try {
          getAudioEl().src = url;
          setTtsBlocked(true);
        } catch { /* no-op */ }
        return;
      }
      playTTS(url);
    },
    [token, playTTS, getAudioEl]
  );

  // ── Recording time limit ─────────────────────────────────────────────────

  useEffect(() => {
    if (!isRecording || paused) {
      setRecordingSeconds(0);
      recordingStartTimeRef.current = null;
      return;
    }
    recordingStartTimeRef.current = Date.now();
    beepFiredRef.current = false;
    const interval = setInterval(() => {
      if (!recordingStartTimeRef.current) return;
      const elapsed = Math.floor((Date.now() - recordingStartTimeRef.current) / 1000);
      const remaining = MAX_RECORDING_SECONDS - elapsed;
      // 30s-remaining cue: beep + vibrate (respect prefers-reduced-motion for beep)
      if (!beepFiredRef.current && remaining === 30) {
        beepFiredRef.current = true;
        try {
          const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
          if (!reduced) {
            const AC = (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext);
            const ctx = new AC();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.frequency.value = 440;
            gain.gain.value = 0.05;
            osc.connect(gain); gain.connect(ctx.destination);
            osc.start();
            osc.stop(ctx.currentTime + 0.1);
            setTimeout(() => ctx.close().catch(() => {}), 200);
          }
        } catch { /* no-op */ }
        try {
          if (typeof navigator.vibrate === "function") navigator.vibrate(200);
        } catch { /* no-op */ }
      }
      if (elapsed >= MAX_RECORDING_SECONDS) {
        handleStopAndPreview(false);
        setRecordingSeconds(MAX_RECORDING_SECONDS);
      } else {
        setRecordingSeconds(elapsed);
      }
    }, 1000);
    return () => clearInterval(interval);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isRecording, paused]);

  // ── Mic level meter ───────────────────────────────────────────────────

  useEffect(() => {
    if (micTestDone || phase !== "interview" || !micPermissionRequested) return;
    navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
      micStreamRef.current = stream;
      const ctx = new AudioContext();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      analyserRef.current = analyser;
      const data = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteFrequencyData(data);
        const avg = data.reduce((a, b) => a + b, 0) / data.length;
        setMicLevel(Math.min(100, avg * 2));
        if (avg > 15) setMicTestDone(true);
        micAnimRef.current = requestAnimationFrame(tick);
      };
      micAnimRef.current = requestAnimationFrame(tick);
    }).catch(() => setMicTestDone(true));
    return () => {
      if (micAnimRef.current) cancelAnimationFrame(micAnimRef.current);
      micStreamRef.current?.getTracks().forEach((t) => t.stop());
      if (analyserRef.current?.context && "close" in analyserRef.current.context) {
        (analyserRef.current.context as AudioContext).close().catch(() => {});
      }
    };
  }, [phase, micTestDone, micPermissionRequested]);

  useEffect(() => {
    if (micTestDone && pendingFirstTtsRef.current) {
      const url = pendingFirstTtsRef.current;
      pendingFirstTtsRef.current = null;
      playTTS(url);
    }
  }, [micTestDone, playTTS]);

  // ── Session storage for in-progress interview ────────────────────────────

  const sessionKey = token ? `interview_progress_${token}` : null;

  function saveSession(pid: string, question: string, turn: number, ti?: number | null, qi?: number, st?: Stimulus | null) {
    if (!sessionKey) return;
    sessionStorage.setItem(sessionKey, JSON.stringify({
      participantId: pid, currentQuestion: question, turnCount: turn,
      turnIndex: ti ?? null, questionIndex: qi ?? 0,
      stimulus: st ?? null,
    }));
  }

  function clearSession() {
    if (sessionKey) sessionStorage.removeItem(sessionKey);
  }

  function getSavedSession(): { participantId: string; currentQuestion: string; turnCount: number; turnIndex?: number | null; questionIndex?: number; stimulus?: Stimulus | null } | null {
    if (!sessionKey) return null;
    try {
      const raw = sessionStorage.getItem(sessionKey);
      return raw ? JSON.parse(raw) : null;
    } catch { return null; }
  }

  // ── Verification ─────────────────────────────────────────────────────────

  /** Clear the code field and any error/confirmation left over from a past try. */
  function resetCodeEntry() {
    setVerificationCode("");
    setCodeError(null);
    setCodeResent(false);
  }

  /** Put the caret in the code box without yanking the page around on mobile. */
  function focusCodeInput() {
    window.setTimeout(() => {
      codeInputRef.current?.focus({ preventScroll: true });
    }, 80);
  }

  async function handleSendVerification() {
    if (!token || !verificationEmail.trim()) return;
    setSendingVerification(true);
    setError("");
    try {
      await requestVerification(token, verificationEmail.trim(), (i18n.language || "en").slice(0, 2));
      setResendCountdown(60);
      resetCodeEntry();
      setPhase("email_sent");
      focusCodeInput();
    } catch {
      setError(t("emailEntry.sendError"));
    } finally {
      setSendingVerification(false);
    }
  }

  async function handleResendVerification() {
    if (!token || resendCountdown > 0) return;
    setError("");
    try {
      await requestVerification(token, verificationEmail.trim(), (i18n.language || "en").slice(0, 2));
      setResendCountdown(60);
      // A new code invalidates the previous one, so the field starts clean and
      // an "attempts exhausted" lock is lifted.
      resetCodeEntry();
      setCodeResent(true);
      focusCodeInput();
    } catch {
      setError(t("emailEntry.resendError"));
    }
  }

  /** Exchange the six-digit code for a session, then join the magic-link path. */
  async function handleVerifyCode(candidate?: string) {
    const digits = (candidate ?? verificationCode).replace(/\D/g, "").slice(0, 6);
    if (!token || digits.length !== 6 || verifyingCode) return;
    if (codeError === "too_many_attempts") return; // locked until a new code is sent
    setVerifyingCode(true);
    setCodeError(null);
    setCodeResent(false);
    setError("");
    try {
      const res = await verifyInterviewCode(token, verificationEmail.trim(), digits);
      applyVerifiedSession(res);
    } catch (err) {
      const kind = codeErrorKind(err);
      setCodeError(kind);
      setVerificationCode("");
      if (kind !== "too_many_attempts") focusCodeInput();
    } finally {
      setVerifyingCode(false);
    }
  }

  /** Digits only, so a pasted "123 456" works. Auto-submits on the sixth digit. */
  function handleCodeChange(raw: string) {
    const digits = raw.replace(/\D/g, "").slice(0, 6);
    setVerificationCode(digits);
    setCodeResent(false);
    if (codeError && codeError !== "too_many_attempts") setCodeError(null);
    if (digits.length === 6) void handleVerifyCode(digits);
  }

  // ── Consent ──────────────────────────────────────────────────────────────

  function handleConsentAccept() {
    setConsentGiven(true);
    proceedFromConsent();
  }

  async function proceedFromConsent() {
    if (!token) return;
    setStarting(true);
    setError("");
    try {
      // Check for email-based resume
      if (email.trim()) {
        const resume = await checkResume(token, email.trim(), sessionToken);
        if (resume.found && resume.participant_id) {
          setResumeCheck(resume);
          setLoadingResumeSummary(true);
          try {
            const summary = await getResumeSummary(token, resume.participant_id);
            setResumeSummary(summary);
          } catch { /* summary optional */ }
          finally { setLoadingResumeSummary(false); }
          setStarting(false);
          return;
        }
      }
      // Check for session-storage resume
      const saved = getSavedSession();
      if (saved) {
        restoreSavedSession(saved);
        setStarting(false);
        return;
      }
      // Returning participant we already know by name: straight on to
      // screening/interview. Everyone else gets the one-field first-name
      // screen; demographics are asked AFTER the interview, optionally.
      if (profileComplete && profile.firstName) {
        await routeAfterProfile();
        return;
      }
      // Studies that need the profile to interpret or segment answers ask
      // for it up front; everyone else gets the one-field first-name screen
      // and the full questionnaire after the interview.
      if (info?.profile_before_interview) {
        setShowPreQuestionnaire(true);
        setStarting(false);
        return;
      }
      setPhase("profile");
      setStarting(false);
      return;
    } catch {
      setError(t("consent.startError"));
    } finally {
      setStarting(false);
    }
  }

  // ── Profile ───────────────────────────────────────────────────────────────

  /** Routes from profile (or skip) to screening/interview. Shared by the
   *  "Continue" and "Skip" buttons on the minimal profile screen. */
  async function routeAfterProfile() {
    if (!token) return;
    setStarting(true);
    setError("");
    try {
      const questions = await getScreeningQuestions(token, (i18n.language || "en").slice(0, 2));
      if (questions.length > 0) {
        setScreeningQuestions(questions);
        setScreeningStep(0);
        setScreeningAnswers({});
        setPhase("screening");
      } else {
        await doStartInterview();
      }
    } catch {
      setError(t("consent.startError"));
    } finally {
      setStarting(false);
    }
  }

  async function proceedFromProfile() {
    const name = profile.firstName.trim();
    if (name) setDisplayName(name);
    await routeAfterProfile();
  }

  /** Called when the participant finishes (or skips through) the optional
   *  post-interview questionnaire on the completion screen. The component
   *  already persisted the answers (panel profile or participant profile). */
  function handleQuestionnaireComplete(data: QuestionnaireResult) {
    setPanelConsentGiven(data.panelConsent);
    if (data.firstName) setProfile((p) => ({ ...p, firstName: data.firstName }));
    if (data.ageRange) setAgeRange(data.ageRange);
    if (data.country) setCountry(data.country);
    setPostProfileState("done");
    setShowPostQuestionnaire(false);
  }

  /** Finishing (or skipping) the pre-interview questionnaire. Same component
   *  and same persistence as the post-interview path; the only difference is
   *  that it continues into screening/interview instead of ending. */
  async function handlePreQuestionnaireComplete(data: QuestionnaireResult) {
    setPanelConsentGiven(data.panelConsent);
    if (data.firstName) {
      setProfile((p) => ({ ...p, firstName: data.firstName }));
      setDisplayName(data.firstName);
    }
    if (data.ageRange) setAgeRange(data.ageRange);
    if (data.country) setCountry(data.country);
    setDidPreQuestionnaire(true);
    setShowPreQuestionnaire(false);
    await routeAfterProfile();
  }

  /** Post-interview panel opt-in for participants who declined earlier. Flips
   *  panel_consent on the existing profile via the same upsert endpoint. */
  async function handlePostInterviewOptIn() {
    if (!token || !sessionToken || !email) return;
    setRepromptState("saving");
    try {
      await savePanelProfile(token, {
        email,
        session_token: sessionToken,
        preferred_language: (i18n.language || "en").slice(0, 2),
        panel_consent: true,
        tag_ids: [],
      });
      setRepromptState("done");
    } catch {
      setRepromptState("idle");
    }
  }

  // ── Interview start ────────────────────────────────────────────────────

  async function doStartInterview() {
    if (!token) return;
    const chosenLang = (i18n.language || "en").slice(0, 2);
    let res;
    try {
      res = await startInterview(token, {
        displayName: profile.firstName.trim() || displayName || undefined,
        profession: profile.jobFunction || profession || undefined,
        ageRange: profile.ageRange || ageRange || undefined,
        country: country || profile.city || undefined,
        email: email || undefined,
        sessionToken: sessionToken || undefined,
        preferredLanguage: chosenLang,
        screeningAnswers,
      });
    } catch (err: unknown) {
      // The workspace billing gate returns 403 {code: "study_unavailable"} —
      // e.g. the researcher hasn't verified their email, or the study is out
      // of credits. Show a calm terminal message, not a retryable error.
      const e = err as {
        response?: {
          status?: number;
          data?: { detail?: { code?: string; message?: string; participant_id?: string } };
        };
      };
      const detail = e?.response?.data?.detail;
      if (e?.response?.status === 403 && detail?.code === "study_unavailable") {
        // Always use the localized copy — the backend `message` is a fixed
        // English sentence and would leak English into non-EN interviews.
        setStudyUnavailableMsg(t("studyUnavailable.body"));
        setPhase("study_unavailable");
        return;
      }
      // The link hit its participant limit. Terminal, not retryable.
      if (e?.response?.status === 403 && detail?.code === "link_full") {
        setPhase("link_full");
        return;
      }
      // This email already finished the interview on this link.
      if (e?.response?.status === 409 && detail?.code === "already_completed") {
        setPhase("already_completed");
        return;
      }
      // An interview for this email is already open (second device, second
      // tab, or a /resume check that got skipped). Offer to continue it
      // rather than silently starting a duplicate.
      if (e?.response?.status === 409 && detail?.code === "resume_available") {
        const resume = await checkResume(token, email.trim());
        if (resume.found && resume.participant_id) {
          setResumeCheck(resume);
          setLoadingResumeSummary(true);
          try {
            setResumeSummary(await getResumeSummary(token, resume.participant_id));
          } catch { /* summary optional */ }
          finally { setLoadingResumeSummary(false); }
          return;
        }
      }
      throw err;
    }
    // Lock the UI chrome (progress, completion screen, banners) to the language
    // the backend is actually conducting the interview in — never let the
    // client-side i18n state drift away from what the AI is speaking.
    lockInterviewLanguage(res.language);
    setParticipantId(res.participant_id);
    setCurrentQuestion(res.first_question);
    setStimulus(res.stimulus ?? null);
    setTurnCount(1);
    setQuestionIndex(res.question_index ?? 0);
    setIsFollowUp(false);
    setIsWarmup(res.is_warmup ?? false);
    setTurnIndex(res.turn_index ?? null);
    const total = (info?.interview_duration_minutes ?? 0) * 60;
    setTotalSeconds(total);
    setElapsedSeconds(0);
    saveSession(res.participant_id, res.first_question, 1, res.turn_index ?? null, res.question_index ?? 0, res.stimulus ?? null);
    setPhase("interview");
    if (res.tts_audio_url) {
      pendingFirstTtsRef.current = res.tts_audio_url;
    } else {
      setTtsEnded(true);
      void fetchDeferredTts(res.participant_id, res.turn_index);
    }
  }

  function restoreSavedSession(saved: NonNullable<ReturnType<typeof getSavedSession>>) {
    setParticipantId(saved.participantId);
    setCurrentQuestion(saved.currentQuestion);
    setStimulus(saved.stimulus ?? null);
    setTurnCount(saved.turnCount);
    setTurnIndex(saved.turnIndex ?? null);
    setQuestionIndex(saved.questionIndex ?? 0);
    setPhase("interview");
  }

  function handleResumeSession() {
    const saved = getSavedSession();
    if (!saved) return;
    restoreSavedSession(saved);
  }

  async function handleConfirmResume() {
    if (!resumeCheck?.participant_id) return;
    // Re-lock the UI to the language this interview was started in.
    lockInterviewLanguage(resumeSummary?.language);
    setParticipantId(resumeCheck.participant_id);
    setCurrentQuestion(resumeCheck.last_question ?? "");
    setStimulus(resumeCheck.last_stimulus ?? null);
    setTurnCount(resumeCheck.turn_count ?? 1);
    setQuestionIndex(resumeCheck.question_index ?? 0);
    setTurnIndex(null);
    const total = (info?.interview_duration_minutes ?? 0) * 60;
    setTotalSeconds(total);
    const alreadyElapsed = (resumeSummary?.elapsed_minutes ?? 0) * 60;
    setElapsedSeconds(Math.min(alreadyElapsed, total));
    saveSession(resumeCheck.participant_id, resumeCheck.last_question ?? "", resumeCheck.turn_count ?? 1, null, resumeCheck.question_index ?? 0, resumeCheck.last_stimulus ?? null);
    setResumeCheck(null);
    setResumeSummary(null);
    setPhase("interview");
  }

  async function handleScreeningAnswer(questionId: string, answer: string) {
    const updated = { ...screeningAnswers, [questionId]: answer };
    setScreeningAnswers(updated);
    if (screeningStep < screeningQuestions.length - 1) {
      setScreeningStep((s) => s + 1);
    } else {
      setScreeningLoading(true);
      setScreeningError("");
      setScreeningErrorKind(null);
      try {
        const result = await submitScreening(token!, updated);
        if (result.qualified) {
          await doStartInterview();
        } else {
          setDisqualifiedOn(result.disqualified_on ?? "");
          setPhase("disqualified");
        }
      } catch (err: unknown) {
        // Distinguish network/timeout vs server error so we can show
        // tailored copy. Axios sets `response` only when the server
        // actually answered.
        const e = err as { response?: { status?: number }; message?: string };
        const isNetwork = !e?.response || e?.message === "Network Error";
        const isRateLimited = e?.response?.status === 429;
        const kind = isNetwork ? "network" : isRateLimited ? "ratelimit" : "server";
        setScreeningErrorKind(kind);
        setScreeningError(
          kind === "network"
            ? t("screening.submissionErrorNetwork")
            : kind === "ratelimit"
              ? t("screening.rateLimited", { defaultValue: "Too many attempts in a short time. Please wait a minute before trying again." })
              : t("screening.submissionErrorServer"),
        );
        setScreeningRetryCount((c) => c + 1);
        // Important: do NOT clear `screeningAnswers[questionId]` — keep
        // the participant's selection so the retry is one click away.
      } finally {
        setScreeningLoading(false);
      }
    }
  }

  /** Tap-to-stop. With `autoSend` (the normal tap) the take sends itself
   *  after a short Undo window; the 240s cap and interruptions land in the
   *  playable preview instead so the participant can listen before sending. */
  async function handleStopAndPreview(autoSend = true) {
    try {
      const blob = await stopRecording();
      lastBlobRef.current = blob;
      setPendingBlob(blob);
      setTtsEnded(false);
      if (autoSend) {
        setAutoSending(true);
        if (autoSendTimerRef.current) window.clearTimeout(autoSendTimerRef.current);
        autoSendTimerRef.current = window.setTimeout(() => {
          autoSendTimerRef.current = null;
          setAutoSending(false);
          setPendingBlob(null);
          void submitAnswer(blob);
        }, 2500);
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "";
      if (msg === SILENT_RECORDING) {
        // The whole take was a flat line: the mic is muted or the OS is
        // recording from the wrong device. Re-run the mic test right away.
        triggerMicRecheck();
        return;
      }
      setError(
        msg === RECORDING_TOO_SHORT
          ? t("recording.tooShort")
          : t("interview.recordingError")
      );
    }
  }

  function handleUndoAutoSend() {
    if (autoSendTimerRef.current) window.clearTimeout(autoSendTimerRef.current);
    autoSendTimerRef.current = null;
    setAutoSending(false);
  }

  async function handleSubmitPending() {
    if (!pendingBlob) return;
    const blob = pendingBlob;
    setPendingBlob(null);
    await submitAnswer(blob);
  }

  /** The server's active-time clock is authoritative: it ignores the gaps
   *  where the participant paused or locked their screen (each gap capped at
   *  5 minutes), so it is always the truth about the remaining budget. Every
   *  TurnResponse (start / respond / skip / finish / 409 resync) snaps the
   *  local countdown back onto it instead of letting local drift accumulate. */
  function syncClockFromServer(res: Pick<SubmitAudioResponse, "elapsed_seconds" | "total_seconds">) {
    if (res.total_seconds !== undefined && res.total_seconds > 0) setTotalSeconds(res.total_seconds);
    if (res.elapsed_seconds !== undefined) setElapsedSeconds(res.elapsed_seconds);
  }

  /** Apply a TurnResponse that carries the next (non-complete) question. */
  function applyNextTurn(res: SubmitAudioResponse, nextTurn: number) {
    setCurrentQuestion(res.question_text ?? "");
    setStimulus(res.stimulus ?? null);
    setTurnCount(nextTurn);
    setQuestionIndex(res.question_index ?? questionIndex);
    setIsFollowUp(res.is_follow_up ?? false);
    setIsWarmup(false);
    setTurnIndex(res.turn_index ?? null);
    syncClockFromServer(res);
    setTtsEnded(false);
    // Drop any parked audio from the previous turn: if this turn's deferred
    // fetch fails, a stale "Play the question" button would otherwise replay
    // the question they already answered.
    setTtsBlocked(false);
    try {
      const el = getAudioEl();
      el.pause();
      el.removeAttribute("src");
    } catch { /* element not created yet */ }
    saveSession(participantId, res.question_text ?? "", nextTurn, res.turn_index ?? null, res.question_index ?? questionIndex, res.stimulus ?? null);
    if (res.tts_audio_url) {
      playTTS(res.tts_audio_url);
    } else {
      setTtsEnded(true);
      void fetchDeferredTts(participantId, res.turn_index);
    }
  }

  /** Completion, whether it came from /respond, /skip or /finish. */
  function applyCompletion(res: SubmitAudioResponse, playClosing: boolean) {
    clearSession();
    setTurnIndex(res.turn_index ?? null);
    syncClockFromServer(res);
    setPendingBlob(null);
    lastBlobRef.current = null;
    setPhase("complete");
    if (playClosing && res.tts_audio_url) {
      playTTS(res.tts_audio_url);
    } else if (playClosing) {
      void fetchDeferredTts(participantId, res.turn_index);
    } else if (audioRef.current) {
      audioRef.current.pause();
    }
  }

  /** HTTP 409 turn_mismatch: the server is ahead of us (a retried upload it
   *  had already processed, or a second tab). Resync to its view of the
   *  interview and drop the pending take. Returns true when handled. */
  function handleTurnMismatch(err: unknown): boolean {
    const e = err as { response?: { status?: number; data?: { detail?: Partial<TurnMismatchDetail> } } };
    const detail = e?.response?.data?.detail;
    if (e?.response?.status !== 409 || detail?.code !== "turn_mismatch" || !detail.current) return false;
    const current = detail.current;
    setPendingBlob(null);
    lastBlobRef.current = null;
    setTypedAnswer("");
    setError("");
    if (current.is_complete) {
      applyCompletion(current, true);
    } else {
      applyNextTurn(current, turnCount + 1);
      setNotice(t("interview.turnResynced"));
    }
    return true;
  }

  async function handleSubmitTyped() {
    const value = typedAnswer.trim();
    if (!value) return;
    await submitAnswer(value);
  }

  /** Shared submit pipeline for both recorded (Blob) and typed (string)
   *  answers — same processing steps, transcript flash, dedupe and retry
   *  semantics on both paths. */
  async function submitAnswer(payload: Blob | string) {
    const isTyped = typeof payload === "string";
    setProcessing(true);
    setError("");
    setNotice(null);

    try {
      const res = await submitAudio(token!, participantId, payload, turnIndex);
      emptyStreakRef.current = 0;
      if (isTyped) setTypedAnswer("");
      if (res.is_complete) {
        applyCompletion(res, false);
      } else if (res.question_text) {
        const nextTurn = turnCount + 1;
        // PF-3: surface the engine's coaching hint (or clear it if Claude
        // decided the participant is back on track). Stays dismissed if the
        // user explicitly closed the previous one for this turn.
        if (res.coaching_hint) {
          setCoachingHint(res.coaching_hint);
          setCoachingHintDismissed(false);
        } else {
          setCoachingHint(null);
        }
        applyNextTurn(res, nextTurn);
      }
    } catch (err: unknown) {
      if (handleTurnMismatch(err)) return;
      // Distinguish "we didn't hear you" (422) from transport failures.
      // Empty-transcript: clear the blob so the participant records fresh;
      // transport: keep the blob in pending so they can retry the same take.
      const errWithResp = err as { response?: { status?: number; data?: { detail?: { code?: string } } }; code?: string };
      const status = errWithResp?.response?.status;
      const code = errWithResp?.response?.data?.detail?.code;
      if (errWithResp?.code === RECORDING_TOO_LARGE) {
        // Client-side size guard: the take never left the device. Drop it so
        // the participant records a shorter answer.
        setPendingBlob(null);
        lastBlobRef.current = null;
        setError(t("recording.tooLong"));
      } else if (status === 422 && code === "empty_transcript") {
        if (isTyped) {
          setError(t("interview.textAnswer.emptyError", {
            defaultValue: "Please write an answer before sending.",
          }));
        } else if (emptyStreakRef.current >= 1) {
          // Second unusable take in a row: the problem is the mic, not the
          // room. Stop the loop and send them back to the mic test.
          triggerMicRecheck();
        } else {
          emptyStreakRef.current += 1;
          setPendingBlob(null);
          lastBlobRef.current = null;
          setError(t("interview.emptyTranscript", {
            defaultValue: "We didn't catch that. Please record again in a quieter spot.",
          }));
        }
      } else {
        // Typed answers stay in the textarea (only cleared on success), so a
        // retry is just pressing Send again — the blob path restores from
        // lastBlobRef for the same reason.
        if (!isTyped) setPendingBlob(lastBlobRef.current);
        const isNetwork = !(err as { response?: unknown })?.response;
        if (isNetwork) {
          setError(t("interview.networkError", { defaultValue: "Connection lost. Please check your internet and tap Submit to retry." }));
        } else if (status === 429) {
          // Rate-limited: retrying immediately just re-trips the limit —
          // tell the participant to wait instead of showing a generic error.
          setError(t("interview.rateLimited", { defaultValue: "Too many attempts in a short time. Please wait a minute, then tap Submit again, your answer is saved." }));
        } else {
          setError(t("interview.serverError", { defaultValue: "Something went wrong on our end. Please tap Submit to try again." }));
        }
      }
    } finally {
      setProcessing(false);
    }
  }

  function handleReRecord() {
    setPendingBlob(null);
    lastBlobRef.current = null;
    setError("");
    setNotice(null);
    setTtsEnded(true);
  }

  /** The mic is demonstrably not delivering audio: stop the interview and
   *  re-run the mic test instead of letting the participant loop on failed
   *  takes. Interview state is untouched, so passing the test resumes on
   *  the exact same question. */
  function triggerMicRecheck() {
    emptyStreakRef.current = 0;
    setPendingBlob(null);
    lastBlobRef.current = null;
    setError("");
    setNotice(null);
    setTtsEnded(true);
    setMicRecheck(true);
    setMicTestDone(false);
  }

  /** Discreet pause: stops the question audio and any in-progress take (kept
   *  as a reviewable preview). Resume picks the audio back up. */
  function handlePause() {
    if (isRecording) void handleStopAndPreview(false);
    if (autoSending) handleUndoAutoSend();
    const audio = audioRef.current;
    pausedTtsRef.current = false;
    if (audio && ttsPlaying) {
      try { audio.pause(); } catch { /* no-op */ }
      pausedTtsRef.current = true;
      setTtsPlaying(false);
    }
    setFinishConfirming(false);
    setPaused(true);
  }

  function handleResume() {
    setPaused(false);
    const audio = audioRef.current;
    if (pausedTtsRef.current && audio && !muted) {
      pausedTtsRef.current = false;
      setTtsPlaying(true);
      audio.play().catch(() => { setTtsPlaying(false); setTtsEnded(true); });
    }
  }

  /** "Finish here": end the interview early with what has been shared so far. */
  async function handleFinish() {
    if (!token || !participantId) return;
    setFinishing(true);
    setError("");
    try {
      if (isRecording) {
        try { await stopRecording(); } catch { /* nothing worth keeping */ }
      }
      handleUndoAutoSend();
      const res = await finishInterview(token, participantId);
      setFinishConfirming(false);
      setPaused(false);
      applyCompletion(res, true);
    } catch {
      setError(t("interview.finish.error"));
    } finally {
      setFinishing(false);
    }
  }

  function toggleMute() {
    setMuted((m) => {
      const next = !m;
      try { localStorage.setItem("qp_interview_muted", next ? "1" : "0"); } catch { /* private mode */ }
      if (next && audioRef.current) {
        // Fix 5: Fully reset audio on mute — pause, reset position,
        // clear callbacks to prevent stale state, and enable recording
        audioRef.current.onended = null;
        audioRef.current.onerror = null;
        audioRef.current.pause();
        audioRef.current.currentTime = 0;
        setTtsPlaying(false);
        setTtsEnded(true);
      }
      return next;
    });
  }

  // ── Render helpers ─────────────────────────────────────────────────────

  // Conservative-but-tolerant email regex: must look like an address.
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  const isEmailValid = emailRegex.test(verificationEmail.trim());

  // Researcher identity: prefer logo, fall back to initials avatar.
  // Only ever derive initials from an EXPLICIT researcher_name. We must NOT
  // fall back to the company name (that leaks the client's identity to
  // participants) or the study title (yields meaningless initials). When the
  // researcher hasn't set a name/logo, the avatar is simply hidden.
  function researcherInitials(): string {
    const source = (info?.researcher_name || "")
      .replace(/^\s*\[[^\]]*\]\s*/, "")
      .replace(/^[^\p{L}]+/u, "");
    return source
      .split(/\s+/)
      .filter(Boolean)
      .map((w) => w.match(/\p{L}/u)?.[0] ?? "")
      .filter(Boolean)
      .slice(0, 2)
      .join("")
      .toUpperCase();
  }
  function ResearcherIdentity() {
    if (info?.researcher_logo_url) {
      return (
        <div className="landing-researcher-logo">
          <img src={info.researcher_logo_url} alt={info.researcher_name ?? ""} />
        </div>
      );
    }
    const initials = researcherInitials();
    if (!initials) return null;
    return (
      <div className="researcher-initials-avatar" aria-hidden="true">
        {initials}
      </div>
    );
  }

  // ── Loading / error states ──────────────────────────────────────────────

  if (infoLoading) {
    return (
      <div className="interview-page">
        <div className="interview-container">
          <p className="muted-text">{t("loading")}</p>
        </div>
      </div>
    );
  }

  if (error && !info) {
    return (
      <div className="interview-page">
        <div className="interview-container" style={{ textAlign: "center", paddingTop: 60 }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: "var(--primary, #6366f1)", marginBottom: 32 }}>QualiPulse</div>
          <div style={{ marginBottom: 16 }}><IconLink size={48} /></div>
          <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 10 }}>{t("linkInactive.title")}</h1>
          <p style={{ color: "var(--text-secondary, #6b7280)", fontSize: 15, maxWidth: 380, margin: "0 auto 20px" }}>
            {t("linkInactive.expiredHelp")}
          </p>
          <button
            className="btn btn-ghost"
            onClick={() => window.history.back()}
            style={{ fontSize: 14 }}
          >
            ← {t("linkInactive.goBack")}
          </button>
        </div>
      </div>
    );
  }

  // ── In-app browser interstitial ─────────────────────────────────────────
  // Instagram/Facebook/TikTok webviews don't grant microphone access — the
  // participant would sail through consent and screening only to dead-end at
  // the mic step with a misleading "check Safari settings" error. Catch them
  // here, before they invest anything, and steer them to a real browser.
  // QA override: sessionStorage.setItem("qp_force_webview", "1").
  const forceWebview =
    typeof sessionStorage !== "undefined" && sessionStorage.getItem("qp_force_webview") === "1";
  const browserEnv = detectInAppBrowser();
  if ((browserEnv.inApp || !browserEnv.canRecord || forceWebview) && !webviewBypass) {
    const intentUrl = browserEnv.os === "android" ? androidChromeIntentUrl() : null;
    const copyInterviewLink = () => {
      const url = window.location.href;
      const legacyCopy = () => {
        const ta = document.createElement("textarea");
        ta.value = url;
        ta.setAttribute("readonly", "");
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        try {
          document.execCommand("copy");
        } catch {
          // best effort — the participant can still copy from the URL bar
        }
        document.body.removeChild(ta);
      };
      // Don't await the async clipboard API: some webviews leave its
      // permission promise pending forever, which would swallow the feedback.
      if (navigator.clipboard?.writeText) {
        navigator.clipboard.writeText(url).catch(legacyCopy);
      } else {
        legacyCopy();
      }
      setLinkCopied(true);
    };
    return (
      <div className="interview-page">
        <div className="interview-container mic-test-card">
          <div className="mic-prompt-icon"><IconCompass size={40} /></div>
          <h2 className="mic-test-title">{t("inAppBrowser.title")}</h2>
          <p className="mic-test-subtitle">
            {browserEnv.appName
              ? t("inAppBrowser.bodyNamed", { app: browserEnv.appName })
              : t("inAppBrowser.body")}
          </p>
          <div className="mic-prompt-steps">
            <div className="mic-prompt-step">
              <span className="mic-prompt-num">1</span>
              <span>{t("inAppBrowser.step1")}</span>
            </div>
            <div className="mic-prompt-step">
              <span className="mic-prompt-num">2</span>
              <span>{t("inAppBrowser.step2")}</span>
            </div>
          </div>
          {intentUrl && (
            <a className="btn btn-primary" href={intentUrl} style={{ minHeight: 44 }}>
              {t("inAppBrowser.openChrome")}
            </a>
          )}
          <button
            className={intentUrl ? "btn btn-ghost" : "btn btn-primary"}
            style={{ minHeight: 44, marginTop: 8 }}
            onClick={copyInterviewLink}
          >
            {linkCopied ? t("inAppBrowser.copied") : t("inAppBrowser.copyLink")}
          </button>
          {browserEnv.canRecord && (browserEnv.inApp || forceWebview) && (
            <button
              className="btn btn-ghost"
              style={{ marginTop: 12, fontSize: 13, opacity: 0.8 }}
              onClick={() => setWebviewBypass(true)}
            >
              {t("inAppBrowser.tryAnyway")}
            </button>
          )}
          <p className="mic-prompt-note">{t("inAppBrowser.note")}</p>
        </div>
      </div>
    );
  }

  if (consentDeclined) {
    return (
      <div className="interview-page">
        <div className="interview-container interview-complete">
          <h1 className="interview-complete-title">{t("consent.declinedTitle")}</h1>
          <p className="interview-complete-text">
            {t("consent.declinedDesc")}
          </p>
        </div>
      </div>
    );
  }

  // ── Email entry phase ─────────────────────────────────────────────────

  if (phase === "email_entry") {
    return (
      <div className="interview-page">
        <div className="interview-container" style={{ maxWidth: "var(--participant-card-max-w)" }}>
        <div style={{
          background: "#fff",
          borderRadius: "var(--radius-lg)",
          padding: "48px 36px",
          boxShadow: "var(--shadow-md)",
          maxWidth: "var(--participant-card-max-w)",
          width: "100%",
          margin: "0 auto",
        }}>
          <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 4 }}>
            <LanguagePicker onChange={lockInterviewLanguage} />
          </div>
          <ResearcherIdentity />
          {handoffClaimError && (
            <div className="error-banner" role="alert" style={{ marginBottom: 16 }}>
              {t("handoff.claimExpired")}
            </div>
          )}
          <h1 className="interview-project-name" style={{ marginBottom: 8, textAlign: "center" }}>{info?.project_name}</h1>
          {info?.researcher_name && (
            <p style={{ fontSize: 14, color: "var(--text-secondary, #6b7280)", marginBottom: 24, textAlign: "center" }} dangerouslySetInnerHTML={{ __html: t("emailEntry.studyBy", { name: info.researcher_name }) }} />
          )}
          {info?.interview_duration_minutes && (
            <p className="interview-duration" style={{ textAlign: "center" }}>⏱ {t("emailEntry.duration", { minutes: info.interview_duration_minutes })}</p>
          )}
          {info?.incentive_text && (
            <p className="interview-duration" style={{ textAlign: "center", marginTop: 6 }} title={t("consent.incentiveNote")}>
              <IconGift /> {t("consent.incentiveLabel")} {info.incentive_text}
            </p>
          )}
          <p style={{ color: "var(--text-secondary, #6b7280)", marginBottom: 28, lineHeight: 1.6, textAlign: "center" }}>
            {t("emailEntry.enterEmailDesc")}
          </p>
          {/* Form fields left-aligned for better readability */}
          <div style={{ textAlign: "left" }}>
            <div className="interview-name-field">
              <label className="field-label" htmlFor="interview-email">{t("emailEntry.yourEmail")}</label>
              <input
                id="interview-email"
                type="email"
                className="field-input"
                value={verificationEmail}
                onChange={(e) => setVerificationEmail(e.target.value)}
                placeholder={t("emailEntry.emailPlaceholder")}
                onKeyDown={(e) => e.key === "Enter" && handleSendVerification()}
                autoFocus
              />
            </div>
            {error && <div className="error-banner" role="alert">{error}</div>}
            <button
              className="btn btn-primary btn-lg"
              onClick={handleSendVerification}
              disabled={sendingVerification || !isEmailValid}
              style={{
                width: "100%",
                marginTop: 8,
                minHeight: 44,
                opacity: !isEmailValid ? 0.55 : 1,
              }}
            >
              {sendingVerification ? t("emailEntry.sendingLink") : t("emailEntry.sendLink")}
            </button>
            <p style={{ fontSize: 12, color: "var(--text-muted, #9ca3af)", marginTop: 12, lineHeight: 1.5 }}>
              {t("emailEntry.emailNote")}
            </p>
            {/* "Why we ask for your email" expander — addresses the trust ask */}
            <div className="why-email-expander">
              <button
                type="button"
                className="why-email-toggle"
                aria-expanded={whyEmailOpen}
                onClick={() => setWhyEmailOpen((v) => !v)}
              >
                {whyEmailOpen ? "▾" : "▸"} {t("emailEntry.whyEmailToggle")}
              </button>
              {whyEmailOpen && (
                <p className="why-email-body">{t("emailEntry.whyEmailBody")}</p>
              )}
            </div>
          </div>

          {/* Trust signal */}
          <p style={{ textAlign: "center", fontSize: 12, color: "var(--text-muted, #9ca3af)", marginTop: 16, display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
            {t("emailEntry.trustLine")}
          </p>
        </div>
        </div>
      </div>
    );
  }

  // ── Code entry phase ─────────────────────────────────────────────────────
  // The code is the primary route on purpose: tapping the emailed link opens
  // the study in the mail app's browser, where the microphone often refuses to
  // work and the tab they started in is gone. Typing the code keeps them here.

  if (phase === "email_sent") {
    const codeLocked = codeError === "too_many_attempts";
    const codeErrorText = !codeError
      ? ""
      : codeError === "code_invalid"
      ? t("emailSent.errorInvalid")
      : codeError === "code_expired"
      ? t("emailSent.errorExpired")
      : codeError === "too_many_attempts"
      ? t("emailSent.errorLocked")
      : t("emailSent.errorGeneric");
    return (
      <div className="interview-page">
        <div className="interview-container otp-screen" style={{ maxWidth: 440 }}>
          <div className="otp-icon"><IconMail size={52} /></div>
          <h1 className="otp-title">{t("emailSent.title")}</h1>
          <p
            className="otp-desc"
            dangerouslySetInnerHTML={{ __html: t("emailSent.desc", { email: verificationEmail }) }}
          />
          <p className="otp-why">{t("emailSent.codeWhy")}</p>

          <form
            className="otp-form"
            onSubmit={(e) => { e.preventDefault(); void handleVerifyCode(); }}
          >
            <label className="field-label otp-label" htmlFor="interview-otp">
              {t("emailSent.codeLabel")}
            </label>
            <input
              id="interview-otp"
              ref={codeInputRef}
              className="field-input otp-input"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="[0-9]{6}"
              placeholder={t("emailSent.codePlaceholder")}
              value={verificationCode}
              disabled={verifyingCode || codeLocked}
              aria-invalid={codeError ? true : undefined}
              aria-describedby="interview-otp-status"
              onChange={(e) => handleCodeChange(e.target.value)}
            />
            <button
              type="submit"
              className="btn btn-primary btn-lg otp-submit"
              disabled={verificationCode.length !== 6 || verifyingCode || codeLocked}
            >
              {verifyingCode ? t("emailSent.verifying") : t("emailSent.verify")}
            </button>
          </form>

          <div id="interview-otp-status" className="otp-status" aria-live="polite">
            {codeErrorText ? (
              <p className="error-banner otp-error">{codeErrorText}</p>
            ) : codeResent ? (
              <p className="otp-resent">{t("emailSent.codeResent")}</p>
            ) : null}
          </div>

          <p className="otp-expiry">{t("emailSent.expiry")}</p>
          {error && <div className="error-banner" role="alert">{error}</div>}
          <button
            className="btn btn-ghost otp-resend"
            onClick={handleResendVerification}
            disabled={resendCountdown > 0}
          >
            {resendCountdown > 0 ? t("emailSent.resendCooldown", { seconds: resendCountdown }) : t("emailSent.resend")}
          </button>

          <div className="otp-link-alt">
            <p className="otp-link-alt-title">{t("emailSent.linkAlternativeTitle")}</p>
            <p className="otp-link-alt-body">{t("emailSent.linkAlternative")}</p>
          </div>

          <button
            className="btn btn-ghost btn-sm otp-change-email"
            onClick={() => { setPhase("email_entry"); setError(""); resetCodeEntry(); }}
          >
            ← {t("emailSent.differentEmail")}
          </button>
        </div>
      </div>
    );
  }

  // ── Resume confirm ───────────────────────────────────────────────────────
  // Shown when checkResume returned an in-progress participant (cross-device
  // resume via email).
  //
  // Rendered BEFORE the consent branch on purpose, for the same reason as
  // showPreQuestionnaire below: proceedFromConsent only sets resumeCheck, it
  // never changes `phase`. With this check placed after the consent branch,
  // a returning participant tapping "I'm ready, begin" re-rendered the consent
  // screen and the button appeared to do nothing.

  if (resumeCheck?.found && resumeCheck.participant_id) {
    return (
      <div className="interview-page">
        <div className="interview-container resume-confirm-card">
          <h1 className="consent-title">{t("resume.title")}</h1>
          <p className="resume-confirm-subtitle" dangerouslySetInnerHTML={{ __html: t("resume.desc", { projectName: info?.project_name ?? "" }) }} />
          {loadingResumeSummary ? (
            <p className="muted-text">{t("resume.loadingProgress")}</p>
          ) : resumeSummary && resumeSummary.questions_covered.length > 0 ? (
            <div className="resume-summary-panel">
              <p className="resume-summary-label">{t("resume.coveredTopics")}</p>
              <ul className="resume-summary-list">
                {resumeSummary.questions_covered.map((q, i) => (
                  <li key={i} className="resume-summary-item">
                    <span className="resume-summary-check">✓</span>
                    <span>{q}</span>
                  </li>
                ))}
              </ul>
              {resumeSummary.elapsed_minutes > 0 && (
                <p className="muted-text" style={{ marginTop: 8, fontSize: 13 }}>
                  {info?.interview_duration_minutes
                    ? t("resume.elapsedOf", { elapsed: Math.round(resumeSummary.elapsed_minutes), total: info.interview_duration_minutes })
                    : t("resume.elapsed", { minutes: Math.round(resumeSummary.elapsed_minutes) })}
                </p>
              )}
            </div>
          ) : null}
          {resumeCheck.last_question && (
            <div className="resume-last-question">
              <p className="resume-last-label">{t("resume.lastQuestion")}</p>
              <p className="resume-last-text">"{resumeCheck.last_question}"</p>
            </div>
          )}
          <div className="consent-actions">
            <button className="btn btn-primary" onClick={handleConfirmResume}>
              {t("resume.resume")} →
            </button>
            <button
              className="btn btn-ghost"
              onClick={async () => {
                setResumeCheck(null);
                setResumeSummary(null);
                try {
                  const questions = await getScreeningQuestions(token!, (i18n.language || "en").slice(0, 2));
                  if (questions.length > 0) {
                    setScreeningQuestions(questions);
                    setScreeningStep(0);
                    setScreeningAnswers({});
                    setPhase("screening");
                  } else {
                    await doStartInterview();
                  }
                } catch {
                  setError(t("consent.startError"));
                }
              }}
            >
              {t("resume.startOver")}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Consent phase ────────────────────────────────────────────────────────

  // Rendered BEFORE the consent branch on purpose. Accepting consent on a
  // study with profile_before_interview only flips showPreQuestionnaire, it
  // does not change `phase`. With this check below the consent branch the
  // consent screen simply re-rendered and the button appeared to do nothing.
  if (showPreQuestionnaire) {
    return (
      <ParticipantQuestionnaire
        linkToken={token!}
        email={email}
        sessionToken={sessionToken}
        participantId={participantId || null}
        initialFirstName={profile.firstName}
        onComplete={handlePreQuestionnaireComplete}
      />
    );
  }

  if (phase === "consent" && info) {
    return (
      <div className="interview-page">
        <div
          className="interview-container consent-card"
          style={{ maxWidth: "var(--participant-card-max-w)" }}
        >
          <ResearcherIdentity />
          {info.researcher_name && (
            <p className="consent-researcher-name">{info.researcher_name}</p>
          )}
          {info.branding?.mode === "anonymous" && (
            <p className="consent-anonymous-note">{t("consent.anonymousStudy")}</p>
          )}
          <h1 className="consent-title">{t("consent.title")}</h1>
          <p className="consent-project">{info.project_name}</p>
          {info.research_context && (
            <p className="consent-research-context">{info.research_context}</p>
          )}
          <div className="consent-body">
            <p className="consent-ai-disclosure">{t("consent.desc")}</p>
            <p>{t("consent.byParticipating")}</p>
            <ul className="consent-list" style={{ textAlign: "left" }}>
              <li dangerouslySetInnerHTML={{ __html: t("consent.listRecorded") }} />
              <li>{t("consent.listReviewed")}</li>
              <li dangerouslySetInnerHTML={{ __html: t("consent.listVoluntary") }} />
              <li>{t("consent.listSecure")}</li>
            </ul>
            <p className="consent-duration">
              {info.interview_duration_minutes ? (
                <span dangerouslySetInnerHTML={{ __html: t("consent.durationInfo", { minutes: info.interview_duration_minutes }) }} />
              ) : null}
              {info.interview_duration_minutes && info.question_count ? " · " : null}
              {info.question_count ? (
                <span dangerouslySetInnerHTML={{ __html: info.question_count !== 1 ? t("consent.topicCount_plural", { count: info.question_count }) : t("consent.topicCount", { count: info.question_count }) }} />
              ) : null}
              {(info.interview_duration_minutes || info.question_count) ? "." : null}
            </p>
            {info.incentive_text && (
              <p className="consent-incentive" style={{ fontSize: 14, margin: "8px 0 4px" }}>
                <strong>{t("consent.incentiveLabel")}</strong> {info.incentive_text}
                <span className="muted-text" style={{ display: "block", fontSize: 12, marginTop: 2 }}>
                  {t("consent.incentiveNote")}
                </span>
              </p>
            )}
            <p className="consent-privacy-link">
              <a href="/participant-notice" target="_blank" rel="noopener noreferrer">
                {t("consent.participantNotice")}
              </a>
              {info.privacy_policy_url && " · "}
              {info.privacy_policy_url && (
                <a href={info.privacy_policy_url} target="_blank" rel="noopener noreferrer">
                  {t("consent.privacyPolicy")}
                </a>
              )}
            </p>
          </div>

          {/* Panel-join surface intentionally not shown on consent.
              The completion screen carries the panel CTA — keeping
              consent purely about agreement to participate reduces
              cognitive load and keeps the screen high-trust. */}

          {starting && <p className="muted-text" style={{ marginTop: 12 }}>{t("consent.starting")}</p>}
          {error && <div className="error-banner" role="alert">{error}</div>}

          {/* In-progress interview on this device: offer a one-tap resume so a
              reload doesn't force re-reading the whole consent screen. Consent
              was already given when this session originally started. */}
          {getSavedSession() && (
            <div className="resume-summary-panel" style={{ marginTop: 12 }}>
              <p style={{ margin: "0 0 10px", fontSize: 14 }}>{t("consent.resumeAvailable", { defaultValue: "You have an interview in progress on this device." })}</p>
              <button className="btn btn-secondary" style={{ minHeight: 44 }} onClick={handleResumeSession}>
                {t("consent.resumeCta", { defaultValue: "Continue where you left off" })} →
              </button>
            </div>
          )}

          <div className="consent-actions">
            {declineConfirming ? (
              <>
                <p style={{ width: "100%", margin: "0 0 8px", fontSize: 14, color: "var(--text-secondary)" }} role="alert">
                  {t("consent.declineConfirmText")}
                </p>
                <button className="btn btn-primary" onClick={() => setDeclineConfirming(false)}>
                  {t("consent.declineConfirmNo", { defaultValue: "Keep going" })}
                </button>
                <button className="btn btn-ghost" onClick={() => setConsentDeclined(true)} style={{ color: "var(--text-secondary)" }}>
                  {t("consent.declineConfirmYes", { defaultValue: "Yes, decline" })}
                </button>
              </>
            ) : (
              <>
                <button
                  className="btn btn-primary"
                  onClick={handleConsentAccept}
                  disabled={starting}
                >
                  {t("consent.accept")}
                </button>
                <button className="btn btn-ghost" onClick={() => setDeclineConfirming(true)} style={{ color: "var(--text-secondary)" }}>
                  {t("consent.decline")}
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    );
  }

  // ── Profile collection phase ──────────────────────────────────────────────
  // Minimal "what's your first name?" capture. Heavier demographics + interest
  // tagging happen in the post-completion panel funnel (PF-4), not here —
  // pre-interview should stay near-frictionless.

  if (phase === "profile") {
    const trimmed = profile.firstName.trim();
    return (
      <div className="interview-page">
        <div className="interview-container" style={{ maxWidth: 560 }}>
          <div
            className="profile-min-card"
            style={{
              background: "var(--bg-surface, #fff)",
              borderRadius: "var(--radius-lg)",
              padding: "40px 32px",
              boxShadow: "var(--shadow-md)",
              maxWidth: 480,
              width: "100%",
              margin: "0 auto",
            }}
          >
            <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 8 }}>
              {t("profile.minTitle")}
            </h1>
            <p style={{ color: "var(--text-secondary, #6b7280)", marginBottom: 24, lineHeight: 1.55 }}>
              {t("profile.minSubtitle")}
            </p>
            <div className="interview-name-field">
              <label className="field-label" htmlFor="profile-min-first-name">
                {t("profile.firstNameLabel")}
              </label>
              <input
                id="profile-min-first-name"
                type="text"
                className="field-input"
                value={profile.firstName}
                onChange={(e) => setProfile((p) => ({ ...p, firstName: e.target.value }))}
                placeholder={t("profile.firstNamePlaceholder")}
                autoFocus
                autoComplete="given-name"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && trimmed) proceedFromProfile();
                }}
              />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 24 }}>
              <button
                className="btn btn-primary"
                disabled={!trimmed || starting}
                onClick={proceedFromProfile}
              >
                {starting ? t("profile.starting") : t("profile.continue")} →
              </button>
              <button
                className="btn btn-ghost"
                onClick={() => { setProfile((p) => ({ ...p, firstName: "" })); void routeAfterProfile(); }}
                style={{ alignSelf: "center", color: "var(--text-tertiary)", fontSize: 13, minHeight: 44 }}
                disabled={starting}
              >
                {t("profile.skipName")}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── Screening phase ──────────────────────────────────────────────────────

  if (phase === "screening") {
    const sq = screeningQuestions[screeningStep];
    if (!sq) return null;
    const progress = ((screeningStep + 1) / screeningQuestions.length) * 100;
    return (
      <div className="interview-page">
        <div className="interview-container interview-profiling">
          <div className="profiling-header">
            <p className="profiling-intro">{t("screening.title")}</p>
            <div className="profiling-progress-bar">
              <div className="profiling-progress-fill" style={{ width: `${progress}%` }} />
            </div>
            <p className="profiling-step-label">{t("screening.progressLabel", { current: screeningStep + 1, total: screeningQuestions.length })}</p>
          </div>
          <div className="profiling-question">
            <h2 className="profiling-label" aria-live="polite">{sq.question}</h2>
            <div className="profiling-options">
              {sq.options.map((opt) => {
                // Submit the canonical `value` (the gate's stable identity);
                // display the localized `label`.
                const isSelected = screeningAnswers[sq.id] === opt.value;
                return (
                  <button
                    key={opt.value}
                    className={`profiling-option-btn${isSelected ? " selected" : ""}`}
                    onClick={() => !screeningLoading && handleScreeningAnswer(sq.id, opt.value)}
                    disabled={screeningLoading}
                  >
                    {screeningLoading && isSelected ? t("screening.checking") : opt.label}
                  </button>
                );
              })}
            </div>
          </div>
          {screeningError && (
            <div className="screening-error-card" role="alert">
              <p className="screening-error-card__title">
                {screeningErrorKind === "network"
                  ? t("screening.submissionErrorNetwork")
                  : screeningErrorKind === "ratelimit"
                    ? t("screening.rateLimited", { defaultValue: "Too many attempts in a short time. Please wait a minute before trying again." })
                    : t("screening.submissionErrorServer")}
              </p>
              {screeningRetryCount >= 2 && (
                <p className="screening-error-card__escalate">
                  {t("screening.submissionEscalation")}
                </p>
              )}
              <button
                className="btn btn-primary screening-error-card__retry"
                onClick={() => {
                  setScreeningError("");
                  setScreeningErrorKind(null);
                  const last = screeningAnswers[sq.id];
                  if (last) handleScreeningAnswer(sq.id, last);
                }}
              >
                {t("screening.retry")}
              </button>
            </div>
          )}
          {error && <div className="error-banner" role="alert">{error}</div>}
          {screeningStep > 0 && !screeningLoading && (
            <button
              className="profiling-back-btn"
              onClick={() => setScreeningStep((s) => s - 1)}
            >
              ← {t("screening.back")}
            </button>
          )}
        </div>
      </div>
    );
  }

  // ── Disqualified phase ───────────────────────────────────────────────────

  if (phase === "disqualified") {
    return (
      <div className="interview-page">
        <div className="interview-container interview-complete">
          <div className="complete-icon disqualified-icon"><IconHeart size={48} /></div>
          <h1 className="interview-complete-title">{t("screening.disqualified.title")}</h1>
          <p className="interview-complete-text" dangerouslySetInnerHTML={{ __html: t("screening.disqualified.desc", { projectName: info?.project_name ?? "" }) }} />
          <p className="interview-complete-text" style={{ marginTop: 12 }}>
            {t("screening.disqualified.desc2")}
          </p>
          {email && (
            <p className="disqualified-email-note" dangerouslySetInnerHTML={{ __html: t("screening.disqualified.emailNote", { email }) }} />
          )}

          <button
            type="button"
            className="disqualified-future-toggle"
            aria-expanded={showFutureStudies}
            onClick={() => setShowFutureStudies((v) => !v)}
          >
            {t("screening.disqualified.futureStudies")}
          </button>
          {showFutureStudies && (
            <p className="disqualified-future-note">
              {t("screening.disqualified.futureStudiesNote")}
            </p>
          )}

          <p className="disqualified-mistake">
            {t("screening.disqualified.contactMistake")}
          </p>
          <p className="muted-text" style={{ marginTop: 24 }}>{t("screening.disqualified.close")}</p>
        </div>
      </div>
    );
  }

  // ── Study unavailable (workspace billing gate) ───────────────────────────

  if (phase === "study_unavailable") {
    return (
      <div className="interview-page">
        <div className="interview-container interview-complete">
          <div className="complete-icon"><IconHeart size={48} /></div>
          <h1 className="interview-complete-title">{t("studyUnavailable.title")}</h1>
          <p className="interview-complete-text">
            {studyUnavailableMsg || t("studyUnavailable.body")}
          </p>
          <p className="muted-text" style={{ marginTop: 24 }}>{t("studyUnavailable.close")}</p>
        </div>
      </div>
    );
  }

  // ── Link at capacity / already completed ─────────────────────────────────
  // Both are terminal states for this participant: no retry, no CTA.

  if (phase === "link_full" || phase === "already_completed") {
    const key = phase === "link_full" ? "linkFull" : "alreadyCompleted";
    return (
      <div className="interview-page">
        <div className="interview-container interview-complete">
          <div className="complete-icon"><IconHeart size={48} /></div>
          <h1 className="interview-complete-title">{t(`${key}.title`)}</h1>
          <p className="interview-complete-text">{t(`${key}.body`)}</p>
          <p className="muted-text" style={{ marginTop: 24 }}>{t("studyUnavailable.close")}</p>
        </div>
      </div>
    );
  }

  // ── Mic permission prompt ────────────────────────────────────────────────

  if (phase === "interview" && !micTestDone && !micPermissionRequested) {
    return (
      <div className="interview-page">
        <div className="interview-container mic-test-card">
          <div className="mic-prompt-icon"><IconMic size={40} /></div>
          <h2 className="mic-test-title">{t("micPrompt.title")}</h2>
          <p className="mic-test-subtitle" dangerouslySetInnerHTML={{ __html: t("micPrompt.subtitle") }} />
          <div className="mic-prompt-steps">
            <div className="mic-prompt-step">
              <span className="mic-prompt-num">1</span>
              <span>{t("micPrompt.step1")}</span>
            </div>
            <div className="mic-prompt-step">
              <span className="mic-prompt-num">2</span>
              <span dangerouslySetInnerHTML={{ __html: t("micPrompt.step2") }} />
            </div>
            <div className="mic-prompt-step">
              <span className="mic-prompt-num">3</span>
              <span>{t("micPrompt.step3")}</span>
            </div>
          </div>
          <button
            className="btn btn-primary"
            onClick={() => {
              // Unlock audio playback inside this user gesture so the first
              // question's TTS can autoplay on iOS Safari afterwards.
              unlockAudio();
              setMicPermissionRequested(true);
            }}
          >
            {t("micPrompt.enable")} →
          </button>
          <p className="mic-prompt-note">
            {t("micPrompt.note")}
          </p>
        </div>
      </div>
    );
  }

  // ── Mic test phase ────────────────────────────────────────────────────────

  if (phase === "interview" && !micTestDone) {
    // Three visual states so the participant always knows where they are:
    //   waiting   → no signal yet, mic icon pulses, "Say a few words"
    //   listening → small signal but below threshold, level bar coloured
    //   ready     → above threshold, big green check, big primary CTA
    const micState: "waiting" | "listening" | "ready" =
      micLevel > 20 ? "ready" : micLevel > 4 ? "listening" : "waiting";
    return (
      <div className="interview-page">
        <div className="interview-container mic-test-card">
          <div className={`mic-test-icon mic-test-icon--${micState}`} aria-hidden="true">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z" />
              <path d="M19 11a7 7 0 0 1-14 0" />
              <line x1="12" y1="18" x2="12" y2="22" />
              <line x1="8" y1="22" x2="16" y2="22" />
            </svg>
          </div>
          <h2 className="mic-test-title">{t("micTest.title")}</h2>
          {micRecheck && (
            <div className="error-banner" role="alert" style={{ marginBottom: 12 }}>
              {t("micTest.recheckNotice", {
                defaultValue: "We couldn't hear your last answer, so let's check your microphone. Your interview will continue right where it left off.",
              })}
            </div>
          )}
          <p className="mic-test-subtitle">{t("micTest.descClear")}</p>
          <div className="mic-level-wrap">
            <div className={`mic-level-bar mic-level-bar--${micState}`} style={{ width: `${micLevel}%` }} />
          </div>
          {micState === "ready" ? (
            <p className="mic-test-status mic-test-ok">✓ {t("micTest.autoPass")}</p>
          ) : micState === "listening" ? (
            <p className="mic-test-status">{t("micTest.listening")}</p>
          ) : (
            <p className="mic-test-status">{t("micTest.speakPromptClear")}</p>
          )}
          <div className="mic-test-actions" style={{ flexDirection: "column", gap: 10 }}>
            {micLevel > 20 && (
              <button
                className="btn btn-primary"
                style={{ minHeight: 48, minWidth: 220 }}
                onClick={() => {
                  if (micAnimRef.current) cancelAnimationFrame(micAnimRef.current);
                  micStreamRef.current?.getTracks().forEach((tr) => tr.stop());
                  setMicTestDone(true);
                }}
              >
                {t("micTest.startInterview")} →
              </button>
            )}
            <button
              className="btn btn-secondary"
              style={{ minHeight: 48, minWidth: 220 }}
              onClick={() => {
                if (micAnimRef.current) cancelAnimationFrame(micAnimRef.current);
                micStreamRef.current?.getTracks().forEach((tr) => tr.stop());
                setMicTestDone(true);
              }}
            >
              {t("micTest.skip")}
            </button>
            {micRecheck && participantId && (
              /* Mid-interview mic failure: the mic on THIS device is suspect,
                 so offer to pick the interview up on another one. */
              <DeviceHandoff token={token!} participantId={participantId} />
            )}
          </div>
        </div>
      </div>
    );
  }

  // ── Realtime voice interview (beta) ──────────────────────────────────────
  // Whole-conversation WebRTC flow: the live model listens and speaks while
  // the backend sideband runs the interview logic. Replaces the classic
  // record/submit UI (and its pause screen) for opted-in studies. Mic
  // permission + test above still apply; completion re-joins the classic
  // questionnaire + completion screens.

  if (phase === "interview" && info?.interview_mode === "realtime_beta" && participantId && !realtimeFallback) {
    return (
      <RealtimeInterview
        token={token!}
        participantId={participantId}
        questionCount={info.question_count ?? 0}
        firstQuestion={currentQuestion}
        onComplete={() => {
          clearSession();
          setPhase("complete");
        }}
        onFallback={async () => {
          // Continue this same interview in the classic flow, from the
          // question currently pending server-side. /respond is
          // mode-agnostic, so nothing else changes.
          realtimeFallbackRef.current = true;
          setRealtimeFallback(true);
          try {
            const s = await getInterviewStatus(token!, participantId);
            const qIdx = s.question_index ?? 0;
            const lastTurnIdx = Math.max(0, s.turn_count - 1);
            if (s.last_question) setCurrentQuestion(s.last_question);
            setStimulus(s.last_stimulus ?? null);
            setTurnCount(s.turn_count);
            setTurnIndex(lastTurnIdx);
            setQuestionIndex(Math.max(0, qIdx));
            setIsFollowUp(Boolean(s.is_follow_up));
            setIsWarmup(qIdx < 0);
            saveSession(participantId, s.last_question ?? currentQuestion ?? "", s.turn_count, lastTurnIdx, Math.max(0, qIdx));
            setTtsEnded(true);
            void fetchDeferredTts(participantId, lastTurnIdx);
          } catch {
            // Status fetch failed: fall back on whatever state we already
            // hold; the first /respond will resync via turn_mismatch.
            setTtsEnded(true);
          }
        }}
      />
    );
  }

  // ── Paused screen ────────────────────────────────────────────────────────

  if (phase === "interview" && paused) {
    return (
      <div className="interview-page">
        <div className="interview-container mic-test-card">
          <div className="mic-prompt-icon"><span aria-hidden="true">⏸</span></div>
          <h2 className="mic-test-title">{t("interview.pause.title")}</h2>
          <p className="mic-test-subtitle">{t("interview.pause.body")}</p>
          {error && <div className="error-banner" role="alert">{error}</div>}
          <button
            className="btn btn-primary"
            style={{ minHeight: 48, minWidth: 220 }}
            onClick={handleResume}
          >
            {t("interview.pause.resume")}
          </button>
          {finishConfirming ? (
            <div style={{ marginTop: 20 }}>
              <p style={{ fontSize: 14, color: "var(--text-secondary)", marginBottom: 10 }}>
                {t("interview.finish.confirmText")}
              </p>
              <div style={{ display: "flex", gap: 10, justifyContent: "center", flexWrap: "wrap" }}>
                <button className="btn btn-secondary" style={{ minHeight: 44 }} disabled={finishing} onClick={handleFinish}>
                  {finishing ? t("interview.finish.finishing") : t("interview.finish.confirmYes")}
                </button>
                <button className="btn btn-ghost" style={{ minHeight: 44 }} onClick={() => setFinishConfirming(false)}>
                  {t("interview.finish.confirmNo")}
                </button>
              </div>
            </div>
          ) : (
            <button
              className="btn btn-ghost"
              style={{ marginTop: 12, minHeight: 44, color: "var(--text-secondary)" }}
              onClick={() => setFinishConfirming(true)}
            >
              {t("interview.finish.button")}
            </button>
          )}
        </div>
      </div>
    );
  }

  // ── Interview phase ───────────────────────────────────────────────────────

  if (phase === "interview") {
    const hideCounter = isWarmup || questionIndex < 0;
    const remainingSecs = Math.max(0, totalSeconds - elapsedSeconds);
    const showTimeLeft = totalSeconds > 0 && remainingSecs < 120 && !paused;
    return (
      <div className="interview-page">
        <div className="interview-container interview-active">
          {info?.question_count && info.question_count > 0 && (
            <div
              className="interview-progress-bar-wrap"
              role="progressbar"
              aria-valuenow={questionIndex}
              aria-valuemin={0}
              aria-valuemax={info.question_count}
              aria-label={t("interview.progressLabel", { current: questionIndex + 1, total: info.question_count })}
            >
              <div
                className="interview-progress-bar-fill"
                style={{ width: `${(isWarmup || questionIndex < 0) ? 0 : Math.min(((questionIndex) / info.question_count) * 100, 95)}%` }}
              />
            </div>
          )}
          {/* Single polite live region: announces the new question text, then
              processing-state changes. Plain text, no emoji. */}
          <div className="sr-only" aria-live="polite" aria-atomic="true">{liveMessage}</div>
          <div className="interview-progress">
            <span className="interview-turn-count">
              {isWarmup
                ? t("interview.warmupLabel")
                : hideCounter
                  ? ""
                  : isFollowUp
                    ? t("interview.followUpLabel", { current: questionIndex + 1, total: info?.question_count ?? "?" })
                    : t("interview.progressLabel", { current: questionIndex + 1, total: info?.question_count ?? "?" })}
            </span>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              {showTimeLeft && (
                <span className="interview-time-remaining">
                  {(() => {
                    const mins = Math.floor(remainingSecs / 60);
                    const secs = remainingSecs % 60;
                    return <span>{mins > 0 ? t("interview.timeMinLeft", { mins }) : t("interview.timeSecLeft", { secs })}</span>;
                  })()}
                </span>
              )}
              <button
                className={`mute-btn ${muted ? "muted" : ""}`}
                onClick={toggleMute}
                title={muted ? t("interview.unmuteAudio") : t("interview.muteAudio")}
                aria-label={muted ? t("interview.unmuteAudio") : t("interview.muteAudio")}
              >
                {muted ? (
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="1" y1="1" x2="23" y2="23" />
                    <path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V4a3 3 0 0 0-5.94-.6" />
                    <path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2c0 .76-.13 1.49-.36 2.18" />
                    <line x1="12" y1="19" x2="12" y2="23" />
                    <line x1="8" y1="23" x2="16" y2="23" />
                  </svg>
                ) : (
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                    <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                    <line x1="12" y1="19" x2="12" y2="23" />
                    <line x1="8" y1="23" x2="16" y2="23" />
                  </svg>
                )}
              </button>
            </div>
          </div>

          <div className="interview-question-area">
            {!currentQuestion ? (
              <div style={{ textAlign: "center", padding: "40px", color: "var(--text-muted)" }}>
                <div className="spinner" style={{ margin: "0 auto 12px" }} />
                <p>{t("interview.preparingFirst")}</p>
              </div>
            ) : (
              <>
                <StimulusCard stimulus={stimulus} />
                <p className="interview-question-text">{currentQuestion}</p>
              </>
            )}
          </div>

          {/* Autoplay blocked before any clip ever played (iOS Safari):
              calm tap-to-play fallback so the question is never silently lost. */}
          {ttsBlocked && !muted && (
            <div style={{ textAlign: "center", marginBottom: 12 }}>
              <button
                className="btn btn-secondary"
                style={{ minHeight: 44 }}
                onClick={() => {
                  const url = audioRef.current?.src;
                  if (url) playTTS(url);
                  else setTtsBlocked(false);
                }}
              >
                <IconSpeaker /> {t("interview.playQuestion", { defaultValue: "Play the question" })}
              </button>
            </div>
          )}

          {/* Fix 2: TTS audio failure warning */}
          {ttsFailedWarning && (
            <div className="error-banner" role="alert" style={{ background: "#fef3c7", color: "#92400e", border: "1px solid #fcd34d", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
              <span>
                {t("interview.ttsFailedWarning")}
              </span>
              <button
                className="btn btn-ghost btn-sm"
                style={{ whiteSpace: "nowrap", flexShrink: 0 }}
                onClick={() => {
                  if (audioRef.current?.src) {
                    setTtsFailedWarning(false);
                    const url = audioRef.current.src;
                    playTTS(url);
                  }
                }}
              >
                {t("interview.ttsReplay")}
              </button>
            </div>
          )}
          {error && <div className="error-banner" role="alert">{error}</div>}
          {notice && (
            <div className="interview-notice">
              <span>{notice}</span>
              <button
                type="button"
                className="interview-notice__close"
                aria-label={t("interview.dismiss")}
                onClick={() => setNotice(null)}
              >
                ×
              </button>
            </div>
          )}
          {recError === "PERMISSION_DENIED" && !textMode ? (
            <div className="mic-permission-error">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#dc2626" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="1" y1="1" x2="23" y2="23" />
                <path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V4a3 3 0 0 0-5.94-.6" />
                <path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2c0 .76-.13 1.49-.36 2.18" />
                <line x1="12" y1="19" x2="12" y2="23" />
                <line x1="8" y1="23" x2="16" y2="23" />
              </svg>
              <h3 className="mic-permission-title">{t("micTest.permissionDenied")}</h3>
              <p className="mic-permission-text">
                {t("micTest.permissionDeniedDesc")}
              </p>
              {(() => {
                const ua = navigator.userAgent;
                if (/iPad|iPhone|iPod/.test(ua)) return (
                  <p className="mic-permission-text" style={{ fontSize: 13, marginTop: 8 }}>
                    {t("micTest.permissionDeniedIOS")}
                  </p>
                );
                if (/Firefox/.test(ua)) return (
                  <p className="mic-permission-text" style={{ fontSize: 13, marginTop: 8 }}>
                    {t("micTest.permissionDeniedFirefox")}
                  </p>
                );
                if (/Safari/.test(ua) && !/Chrome/.test(ua)) return (
                  <p className="mic-permission-text" style={{ fontSize: 13, marginTop: 8 }}>
                    {t("micTest.permissionDeniedSafari")}
                  </p>
                );
                // Default: Chrome or unknown
                return (
                  <p className="mic-permission-text" style={{ fontSize: 13, marginTop: 8 }}>
                    {t("micTest.permissionDeniedChrome")}
                  </p>
                );
              })()}
              {/* Accessibility fallback — anyone landing on this error is
                  exactly who the typed-answer path exists for. */}
              <button
                className="btn btn-primary"
                style={{ minHeight: 44 }}
                onClick={() => {
                  setTextMode(true);
                  setError("");
                }}
              >
                {t("interview.textAnswer.micErrorCta")}
              </button>
              <button
                className="btn btn-ghost"
                style={{ minHeight: 44, marginTop: 8 }}
                onClick={() => window.location.reload()}
              >
                {t("micTest.refresh")}
              </button>
              {participantId && (
                <div style={{ marginTop: 8 }}>
                  <DeviceHandoff token={token!} participantId={participantId} />
                </div>
              )}
            </div>
          ) : recError && !textMode ? (
            <div className="error-banner" role="alert">
              {["MIC_GENERIC", "MIC_NOT_FOUND", "MIC_IN_USE", "MIC_CONSTRAINTS"].includes(recError)
                ? t(`micError.${recError}`)
                : recError}
            </div>
          ) : null}

          {coachingHint && !coachingHintDismissed && (
            <div className="coaching-hint">
              <span className="coaching-hint__icon"><IconBulb /></span>
              <span className="coaching-hint__text">{coachingHint}</span>
              <button
                type="button"
                className="coaching-hint__close"
                aria-label={t("interview.dismiss")}
                onClick={() => setCoachingHintDismissed(true)}
              >
                ×
              </button>
            </div>
          )}

          <div className="interview-controls">
            {processing ? (
              <div className="processing-indicator">
                <div className="spinner" style={{ width: 28, height: 28 }} />
                <span className="processing-label">
                  {processingLong
                    ? t("interview.processing.stillWorking")
                    : t("interview.processing.listening")}
                </span>
              </div>
            ) : autoSending && pendingBlob ? (
              <div className="autosend-toast" role="status">
                <div className="spinner" style={{ width: 20, height: 20 }} />
                <span className="autosend-toast__label">{t("interview.sendingAnswer")}</span>
                <button type="button" className="btn btn-secondary autosend-toast__undo" onClick={handleUndoAutoSend}>
                  {t("interview.undo")}
                </button>
              </div>
            ) : pendingBlob ? (
              <div className="recording-preview">
                <div className="recording-preview-icon" aria-hidden="true">✓</div>
                <p className="recording-preview-label">{t("interview.recordingCaptured")}</p>
                {previewUrl && (
                  <audio
                    controls
                    src={previewUrl}
                    className="recording-preview-player"
                    style={{ width: "100%", maxWidth: 320 }}
                  />
                )}
                <div className="recording-preview-actions">
                  <button className="btn btn-primary" style={{ minHeight: 44 }} onClick={handleSubmitPending}>
                    {t("interview.submitButton")} →
                  </button>
                  <button className="btn btn-ghost" style={{ minHeight: 44 }} onClick={handleReRecord}>
                    ↺ {t("interview.reRecord")}
                  </button>
                </div>
              </div>
            ) : textMode ? (
              <div
                className="text-answer-area"
                style={{ width: "100%", maxWidth: 480, margin: "0 auto", display: "flex", flexDirection: "column", gap: 10, textAlign: "left" }}
              >
                <label htmlFor="typed-answer-input" className="record-label" style={{ textAlign: "left", margin: 0 }}>
                  {t("interview.textAnswer.label")}
                </label>
                <textarea
                  id="typed-answer-input"
                  value={typedAnswer}
                  onChange={(e) => setTypedAnswer(e.target.value)}
                  maxLength={MAX_TYPED_ANSWER_CHARS}
                  rows={5}
                  placeholder={t("interview.textAnswer.placeholder")}
                  aria-label={t("interview.textAnswer.label")}
                  style={{
                    width: "100%",
                    minHeight: 120,
                    resize: "vertical",
                    padding: 12,
                    fontSize: 15,
                    lineHeight: 1.5,
                    fontFamily: "inherit",
                    borderRadius: 10,
                    border: "1px solid var(--border-subtle, #d1d5db)",
                    color: "var(--text-primary)",
                    background: "var(--bg-primary, #fff)",
                  }}
                />
                <button
                  className="btn btn-primary"
                  style={{ minHeight: 44 }}
                  onClick={handleSubmitTyped}
                  disabled={!typedAnswer.trim() || ttsPlaying}
                  title={ttsPlaying ? t("interview.waitForQuestion") : undefined}
                  aria-label={t("interview.textAnswer.submit")}
                >
                  {t("interview.textAnswer.submit")} →
                </button>
                {ttsPlaying && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    style={{ fontSize: 12 }}
                    onClick={() => {
                      if (audioRef.current) {
                        audioRef.current.pause();
                        audioRef.current.currentTime = 0;
                      }
                      setTtsPlaying(false);
                      setTtsEnded(true);
                    }}
                  >
                    {t("interview.skipAudio", { defaultValue: "Skip audio, I'm ready" })}
                  </button>
                )}
                <button
                  type="button"
                  className="text-answer-toggle"
                  style={{
                    background: "none",
                    border: "none",
                    padding: "10px 0",
                    minHeight: 44,
                    cursor: "pointer",
                    fontSize: 13,
                    color: "var(--text-secondary)",
                    textDecoration: "underline",
                  }}
                  onClick={() => setTextMode(false)}
                >
                  {t("interview.textAnswer.switchToVoice")}
                </button>
              </div>
            ) : isRecording ? (
              <>
                <button
                  className="record-btn recording"
                  onClick={() => handleStopAndPreview(true)}
                  aria-label={t("interview.tapToStop")}
                  aria-pressed={true}
                >
                  <div className="record-btn-inner recording-pulse" />
                </button>
                <p className="record-label">{t("interview.tapToStop")}</p>
                {recordingSeconds > 0 && (() => {
                  const isWarning = recordingSeconds >= MAX_RECORDING_SECONDS - 30;
                  return (
                    <p className={`recording-timer ${isWarning ? "recording-timer--warning" : ""}`}>
                      {isWarning && (
                        <svg
                          className="recording-timer__glyph"
                          width="14"
                          height="14"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          aria-hidden="true"
                        >
                          <circle cx="12" cy="13" r="8" />
                          <path d="M12 9v4l2 2" />
                          <path d="M9 2h6" />
                        </svg>
                      )}
                      {Math.floor((MAX_RECORDING_SECONDS - recordingSeconds) / 60)}:
                      {String((MAX_RECORDING_SECONDS - recordingSeconds) % 60).padStart(2, "0")} {t("interview.remaining")}
                    </p>
                  );
                })()}
              </>
            ) : (
              <>
                <button
                  className={`record-btn ${ttsPlaying ? "record-btn--waiting" : ttsEnded ? "record-btn--ready" : ""}`}
                  onClick={ttsPlaying ? undefined : () => {
                    setNotice(null);
                    startRecording();
                  }}
                  disabled={ttsPlaying}
                  title={ttsPlaying ? t("interview.waitForQuestion") : t("interview.tapToRecord")}
                  aria-label={ttsPlaying ? t("interview.waitForQuestion") : t("interview.tapToRecord")}
                  aria-pressed={false}
                >
                  <svg
                    className="record-btn-mic"
                    width="28"
                    height="28"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z" />
                    <path d="M19 11a7 7 0 0 1-14 0" />
                    <line x1="12" y1="18" x2="12" y2="22" />
                    <line x1="8" y1="22" x2="16" y2="22" />
                  </svg>
                </button>
                <p className="record-label">
                  {ttsPlaying ? (
                    <>
                      <span aria-hidden="true">⏵ </span>
                      {t("interview.listeningToQuestion")}
                    </>
                  ) : (
                    t("interview.tapToRecord")
                  )}
                </p>
                {!ttsPlaying && (
                  <p className="muted-text" style={{ fontSize: 12, marginTop: 4 }}>
                    {t("interview.maxRecordingHint", {
                      minutes: Math.round(MAX_RECORDING_SECONDS / 60),
                      defaultValue: "Up to {{minutes}} minutes per answer",
                    })}
                  </p>
                )}
                {ttsPlaying && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    style={{ marginTop: 8, fontSize: 12 }}
                    onClick={() => {
                      if (audioRef.current) {
                        audioRef.current.pause();
                        audioRef.current.currentTime = 0;
                      }
                      setTtsPlaying(false);
                      setTtsEnded(true);
                    }}
                  >
                    {t("interview.skipAudio", { defaultValue: "Skip audio, I'm ready" })}
                  </button>
                )}
              </>
            )}
          </div>

          {!processing && !isRecording && !pendingBlob && !textMode && (
            <button
              type="button"
              className="text-answer-toggle"
              style={{
                display: "block",
                margin: "4px auto 0",
                background: "none",
                border: "none",
                padding: "10px 8px",
                minHeight: 44,
                cursor: "pointer",
                fontSize: 13,
                color: "var(--text-secondary)",
                textDecoration: "underline",
              }}
              onClick={() => {
                setTextMode(true);
                setError("");
              }}
            >
              {t("interview.textAnswer.toggle")}
            </button>
          )}

          {!processing && (
            <div className="interview-session-controls">
              <button type="button" className="session-control-btn" onClick={handlePause}>
                {t("interview.pause.button")}
              </button>
              <span aria-hidden="true">·</span>
              {finishConfirming ? (
                <span className="session-finish-confirm">
                  {t("interview.finish.confirmText")}{" "}
                  <button type="button" className="session-control-btn session-control-btn--strong" disabled={finishing} onClick={handleFinish}>
                    {finishing ? t("interview.finish.finishing") : t("interview.finish.confirmYes")}
                  </button>{" "}
                  <button type="button" className="session-control-btn" onClick={() => setFinishConfirming(false)}>
                    {t("interview.finish.confirmNo")}
                  </button>
                </span>
              ) : (
                <button type="button" className="session-control-btn" onClick={() => setFinishConfirming(true)}>
                  {t("interview.finish.button")}
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    );
  }

  // ── Complete phase ────────────────────────────────────────────────────────

  if (showPostQuestionnaire) {
    return (
      <ParticipantQuestionnaire
        linkToken={token!}
        email={email}
        sessionToken={sessionToken}
        participantId={participantId || null}
        initialFirstName={profile.firstName}
        onComplete={handleQuestionnaireComplete}
      />
    );
  }

  const completeName = profile.firstName || displayName || email?.split("@")[0] || null;

  return (
    <div className="interview-page">
      <div className="interview-container interview-complete">
        <div className="complete-icon">
          <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
            <polyline points="22 4 12 14.01 9 11.01" />
          </svg>
        </div>
        <h1 className="interview-complete-title">
          {completeName ? t("completion.title", { name: completeName.charAt(0).toUpperCase() + completeName.slice(1) }) : t("completion.titleGeneric")}
        </h1>
        <p className="interview-complete-text" dangerouslySetInnerHTML={{ __html: t("completion.responsesRecorded", { projectName: info?.project_name ?? "" }) }} />
        {turnCount > 1 && (
          <p className="interview-complete-meta">
            {(turnCount - 1) !== 1 ? t("completion.answeredCount_plural", { count: turnCount - 1 }) : t("completion.answeredCount", { count: turnCount - 1 })}
          </p>
        )}

        <div className="interview-complete-next">
          <p className="interview-complete-next-label">{t("completion.whatNext")}</p>
          {[t("completion.nextStep1"), t("completion.nextStep2"), t("completion.nextStep3")].some(Boolean) ? (
            <ul className="interview-complete-next-list">
              {t("completion.nextStep1") && <li>{t("completion.nextStep1")}</li>}
              {t("completion.nextStep2") && <li>{t("completion.nextStep2")}</li>}
              {t("completion.nextStep3") && <li>{t("completion.nextStep3")}</li>}
            </ul>
          ) : (
            <p style={{ color: "var(--text-secondary)", fontSize: "0.95rem", lineHeight: 1.6 }}>
              {t("completion.nextStepFallback")}
            </p>
          )}
        </div>

        {/* Optional post-interview questionnaire: "a minute about you". For
            magic-link participants it feeds the reusable panel profile; for
            everyone else it lands on the participant row only. Returning
            panelists with a complete profile skip it. */}
        {postProfileState === "done" ? (
          <div className="interview-complete-future">
            <strong style={{ color: "var(--text-primary)" }}>{t("completion.postProfile.thanksTitle")}</strong>{" "}
            {t("completion.postProfile.thanksBody")}
          </div>
        ) : postProfileState === "idle" && !profileComplete && !didPreQuestionnaire && participantId ? (
          <div className="interview-complete-future interview-complete-future--prompt">
            <strong style={{ color: "var(--text-primary)" }}>{t("completion.postProfile.title")}</strong>
            <p style={{ margin: "8px 0 14px" }}>{t("completion.postProfile.body")}</p>
            <button
              className="btn btn-primary"
              style={{ width: "100%", minHeight: 44 }}
              onClick={() => setShowPostQuestionnaire(true)}
            >
              {t("completion.postProfile.cta")}
            </button>
            <button className="questionnaire-decline-btn" onClick={() => setPostProfileState("skipped")}>
              {t("completion.postProfile.dismiss")}
            </button>
          </div>
        ) : null}

        {/* Panel opt-in. If they accepted in the questionnaire, just confirm.
            If they declined (or skipped), re-prompt here with the fuller
            paid-studies explanation — a softer, better-informed second ask. */}
        {panelConsentGiven ? (
          <div className="interview-complete-future">
            <strong style={{ color: "var(--text-primary)" }}>{t("completion.panelConfirmTitle")}</strong>{" "}
            {t("completion.panelConfirmBody")}
          </div>
        ) : repromptState === "done" ? (
          <div className="interview-complete-future">
            <strong style={{ color: "var(--text-primary)" }}>{t("completion.panelConfirmTitle")}</strong>{" "}
            {t("completion.panelConfirmBody")}
          </div>
        ) : repromptState === "dismissed" || !sessionToken || !(profileComplete || postProfileState !== "idle") ? null : (
          <div className="interview-complete-future interview-complete-future--prompt">
            <strong style={{ color: "var(--text-primary)" }}>{t("completion.panelReprompt.title")}</strong>
            <p style={{ margin: "8px 0 14px" }}>{t("completion.panelReprompt.body")}</p>
            <button
              className="btn btn-primary"
              style={{ width: "100%", minHeight: 44 }}
              disabled={repromptState === "saving"}
              onClick={handlePostInterviewOptIn}
            >
              {repromptState === "saving" ? t("completion.panelReprompt.saving") : t("completion.panelReprompt.cta")}
            </button>
            <button className="questionnaire-decline-btn" onClick={() => setRepromptState("dismissed")}>
              {t("completion.panelReprompt.dismiss")}
            </button>
          </div>
        )}

        {/* Panel enrichment — consented panelists can add more profiling
            details right now ("the more you add, the more studies"). Reuses
            the still-valid participant session. */}
        {(panelConsentGiven || repromptState === "done") && sessionToken && (
          showEnrichment ? (
            <div style={{ marginTop: 16 }}>
              <PanelEnrichment token={sessionToken} embedded />
            </div>
          ) : (
            <button
              className="btn btn-primary"
              style={{ width: "100%", minHeight: 44, marginTop: 16 }}
              onClick={() => setShowEnrichment(true)}
            >
              {t("completion.enrichCta")}
            </button>
          )
        )}

        {/* Privacy / data-rights footer — GDPR transparency for participants */}
        <div className="interview-complete-footer" style={{
          marginTop: 24,
          paddingTop: 16,
          borderTop: "1px solid var(--border-subtle)",
          fontSize: 12,
          color: "var(--text-tertiary)",
          textAlign: "center",
          lineHeight: 1.6,
        }}>
          <a
            href="/participant-notice"
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: "inherit", textDecoration: "underline" }}
          >
            {t("consent.participantNotice")}
          </a>
          {info?.privacy_policy_url && " · "}
          {info?.privacy_policy_url && (
            <a
              href={info.privacy_policy_url}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: "inherit", textDecoration: "underline" }}
            >
              {t("consent.privacyPolicy")}
            </a>
          )}
          {" · "}
          <span>
            {t("completion.dataRights", {
              defaultValue: "To request deletion of your data, contact the researcher who shared this link.",
            })}
          </span>
        </div>
      </div>
    </div>
  );
}
