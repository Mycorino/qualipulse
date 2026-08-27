import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  createRealtimeSession,
  getInterviewStatus,
  uploadSessionRecording,
} from "../api/interviews";

/**
 * Realtime voice interview (beta).
 *
 * The browser talks WebRTC directly to the OpenAI Realtime API: the model
 * listens, detects turns and speaks, while the backend's sideband bridge
 * runs the actual interview logic (Claude decisions, pacing, completion).
 * This component owns three client-side jobs:
 *
 * 1. Signaling: SDP offer -> backend proxy -> SDP answer.
 * 2. The parallel session recording: the Realtime API never returns raw
 *    audio, so we mix the mic + the interviewer's voice through a
 *    WebAudio graph into one MediaRecorder and upload the file at the end.
 * 3. Progress: the data channel gives live captions and speaking state;
 *    a light poll of /status gives question progress and completion.
 */

interface RealtimeInterviewProps {
  token: string;
  participantId: string;
  questionCount: number;
  firstQuestion: string | null;
  onComplete: () => void;
  /** Give up on the live transport and continue this same interview in the
   *  classic record/submit flow, from the question currently pending. */
  onFallback: () => void;
}

type ConnState = "connecting" | "live" | "ending" | "error";
type VoiceState = "idle" | "speaking" | "listening" | "thinking";

const RECORDER_MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/ogg;codecs=opus",
];

// How long we keep waiting for the goodbye line to finish playing after the
// backend marks the interview completed, before wrapping up anyway.
const ENDING_GRACE_MS = 25_000;
const STATUS_POLL_MS = 3_500;

