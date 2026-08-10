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
  skipQuestion,
  requestVerification,
  getPanelTags,
  savePanelProfile,
  InterviewInfo,
  ScreeningQuestion,
  ResumeCheck,
  ResumeSummary,
  PanelTag,
} from "../api/interviews";
import { useAudioRecorder } from "../hooks/useAudioRecorder";
import LanguagePicker from "../components/LanguagePicker";
import ParticipantQuestionnaire, { QuestionnaireResult } from "../components/ParticipantQuestionnaire";
import PanelEnrichment from "../components/PanelEnrichment";
import { SUPPORTED_LANGUAGES } from "../i18n";
import { applyParticipantBranding } from "../utils/branding";
import { detectInAppBrowser, androidChromeIntentUrl } from "../utils/inAppBrowser";

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
  | "questionnaire"
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

export default function Interview() {
  const { t, i18n } = useTranslation("interview");
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const location = useLocation();

  const [phase, setPhase] = useState<Phase>("email_entry");
  const [info, setInfo] = useState<InterviewInfo | null>(null);
  const [infoLoading, setInfoLoading] = useState(true);
  const [error, setError] = useState("");

  // Verification / session
  const [verificationEmail, setVerificationEmail] = useState("");
  const [sendingVerification, setSendingVerification] = useState(false);
  const [resendCountdown, setResendCountdown] = useState(0);
  const [sessionToken, setSessionToken] = useState<string | null>(null);
  const [email, setEmail] = useState(""); // from verified session

  // Consent
  const [consentGiven, setConsentGiven] = useState(false);
  const [consentDeclined, setConsentDeclined] = useState(false);
  // Two-tap decline: declining is terminal (no way back to the study), so an
  // accidental tap shouldn't end it. First tap arms an inline confirmation.
  const [declineConfirming, setDeclineConfirming] = useState(false);

  // Panel profile
  const [profile, setProfile] = useState<ProfileState>(EMPTY_PROFILE);
  const [panelTags, setPanelTags] = useState<PanelTag[]>([]);
  const [panelProfileSaving, setPanelProfileSaving] = useState(false);
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
  // TEMP dev/testing shortcut: visit any interview link with `?devskip=1` once
  // to enable a "Skip to end" button (persisted in localStorage; `?devskip=0`
  // to disable). Lets you jump straight to the completion screen to test the
  // post-interview panel flow without recording an interview. Remove later.
  const [devSkip, setDevSkip] = useState(
    () => typeof window !== "undefined" && localStorage.getItem("qp_devskip") === "1"
  );

  // Interview state
  const [displayName, setDisplayName] = useState("");
  const [profession, setProfession] = useState("");
  const [ageRange, setAgeRange] = useState("");
  const [country, setCountry] = useState("");
  const [participantId, setParticipantId] = useState("");
  const [currentQuestion, setCurrentQuestion] = useState("");
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
  const [ttsPlaying, setTtsPlaying] = useState(false);
  const [ttsEnded, setTtsEnded] = useState(true);
  const [processingStep, setProcessingStep] = useState(0);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const recordingStartTimeRef = useRef<number | null>(null);
  const MAX_RECORDING_SECONDS = 240;
  const [micTestDone, setMicTestDone] = useState(false);
  const [micLevel, setMicLevel] = useState(0);
  const micStreamRef = useRef<MediaStream | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const micAnimRef = useRef<number | null>(null);
  const [lastTranscript, setLastTranscript] = useState<string | null>(null);
  const [showTranscript, setShowTranscript] = useState(false);
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
  const [transcriptDismissed, setTranscriptDismissed] = useState(false);
  const [transcriptExpanded, setTranscriptExpanded] = useState(false);
  const [transcriptFading, setTranscriptFading] = useState(false);
  const [skipBtnReady, setSkipBtnReady] = useState(false);
  const skipBtnTimerRef = useRef<number | null>(null);
  const beepFiredRef = useRef(false);
  const [showFutureStudies, setShowFutureStudies] = useState(false);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const pendingFirstTtsRef = useRef<string | null>(null);
  // Holds the questionnaire result so doStartInterview reads it synchronously
  // (setState is async — the no-screening path starts the interview in the
  // same tick the questionnaire completes).
  const collectedRef = useRef<QuestionnaireResult | null>(null);
  const { isRecording, error: recError, startRecording, stopRecording } =
    useAudioRecorder();

  // Auto-dismiss the "We heard" flash so the previous answer doesn't linger
  // under the next question: start fading at 6.5s, gone at 7.5s. Paused while
  // the participant has expanded it to read the full transcript.
  useEffect(() => {
    if (!showTranscript || !lastTranscript || transcriptDismissed || transcriptExpanded) return;
    const fadeTimer = window.setTimeout(() => setTranscriptFading(true), 6500);
    const hideTimer = window.setTimeout(() => setTranscriptDismissed(true), 7500);
    return () => {
      window.clearTimeout(fadeTimer);
      window.clearTimeout(hideTimer);
      setTranscriptFading(false);
    };
  }, [showTranscript, lastTranscript, transcriptDismissed, transcriptExpanded]);

  // ── Session / URL handling on load ──────────────────────────────────────

  useEffect(() => {
    if (!token) return;

    // Check URL for ?session param (from InterviewVerify redirect)
    const params = new URLSearchParams(location.search);
    const sessionParam = params.get("session");

    // Read the returning-participant meta (profile_complete / first_name /
    // preferred_language) that InterviewVerify stashed alongside the session.
    const applyProfileMeta = () => {
      try {
        const raw = sessionStorage.getItem(`interview_profile_meta_${token}`);
        if (!raw) return;
        const meta = JSON.parse(raw) as {
          profile_complete?: boolean;
          first_name?: string | null;
          preferred_language?: string | null;
        };
        if (meta.profile_complete) setProfileComplete(true);
        if (meta.first_name) setProfile((p) => ({ ...p, firstName: meta.first_name as string }));
        const ml = (meta.preferred_language || "").slice(0, 2);
        if (ml && (SUPPORTED_LANGUAGES as readonly string[]).includes(ml)) {
          localStorage.setItem("qp_interview_lang", ml);
          i18n.changeLanguage(ml);
        }
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
        applyProfileMeta();
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
        applyProfileMeta();
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

  // Load panel tags when entering profile phase
  useEffect(() => {
    if (phase === "profile" && panelTags.length === 0) {
      getPanelTags().then(setPanelTags).catch(() => {});
    }
  }, [phase]);

  // Branded studies re-theme the whole participant experience (accent color
  // + font) by overriding the design-system CSS variables; cleanup restores
  // them so the theme never leaks past this page.
  useEffect(() => applyParticipantBranding(info?.branding), [info?.branding]);

  // TEMP: toggle the dev "skip to end" affordance from the URL (?devskip=1/0).
  useEffect(() => {
    const v = new URLSearchParams(location.search).get("devskip");
    if (v === "1") { localStorage.setItem("qp_devskip", "1"); setDevSkip(true); }
    else if (v === "0") { localStorage.removeItem("qp_devskip"); setDevSkip(false); }
  }, [location.search]);

  // Resend countdown
  useEffect(() => {
    if (resendCountdown <= 0) return;
    const t = setTimeout(() => setResendCountdown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [resendCountdown]);

  // ── Skip-button gating: 5s grace period after each question ──────────────
  useEffect(() => {
    if (phase !== "interview") return;
    setSkipBtnReady(false);
    if (skipBtnTimerRef.current) window.clearTimeout(skipBtnTimerRef.current);
    if (!currentQuestion) return;
    skipBtnTimerRef.current = window.setTimeout(() => setSkipBtnReady(true), 5000);
    return () => {
      if (skipBtnTimerRef.current) window.clearTimeout(skipBtnTimerRef.current);
    };
  }, [currentQuestion, phase]);

  // ── Live countdown during interview ──────────────────────────────────────

  useEffect(() => {
    if (phase !== "interview" || totalSeconds === 0) return;
    const interval = setInterval(() => {
      setElapsedSeconds((s) => Math.min(s + 1, totalSeconds));
    }, 1000);
    return () => clearInterval(interval);
  }, [phase, totalSeconds]);

  // ── beforeunload warning during active interview ─────────────────────
  useEffect(() => {
    if (phase !== "interview" || !participantId) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [phase, participantId]);

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

  // ── Recording time limit ─────────────────────────────────────────────────

  useEffect(() => {
    if (!isRecording) {
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
        handleStopAndPreview();
        setRecordingSeconds(MAX_RECORDING_SECONDS);
      } else {
        setRecordingSeconds(elapsed);
      }
    }, 1000);
    return () => clearInterval(interval);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isRecording]);

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

  function saveSession(pid: string, question: string, turn: number) {
    if (!sessionKey) return;
    sessionStorage.setItem(sessionKey, JSON.stringify({ participantId: pid, currentQuestion: question, turnCount: turn }));
  }

  function clearSession() {
    if (sessionKey) sessionStorage.removeItem(sessionKey);
  }

  function getSavedSession(): { participantId: string; currentQuestion: string; turnCount: number } | null {
    if (!sessionKey) return null;
    try {
      const raw = sessionStorage.getItem(sessionKey);
      return raw ? JSON.parse(raw) : null;
    } catch { return null; }
  }

  // ── Verification ─────────────────────────────────────────────────────────

  async function handleSendVerification() {
    if (!token || !verificationEmail.trim()) return;
    setSendingVerification(true);
    setError("");
    try {
      await requestVerification(token, verificationEmail.trim(), (i18n.language || "en").slice(0, 2));
      setResendCountdown(60);
      setPhase("email_sent");
    } catch {
      setError(t("emailEntry.sendError"));
    } finally {
      setSendingVerification(false);
    }
  }

  async function handleResendVerification() {
    if (!token || resendCountdown > 0) return;
    try {
      await requestVerification(token, verificationEmail.trim(), (i18n.language || "en").slice(0, 2));
      setResendCountdown(60);
    } catch {
      setError(t("emailEntry.resendError"));
    }
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
        setParticipantId(saved.participantId);
        setCurrentQuestion(saved.currentQuestion);
        setTurnCount(saved.turnCount);
        setPhase("interview");
        setStarting(false);
        return;
      }
      // Returning participant with a complete panel profile → skip the
      // profiling questionnaire and go straight to screening/interview.
      if (profileComplete) {
        await routeAfterProfile();
        return;
      }
      // New / incomplete participant → run the profiling questionnaire
      // (collects demographics into the reusable panel profile).
      setPhase("questionnaire");
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
    await routeAfterProfile();
  }

  async function handleProfileContinue() {
    await routeAfterProfile();
  }

  function handleSkipProfile() {
    routeAfterProfile();
  }

  /** Called when the participant finishes (or skips through) the profiling
   *  questionnaire. The questionnaire already persisted the panel profile;
   *  here we just carry the few fields needed to create the participant row
   *  and continue to screening/interview. */
  async function handleQuestionnaireComplete(data: QuestionnaireResult) {
    collectedRef.current = data;
    setPanelConsentGiven(data.panelConsent);
    if (data.firstName) {
      setProfile((p) => ({ ...p, firstName: data.firstName }));
      setDisplayName(data.firstName);
    }
    if (data.ageRange) setAgeRange(data.ageRange);
    if (data.country) setCountry(data.country);
    await routeAfterProfile();
  }

  /** TEMP dev shortcut — jump straight to the completion screen (skipping
   *  questionnaire / screening / interview) to test the post-interview panel
   *  flow. Treats the panelist as consented so the enrichment CTA shows. */
  function handleDevSkipToEnd() {
    setPanelConsentGiven(true);
    setTurnCount(3);
    setPhase("complete");
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

  function toggleTag(id: number) {
    setProfile((p) => {
      const has = p.selectedTagIds.includes(id);
      if (has) {
        return { ...p, selectedTagIds: p.selectedTagIds.filter((t) => t !== id) };
      }
      if (p.selectedTagIds.length >= 5) return p; // max 5
      return { ...p, selectedTagIds: [...p.selectedTagIds, id] };
    });
  }

  // ── Interview start ────────────────────────────────────────────────────

  async function doStartInterview() {
    if (!token) return;
    // Prefer the just-collected questionnaire data (read synchronously from a
    // ref to dodge setState lag), then fall back to any restored state.
    const c = collectedRef.current;
    const chosenLang = (i18n.language || "en").slice(0, 2);
    let res;
    try {
      res = await startInterview(token, {
        displayName: c?.firstName || profile.firstName || displayName || undefined,
        profession: profile.jobFunction || profession || undefined,
        ageRange: c?.ageRange || profile.ageRange || ageRange || undefined,
        country: c?.country || country || profile.city || undefined,
        email: email || undefined,
        sessionToken: sessionToken || undefined,
        preferredLanguage: chosenLang,
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
    setTurnCount(1);
    setQuestionIndex(0);
    setIsFollowUp(false);
    const total = (info?.interview_duration_minutes ?? 0) * 60;
    setTotalSeconds(total);
    setElapsedSeconds(0);
    saveSession(res.participant_id, res.first_question, 1);
    setPhase("interview");
    if (res.tts_audio_url) pendingFirstTtsRef.current = res.tts_audio_url;
    else setTtsEnded(true);
  }

  function handleResumeSession() {
    const saved = getSavedSession();
    if (!saved) return;
    setParticipantId(saved.participantId);
    setCurrentQuestion(saved.currentQuestion);
    setTurnCount(saved.turnCount);
    setPhase("interview");
  }

  async function handleConfirmResume() {
    if (!resumeCheck?.participant_id) return;
    // Re-lock the UI to the language this interview was started in.
    lockInterviewLanguage(resumeSummary?.language);
    setParticipantId(resumeCheck.participant_id);
    setCurrentQuestion(resumeCheck.last_question ?? "");
    setTurnCount(resumeCheck.turn_count ?? 1);
    setQuestionIndex(resumeCheck.question_index ?? 0);
    const total = (info?.interview_duration_minutes ?? 0) * 60;
    setTotalSeconds(total);
    const alreadyElapsed = (resumeSummary?.elapsed_minutes ?? 0) * 60;
    setElapsedSeconds(Math.min(alreadyElapsed, total));
    saveSession(resumeCheck.participant_id, resumeCheck.last_question ?? "", resumeCheck.turn_count ?? 1);
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

  async function handleStopAndPreview() {
    try {
      const blob = await stopRecording();
      lastBlobRef.current = blob;
      setPendingBlob(blob);
      setTtsEnded(false);
    } catch (_e) {
      setError(t("interview.recordingError", { defaultValue: "Recording was interrupted. Please try again." }));
    }
  }

  async function handleSubmitPending() {
    if (!pendingBlob) return;
    setProcessing(true);
    setProcessingStep(0);
    setShowTranscript(false);
    setLastTranscript(null);
    const blob = pendingBlob;
    setPendingBlob(null);

    const stepInterval = setInterval(() => {
      setProcessingStep((s) => Math.min(s + 1, 3));
    }, 3000);

    try {
      const res = await submitAudio(token!, participantId, blob);
      clearInterval(stepInterval);
      if (res.is_complete) {
        clearSession();
        setPhase("complete");
        if (audioRef.current) audioRef.current.pause();
        // Save panel profile if consent given
        // Panel-join surface was removed from consent; participants no
        // longer opt into the panel during the interview flow. Leave the
        // hook in place so it's a one-line restore if we add a panel
        // surface elsewhere — but never call it without consent.
      } else if (res.question_text) {
        const nextTurn = turnCount + 1;
        setCurrentQuestion(res.question_text);
        setTurnCount(nextTurn);
        setQuestionIndex(res.question_index ?? questionIndex);
        setIsFollowUp(res.is_follow_up ?? false);
        if (res.elapsed_seconds !== undefined) setElapsedSeconds(res.elapsed_seconds);
        if (res.total_seconds !== undefined && res.total_seconds > 0) setTotalSeconds(res.total_seconds);
        if (res.transcript) {
          setLastTranscript(res.transcript);
          setShowTranscript(true);
          setTranscriptDismissed(false);
          setTranscriptExpanded(false);
          setTranscriptFading(false);
        }
        // PF-3: surface the engine's coaching hint (or clear it if Claude
        // decided the participant is back on track). Stays dismissed if the
        // user explicitly closed the previous one for this turn.
        if (res.coaching_hint) {
          setCoachingHint(res.coaching_hint);
          setCoachingHintDismissed(false);
        } else {
          setCoachingHint(null);
        }
        setTtsEnded(false);
        saveSession(participantId, res.question_text, nextTurn);
        if (res.tts_audio_url) playTTS(res.tts_audio_url);
        else setTtsEnded(true);
      }
    } catch (err: unknown) {
      clearInterval(stepInterval);
      // Distinguish "we didn't hear you" (422) from transport failures.
      // Empty-transcript: clear the blob so the participant records fresh;
      // transport: keep the blob in pending so they can retry the same take.
      const errWithResp = err as { response?: { status?: number; data?: { detail?: { code?: string } } } };
      const status = errWithResp?.response?.status;
      const code = errWithResp?.response?.data?.detail?.code;
      if (status === 422 && code === "empty_transcript") {
        setPendingBlob(null);
        lastBlobRef.current = null;
        setError(t("interview.emptyTranscript", {
          defaultValue: "We didn't catch that — please record again in a quieter spot.",
        }));
      } else {
        setPendingBlob(lastBlobRef.current);
        const isNetwork = !(err as { response?: unknown })?.response;
        if (isNetwork) {
          setError(t("interview.networkError", { defaultValue: "Connection lost — please check your internet and tap Submit to retry." }));
        } else if (status === 429) {
          // Rate-limited: retrying immediately just re-trips the limit —
          // tell the participant to wait instead of showing a generic error.
          setError(t("interview.rateLimited", { defaultValue: "Too many attempts in a short time. Please wait a minute, then tap Submit again — your answer is saved." }));
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
    setTtsEnded(true);
  }

  async function handleSkip() {
    if (!token) return;
    setProcessing(true);
    setPendingBlob(null);
    try {
      const res = await skipQuestion(token, participantId);
      if (res.is_complete) {
        clearSession();
        setPhase("complete");
        // Panel-join surface was removed from consent; participants no
        // longer opt into the panel during the interview flow. Leave the
        // hook in place so it's a one-line restore if we add a panel
        // surface elsewhere — but never call it without consent.
      } else if (res.question_text) {
        const nextTurn = turnCount + 1;
        setCurrentQuestion(res.question_text);
        setTurnCount(nextTurn);
        setQuestionIndex(res.question_index ?? questionIndex);
        setIsFollowUp(false);
        setTtsEnded(false);
        saveSession(participantId, res.question_text, nextTurn);
        if (res.tts_audio_url) playTTS(res.tts_audio_url);
        else setTtsEnded(true);
      }
    } catch {
      setError(t("interview.skipError"));
    } finally {
      setProcessing(false);
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

  const interestTags = panelTags.filter((t) => t.category === "interest");
  const behaviorTags = panelTags.filter((t) => t.category === "behavior");

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

  // TEMP dev affordance — a small floating "Skip to end" button shown only when
  // `?devskip=1` was set and a session exists, so the post-interview screen can
  // be reached without recording an interview. Remove when done testing.
  const devSkipBtn = devSkip && sessionToken && phase !== "complete" ? (
    <button
      onClick={handleDevSkipToEnd}
      style={{
        position: "fixed", bottom: 16, right: 16, zIndex: 9999,
        padding: "8px 14px", fontSize: 13, fontFamily: "inherit",
        background: "#1f2937", color: "#fff", border: "1px dashed #9ca3af",
        borderRadius: 8, cursor: "pointer", opacity: 0.85,
      }}
    >
      ⏭ Skip to end (dev)
    </button>
  ) : null;

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
          <div style={{ fontSize: 48, marginBottom: 16 }}><span aria-hidden="true">🔗</span></div>
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
          <div className="mic-prompt-icon"><span aria-hidden="true">🧭</span></div>
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
          <h1 className="interview-project-name" style={{ marginBottom: 8, textAlign: "center" }}>{info?.project_name}</h1>
          {info?.researcher_name && (
            <p style={{ fontSize: 14, color: "var(--text-secondary, #6b7280)", marginBottom: 24, textAlign: "center" }} dangerouslySetInnerHTML={{ __html: t("emailEntry.studyBy", { name: info.researcher_name }) }} />
          )}
          {info?.interview_duration_minutes && (
            <p className="interview-duration" style={{ textAlign: "center" }}>⏱ {t("emailEntry.duration", { minutes: info.interview_duration_minutes })}</p>
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

  // ── Email sent (check inbox) phase ───────────────────────────────────────

  if (phase === "email_sent") {
    return (
      <div className="interview-page">
        <div className="interview-container" style={{ textAlign: "center", maxWidth: 440 }}>
          <div style={{ fontSize: 52, marginBottom: 16 }}><span aria-hidden="true">📬</span></div>
          <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 8 }}>{t("emailSent.title")}</h1>
          <p style={{ color: "var(--text-secondary, #6b7280)", lineHeight: 1.6, marginBottom: 8 }} dangerouslySetInnerHTML={{ __html: t("emailSent.desc", { email: verificationEmail }) }} />
          <p style={{ color: "var(--text-secondary, #6b7280)", fontSize: 13, marginBottom: 24 }}>
            {t("emailSent.expiry")}
          </p>
          {error && <div className="error-banner" role="alert">{error}</div>}
          <button
            className="btn btn-ghost"
            onClick={handleResendVerification}
            disabled={resendCountdown > 0}
            style={{ marginBottom: 12 }}
          >
            {resendCountdown > 0 ? t("emailSent.resendCooldown", { seconds: resendCountdown }) : t("emailSent.resend")}
          </button>
          <br />
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => { setPhase("email_entry"); setError(""); }}
          >
            ← {t("emailSent.differentEmail")}
          </button>
        </div>
      </div>
    );
  }

  // ── Consent phase ────────────────────────────────────────────────────────

  if (phase === "consent" && info) {
    return (
      <div className="interview-page">
        {devSkipBtn}
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
                  {t("consent.declineConfirmText", { defaultValue: "Are you sure? Declining ends your participation — you won't be able to come back to this study." })}
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

  // ── Resume confirm ───────────────────────────────────────────────────────
  // Shown when checkResume returned an in-progress participant (cross-device
  // resume via email). Restored after PR #71 accidentally removed it; without
  // this block, proceedFromConsent would set resumeCheck state but render
  // nothing, leaving the user stuck on the consent screen.

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
                onClick={proceedFromProfile}
                style={{ alignSelf: "center", color: "var(--text-tertiary)", fontSize: 13 }}
              >
                {t("profile.skip")}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── Profiling questionnaire phase ────────────────────────────────────────

  if (phase === "questionnaire") {
    return (
      <>
        {devSkipBtn}
        <ParticipantQuestionnaire
          linkToken={token!}
          email={email}
          sessionToken={sessionToken}
          initialFirstName={profile.firstName}
          onComplete={handleQuestionnaireComplete}
        />
      </>
    );
  }

  // ── Screening phase ──────────────────────────────────────────────────────

  if (phase === "screening") {
    const sq = screeningQuestions[screeningStep];
    if (!sq) return null;
    const progress = ((screeningStep + 1) / screeningQuestions.length) * 100;
    return (
      <div className="interview-page">
        {devSkipBtn}
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
          <div className="complete-icon disqualified-icon"><span aria-hidden="true">🙏</span></div>
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
          <div className="complete-icon"><span aria-hidden="true">🙏</span></div>
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
          <div className="complete-icon"><span aria-hidden="true">🙏</span></div>
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
          <div className="mic-prompt-icon"><span aria-hidden="true">🎙️</span></div>
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
          </div>
        </div>
      </div>
    );
  }

  // ── Interview phase ───────────────────────────────────────────────────────

  if (phase === "interview") {
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
                style={{ width: `${Math.min(((questionIndex) / info.question_count) * 100, 95)}%` }}
              />
            </div>
          )}
          <div className="interview-progress" role="status" aria-live="polite">
            <span className="interview-turn-count">
              {isFollowUp
                ? t("interview.followUpLabel", { current: questionIndex + 1, total: info?.question_count ?? "?" })
                : t("interview.progressLabel", { current: questionIndex + 1, total: info?.question_count ?? "?" })}
            </span>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              {totalSeconds > 0 && (
                <span className="interview-time-remaining">
                  {(() => {
                    const remaining = Math.max(0, totalSeconds - elapsedSeconds);
                    const mins = Math.floor(remaining / 60);
                    const secs = remaining % 60;
                    const pct = elapsedSeconds / totalSeconds;
                    const cls = pct > 0.9 ? "time-critical" : pct > 0.75 ? "time-warning" : "";
                    return <span className={cls}>{mins > 0 ? t("interview.timeMinLeft", { mins }) : t("interview.timeSecLeft", { secs })}</span>;
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

          <div
            className="interview-question-area"
            aria-live="polite"
            aria-atomic="true"
          >
            {!currentQuestion ? (
              <div style={{ textAlign: "center", padding: "40px", color: "var(--text-muted)" }}>
                <div className="spinner" style={{ margin: "0 auto 12px" }} />
                <p>{t("interview.preparingFirst")}</p>
              </div>
            ) : (
              <p className="interview-question-text">{currentQuestion}</p>
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
                🔊 {t("interview.playQuestion", { defaultValue: "Play the question" })}
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
          {recError === "PERMISSION_DENIED" ? (
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
              <button className="btn btn-primary" onClick={() => window.location.reload()}>
                {t("micTest.refresh")}
              </button>
            </div>
          ) : recError ? (
            <div className="error-banner" role="alert">
              {["MIC_GENERIC", "MIC_NOT_FOUND", "MIC_IN_USE", "MIC_CONSTRAINTS"].includes(recError)
                ? t(`micError.${recError}`)
                : recError}
            </div>
          ) : null}

          {coachingHint && !coachingHintDismissed && (
            <div className="coaching-hint" role="status" aria-live="polite">
              <span className="coaching-hint__icon" aria-hidden="true">💡</span>
              <span className="coaching-hint__text">{coachingHint}</span>
              <button
                type="button"
                className="coaching-hint__close"
                aria-label={t("interview.transcriptDismiss")}
                onClick={() => setCoachingHintDismissed(true)}
              >
                ×
              </button>
            </div>
          )}

          {showTranscript && !transcriptDismissed && lastTranscript && (() => {
            const TRUNCATE = 200;
            const isLong = lastTranscript.length > TRUNCATE;
            const display = isLong && !transcriptExpanded
              ? lastTranscript.slice(0, TRUNCATE).trimEnd() + "…"
              : lastTranscript;
            return (
              <div className={`transcript-flash${transcriptFading ? " transcript-flash--fading" : ""}`}>
                <span className="transcript-flash-label">{t("interview.transcript")}</span>
                <span className="transcript-flash-text">"{display}"</span>
                {isLong && (
                  <button
                    type="button"
                    className="transcript-flash__readmore"
                    onClick={() => setTranscriptExpanded((v) => !v)}
                  >
                    {transcriptExpanded ? t("interview.transcriptReadLess") : t("interview.transcriptReadMore")}
                  </button>
                )}
                <button
                  type="button"
                  className="transcript-flash__close"
                  aria-label={t("interview.transcriptDismiss")}
                  onClick={() => setTranscriptDismissed(true)}
                >
                  ×
                </button>
              </div>
            );
          })()}

          <div className="interview-controls">
            {processing ? (
              <div className={`processing-indicator processing-step-${processingStep}`} aria-live="polite">
                <div className="spinner" style={{ width: 28, height: 28 }} />
                <span className="processing-label">
                  {processingStep === 0 && <>{t("interview.processing.transcribing")}</>}
                  {processingStep === 1 && <>{t("interview.processing.thinking")}</>}
                  {processingStep === 2 && <>{t("interview.processing.preparing")}</>}
                  {processingStep >= 3 && <>{t("interview.processing.takingLonger", { defaultValue: "Still working — hang tight…" })}</>}
                </span>
              </div>
            ) : pendingBlob ? (
              <div className="recording-preview">
                <div className="recording-preview-icon">✓</div>
                <p className="recording-preview-label">{t("interview.recordingCaptured")}</p>
                <div className="recording-preview-actions">
                  <button className="btn btn-primary" onClick={handleSubmitPending}>
                    {t("interview.submitButton")} →
                  </button>
                  <button className="btn btn-ghost" onClick={handleReRecord}>
                    ↺ {t("interview.reRecord")}
                  </button>
                </div>
              </div>
            ) : isRecording ? (
              <>
                <button className="record-btn recording" onClick={handleStopAndPreview} aria-label={t("interview.tapToStop")}>
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
                    setTranscriptDismissed(true);
                    startRecording();
                  }}
                  disabled={ttsPlaying}
                  title={ttsPlaying ? t("interview.waitForQuestion") : t("interview.tapToRecord")}
                  aria-label={ttsPlaying ? t("interview.waitForQuestion") : t("interview.tapToRecord")}
                >
                  <div className="record-btn-inner" />
                </button>
                <p className="record-label">
                  {ttsPlaying ? "⏵ " + t("interview.listeningToQuestion") : t("interview.tapToRecord")}
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
                    {t("interview.skipAudio", { defaultValue: "Skip audio — I'm ready" })}
                  </button>
                )}
              </>
            )}
          </div>

          {!processing && !isRecording && !pendingBlob && (
            <button
              className={`skip-question-btn skip-question-btn--fade${skipBtnReady ? " skip-question-btn--visible" : ""}`}
              onClick={handleSkip}
              aria-label={t("interview.skipQuestion")}
              aria-hidden={!skipBtnReady}
              tabIndex={skipBtnReady ? 0 : -1}
            >
              {t("interview.skipQuestion")}
            </button>
          )}
        </div>
      </div>
    );
  }

  // ── Complete phase ────────────────────────────────────────────────────────

  const completeName = profile.firstName || email?.split("@")[0] || null;

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

        {/* Panel opt-in. If they accepted pre-interview, just confirm. If they
            declined (or skipped), re-prompt here with the fuller paid-studies
            explanation — a softer, better-informed second ask. */}
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
        ) : repromptState === "dismissed" || !sessionToken ? null : (
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
