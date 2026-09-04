import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  createRealtimeSession,
  getInterviewStatus,
  uploadSessionRecording,
  type Stimulus,
} from "../api/interviews";
import StimulusCard from "./StimulusCard";

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
// Speech-grade bitrate for the session recording. Left to the browser's
// default (iOS Safari: ~170 kbps) a 25-minute interview reached 32 MB, which
// is Cloud Run's hard request-size limit: every later upload was rejected
// at the edge and the last eight minutes of a 32-minute interview were
// lost. 48 kbps mono keeps an hour under ~22 MB and is transparent for
// voice; Whisper and the per-turn clip slicer are unaffected.
const RECORDER_BITS_PER_SECOND = 48_000;
// Upload cadence. Every upload re-sends the whole recording so far, so the
// cost grows with the session: a 30 MB file took 52 s to upload against a
// 45 s timer, back to back. The next upload waits a multiple of how long
// the last one took, within these bounds, so a long session uploads less
// often rather than continuously (the tab-hide flush and the completion
// upload still catch the tail).
const UPLOAD_MIN_INTERVAL_MS = 45_000;
const UPLOAD_MAX_INTERVAL_MS = 180_000;
const UPLOAD_BACKOFF_FACTOR = 3;

// How long we keep waiting for the goodbye line to finish playing after the
// backend marks the interview completed, before wrapping up anyway.
const ENDING_GRACE_MS = 25_000;
// Speaker tail: how long after the interviewer's audio finishes PLAYING
// (output_audio_buffer.stopped) before the mic is re-armed, so the room's
// reverb of its own sentence is not heard as an answer.
const MIC_REARM_DELAY_MS = 350;
// Safety net: response.done fires when generation ends, which can be seconds
// before playback ends. If output_audio_buffer.stopped never arrives, re-arm
// this long after response.done rather than staying muted forever.
const RESPONSE_DONE_FALLBACK_MS = 6_000;
const STATUS_POLL_MS = 3_500;
// Stall watchdog. The backend sideband is a separate process from the
// OpenAI call: a deploy, restart or crash kills it while the audio call
// stays up, and the participant's answers then go nowhere (the screen sat
// on "One moment" forever in exactly that case). After the participant's
// audio commits, some response (ack, backchannel or question) normally
// follows within ~5-8s; a hesitation-only fragment deliberately gets none,
// so the window is long. Past it, the call is rebuilt (new SDP, new
// sideband, which re-asks the pending question), a bounded number of times.
const STALL_AFTER_ANSWER_MS = 45_000;
// The opening line normally arrives within seconds of the data channel
// opening; without it the sideband never attached.
const STALL_AFTER_OPEN_MS = 25_000;
const STALL_CHECK_MS = 5_000;
const MAX_AUTO_RECONNECTS = 2;

