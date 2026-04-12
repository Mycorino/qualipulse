import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

import {
  getInterviewInfo,
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
  PanelProfileData,
} from "../api/interviews";
import { useAudioRecorder } from "../hooks/useAudioRecorder";

type Phase =
  | "email_entry"
  | "email_sent"
  | "consent"
  | "profile"
  | "screening"
  | "disqualified"
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
  const [panelConsent, setPanelConsent] = useState(false);

  // Panel profile
  const [profile, setProfile] = useState<ProfileState>(EMPTY_PROFILE);
  const [panelTags, setPanelTags] = useState<PanelTag[]>([]);
  const [panelProfileSaving, setPanelProfileSaving] = useState(false);

  // Interview state
  const [displayName, setDisplayName] = useState("");
  const [profession, setProfession] = useState("");
  const [ageRange, setAgeRange] = useState("");
  const [country, setCountry] = useState("");
  const [participantId, setParticipantId] = useState("");
  const [currentQuestion, setCurrentQuestion] = useState("");
  const [processing, setProcessing] = useState(false);
  const [starting, setStarting] = useState(false);
  const [muted, setMuted] = useState(false);
  const [turnCount, setTurnCount] = useState(0);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [isFollowUp, setIsFollowUp] = useState(false);
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
  const MAX_RECORDING_SECONDS = 180;
  const [micTestDone, setMicTestDone] = useState(false);
  const [micLevel, setMicLevel] = useState(0);
  const micStreamRef = useRef<MediaStream | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const micAnimRef = useRef<number | null>(null);
  const [lastTranscript, setLastTranscript] = useState<string | null>(null);
  const [showTranscript, setShowTranscript] = useState(false);
  const [micPermissionRequested, setMicPermissionRequested] = useState(false);

  const [ttsFailedWarning, setTtsFailedWarning] = useState(false);
  const [panelSaveError, setPanelSaveError] = useState(false);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const { isRecording, error: recError, startRecording, stopRecording } =
    useAudioRecorder();

  // ── Session / URL handling on load ──────────────────────────────────────

  useEffect(() => {
    if (!token) return;

    // Check URL for ?session param (from InterviewVerify redirect)
    const params = new URLSearchParams(location.search);
    const sessionParam = params.get("session");

    if (sessionParam) {
      const payload = parseJwtPayload(sessionParam);
      if (payload?.email) {
        const emailVal = String(payload.email);
        setEmail(emailVal);
        setSessionToken(sessionParam);
        sessionStorage.setItem(`interview_session_${token}`, sessionParam);
        navigate(`/i/${token}`, { replace: true });
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
    getInterviewInfo(token)
      .then((data) => {
        setInfo(data);
        // Participant-facing interview uses the project's language, not the researcher's UI language
        if (data.language && (data.language === "fr" || data.language === "en")) {
          i18n.changeLanguage(data.language);
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

  // Resend countdown
  useEffect(() => {
    if (resendCountdown <= 0) return;
    const t = setTimeout(() => setResendCountdown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [resendCountdown]);

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

  // ── TTS ────────────────────────────────────────────────────────────────

  const playTTS = useCallback(
    (url: string) => {
      if (audioRef.current) {
        audioRef.current.onended = null;
        audioRef.current.onerror = null;
        audioRef.current.pause();
      }
      setTtsFailedWarning(false);
      const audio = new Audio(url);
      audioRef.current = audio;
      if (!muted) {
        setTtsPlaying(true);
        setTtsEnded(false);
        audio.onended = () => { setTtsPlaying(false); setTtsEnded(true); };
        audio.onerror = () => {
          setTtsPlaying(false);
          setTtsEnded(true);
          // Fix 2: Show visible warning so user knows audio failed
          setTtsFailedWarning(true);
        };
        audio.play().catch(() => {
          setTtsPlaying(false);
          setTtsEnded(true);
          setTtsFailedWarning(true);
        });
      }
    },
    [muted]
  );

  // ── Recording time limit ─────────────────────────────────────────────────

  useEffect(() => {
    if (!isRecording) {
      setRecordingSeconds(0);
      recordingStartTimeRef.current = null;
      return;
    }
    recordingStartTimeRef.current = Date.now();
    const interval = setInterval(() => {
      if (!recordingStartTimeRef.current) return;
      const elapsed = Math.floor((Date.now() - recordingStartTimeRef.current) / 1000);
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
    };
  }, [phase, micTestDone, micPermissionRequested]);

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
      await requestVerification(token, verificationEmail.trim());
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
      await requestVerification(token, verificationEmail.trim());
      setResendCountdown(60);
    } catch {
      setError(t("emailEntry.resendError"));
    }
  }

  // Skip path: participants whose mail provider (iCloud, Outlook, strict
  // corp filters) silently drops our magic link shouldn't get locked out
  // of the study. This jumps straight to the consent screen and lets the
  // backend create a participant without a session token.
  function handleSkipEmail() {
    setError("");
    setPhase("consent");
  }

  // ── Consent ──────────────────────────────────────────────────────────────

  function handleConsentAccept() {
    setConsentGiven(true);
    const panelEnabled = info?.panel_collection_enabled !== false;
    if (panelEnabled && panelConsent) {
      setPhase("profile");
    } else {
      proceedFromConsent();
    }
  }

  async function proceedFromConsent() {
    if (!token) return;
    setStarting(true);
    setError("");
    try {
      // Check for email-based resume
      if (email.trim()) {
        const resume = await checkResume(token, email.trim());
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
      // Proceed to screening or interview
      const questions = await getScreeningQuestions(token);
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

  // ── Profile ───────────────────────────────────────────────────────────────

  async function handleProfileContinue() {
    await proceedFromConsent();
  }

  function handleSkipProfile() {
    proceedFromConsent();
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
    // ``sessionToken`` is optional — participants who took the "skip email"
    // path don't have one and the backend now accepts that. Only attach
    // the token when we actually have one.
    const res = await startInterview(token, {
      displayName: profile.firstName || displayName || undefined,
      profession: profile.jobFunction || profession || undefined,
      ageRange: profile.ageRange || ageRange || undefined,
      country: profile.city || country || undefined,
      email: email || undefined,
      sessionToken: sessionToken || undefined,
    });
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
    if (res.tts_audio_url) playTTS(res.tts_audio_url);
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
      try {
        const result = await submitScreening(token!, updated);
        if (result.qualified) {
          await doStartInterview();
        } else {
          setDisqualifiedOn(result.disqualified_on ?? "");
          setPhase("disqualified");
        }
      } catch {
        setScreeningError(t("screening.submissionError"));
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
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : t("interview.recordingError");
      setError(msg);
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
      setProcessingStep((s) => Math.min(s + 1, 2));
    }, 2500);

    try {
      const res = await submitAudio(token!, participantId, blob);
      clearInterval(stepInterval);
      if (res.is_complete) {
        clearSession();
        setPhase("complete");
        if (audioRef.current) audioRef.current.pause();
        // Save panel profile if consent given
        if (panelConsent && email) {
          savePanelProfile(token!, buildPanelProfileData()).catch(() => {
            setPanelSaveError(true);
          });
        }
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
          setTimeout(() => setShowTranscript(false), 4000);
        }
        setTtsEnded(false);
        saveSession(participantId, res.question_text, nextTurn);
        if (res.tts_audio_url) playTTS(res.tts_audio_url);
        else setTtsEnded(true);
      }
    } catch (err: unknown) {
      clearInterval(stepInterval);
      setPendingBlob(lastBlobRef.current);
      const msg = err instanceof Error ? err.message : t("interview.uploadError");
      setError(msg);
    } finally {
      setProcessing(false);
    }
  }

  function buildPanelProfileData(): PanelProfileData {
    return {
      email,
      first_name: profile.firstName || undefined,
      age_range: profile.ageRange || undefined,
      gender: profile.gender || undefined,
      country: country || profile.city || undefined,
      city: profile.city || undefined,
      employment_status: profile.employment || undefined,
      job_function: profile.jobFunction || undefined,
      seniority: profile.seniority || undefined,
      industry: profile.industry || undefined,
      company_size: profile.companySize || undefined,
      panel_consent: true,
      tag_ids: profile.selectedTagIds,
    };
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
        if (panelConsent && email) {
          savePanelProfile(token!, buildPanelProfileData()).catch(() => {
            setPanelSaveError(true);
          });
        }
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

  const panelEnabled = info?.panel_collection_enabled !== false;

  const interestTags = panelTags.filter((t) => t.category === "interest");
  const behaviorTags = panelTags.filter((t) => t.category === "behavior");

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
          <p style={{ color: "var(--text-secondary, #6b7280)", fontSize: 15, maxWidth: 380, margin: "0 auto" }}>
            {t("linkInactive.desc")}
          </p>
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
        <div className="interview-container" style={{ maxWidth: 480 }}>
        <div style={{
          background: "#fff",
          borderRadius: "var(--radius-lg)",
          padding: "48px 36px",
          boxShadow: "var(--shadow-md)",
          maxWidth: "480px",
          width: "100%",
          margin: "0 auto",
        }}>
          {info?.researcher_logo_url && (
            <div className="landing-researcher-logo">
              <img src={info.researcher_logo_url} alt={info.researcher_name ?? "Researcher"} />
            </div>
          )}
          <h1 className="interview-project-name" style={{ marginBottom: 8 }}>{info?.project_name}</h1>
          {info?.researcher_name && (
            <p style={{ fontSize: 14, color: "var(--text-secondary, #6b7280)", marginBottom: 24 }} dangerouslySetInnerHTML={{ __html: t("emailEntry.studyBy", { name: info.researcher_name }) }} />
          )}
          {info?.interview_duration_minutes && (
            <p className="interview-duration">⏱ {t("emailEntry.duration", { minutes: info.interview_duration_minutes })}</p>
          )}
          <p style={{ color: "var(--text-secondary, #6b7280)", marginBottom: 28, lineHeight: 1.6 }}>
            {t("emailEntry.enterEmailDesc")}
          </p>
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
            disabled={sendingVerification || !verificationEmail.trim()}
            style={{ width: "100%", marginTop: 8, minHeight: 44 }}
          >
            {sendingVerification ? t("emailEntry.sendingLink") : t("emailEntry.sendLink")}
          </button>
          <p style={{ fontSize: 12, color: "var(--text-muted, #9ca3af)", marginTop: 12, lineHeight: 1.5, textAlign: "center" }}>
            {t("emailEntry.emailNote")}
          </p>

          {/* Escape hatch for participants whose mail provider drops or
              heavily delays the magic link (iCloud Hide My Email, strict
              corporate filters, etc.). The interview will still run, we
              just won't store a verified email against the participant. */}
          <div
            style={{
              marginTop: 20,
              paddingTop: 16,
              borderTop: "1px dashed var(--border, #e5e7eb)",
              textAlign: "center",
            }}
          >
            <button
              type="button"
              className="btn btn-ghost"
              onClick={handleSkipEmail}
              style={{ minHeight: 44, fontSize: 14 }}
            >
              {t("emailEntry.skipEmail", {
                defaultValue: "Continue without email →",
              })}
            </button>
            <p
              style={{
                fontSize: 11,
                color: "var(--text-muted, #9ca3af)",
                marginTop: 6,
                lineHeight: 1.5,
              }}
            >
              {t("emailEntry.skipEmailNote", {
                defaultValue:
                  "You won't be able to resume later from a different device.",
              })}
            </p>
          </div>
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
        <div className="interview-container consent-card">
          {info.researcher_logo_url && (
            <div className="consent-researcher-logo">
              <img src={info.researcher_logo_url} alt={info.researcher_name ?? "Researcher logo"} />
            </div>
          )}
          {info.researcher_name && (
            <p className="consent-researcher-name">{info.researcher_name}</p>
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
            {info.privacy_policy_url && (
              <p className="consent-privacy-link">
                <a href={info.privacy_policy_url} target="_blank" rel="noopener noreferrer">
                  {t("consent.privacyPolicy")} →
                </a>
              </p>
            )}
          </div>

          {panelEnabled && (
            <div
              style={{
                borderTop: "1px solid var(--border, #e2e8f0)",
                marginTop: 20,
                paddingTop: 20,
              }}
            >
              <label
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 12,
                  cursor: "pointer",
                }}
              >
                <input
                  type="checkbox"
                  checked={panelConsent}
                  onChange={(e) => setPanelConsent(e.target.checked)}
                  style={{ marginTop: 3, flexShrink: 0 }}
                />
                <div>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>
                    {t("consent.panelJoinTitle")}
                  </span>
                  <span style={{ color: "var(--text-secondary, #6b7280)", fontSize: 13 }}>
                    {" "}— {t("consent.panelJoinDesc")}
                  </span>
                  <p style={{ color: "var(--text-secondary, #6b7280)", fontSize: 12, margin: "4px 0 0" }}>
                    {t("consent.panelJoinNote")}
                  </p>
                </div>
              </label>
            </div>
          )}

          {starting && <p className="muted-text" style={{ marginTop: 12 }}>{t("consent.starting")}</p>}
          {error && <div className="error-banner" role="alert">{error}</div>}

          <div className="consent-actions">
            <button
              className="btn btn-primary"
              onClick={handleConsentAccept}
              disabled={starting}
            >
              {t("consent.accept")}
            </button>
            <button className="btn btn-ghost" onClick={() => setConsentDeclined(true)} style={{ color: "var(--text-secondary)" }}>
              {t("consent.decline")}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Profile collection phase ──────────────────────────────────────────────

  if (phase === "profile") {
    return (
      <div className="interview-page">
        <div className="interview-container" style={{ maxWidth: 560 }}>
          <div style={{
            background: "#fff",
            borderRadius: "var(--radius-lg)",
            padding: "48px 36px",
            boxShadow: "var(--shadow-md)",
            maxWidth: "560px",
            width: "100%",
            margin: "0 auto",
          }}>
          <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 6 }}>{t("profile.title")}</h1>
          <p style={{ color: "var(--text-secondary, #6b7280)", marginBottom: 28, lineHeight: 1.6 }}>
            {t("profile.subtitle")}
          </p>

          {/* Section: About You */}
          <div style={{ borderTop: "2px solid var(--border, #e2e8f0)", paddingTop: 20, marginBottom: 4 }}>
            <p style={{ fontWeight: 700, fontSize: 13, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary, #6b7280)", marginBottom: 16 }}>{t("profile.sectionAboutYou")}</p>
          </div>

          {/* First name */}
          <div className="interview-name-field">
            <label className="field-label" htmlFor="profile-first-name">{t("profile.firstNameLabel")} <span className="optional-tag">{t("profile.optional")}</span></label>
            <input
              id="profile-first-name"
              type="text"
              className="field-input"
              value={profile.firstName}
              onChange={(e) => setProfile((p) => ({ ...p, firstName: e.target.value }))}
              placeholder={t("profile.firstNamePlaceholder")}
            />
          </div>

          {/* Age range */}
          <div className="interview-name-field">
            <label className="field-label">{t("profile.ageRangeLabel")}</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 4 }}>
              {["18-24", "25-34", "35-44", "45-54", "55+"].map((opt) => (
                <button
                  key={opt}
                  className={`profiling-option-btn${profile.ageRange === opt ? " selected" : ""}`}
                  onClick={() => setProfile((p) => ({ ...p, ageRange: p.ageRange === opt ? "" : opt }))}
                >
                  {opt}
                </button>
              ))}
            </div>
          </div>

          {/* Gender */}
          <div className="interview-name-field">
            <label className="field-label">{t("profile.genderLabel")}</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 4 }}>
              {[
                { value: "male", label: t("profile.genderMan") },
                { value: "female", label: t("profile.genderWoman") },
                { value: "non_binary", label: t("profile.genderNonBinary") },
                { value: "prefer_not", label: t("profile.genderPreferNot") },
              ].map(({ value, label }) => (
                <button
                  key={value}
                  className={`profiling-option-btn${profile.gender === value ? " selected" : ""}`}
                  onClick={() => setProfile((p) => ({ ...p, gender: p.gender === value ? "" : value }))}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Section: Work Experience */}
          <div style={{ borderTop: "2px solid var(--border, #e2e8f0)", paddingTop: 20, marginTop: 8, marginBottom: 4 }}>
            <p style={{ fontWeight: 700, fontSize: 13, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary, #6b7280)", marginBottom: 16 }}>{t("profile.sectionWorkExperience")}</p>
          </div>

          {/* Employment */}
          <div className="interview-name-field">
            <label className="field-label">{t("profile.employmentLabel")}</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 4 }}>
              {[
                { value: "full_time", label: t("profile.employmentFullTime") },
                { value: "part_time", label: t("profile.employmentPartTime") },
                { value: "freelance", label: t("profile.employmentFreelance") },
                { value: "student", label: t("profile.employmentStudent") },
                { value: "retired", label: t("profile.employmentRetired") },
                { value: "other", label: t("profile.employmentOther") },
              ].map(({ value, label }) => (
                <button
                  key={value}
                  className={`profiling-option-btn${profile.employment === value ? " selected" : ""}`}
                  onClick={() => setProfile((p) => ({ ...p, employment: p.employment === value ? "" : value }))}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Job function */}
          <div className="interview-name-field">
            <label className="field-label" htmlFor="profile-job-function">{t("profile.jobFunctionLabel")} <span className="optional-tag">{t("profile.optional")}</span></label>
            <select
              id="profile-job-function"
              className="field-input"
              value={profile.jobFunction}
              onChange={(e) => setProfile((p) => ({ ...p, jobFunction: e.target.value }))}
            >
              <option value="">{t("profile.jobFunctionPlaceholder")}</option>
              {["Engineering", "Product", "Marketing", "Design", "Finance", "Operations", "HR", "Executive", "Other"].map((f) => (
                <option key={f} value={f.toLowerCase()}>{f}</option>
              ))}
            </select>
          </div>

          {/* Industry */}
          <div className="interview-name-field">
            <label className="field-label" htmlFor="profile-industry">{t("profile.industryLabel")} <span className="optional-tag">{t("profile.optional")}</span></label>
            <input
              id="profile-industry"
              type="text"
              className="field-input"
              value={profile.industry}
              onChange={(e) => setProfile((p) => ({ ...p, industry: e.target.value }))}
              placeholder={t("profile.industryPlaceholder")}
            />
          </div>

          {/* Company size */}
          <div className="interview-name-field">
            <label className="field-label">{t("profile.companySizeLabel")}</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 4 }}>
              {[
                { value: "1", label: t("profile.companySizeJustMe") },
                { value: "2-10", label: "2–10" },
                { value: "11-50", label: "11–50" },
                { value: "51-200", label: "51–200" },
                { value: "201+", label: "200+" },
              ].map(({ value, label }) => (
                <button
                  key={value}
                  className={`profiling-option-btn${profile.companySize === value ? " selected" : ""}`}
                  onClick={() => setProfile((p) => ({ ...p, companySize: p.companySize === value ? "" : value }))}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Seniority */}
          <div className="interview-name-field">
            <label className="field-label">{t("profile.seniorityLabel")}</label>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 4 }}>
              {[
                { value: "junior", label: t("profile.seniorityJunior") },
                { value: "mid", label: t("profile.seniorityMid") },
                { value: "senior", label: t("profile.senioritySenior") },
                { value: "manager", label: t("profile.seniorityManager") },
                { value: "director", label: t("profile.seniorityDirector") },
                { value: "c_suite", label: t("profile.seniorityCSuite") },
              ].map(({ value, label }) => (
                <button
                  key={value}
                  className={`profiling-option-btn${profile.seniority === value ? " selected" : ""}`}
                  onClick={() => setProfile((p) => ({ ...p, seniority: p.seniority === value ? "" : value }))}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Interests & behaviors */}
          {panelTags.length > 0 && (
            <div className="interview-name-field">
              <label className="field-label">
                {t("profile.interestsLabel")}{" "}
                <span className="optional-tag">({t("profile.interestsMax")})</span>
              </label>
              {interestTags.length > 0 && (
                <>
                  <p style={{ fontSize: 12, color: "var(--text-secondary, #6b7280)", margin: "8px 0 6px" }}>{t("profile.interestsTab")}</p>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {interestTags.map((tag) => (
                      <button
                        key={tag.id}
                        className={`profiling-option-btn${profile.selectedTagIds.includes(tag.id) ? " selected" : ""}`}
                        onClick={() => toggleTag(tag.id)}
                        disabled={!profile.selectedTagIds.includes(tag.id) && profile.selectedTagIds.length >= 5}
                      >
                        {tag.name}
                      </button>
                    ))}
                  </div>
                </>
              )}
              {behaviorTags.length > 0 && (
                <>
                  <p style={{ fontSize: 12, color: "var(--text-secondary, #6b7280)", margin: "10px 0 6px" }}>{t("profile.behaviorsTab")}</p>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {behaviorTags.map((tag) => (
                      <button
                        key={tag.id}
                        className={`profiling-option-btn${profile.selectedTagIds.includes(tag.id) ? " selected" : ""}`}
                        onClick={() => toggleTag(tag.id)}
                        disabled={!profile.selectedTagIds.includes(tag.id) && profile.selectedTagIds.length >= 5}
                      >
                        {tag.name}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}

          {/* Section: Location */}
          <div style={{ borderTop: "2px solid var(--border, #e2e8f0)", paddingTop: 20, marginTop: 8, marginBottom: 4 }}>
            <p style={{ fontWeight: 700, fontSize: 13, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary, #6b7280)", marginBottom: 16 }}>{t("profile.sectionLocation")}</p>
          </div>

          {/* City */}
          <div className="interview-name-field">
            <label className="field-label" htmlFor="profile-city">{t("profile.cityLabel")} <span className="optional-tag">{t("profile.optional")}</span></label>
            <input
              id="profile-city"
              type="text"
              className="field-input"
              value={profile.city}
              onChange={(e) => setProfile((p) => ({ ...p, city: e.target.value }))}
              placeholder={t("profile.cityPlaceholder")}
            />
          </div>

          {error && <div className="error-banner" role="alert">{error}</div>}

          <div style={{ display: "flex", gap: 12, marginTop: 8 }}>
            <button
              className="btn btn-primary"
              onClick={handleProfileContinue}
              disabled={starting}
              style={{ flex: 1 }}
            >
              {starting ? t("profile.starting") : t("profile.continue")}
            </button>
            <button className="btn btn-ghost" onClick={handleSkipProfile} disabled={starting}>
              {t("profile.skip")}
            </button>
          </div>
          </div>
        </div>
      </div>
    );
  }

  // ── Resume confirm ───────────────────────────────────────────────────────

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
                  const questions = await getScreeningQuestions(token!);
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
            <p className="profiling-step-label">{screeningStep + 1} / {screeningQuestions.length}</p>
          </div>
          <div className="profiling-question">
            <h2 className="profiling-label">{sq.question}</h2>
            <div className="profiling-options">
              {sq.options.map((opt) => (
                <button
                  key={opt}
                  className="profiling-option-btn"
                  onClick={() => !screeningLoading && handleScreeningAnswer(sq.id, opt)}
                  disabled={screeningLoading}
                >
                  {screeningLoading && screeningAnswers[sq.id] === opt ? t("screening.checking") : opt}
                </button>
              ))}
            </div>
          </div>
          {screeningError && (
            <div className="error-banner" role="alert" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
              <span>{screeningError}</span>
              <button
                className="btn btn-ghost btn-sm"
                style={{ whiteSpace: "nowrap", flexShrink: 0 }}
                onClick={() => {
                  setScreeningError("");
                  handleScreeningAnswer(sq.id, screeningAnswers[sq.id]);
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
          <p className="muted-text" style={{ marginTop: 24 }}>{t("screening.disqualified.close")}</p>
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
            onClick={() => setMicPermissionRequested(true)}
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
    return (
      <div className="interview-page">
        <div className="interview-container mic-test-card">
          <h2 className="mic-test-title">{t("micTest.title")}</h2>
          <p className="mic-test-subtitle">{t("micTest.desc")}</p>
          <div className="mic-level-wrap">
            <div className="mic-level-bar" style={{ width: `${micLevel}%` }} />
          </div>
          {micLevel > 20 ? (
            <p className="mic-test-status mic-test-ok">✓ {t("micTest.autoPass")}</p>
          ) : (
            <p className="mic-test-status">{t("micTest.speakPrompt")}</p>
          )}
          <div className="mic-test-actions">
            <button
              className="btn btn-primary"
              onClick={() => {
                if (micAnimRef.current) cancelAnimationFrame(micAnimRef.current);
                micStreamRef.current?.getTracks().forEach((tr) => tr.stop());
                setMicTestDone(true);
              }}
            >
              {micLevel > 20 ? t("micTest.startInterview") + " →" : t("micTest.skip")}
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
          <div className="interview-progress">
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

          <div className="interview-question-area">
            {!currentQuestion ? (
              <div style={{ textAlign: "center", padding: "40px", color: "var(--text-muted)" }}>
                <div className="spinner" style={{ margin: "0 auto 12px" }} />
                <p>{t("interview.preparingFirst")}</p>
              </div>
            ) : (
              <p className="interview-question-text">{currentQuestion}</p>
            )}
          </div>

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
              {/iPad|iPhone|iPod/.test(navigator.userAgent) && (
                <p className="mic-permission-text" style={{ fontSize: 13, marginTop: 8 }}>
                  {t("micTest.permissionDeniedIOS")}
                </p>
              )}
              <button className="btn btn-primary" onClick={() => window.location.reload()}>
                {t("micTest.refresh")}
              </button>
            </div>
          ) : recError ? (
            <div className="error-banner" role="alert">{recError}</div>
          ) : null}

          {showTranscript && lastTranscript && (
            <div className="transcript-flash">
              <span className="transcript-flash-label">{t("interview.transcript")}</span>
              <span className="transcript-flash-text">"{lastTranscript}"</span>
            </div>
          )}

          <div className="interview-controls">
            {processing ? (
              <div className="processing-indicator" aria-live="polite">
                <div className="spinner" style={{ width: 28, height: 28 }} />
                <span style={{ fontSize: "1rem" }}>{[t("interview.processing.transcribing"), t("interview.processing.thinking"), t("interview.processing.preparing")][processingStep]}</span>
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
                {recordingSeconds > 0 && (
                  <p className={`recording-timer ${recordingSeconds >= MAX_RECORDING_SECONDS - 30 ? "recording-timer--warning" : ""}`}>
                    {Math.floor((MAX_RECORDING_SECONDS - recordingSeconds) / 60)}:
                    {String((MAX_RECORDING_SECONDS - recordingSeconds) % 60).padStart(2, "0")} {t("interview.remaining")}
                  </p>
                )}
              </>
            ) : (
              <>
                <button
                  className={`record-btn ${ttsPlaying ? "record-btn--waiting" : ttsEnded ? "record-btn--ready" : ""}`}
                  onClick={ttsPlaying ? undefined : startRecording}
                  disabled={ttsPlaying}
                  title={ttsPlaying ? t("interview.waitForQuestion") : t("interview.tapToRecord")}
                  aria-label={ttsPlaying ? t("interview.waitForQuestion") : t("interview.tapToRecord")}
                >
                  <div className="record-btn-inner" />
                </button>
                <p className="record-label">
                  {ttsPlaying ? "⏵ " + t("interview.listeningToQuestion") : t("interview.tapToRecord")}
                </p>
              </>
            )}
          </div>

          {!processing && !isRecording && !pendingBlob && (
            <button className="skip-question-btn" onClick={handleSkip} aria-label={t("interview.skipQuestion")}>
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

        {panelConsent && (
          <div
            style={{
              background: "linear-gradient(135deg, #ede9fe 0%, #e0e7ff 100%)",
              borderRadius: 12,
              padding: "20px 24px",
              margin: "24px 0",
              textAlign: "center",
            }}
          >
            <div style={{ fontSize: 28, marginBottom: 8 }}><span aria-hidden="true">🎉</span></div>
            <p style={{ fontWeight: 700, color: "#4f46e5", marginBottom: 4 }}>
              {t("completion.panelJoined")}
            </p>
            <p style={{ color: "#6b7280", fontSize: 13 }}>
              {t("completion.panelJoinedDesc")}
            </p>
          </div>
        )}

        {/* Fix 3: Panel profile save failure warning */}
        {panelSaveError && (
          <div style={{
            background: "#fef3c7",
            color: "#92400e",
            border: "1px solid #fcd34d",
            borderRadius: 8,
            padding: "12px 16px",
            margin: "0 0 16px",
            fontSize: 13,
            lineHeight: 1.5,
          }}>
            {t("completion.panelSaveError")}
          </div>
        )}

        <div className="interview-complete-next">
          <p className="interview-complete-next-label">{t("completion.whatNext")}</p>
          <ul className="interview-complete-next-list">
            <li>{t("completion.nextStep1")}</li>
            <li>{t("completion.nextStep2")}</li>
            <li>{t("completion.nextStep3")}</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