export default function RealtimeInterview({
  token,
  participantId,
  questionCount,
  firstQuestion,
  onComplete,
  onFallback,
}: RealtimeInterviewProps) {
  const { t } = useTranslation("interview");

  const [connState, setConnState] = useState<ConnState>("connecting");
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const [caption, setCaption] = useState<string | null>(firstQuestion);
  const [questionIndex, setQuestionIndex] = useState<number>(0);
  const [isFollowUp, setIsFollowUp] = useState(false);
  const [uploading, setUploading] = useState(false);
  // Participant-controlled pause: VAD is switched off in the session and
  // the input buffer cleared (see toggleMicPause), so nothing can commit
  // and the interviewer stays silent until resume. The mic track is also
  // disabled, so the session recording goes honestly silent with it.
  const [micPaused, setMicPaused] = useState(false);

  const pcRef = useRef<RTCPeerConnection | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const remoteAudioRef = useRef<HTMLAudioElement | null>(null);
  const captionRef = useRef("");
  const finishedRef = useRef(false);
  const dcRef = useRef<RTCDataChannel | null>(null);
  // turn_detection config from the SDP exchange, needed to re-arm VAD after
  // a pause (pause = session.update turn_detection null: true push-to-talk
  // off-switch — merely muting the track feeds VAD silence, which it reads
  // as "done talking" and commits the half-said answer).
  const turnDetectionRef = useRef<unknown | null>(null);
  const uploadBusyRef = useRef(false);
  const uploadedBytesRef = useRef(0);
  const speakingRef = useRef(false);
  const setupSeqRef = useRef(0);

  const sendEvent = useCallback((event: Record<string, unknown>) => {
    const dc = dcRef.current;
    if (dc && dc.readyState === "open") {
      try { dc.send(JSON.stringify(event)); } catch { /* channel closing */ }
    }
  }, []);

  const toggleMicPause = useCallback(() => {
    // A click is a user gesture: use it to rescue a suspended AudioContext
    // (Safari starts them suspended when created outside a gesture, which
    // silently produced empty session recordings).
    void audioCtxRef.current?.resume().catch(() => undefined);
    setMicPaused((prev) => {
      const next = !prev;
      if (next) {
        micStreamRef.current?.getAudioTracks().forEach((tr) => { tr.enabled = false; });
        // Turn VAD off entirely and drop any half-captured speech, so the
        // interviewer cannot commit a turn (and speak) while paused.
        sendEvent({ type: "session.update", session: { type: "realtime", audio: { input: { turn_detection: null } } } });
        sendEvent({ type: "input_audio_buffer.clear" });
      } else {
        sendEvent({ type: "input_audio_buffer.clear" });
        if (turnDetectionRef.current) {
          sendEvent({ type: "session.update", session: { type: "realtime", audio: { input: { turn_detection: turnDetectionRef.current } } } });
        }
        micStreamRef.current?.getAudioTracks().forEach((tr) => { tr.enabled = true; });
      }
      return next;
    });
  }, [sendEvent]);

  const teardown = useCallback(() => {
    try { recorderRef.current?.state !== "inactive" && recorderRef.current?.stop(); } catch { /* already stopped */ }
    recorderRef.current = null;
    try { pcRef.current?.close(); } catch { /* already closed */ }
    pcRef.current = null;
    micStreamRef.current?.getTracks().forEach((tr) => tr.stop());
    micStreamRef.current = null;
    void audioCtxRef.current?.close().catch(() => undefined);
    audioCtxRef.current = null;
  }, []);

  const startRecorder = useCallback((mic: MediaStream, remote: MediaStream) => {
    try {
      const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const ctx = new Ctx();
      audioCtxRef.current = ctx;
      // Safari (and some Chrome autoplay states) create the context
      // suspended when instantiated outside a user gesture; a suspended
      // graph records pure silence. Resume immediately, and again from the
      // pause-button gesture as a fallback.
      void ctx.resume().catch(() => undefined);
      const dest = ctx.createMediaStreamDestination();
      ctx.createMediaStreamSource(mic).connect(dest);
      ctx.createMediaStreamSource(remote).connect(dest);
      const mime = RECORDER_MIME_CANDIDATES.find((m) => MediaRecorder.isTypeSupported(m));
      const recorder = new MediaRecorder(dest.stream, mime ? { mimeType: mime } : undefined);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.start(3000);
      recorderRef.current = recorder;
    } catch {
      // Recording is a research artefact, never a participant blocker: the
      // interview continues audio-less on our side (transcripts still land
      // server-side through the realtime transcription events).
    }
  }, []);

  // Upload whatever the recorder has so far. The server overwrites, so the
  // last (longest) upload wins; a participant who abandons the tab now
  // costs us the final seconds, not the whole recording.
  const uploadPartial = useCallback(async () => {
    if (uploadBusyRef.current || chunksRef.current.length === 0) return;
    const blob = new Blob(chunksRef.current, { type: chunksRef.current[0].type || "audio/webm" });
    if (blob.size < 500 || blob.size <= uploadedBytesRef.current) return;
    uploadBusyRef.current = true;
    try {
      await uploadSessionRecording(token, participantId, blob);
      uploadedBytesRef.current = blob.size;
    } catch {
      // Next tick retries with a bigger blob.
    } finally {
      uploadBusyRef.current = false;
    }
  }, [participantId, token]);

  useEffect(() => {
    const timer = setInterval(() => {
      if (!finishedRef.current) void uploadPartial();
    }, 45_000);
    const onHide = () => { if (!finishedRef.current) void uploadPartial(); };
    window.addEventListener("pagehide", onHide);
    document.addEventListener("visibilitychange", onHide);
    return () => {
      clearInterval(timer);
      window.removeEventListener("pagehide", onHide);
      document.removeEventListener("visibilitychange", onHide);
    };
  }, [uploadPartial]);

  const finishUp = useCallback(async () => {
    if (finishedRef.current) return;
    finishedRef.current = true;
    setConnState("ending");
    setUploading(true);
    const recorder = recorderRef.current;
    const blob: Blob | null = await new Promise((resolve) => {
      if (!recorder || recorder.state === "inactive") {
        resolve(chunksRef.current.length ? new Blob(chunksRef.current, { type: chunksRef.current[0].type }) : null);
        return;
      }
      recorder.onstop = () => {
        resolve(chunksRef.current.length ? new Blob(chunksRef.current, { type: chunksRef.current[0].type }) : null);
      };
      try { recorder.stop(); } catch { resolve(null); }
    });
    teardown();
    if (blob && blob.size > 500) {
      try {
        await uploadSessionRecording(token, participantId, blob);
      } catch {
        // Best-effort: losing the recording never blocks the completion screen.
      }
    }
    setUploading(false);
    onComplete();
  }, [onComplete, participantId, teardown, token]);

  const handleDataChannelEvent = useCallback((raw: string) => {
    let event: { type?: string; delta?: string } | null = null;
    try { event = JSON.parse(raw); } catch { return; }
    if (!event || typeof event.type !== "string") return;
    switch (event.type) {
      case "response.output_audio_transcript.delta":
        if (typeof event.delta === "string") {
          if (!speakingRef.current) captionRef.current = "";
          speakingRef.current = true;
          captionRef.current += event.delta;
          setCaption(captionRef.current);
          setVoiceState("speaking");
        }
        break;
      case "response.done":
        speakingRef.current = false;
        setVoiceState("idle");
        break;
      case "input_audio_buffer.speech_started":
        setVoiceState("listening");
        break;
      case "input_audio_buffer.speech_stopped":
        setVoiceState("thinking");
        break;
      default:
        break;
    }
  }, []);

  const connect = useCallback(async () => {
    const seq = ++setupSeqRef.current;
    setConnState("connecting");
    try {
      const mic = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (seq !== setupSeqRef.current) { mic.getTracks().forEach((tr) => tr.stop()); return; }
      micStreamRef.current = mic;

      const pc = new RTCPeerConnection();
      pcRef.current = pc;
      pc.addTrack(mic.getAudioTracks()[0], mic);
      pc.ontrack = (e) => {
        const remote = e.streams[0];
        if (remoteAudioRef.current) {
          remoteAudioRef.current.srcObject = remote;
          void remoteAudioRef.current.play().catch(() => undefined);
        }
        startRecorder(mic, remote);
      };
      const dc = pc.createDataChannel("oai-events");
      dcRef.current = dc;
      dc.onmessage = (e) => handleDataChannelEvent(String(e.data));
      pc.onconnectionstatechange = () => {
        if (finishedRef.current) return;
        if (pc.connectionState === "connected") setConnState("live");
        if (pc.connectionState === "failed") setConnState("error");
      };

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      // Wait briefly for ICE gathering so the offer carries our candidates
      // (the exchange is non-trickle: one POST, one answer).
      await new Promise<void>((resolve) => {
        if (pc.iceGatheringState === "complete") { resolve(); return; }
        const timer = setTimeout(resolve, 1500);
        pc.onicegatheringstatechange = () => {
          if (pc.iceGatheringState === "complete") { clearTimeout(timer); resolve(); }
        };
      });
      const sdp = pc.localDescription?.sdp;
      if (!sdp) throw new Error("no local SDP");
      const session = await createRealtimeSession(token, participantId, sdp);
      turnDetectionRef.current = session.turnDetection;
      if (seq !== setupSeqRef.current) return;
      await pc.setRemoteDescription({ type: "answer", sdp: session.sdp });
    } catch {
      if (seq === setupSeqRef.current && !finishedRef.current) {
        teardown();
        setConnState("error");
      }
    }
  }, [handleDataChannelEvent, participantId, startRecorder, teardown, token]);

  // Connect once on mount; tear everything down on unmount.
  useEffect(() => {
    void connect();
    return () => {
      setupSeqRef.current += 1;
      teardown();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Progress + completion polling. The backend flips the participant to
  // "completed" the moment Claude's closing turn is persisted; we then let
  // the goodbye finish playing before stopping the recorder and uploading.
  useEffect(() => {
    if (connState === "error") return;
    const timer = setInterval(async () => {
      if (finishedRef.current) return;
      try {
        const status = await getInterviewStatus(token, participantId);
        if (typeof status.question_index === "number" && status.question_index >= 0) {
          setQuestionIndex(status.question_index);
        }
        setIsFollowUp(Boolean(status.is_follow_up));
        if (status.status === "completed") {
          clearInterval(timer);
          const startedWaiting = Date.now();
          const waitForGoodbye = setInterval(() => {
            if (!speakingRef.current || Date.now() - startedWaiting > ENDING_GRACE_MS) {
              clearInterval(waitForGoodbye);
              // Small tail so the last audio frames land in the recording.
              setTimeout(() => void finishUp(), 800);
            }
          }, 500);
        }
      } catch {
        // Transient poll failures are fine; the next tick retries.
      }
    }, STATUS_POLL_MS);
    return () => clearInterval(timer);
  }, [connState, finishUp, participantId, token]);

  const hideCounter = questionIndex < 0 || questionCount <= 0;
  const stateLine =
    connState === "connecting"
      ? t("realtime.connecting")
      : connState === "ending"
        ? t("realtime.wrappingUp")
        : micPaused
          ? t("realtime.pausedState")
          : voiceState === "speaking"
          ? t("realtime.speaking")
          : voiceState === "listening"
            ? t("realtime.listening")
            : voiceState === "thinking"
              ? t("realtime.thinking")
              : t("realtime.live");

  if (connState === "error") {
    return (
      <div className="interview-page">
        <div className="interview-container mic-test-card">
          <div className="mic-prompt-icon"><span aria-hidden="true">📡</span></div>
          <h2 className="mic-test-title">{t("realtime.errorTitle")}</h2>
          <p className="mic-test-subtitle">{t("realtime.errorBody")}</p>
          <button
            className="btn btn-primary"
            style={{ minHeight: 48, minWidth: 200 }}
            onClick={() => void connect()}
          >
            {t("realtime.retry")}
          </button>
          <button
            className="btn btn-ghost"
            style={{ marginTop: 12, minHeight: 44, color: "var(--text-secondary)" }}
            onClick={() => {
              // Stop this component's timers/streams for good, then hand the
              // interview back to the classic flow at the pending question.
              finishedRef.current = true;
              setupSeqRef.current += 1;
              teardown();
              onFallback();
            }}
          >
            {t("realtime.fallback")}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="interview-page">
      <div className="interview-container interview-active realtime-live">
        <audio ref={remoteAudioRef} autoPlay style={{ display: "none" }} />
        <div className="realtime-beta-badge">{t("realtime.beta")}</div>
        {!hideCounter && (
          <p className="interview-progress">
            {isFollowUp
              ? t("interview.followUpLabel", { current: questionIndex + 1, total: questionCount })
              : t("interview.progressLabel", { current: questionIndex + 1, total: questionCount })}
          </p>
        )}
        <div
          className={`realtime-orb realtime-orb--${connState === "connecting" ? "connecting" : micPaused ? "paused" : voiceState}`}
          aria-hidden="true"
        />
        <p className="realtime-state" role="status" aria-live="polite">
          {uploading ? t("realtime.saving") : stateLine}
        </p>
        {caption && connState !== "connecting" && (
          <p className="realtime-caption">{caption}</p>
        )}
        {connState === "live" && (
          <button
            className={micPaused ? "btn btn-primary" : "btn btn-secondary"}
            style={{ minHeight: 44, minWidth: 220 }}
            onClick={toggleMicPause}
            aria-pressed={micPaused}
          >
            {micPaused ? t("realtime.resume") : t("realtime.pauseMic")}
          </button>
        )}
        <p className="realtime-recording-notice">{t("realtime.recordingNotice")}</p>
      </div>
    </div>
  );
}