// Explicit constraints: without echoCancellation the interviewer's voice
// comes back through the microphone, gets transcribed as if the participant
// had said it, and (with barge-in) cuts the interviewer off mid-sentence.
// Browsers usually default these on, but "usually" is not good enough for
// the one thing that breaks the conversation. Shared by the initial connect
// and the pause/resume reacquisition.
const MIC_CONSTRAINTS: MediaTrackConstraints = {
  echoCancellation: true,
  noiseSuppression: true,
  autoGainControl: true,
};

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
  // The artefact on screen for the current question (concept test). The
  // realtime flow has no per-turn HTTP response to read it from, so it
  // rides the same /status poll as progress; assigned wholesale so a
  // question without one clears the previous artefact.
  const [stimulus, setStimulus] = useState<Stimulus | null>(null);
  const [uploading, setUploading] = useState(false);
  // Participant-controlled pause: VAD is switched off in the session and
  // the input buffer cleared (see pauseMic), so nothing can commit and the
  // interviewer stays silent until resume. The mic track is fully STOPPED
  // (not just disabled) so the device is released and the phone's
  // mic-in-use indicator goes off; resume reacquires it via replaceTrack.
  const [micPaused, setMicPaused] = useState(false);

  const pcRef = useRef<RTCPeerConnection | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const remoteAudioRef = useRef<HTMLAudioElement | null>(null);
  const captionRef = useRef("");
  const captionOpenRef = useRef(false);
  // Which filler response (if any) is in flight: "ack" | "backchannel".
  // Fillers are never captioned; a backchannel also never mutes the mic.
  const sideKindRef = useRef<"ack" | "backchannel" | null>(null);
  const finishedRef = useRef(false);
  const dcRef = useRef<RTCDataChannel | null>(null);
  // turn_detection config from the SDP exchange, needed to re-arm VAD after
  // a pause (pause = session.update turn_detection null: true push-to-talk
  // off-switch — merely muting the track feeds VAD silence, which it reads
  // as "done talking" and commits the half-said answer).
  const turnDetectionRef = useRef<unknown | null>(null);
  const uploadBusyRef = useRef(false);
  const uploadedBytesRef = useRef(0);
  // Earliest time the periodic upload may run again (adaptive backoff).
  const nextUploadAtRef = useRef(0);
  const speakingRef = useRef(false);
  const setupSeqRef = useRef(0);
  const micPausedRef = useRef(false);
  // This connection's recording segment (from the SDP exchange): tags
  // every upload so a resumed session never overwrites earlier audio.
  const segmentIdRef = useRef<string | null>(null);
  // The OpenAI call died under us (data channel closed / ICE failed) — set
  // while paused so resume knows to rebuild the call instead of talking
  // into a dead one. A 10-minute pause on a locked phone reliably kills
  // the call (iOS suspends the page; OpenAI hangs up the idle session).
  const deadCallRef = useRef(false);
  // Filled once reconnect() exists (it is declared after connect()).
  const reconnectRef = useRef<(() => Promise<void>) | null>(null);
  // Stall watchdog: when the server was last given something it owes a
  // response for (audio committed, channel opened), null once it responds.
  const awaitingSinceRef = useRef<{ at: number; limit: number } | null>(null);
  const autoReconnectsRef = useRef(0);
  const [reconnecting, setReconnecting] = useState(false);
  const micRearmTimerRef = useRef<number | null>(null);
  // The RTCRtpSender carrying the mic track: pause fully STOPS the track
  // (releasing the device, so the phone's mic-in-use indicator goes off) and
  // resume swaps a freshly acquired track back in via replaceTrack.
  const micSenderRef = useRef<RTCRtpSender | null>(null);
  // The recorder's mixing destination, so a resumed mic can be wired back
  // into the session recording.
  const recorderDestRef = useRef<MediaStreamAudioDestinationNode | null>(null);

  // Echo cancellation is imperfect on speakerphone and laptop speakers, so
  // belt and braces: the microphone is physically muted while the
  // interviewer speaks, then re-armed a beat after it stops (the beat lets
  // the last audio drain out of the speaker before the mic reopens).
  const setMicLive = useCallback((live: boolean) => {
    if (micPausedRef.current && live) return; // participant paused: stay off
    micStreamRef.current?.getAudioTracks().forEach((tr) => { tr.enabled = live; });
  }, []);

  const sendEvent = useCallback((event: Record<string, unknown>) => {
    const dc = dcRef.current;
    if (dc && dc.readyState === "open") {
      try { dc.send(JSON.stringify(event)); } catch { /* channel closing */ }
    }
  }, []);

  useEffect(() => { micPausedRef.current = micPaused; }, [micPaused]);

  const pauseMic = useCallback(() => {
    // Set the ref synchronously: the speaking gate's re-arm timer can fire
    // before React flushes the state effect, and it must not reopen a mic
    // the participant just paused.
    micPausedRef.current = true;
    setMicPaused(true);
    awaitingSinceRef.current = null;
    // Turn VAD off entirely and drop any half-captured speech, so the
    // interviewer cannot commit a turn (and speak) while paused: the
    // documented push-to-talk off-switch (merely muting the track feeds VAD
    // silence, which it reads as "done talking").
    sendEvent({ type: "session.update", session: { type: "realtime", audio: { input: { turn_detection: null } } } });
    // Fully STOP the track rather than disable it: the phone keeps its
    // mic-in-use indicator lit for a live-but-muted track, and "pause"
    // must visibly let go of the microphone.
    micStreamRef.current?.getTracks().forEach((tr) => tr.stop());
    micStreamRef.current = null;
    sendEvent({ type: "input_audio_buffer.clear" });
  }, [sendEvent]);

  const resumeMic = useCallback(async () => {
    // A click is a user gesture: use it to rescue a suspended AudioContext
    // (Safari starts them suspended when created outside a gesture, which
    // silently produced empty session recordings).
    void audioCtxRef.current?.resume().catch(() => undefined);
    // A long pause (locked phone, backgrounded tab) usually killed the
    // call: iOS suspends the page and OpenAI hangs up. Reacquiring the mic
    // alone would leave the participant talking to a dead connection, so
    // rebuild the whole call — new SDP exchange, new sideband (it re-asks
    // the pending question), new recording segment.
    if (
      deadCallRef.current ||
      dcRef.current?.readyState !== "open" ||
      pcRef.current?.connectionState !== "connected"
    ) {
      micPausedRef.current = false;
      setMicPaused(false);
      await reconnectRef.current?.();
      return;
    }
    try {
      // Pause stopped the track, so reacquire the device (already granted
      // this session, so no new permission prompt) and swap it into the
      // existing peer connection.
      const mic = await navigator.mediaDevices.getUserMedia({ audio: MIC_CONSTRAINTS });
      const track = mic.getAudioTracks()[0];
      // Resuming mid-sentence must not reopen the mic into the speaker:
      // the speaking gate re-arms it when the interviewer finishes.
      track.enabled = !speakingRef.current;
      micStreamRef.current = mic;
      await micSenderRef.current?.replaceTrack(track);
      // Wire the fresh mic back into the session recording mix.
      const ctx = audioCtxRef.current;
      const dest = recorderDestRef.current;
      if (ctx && dest) {
        try { ctx.createMediaStreamSource(mic).connect(dest); } catch { /* recorder gone */ }
      }
      micPausedRef.current = false;
      setMicPaused(false);
      sendEvent({ type: "input_audio_buffer.clear" });
      if (turnDetectionRef.current) {
        sendEvent({ type: "session.update", session: { type: "realtime", audio: { input: { turn_detection: turnDetectionRef.current } } } });
      }
    } catch {
      // The mic could not be reacquired (permission withdrawn while
      // paused): surface the error state, which offers retry + the classic
      // flow instead of a silently dead conversation.
      setConnState("error");
    }
  }, [sendEvent]);

  const toggleMicPause = useCallback(() => {
    if (micPausedRef.current) void resumeMic();
    else pauseMic();
  }, [pauseMic, resumeMic]);

  const teardown = useCallback(() => {
    if (micRearmTimerRef.current) {
      window.clearTimeout(micRearmTimerRef.current);
      micRearmTimerRef.current = null;
    }
    try { recorderRef.current?.state !== "inactive" && recorderRef.current?.stop(); } catch { /* already stopped */ }
    recorderRef.current = null;
    try { pcRef.current?.close(); } catch { /* already closed */ }
    pcRef.current = null;
    micStreamRef.current?.getTracks().forEach((tr) => tr.stop());
    micStreamRef.current = null;
    micSenderRef.current = null;
    recorderDestRef.current = null;
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
      recorderDestRef.current = dest;
      ctx.createMediaStreamSource(mic).connect(dest);
      ctx.createMediaStreamSource(remote).connect(dest);
      const mime = RECORDER_MIME_CANDIDATES.find((m) => MediaRecorder.isTypeSupported(m));
      const recorder = new MediaRecorder(dest.stream, {
        ...(mime ? { mimeType: mime } : {}),
        audioBitsPerSecond: RECORDER_BITS_PER_SECOND,
      });
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
    const startedAt = Date.now();
    try {
      await uploadSessionRecording(token, participantId, blob, segmentIdRef.current);
      uploadedBytesRef.current = blob.size;
    } catch {
      // Next tick retries with a bigger blob.
    } finally {
      uploadBusyRef.current = false;
      const took = Date.now() - startedAt;
      nextUploadAtRef.current =
        Date.now() +
        Math.min(UPLOAD_MAX_INTERVAL_MS, Math.max(UPLOAD_MIN_INTERVAL_MS, took * UPLOAD_BACKOFF_FACTOR));
    }
  }, [participantId, token]);

  useEffect(() => {
    const timer = setInterval(() => {
      if (!finishedRef.current && Date.now() >= nextUploadAtRef.current) void uploadPartial();
    }, UPLOAD_MIN_INTERVAL_MS);
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
        await uploadSessionRecording(token, participantId, blob, segmentIdRef.current);
      } catch {
        // Best-effort: losing the recording never blocks the completion screen.
      }
    }
    setUploading(false);
    onComplete();
  }, [onComplete, participantId, teardown, token]);

  const handleDataChannelEvent = useCallback((raw: string) => {
    let event: {
      type?: string;
      delta?: string;
      response?: { metadata?: { kind?: string } | null } | null;
    } | null = null;
    try { event = JSON.parse(raw); } catch { return; }
    if (!event || typeof event.type !== "string") return;
    switch (event.type) {
      case "response.created": {
        awaitingSinceRef.current = null;
        // The sideband tags its filler responses: "ack" (spoken after an
        // answer, muted like a question but never captioned) and
        // "backchannel" (a soft "mm-hm" while the participant thinks: not
        // captioned AND the mic stays live, because the whole point is
        // that they can keep talking through it). Untagged = a question.
        const kind = event.response?.metadata?.kind ?? "question";
        sideKindRef.current = kind === "ack" || kind === "backchannel" ? kind : null;
        if (kind === "backchannel") break;
        speakingRef.current = true;
        if (micRearmTimerRef.current) {
          window.clearTimeout(micRearmTimerRef.current);
          micRearmTimerRef.current = null;
        }
        setMicLive(false);
        setVoiceState("speaking");
        break;
      }
      case "response.output_audio_transcript.delta":
        if (sideKindRef.current) break;
        if (typeof event.delta === "string") {
          if (!captionOpenRef.current) captionRef.current = "";
          captionOpenRef.current = true;
          captionRef.current += event.delta;
          setCaption(captionRef.current);
          setVoiceState("speaking");
        }
        break;
      case "response.done":
        captionOpenRef.current = false;
        if (sideKindRef.current === "backchannel") {
          sideKindRef.current = null;
          break;
        }
        // Generation is done but the speaker is still playing the buffered
        // tail; the real re-arm happens on output_audio_buffer.stopped.
        // This long timer only covers that event never arriving.
        if (!micRearmTimerRef.current) {
          micRearmTimerRef.current = window.setTimeout(() => {
            micRearmTimerRef.current = null;
            speakingRef.current = false;
            setVoiceState("idle");
            setMicLive(true);
          }, RESPONSE_DONE_FALLBACK_MS);
        }
        break;
      case "output_audio_buffer.started":
        if (sideKindRef.current === "backchannel") break;
        speakingRef.current = true;
        setMicLive(false);
        break;
      case "output_audio_buffer.stopped":
      case "output_audio_buffer.cleared":
        if (sideKindRef.current === "backchannel") {
          sideKindRef.current = null;
          break;
        }
        sideKindRef.current = null;
        // Playback has actually left the speaker: now it is safe to listen.
        speakingRef.current = false;
        setVoiceState("idle");
        if (micRearmTimerRef.current) {
          window.clearTimeout(micRearmTimerRef.current);
        }
        micRearmTimerRef.current = window.setTimeout(() => {
          micRearmTimerRef.current = null;
          setMicLive(true);
        }, MIC_REARM_DELAY_MS);
        break;
      case "input_audio_buffer.speech_started":
        setVoiceState("listening");
        break;
      case "input_audio_buffer.speech_stopped":
        setVoiceState("thinking");
        break;
      case "input_audio_buffer.committed":
        // The server now holds an answer it owes a reaction to.
        if (!micPausedRef.current) awaitingSinceRef.current = { at: Date.now(), limit: STALL_AFTER_ANSWER_MS };
        break;
      default:
        break;
    }
  }, [setMicLive]);

  const connect = useCallback(async () => {
    const seq = ++setupSeqRef.current;
    setConnState("connecting");
    try {
      const mic = await navigator.mediaDevices.getUserMedia({ audio: MIC_CONSTRAINTS });
      if (seq !== setupSeqRef.current) { mic.getTracks().forEach((tr) => tr.stop()); return; }
      micStreamRef.current = mic;

      const pc = new RTCPeerConnection();
      pcRef.current = pc;
      micSenderRef.current = pc.addTrack(mic.getAudioTracks()[0], mic);
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
      dc.onopen = () => {
        if (seq !== setupSeqRef.current) return;
        awaitingSinceRef.current = { at: Date.now(), limit: STALL_AFTER_OPEN_MS };
      };
      // The data channel closing while the interview is still running means
      // the call ended under us (idle hangup, session cap, network death).
      // Mid-conversation that is the error screen; while paused we stay on
      // the calm paused screen and let resume rebuild the call.
      dc.onclose = () => {
        if (finishedRef.current || seq !== setupSeqRef.current) return;
        deadCallRef.current = true;
        if (!micPausedRef.current) setConnState("error");
      };
      pc.onconnectionstatechange = () => {
        if (finishedRef.current || seq !== setupSeqRef.current) return;
        if (pc.connectionState === "connected") setConnState("live");
        if (pc.connectionState === "failed" || pc.connectionState === "closed") {
          deadCallRef.current = true;
          if (!micPausedRef.current) setConnState("error");
        }
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
      segmentIdRef.current = session.segmentId;
      if (seq !== setupSeqRef.current) return;
      await pc.setRemoteDescription({ type: "answer", sdp: session.sdp });
      deadCallRef.current = false;
    } catch {
      if (seq === setupSeqRef.current && !finishedRef.current) {
        teardown();
        setConnState("error");
      }
    }
  }, [handleDataChannelEvent, participantId, startRecorder, teardown, token]);

  // Full rebuild of a dead call: flush what the recorder holds to the OLD
  // segment first (segmentIdRef still points at it), then tear down and
  // dial a fresh call — new sideband, new recording segment.
  const reconnect = useCallback(async () => {
    setConnState("connecting");
    awaitingSinceRef.current = null;
    try { await uploadPartial(); } catch { /* best-effort flush */ }
    teardown();
    await connect();
    setReconnecting(false);
  }, [connect, teardown, uploadPartial]);
  useEffect(() => { reconnectRef.current = reconnect; }, [reconnect]);

  // Stall watchdog (see STALL_AFTER_ANSWER_MS): the call is up but nothing
  // has answered the participant for too long, so the sideband is gone.
  useEffect(() => {
    const timer = setInterval(() => {
      const pending = awaitingSinceRef.current;
      if (!pending || finishedRef.current || micPausedRef.current) return;
      if (Date.now() - pending.at < pending.limit) return;
      if (dcRef.current?.readyState !== "open") return; // a dead channel is handled by onclose
      awaitingSinceRef.current = null;
      if (autoReconnectsRef.current >= MAX_AUTO_RECONNECTS) {
        deadCallRef.current = true;
        setConnState("error");
        return;
      }
      autoReconnectsRef.current += 1;
      setReconnecting(true);
      void reconnectRef.current?.();
    }, STALL_CHECK_MS);
    return () => clearInterval(timer);
  }, []);

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
    const tick = async () => {
      if (finishedRef.current) return;
      try {
        const status = await getInterviewStatus(token, participantId);
        if (typeof status.question_index === "number" && status.question_index >= 0) {
          setQuestionIndex(status.question_index);
        }
        setIsFollowUp(Boolean(status.is_follow_up));
        setStimulus(status.last_stimulus ?? null);
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
    };
    // Fire once right away so a stimulus pending at connect time (or after
    // a reload) shows without waiting a full poll interval.
    void tick();
    const timer = setInterval(() => void tick(), STATUS_POLL_MS);
    return () => clearInterval(timer);
  }, [connState, finishUp, participantId, token]);

  const hideCounter = questionIndex < 0 || questionCount <= 0;
  const stateLine =
    connState === "connecting"
      ? (reconnecting ? t("realtime.reconnecting") : t("realtime.connecting"))
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
            onClick={() => void reconnect()}
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
        {/* Concept-test artefact for the current question. Same card as the
            classic flow, fed from the /status poll. */}
        {connState !== "connecting" && <StimulusCard stimulus={stimulus} />}
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
