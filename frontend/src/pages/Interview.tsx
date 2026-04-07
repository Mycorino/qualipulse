import { useState, useEffect, useRef, useCallback } from "react";
import { useParams } from "react-router-dom";
import {
  getInterviewInfo,
  getScreeningQuestions,
  submitScreening,
  startInterview,
  submitAudio,
  checkResume,
  getResumeSummary,
  skipQuestion,
  InterviewInfo,
  ScreeningQuestion,
  ResumeCheck,
  ResumeSummary,
} from "../api/interviews";
import { useAudioRecorder } from "../hooks/useAudioRecorder";

type Phase = "landing" | "screening" | "disqualified" | "interview" | "complete";

export default function Interview() {
  const { token } = useParams<{ token: string }>();
  const [phase, setPhase] = useState<Phase>("landing");
  const [info, setInfo] = useState<InterviewInfo | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [profession, setProfession] = useState("");
  const [ageRange, setAgeRange] = useState("");
  const [country, setCountry] = useState("");
  const [email, setEmail] = useState("");
  const [participantId, setParticipantId] = useState("");
  const [currentQuestion, setCurrentQuestion] = useState("");
  const [processing, setProcessing] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const [muted, setMuted] = useState(false);
  const [turnCount, setTurnCount] = useState(0);
  const [infoLoading, setInfoLoading] = useState(true);
  const [consentGiven, setConsentGiven] = useState(false);
  const [consentDeclined, setConsentDeclined] = useState(false);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [isFollowUp, setIsFollowUp] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [totalSeconds, setTotalSeconds] = useState(0);
  const [resumeCheck, setResumeCheck] = useState<ResumeCheck | null>(null);
  const [resumeSummary, setResumeSummary] = useState<ResumeSummary | null>(null);
  const [loadingResumeSummary, setLoadingResumeSummary] = useState(false);

  // Screening state
  const [screeningQuestions, setScreeningQuestions] = useState<ScreeningQuestion[]>([]);
  const [screeningStep, setScreeningStep] = useState(0);
  const [screeningAnswers, setScreeningAnswers] = useState<Record<string, string>>({});
  const [screeningLoading, setScreeningLoading] = useState(false);
  const [disqualifiedOn, setDisqualifiedOn] = useState("");

  // New state for UX improvements
  const lastBlobRef = useRef<Blob | null>(null);
  const [pendingBlob, setPendingBlob] = useState<Blob | null>(null);
  const [ttsPlaying, setTtsPlaying] = useState(false);
  const [ttsEnded, setTtsEnded] = useState(true); // true = can record
  const [processingStep, setProcessingStep] = useState(0);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const MAX_RECORDING_SECONDS = 180;
  const [micTestDone, setMicTestDone] = useState(false);
  const [micLevel, setMicLevel] = useState(0);
  const micStreamRef = useRef<MediaStream | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const micAnimRef = useRef<number | null>(null);
  const [lastTranscript, setLastTranscript] = useState<string | null>(null);
  const [showTranscript, setShowTranscript] = useState(false);
  const [micPermissionRequested, setMicPermissionRequested] = useState(false);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const { isRecording, error: recError, startRecording, stopRecording } =
    useAudioRecorder();

  // Load interview info
  useEffect(() => {
    if (!token) return;
    getInterviewInfo(token)
      .then(setInfo)
      .catch(() => setError("This interview link is invalid or has expired."))
      .finally(() => setInfoLoading(false));
  }, [token]);

  // Live countdown timer during interview
  useEffect(() => {
    if (phase !== "interview" || totalSeconds === 0) return;
    const interval = setInterval(() => {
      setElapsedSeconds((s) => Math.min(s + 1, totalSeconds));
    }, 1000);
    return () => clearInterval(interval);
  }, [phase, totalSeconds]);

  // Play TTS audio
  const playTTS = useCallback(
    (url: string) => {
      if (audioRef.current) audioRef.current.pause();
      const audio = new Audio(url);
      audioRef.current = audio;
      if (!muted) {
        setTtsPlaying(true);
        setTtsEnded(false);
        audio.onended = () => { setTtsPlaying(false); setTtsEnded(true); };
        audio.onerror = () => { setTtsPlaying(false); setTtsEnded(true); };
        audio.play().catch(() => { setTtsPlaying(false); setTtsEnded(true); });
      }
      // If muted, keep ttsEnded=true so they can record immediately
    },
    [muted]
  );

  // Recording time limit
  useEffect(() => {
    if (!isRecording) { setRecordingSeconds(0); return; }
    const interval = setInterval(() => {
      setRecordingSeconds((s) => {
        if (s + 1 >= MAX_RECORDING_SECONDS) {
          handleStopAndPreview();
          return MAX_RECORDING_SECONDS;
        }
        return s + 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isRecording]);

  // Mic level meter effect (only active during mic test, after permission requested)
  useEffect(() => {
    if (micTestDone || phase !== "interview" || !micPermissionRequested) return;
    // Start mic level monitoring
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
        if (avg > 15) setMicTestDone(true); // auto-pass when they speak
        micAnimRef.current = requestAnimationFrame(tick);
      };
      micAnimRef.current = requestAnimationFrame(tick);
    }).catch(() => setMicTestDone(true)); // if denied, skip test
    return () => {
      if (micAnimRef.current) cancelAnimationFrame(micAnimRef.current);
      micStreamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, [phase, micTestDone, micPermissionRequested]);

  const sessionKey = token ? `interview_${token}` : null;

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

  async function doStartInterview() {
    const res = await startInterview(token!, {
      displayName: displayName || undefined,
      profession: profession || undefined,
      ageRange: ageRange || undefined,
      country: country || undefined,
      email: email || undefined,
    });
    setParticipantId(res.participant_id);
    setCurrentQuestion(res.first_question);
    setTurnCount(1);
    setQuestionIndex(0);
    setIsFollowUp(false);
    // Init timing from info
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

  async function handleStart() {
    if (!token) return;
    setStarting(true);
    setError("");
    try {
      // Check for email-based resume first
      if (email.trim()) {
        const resume = await checkResume(token, email.trim());
        if (resume.found && resume.participant_id) {
          setResumeCheck(resume);
          // Fetch summary
          setLoadingResumeSummary(true);
          try {
            const summary = await getResumeSummary(token, resume.participant_id);
            setResumeSummary(summary);
          } catch { /* summary optional */ }
          finally { setLoadingResumeSummary(false); }
          setStarting(false);
          return; // Show resume dialog instead of starting
        }
      }
      // No resume found — proceed normally
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
      setError("Failed to start interview. Please try again.");
    } finally {
      setStarting(false);
    }
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
      try {
        const result = await submitScreening(token!, updated);
        if (result.qualified) {
          await doStartInterview();
        } else {
          setDisqualifiedOn(result.disqualified_on ?? "");
          setPhase("disqualified");
        }
      } catch {
        setError("Something went wrong. Please try again.");
        setPhase("landing");
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
      setTtsEnded(false); // prevent immediate re-record
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Recording failed. Please try again.";
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
      } else if (res.question_text) {
        const nextTurn = turnCount + 1;
        setCurrentQuestion(res.question_text);
        setTurnCount(nextTurn);
        setQuestionIndex(res.question_index ?? questionIndex);
        setIsFollowUp(res.is_follow_up ?? false);
        if (res.elapsed_seconds !== undefined) setElapsedSeconds(res.elapsed_seconds);
        if (res.total_seconds !== undefined && res.total_seconds > 0) setTotalSeconds(res.total_seconds);
        // Show transcript briefly
        if (res.transcript) {
          setLastTranscript(res.transcript);
          setShowTranscript(true);
          setTimeout(() => setShowTranscript(false), 4000);
        }
        setTtsEnded(false);
        saveSession(participantId, res.question_text, nextTurn);
        if (res.tts_audio_url) playTTS(res.tts_audio_url);
        else setTtsEnded(true); // no TTS — can record immediately
      }
    } catch (err: unknown) {
      clearInterval(stepInterval);
      // Restore blob for retry
      setPendingBlob(lastBlobRef.current);
      const msg = err instanceof Error ? err.message : "Upload failed. Tap 'Try again' to resubmit.";
      setError(msg);
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
      setError("Couldn't skip. Please try again.");
    } finally {
      setProcessing(false);
    }
  }

  function toggleMute() {
    setMuted((m) => {
      const next = !m;
      if (next && audioRef.current) {
        audioRef.current.pause();
      }
      return next;
    });
  }

  /* ---- Landing Phase ---- */
  if (infoLoading) {
    return (
      <div className="interview-page">
        <div className="interview-container">
          <p className="muted-text">Loading...</p>
        </div>
      </div>
    );
  }

  if (error && phase === "landing" && !info) {
    return (
      <div className="interview-page">
        <div className="interview-container" style={{ textAlign: "center", paddingTop: 60 }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: "var(--primary, #6366f1)", marginBottom: 32 }}>QualiPulse</div>
          <div style={{ fontSize: 48, marginBottom: 16 }}>🔗</div>
          <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 10 }}>This interview link isn't active</h1>
          <p style={{ color: "var(--text-secondary, #6b7280)", fontSize: 15, maxWidth: 380, margin: "0 auto" }}>
            The link may have expired or been deactivated. Please contact the researcher for a new link.
          </p>
        </div>
      </div>
    );
  }

  /* ---- Consent declined ---- */
  if (consentDeclined) {
    return (
      <div className="interview-page">
        <div className="interview-container interview-complete">
          <h1 className="interview-complete-title">No problem</h1>
          <p className="interview-complete-text">
            You can close this page. Your participation is entirely voluntary — thank you for your time.
          </p>
        </div>
      </div>
    );
  }

  if (phase === "landing" && info) {
    const savedSession = getSavedSession();
    /* ---- Consent overlay ---- */
    if (!consentGiven) {
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
            <h1 className="consent-title">Before you begin</h1>
            <p className="consent-project">{info.project_name}</p>
            {info.research_context && (
              <p className="consent-research-context">{info.research_context}</p>
            )}
            <div className="consent-body">
              <p>By participating in this study you agree to the following:</p>
              <ul className="consent-list">
                <li>Your voice will be <strong>recorded and transcribed</strong> by AI.</li>
                <li>Your responses will be reviewed by the research team.</li>
                <li>Participation is <strong>voluntary</strong> — you may stop at any time.</li>
                <li>Your data will be stored securely and used only for research purposes.</li>
              </ul>
              <p className="consent-duration">
                {info.interview_duration_minutes ? (
                  <>This interview takes approximately <strong>{info.interview_duration_minutes} minutes</strong></>
                ) : null}
                {info.interview_duration_minutes && info.question_count ? " · " : null}
                {info.question_count ? (
                  <><strong>{info.question_count} topic{info.question_count !== 1 ? "s" : ""}</strong> to cover</>
                ) : null}
                {(info.interview_duration_minutes || info.question_count) ? "." : null}
              </p>
              {info.privacy_policy_url && (
                <p className="consent-privacy-link">
                  <a href={info.privacy_policy_url} target="_blank" rel="noopener noreferrer">
                    Read our privacy policy →
                  </a>
                </p>
              )}
            </div>
            <div className="consent-actions">
              <button className="btn btn-primary" onClick={() => setConsentGiven(true)}>
                I agree — continue
              </button>
              <button className="btn btn-ghost" onClick={() => setConsentDeclined(true)}>
                Decline
              </button>
            </div>
          </div>
        </div>
      );
    }

    return (
      <div className="interview-page">
        <div className="interview-container interview-landing">
          {info.researcher_logo_url && (
            <div className="landing-researcher-logo">
              <img src={info.researcher_logo_url} alt={info.researcher_name ?? "Researcher logo"} />
            </div>
          )}
          <h1 className="interview-project-name">{info.project_name}</h1>
          {info.researcher_name && (
            <p style={{ fontSize: 14, color: "var(--text-secondary, #6b7280)", marginTop: 4, marginBottom: 8 }}>
              A research study by <strong>{info.researcher_name}</strong>
            </p>
          )}
          {info.welcome_message && (
            <p className="interview-welcome">{info.welcome_message}</p>
          )}
          {info.interview_duration_minutes && (
            <p className="interview-duration">
              ⏱ Approximately {info.interview_duration_minutes} minutes
            </p>
          )}
          {savedSession && (
            <div className="resume-banner">
              <div>
                <strong>Resume your interview</strong>
                <p>You have an interview in progress (question {savedSession.turnCount}).</p>
              </div>
              <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
                <button className="btn btn-primary btn-sm" onClick={handleResumeSession}>Resume →</button>
                <button className="btn btn-ghost btn-sm" onClick={clearSession}>Start over</button>
              </div>
            </div>
          )}
          <p className="interview-instructions">
            You will be asked a series of questions. For each question, hold the
            record button and speak your answer. Take your time — there are no
            wrong answers.
          </p>

          <div className="interview-name-field">
            <label className="field-label">
              Your name <span className="optional-tag">(optional)</span>
            </label>
            <input
              type="text"
              className="field-input"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="How you'd like to be identified"
            />
          </div>

          <div className="interview-name-field">
            <label className="field-label">
              Your profession <span className="optional-tag">(optional)</span>
            </label>
            <input
              type="text"
              className="field-input"
              value={profession}
              onChange={(e) => setProfession(e.target.value)}
              placeholder="e.g. Teacher, Engineer, Student…"
            />
          </div>

          <div className="interview-name-field">
            <label className="field-label">
              Age range <span className="optional-tag">(optional)</span>
            </label>
            <select
              className="field-input"
              value={ageRange}
              onChange={(e) => setAgeRange(e.target.value)}
            >
              <option value="">Prefer not to say</option>
              <option value="18-24">18–24</option>
              <option value="25-34">25–34</option>
              <option value="35-44">35–44</option>
              <option value="45-54">45–54</option>
              <option value="55-64">55–64</option>
              <option value="65+">65+</option>
            </select>
          </div>

          <div className="interview-name-field">
            <label className="field-label">
              Country <span className="optional-tag">(optional)</span>
            </label>
            <input
              type="text"
              className="field-input"
              value={country}
              onChange={(e) => setCountry(e.target.value)}
              placeholder="e.g. France, United States…"
            />
          </div>

          <div className="interview-name-field">
            <label className="field-label">
              Your email <span className="optional-tag">(optional — to resume later)</span>
            </label>
            <input
              type="email"
              className="field-input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
            />
          </div>

          {error && <div className="error-banner">{error}</div>}

          <button
            className="btn btn-primary btn-lg"
            onClick={handleStart}
            disabled={starting}
          >
            {starting ? "Starting..." : "Start Interview"}
          </button>
        </div>
      </div>
    );
  }

  /* ---- Screening Phase ---- */
  if (phase === "screening") {
    const sq = screeningQuestions[screeningStep];
    const progress = ((screeningStep + 1) / screeningQuestions.length) * 100;
    return (
      <div className="interview-page">
        <div className="interview-container interview-profiling">
          <div className="profiling-header">
            <p className="profiling-intro">A few quick questions before we begin</p>
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
                  {screeningLoading && screeningAnswers[sq.id] === opt ? "Checking..." : opt}
                </button>
              ))}
            </div>
          </div>
          {error && <div className="error-banner">{error}</div>}
          {screeningStep > 0 && !screeningLoading && (
            <button
              className="profiling-back-btn"
              onClick={() => setScreeningStep((s) => s - 1)}
            >
              ← Back
            </button>
          )}
        </div>
      </div>
    );
  }

  /* ---- Disqualified Phase ---- */
  if (phase === "disqualified") {
    return (
      <div className="interview-page">
        <div className="interview-container interview-complete">
          <div className="complete-icon disqualified-icon">🙏</div>
          <h1 className="interview-complete-title">Thank you for your time</h1>
          <p className="interview-complete-text">
            This particular study is looking for a specific audience profile —
            you're not the right fit for <strong>{info?.project_name}</strong> right now.
          </p>
          <p className="interview-complete-text" style={{ marginTop: 12 }}>
            That's completely okay. Your answers helped us confirm we're reaching
            the right participants.
          </p>
          {email && (
            <p className="disqualified-email-note">
              If other studies open up that match your profile, we may reach out to{" "}
              <strong>{email}</strong>.
            </p>
          )}
          <p className="muted-text" style={{ marginTop: 24 }}>
            You can safely close this page.
          </p>
        </div>
      </div>
    );
  }

  /* ---- Resume Confirm Phase ---- */
  if (resumeCheck?.found && resumeCheck.participant_id) {
    return (
      <div className="interview-page">
        <div className="interview-container resume-confirm-card">
          <h1 className="consent-title">Welcome back!</h1>
          <p className="resume-confirm-subtitle">
            You have an interview in progress for <strong>{info?.project_name}</strong>.
          </p>

          {loadingResumeSummary ? (
            <p className="muted-text">Loading your progress...</p>
          ) : resumeSummary && resumeSummary.questions_covered.length > 0 ? (
            <div className="resume-summary-panel">
              <p className="resume-summary-label">Topics you've covered so far:</p>
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
                  {Math.round(resumeSummary.elapsed_minutes)} minutes in
                  {info?.interview_duration_minutes ? ` of ${info.interview_duration_minutes}` : ""}
                </p>
              )}
            </div>
          ) : null}

          {resumeCheck.last_question && (
            <div className="resume-last-question">
              <p className="resume-last-label">Pick up where you left off:</p>
              <p className="resume-last-text">"{resumeCheck.last_question}"</p>
            </div>
          )}

          <div className="consent-actions">
            <button className="btn btn-primary" onClick={handleConfirmResume}>
              Continue my interview →
            </button>
            <button
              className="btn btn-ghost"
              onClick={async () => {
                setResumeCheck(null);
                setResumeSummary(null);
                // Start fresh
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
                  setError("Failed to start interview. Please try again.");
                }
              }}
            >
              Start a new interview
            </button>
          </div>
        </div>
      </div>
    );
  }

  /* ---- Mic Permission Pre-prompt ---- */
  if (phase === "interview" && !micTestDone && !micPermissionRequested) {
    return (
      <div className="interview-page">
        <div className="interview-container mic-test-card">
          <div className="mic-prompt-icon">🎙️</div>
          <h2 className="mic-test-title">This interview uses your microphone</h2>
          <p className="mic-test-subtitle">
            When you click below, your browser will ask for microphone permission.
            Click <strong>Allow</strong> — this is required to record your answers.
          </p>
          <div className="mic-prompt-steps">
            <div className="mic-prompt-step">
              <span className="mic-prompt-num">1</span>
              <span>Click "Enable microphone" below</span>
            </div>
            <div className="mic-prompt-step">
              <span className="mic-prompt-num">2</span>
              <span>Click <strong>Allow</strong> in your browser's permission prompt</span>
            </div>
            <div className="mic-prompt-step">
              <span className="mic-prompt-num">3</span>
              <span>Say something to confirm your mic is working</span>
            </div>
          </div>
          <button
            className="btn btn-primary"
            onClick={() => setMicPermissionRequested(true)}
          >
            Enable microphone →
          </button>
          <p className="mic-prompt-note">
            Your audio is only recorded when you actively press the record button.
          </p>
        </div>
      </div>
    );
  }

  /* ---- Mic Test Phase ---- */
  if (phase === "interview" && !micTestDone) {
    return (
      <div className="interview-page">
        <div className="interview-container mic-test-card">
          <h2 className="mic-test-title">Quick mic check</h2>
          <p className="mic-test-subtitle">Say anything to test your microphone before we begin.</p>
          <div className="mic-level-wrap">
            <div className="mic-level-bar" style={{ width: `${micLevel}%` }} />
          </div>
          {micLevel > 20 ? (
            <p className="mic-test-status mic-test-ok">✓ Microphone detected — you're good to go!</p>
          ) : (
            <p className="mic-test-status">Speak to see your mic level…</p>
          )}
          <div className="mic-test-actions">
            <button
              className="btn btn-primary"
              onClick={() => {
                if (micAnimRef.current) cancelAnimationFrame(micAnimRef.current);
                micStreamRef.current?.getTracks().forEach((t) => t.stop());
                setMicTestDone(true);
              }}
            >
              {micLevel > 20 ? "Start interview →" : "Skip mic test"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  /* ---- Interview Phase ---- */
  if (phase === "interview") {
    return (
      <div className="interview-page">
        <div className="interview-container interview-active">
          {/* Progress */}
          {info?.question_count && info.question_count > 0 && (
            <div className="interview-progress-bar-wrap">
              <div
                className="interview-progress-bar-fill"
                style={{ width: `${Math.min(((questionIndex) / info.question_count) * 100, 95)}%` }}
              />
            </div>
          )}
          <div className="interview-progress">
            <span className="interview-turn-count">
              {isFollowUp
                ? `Follow-up · Q${questionIndex + 1} of ${info?.question_count ?? "?"}`
                : `Q${questionIndex + 1} of ${info?.question_count ?? "?"}`}
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
                    return <span className={cls}>{mins > 0 ? `~${mins} min left` : `${secs}s left`}</span>;
                  })()}
                </span>
              )}
              <button
                className={`mute-btn ${muted ? "muted" : ""}`}
                onClick={toggleMute}
                title={muted ? "Unmute" : "Mute"}
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

          {/* Question */}
          <div className="interview-question-area">
            <p className="interview-question-text">{currentQuestion}</p>
          </div>

          {/* Error */}
          {error && <div className="error-banner">{error}</div>}
          {recError === "PERMISSION_DENIED" ? (
            <div className="mic-permission-error">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#dc2626" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="1" y1="1" x2="23" y2="23" />
                <path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V4a3 3 0 0 0-5.94-.6" />
                <path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2c0 .76-.13 1.49-.36 2.18" />
                <line x1="12" y1="19" x2="12" y2="23" />
                <line x1="8" y1="23" x2="16" y2="23" />
              </svg>
              <h3 className="mic-permission-title">Microphone access denied</h3>
              <p className="mic-permission-text">
                This interview requires microphone access to record your answers.
                Please allow microphone access in your browser, then refresh the page.
              </p>
              <button className="btn btn-primary" onClick={() => window.location.reload()}>
                Refresh &amp; try again
              </button>
            </div>
          ) : recError ? (
            <div className="error-banner">{recError}</div>
          ) : null}

          {/* Transcript flash */}
          {showTranscript && lastTranscript && (
            <div className="transcript-flash">
              <span className="transcript-flash-label">We heard:</span>
              <span className="transcript-flash-text">"{lastTranscript}"</span>
            </div>
          )}

          {/* Recording UI */}
          <div className="interview-controls">
            {processing ? (
              <div className="processing-indicator">
                <div className="spinner" />
                <span>{["Transcribing your answer…", "Thinking…", "Preparing next question…"][processingStep]}</span>
              </div>
            ) : pendingBlob ? (
              /* Preview state — recorded but not yet submitted */
              <div className="recording-preview">
                <div className="recording-preview-icon">✓</div>
                <p className="recording-preview-label">Recording captured</p>
                <div className="recording-preview-actions">
                  <button className="btn btn-primary" onClick={handleSubmitPending}>
                    Submit answer →
                  </button>
                  <button className="btn btn-ghost" onClick={handleReRecord}>
                    ↺ Re-record
                  </button>
                </div>
              </div>
            ) : isRecording ? (
              <>
                <button className="record-btn recording" onClick={handleStopAndPreview}>
                  <div className="record-btn-inner recording-pulse" />
                </button>
                <p className="record-label">Tap to stop recording</p>
                {recordingSeconds > 0 && (
                  <p className={`recording-timer ${recordingSeconds >= MAX_RECORDING_SECONDS - 30 ? "recording-timer--warning" : ""}`}>
                    {Math.floor((MAX_RECORDING_SECONDS - recordingSeconds) / 60)}:
                    {String((MAX_RECORDING_SECONDS - recordingSeconds) % 60).padStart(2, "0")} remaining
                  </p>
                )}
              </>
            ) : (
              <>
                <button
                  className={`record-btn ${ttsPlaying ? "record-btn--waiting" : ttsEnded ? "record-btn--ready" : ""}`}
                  onClick={ttsPlaying ? undefined : startRecording}
                  disabled={ttsPlaying}
                  title={ttsPlaying ? "Wait for the question to finish" : "Tap to start recording"}
                >
                  <div className="record-btn-inner" />
                </button>
                <p className="record-label">
                  {ttsPlaying ? "⏵ Listening to question…" : "Tap to start recording"}
                </p>
              </>
            )}
          </div>

          {/* Skip question */}
          {!processing && !isRecording && !pendingBlob && (
            <button className="skip-question-btn" onClick={handleSkip}>
              Skip this question
            </button>
          )}
        </div>
      </div>
    );
  }

  /* ---- Complete Phase ---- */
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
          {displayName ? `Thank you, ${displayName.split(" ")[0]}!` : "You're done — thank you!"}
        </h1>
        <p className="interview-complete-text">
          Your responses have been recorded and will help shape the research for{" "}
          <strong>{info?.project_name}</strong>.
        </p>
        {turnCount > 1 && (
          <p className="interview-complete-meta">
            You answered {turnCount - 1} question{turnCount - 1 !== 1 ? "s" : ""}.
          </p>
        )}
        <div className="interview-complete-next">
          <p className="interview-complete-next-label">What happens next?</p>
          <ul className="interview-complete-next-list">
            <li>The research team will review your responses.</li>
            <li>Your answers may be used to improve products or services.</li>
            <li>You can safely close this page.</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
