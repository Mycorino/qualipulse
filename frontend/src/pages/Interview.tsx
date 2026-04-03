import { useState, useEffect, useRef, useCallback } from "react";
import { useParams } from "react-router-dom";
import {
  getInterviewInfo,
  getScreeningQuestions,
  submitScreening,
  startInterview,
  submitAudio,
  InterviewInfo,
  ScreeningQuestion,
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

  // Screening state
  const [screeningQuestions, setScreeningQuestions] = useState<ScreeningQuestion[]>([]);
  const [screeningStep, setScreeningStep] = useState(0);
  const [screeningAnswers, setScreeningAnswers] = useState<Record<string, string>>({});
  const [screeningLoading, setScreeningLoading] = useState(false);
  const [disqualifiedOn, setDisqualifiedOn] = useState("");

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

  // Play TTS audio
  const playTTS = useCallback(
    (url: string) => {
      if (muted) return;
      if (audioRef.current) {
        audioRef.current.pause();
      }
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.play().catch(() => {
        // autoplay blocked -- user will read the question
      });
    },
    [muted]
  );

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
    });
    setParticipantId(res.participant_id);
    setCurrentQuestion(res.first_question);
    setTurnCount(1);
    saveSession(res.participant_id, res.first_question, 1);
    setPhase("interview");
    if (res.tts_audio_url) playTTS(res.tts_audio_url);
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

  async function handleStopAndSubmit() {
    if (!token) return;
    setProcessing(true);
    try {
      const blob = await stopRecording();
      const res = await submitAudio(token, participantId, blob);
      if (res.is_complete) {
        clearSession();
        setPhase("complete");
        if (audioRef.current) audioRef.current.pause();
      } else if (res.question_text) {
        const nextTurn = turnCount + 1;
        setCurrentQuestion(res.question_text);
        setTurnCount(nextTurn);
        saveSession(participantId, res.question_text, nextTurn);
        if (res.tts_audio_url) {
          playTTS(res.tts_audio_url);
        }
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Something went wrong. Please try recording again.";
      setError(msg);
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
        <div className="interview-container">
          <p className="interview-error">{error}</p>
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
            <h1 className="consent-title">Before you begin</h1>
            <p className="consent-project">{info.project_name}</p>
            <div className="consent-body">
              <p>By participating in this study you agree to the following:</p>
              <ul className="consent-list">
                <li>Your voice will be <strong>recorded and transcribed</strong> by AI.</li>
                <li>Your responses will be reviewed by the research team.</li>
                <li>Participation is <strong>voluntary</strong> — you may stop at any time.</li>
                <li>Your data will be stored securely and used only for research purposes.</li>
              </ul>
              {info.interview_duration_minutes && (
                <p className="consent-duration">This interview takes approximately <strong>{info.interview_duration_minutes} minutes</strong>.</p>
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
          <h1 className="interview-project-name">{info.project_name}</h1>
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
          <div className="complete-icon">
            <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          </div>
          <h1 className="interview-complete-title">Thank you for your interest</h1>
          <p className="interview-complete-text">
            Based on your answers, you don't match the profile we're looking for in this study.
            We appreciate your time!
          </p>
          {disqualifiedOn && (
            <p className="muted-text" style={{ marginTop: 8, fontSize: 13 }}>
              This study requires a specific audience profile.
            </p>
          )}
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
                style={{ width: `${Math.min((turnCount / (info.question_count * 1.5)) * 100, 90)}%` }}
              />
            </div>
          )}
          <div className="interview-progress">
            <span className="interview-turn-count">Question {turnCount}{info?.question_count ? ` of ~${info.question_count}` : ""}</span>
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

          {/* Recording UI */}
          <div className="interview-controls">
            {processing ? (
              <div className="processing-indicator">
                <div className="spinner" />
                <span>Processing your response...</span>
              </div>
            ) : isRecording ? (
              <>
                <button
                  className="record-btn recording"
                  onClick={handleStopAndSubmit}
                >
                  <div className="record-btn-inner recording-pulse" />
                </button>
                <p className="record-label">Tap to stop recording</p>
              </>
            ) : (
              <>
                <button className="record-btn" onClick={startRecording}>
                  <div className="record-btn-inner" />
                </button>
                <p className="record-label">Tap to start recording</p>
              </>
            )}
          </div>
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
        <h1 className="interview-complete-title">Thank you!</h1>
        <p className="interview-complete-text">
          Your interview has been recorded successfully. You may now close this
          page.
        </p>
      </div>
    </div>
  );
}
