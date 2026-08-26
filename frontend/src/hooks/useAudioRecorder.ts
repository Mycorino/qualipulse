import { useState, useRef, useCallback, useEffect } from "react";

function getSupportedMimeType(): string {
  const types = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
    "audio/ogg",
  ];
  for (const type of types) {
    if (MediaRecorder.isTypeSupported(type)) return type;
  }
  return "";
}

function getFileExtension(mimeType: string): string {
  if (mimeType.includes("mp4")) return "mp4";
  if (mimeType.includes("ogg")) return "ogg";
  return "webm";
}

/** Stable sentinel codes thrown by stopRecording(). The consumer maps them to
 *  localized copy (participants can be in any of the 6 interview languages),
 *  so NO English prose ever leaves this hook. */
export const RECORDING_TOO_SHORT = "RECORDING_TOO_SHORT";
export const NO_ACTIVE_RECORDING = "NO_ACTIVE_RECORDING";
export const SILENT_RECORDING = "SILENT_RECORDING";

/** Peak level (0-255 frequency-bin average) below which a whole take is
 *  treated as a dead mic. A muted or OS-misrouted input stays at exactly 0;
 *  even faint ambient room noise clears this, so quiet speakers are safe. */
const SILENT_PEAK_THRESHOLD = 2;

/** Why a recording stopped without the participant tapping stop. */
export type RecordingInterruptReason = "hidden" | "device" | "error";

interface WakeLockLike {
  release: () => Promise<void>;
  released?: boolean;
}

export interface UseAudioRecorderOptions {
  /**
   * Fired when the recorder stops on its own (screen turned off, mic
   * unplugged, MediaRecorder error). `blob` is the partial take when enough
   * audio was captured to be worth reviewing, null otherwise.
   */
  onInterrupted?: (blob: Blob | null, reason: RecordingInterruptReason) => void;
}

export function useAudioRecorder(options: UseAudioRecorderOptions = {}) {
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const mimeTypeRef = useRef<string>("");
  const resolveRef = useRef<((blob: Blob) => void) | null>(null);
  const rejectRef = useRef<((err: Error) => void) | null>(null);
  const interruptReasonRef = useRef<RecordingInterruptReason | null>(null);
  const wakeLockRef = useRef<WakeLockLike | null>(null);
  const levelCtxRef = useRef<AudioContext | null>(null);
  const levelTimerRef = useRef<number | null>(null);
  const peakLevelRef = useRef(0);
  // Keep the latest callback without re-creating startRecording.
  const onInterruptedRef = useRef(options.onInterrupted);
  onInterruptedRef.current = options.onInterrupted;

  const releaseWakeLock = useCallback(() => {
    const lock = wakeLockRef.current;
    wakeLockRef.current = null;
    if (lock && !lock.released) lock.release().catch(() => {});
  }, []);

  const requestWakeLock = useCallback(async () => {
    try {
      const wl = (navigator as Navigator & {
        wakeLock?: { request: (type: "screen") => Promise<WakeLockLike> };
      }).wakeLock;
      if (!wl) return;
      wakeLockRef.current = await wl.request("screen");
    } catch {
      /* wake lock is best-effort (denied in low-power mode, background tabs) */
    }
  }, []);

  /** Watch the input level for the whole take so a dead mic (muted, wrong
   *  OS input device) is caught on-device instead of after a Whisper round
   *  trip. Best-effort: any AudioContext failure leaves the peak at
   *  Infinity so detection fails open and never blocks a real answer. */
  const startLevelMeter = useCallback((stream: MediaStream) => {
    peakLevelRef.current = Infinity;
    try {
      const AC =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const ctx = new AC();
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      ctx.createMediaStreamSource(stream).connect(analyser);
      levelCtxRef.current = ctx;
      peakLevelRef.current = 0;
      const data = new Uint8Array(analyser.frequencyBinCount);
      // setInterval, not rAF: rAF is throttled when the tab loses focus.
      levelTimerRef.current = window.setInterval(() => {
        analyser.getByteFrequencyData(data);
        const avg = data.reduce((a, b) => a + b, 0) / data.length;
        if (avg > peakLevelRef.current) peakLevelRef.current = avg;
      }, 150);
    } catch {
      /* no meter: peak stays Infinity, take is never flagged silent */
    }
  }, []);

  const stopLevelMeter = useCallback((): number => {
    if (levelTimerRef.current !== null) {
      window.clearInterval(levelTimerRef.current);
      levelTimerRef.current = null;
    }
    levelCtxRef.current?.close().catch(() => {});
    levelCtxRef.current = null;
    return peakLevelRef.current;
  }, []);

  /** Stop on the recorder's behalf; onstop routes the partial take to
   *  onInterrupted because nobody is awaiting stopRecording(). */
  const interrupt = useCallback((reason: RecordingInterruptReason) => {
    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state === "inactive") return;
    if (resolveRef.current) return; // a normal stop is already in flight
    interruptReasonRef.current = reason;
    try {
      recorder.stop();
    } catch {
      recorder.stream.getTracks().forEach((t) => t.stop());
      setIsRecording(false);
      releaseWakeLock();
      stopLevelMeter();
      onInterruptedRef.current?.(null, reason);
    }
  }, [releaseWakeLock, stopLevelMeter]);

  // Screen off / app switched on mobile: the OS usually suspends the mic, so
  // the take would silently go blank. Stop cleanly and keep what we have.
  useEffect(() => {
    if (!isRecording) return;
    const onVisibility = () => {
      if (document.visibilityState === "hidden") interrupt("hidden");
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [isRecording, interrupt]);

  // Never leave the wake lock or level meter held past unmount.
  useEffect(() => () => {
    releaseWakeLock();
    stopLevelMeter();
  }, [releaseWakeLock, stopLevelMeter]);

  const startRecording = useCallback(async () => {
    setError(null);
    chunksRef.current = [];
    interruptReasonRef.current = null;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = getSupportedMimeType();
      mimeTypeRef.current = mimeType;

      const recorder = new MediaRecorder(
        stream,
        mimeType ? { mimeType } : undefined
      );

      // Collect data every 250ms, ensures chunks are populated on Safari
      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      recorder.onerror = () => interrupt("error");
      stream.getTracks().forEach((track) => {
        track.onended = () => interrupt("device");
      });

      recorder.onstop = () => {
        recorder.stream.getTracks().forEach((t) => t.stop());
        setIsRecording(false);
        releaseWakeLock();
        const peakLevel = stopLevelMeter();

        const mimeType = mimeTypeRef.current || "audio/webm";
        const ext = getFileExtension(mimeType);
        const blob = new Blob(chunksRef.current, { type: mimeType });
        const named = blob.size >= 500
          ? new File([blob], `recording.${ext}`, { type: mimeType })
          : null;

        const reason = interruptReasonRef.current;
        interruptReasonRef.current = null;
        if (reason && !resolveRef.current) {
          onInterruptedRef.current?.(named, reason);
          return;
        }

        if (!named) {
          rejectRef.current?.(new Error(RECORDING_TOO_SHORT));
        } else if (peakLevel < SILENT_PEAK_THRESHOLD) {
          // The mic delivered a flat line for the whole take: nothing to
          // transcribe. The consumer routes this back to the mic test.
          rejectRef.current?.(new Error(SILENT_RECORDING));
        } else {
          resolveRef.current?.(named);
        }

        resolveRef.current = null;
        rejectRef.current = null;
      };

      mediaRecorderRef.current = recorder;
      startLevelMeter(stream);
      recorder.start(250); // timeslice: fire ondataavailable every 250ms
      setIsRecording(true);
      void requestWakeLock();
    } catch (err: unknown) {
      // Stable sentinel codes, mapped to localized copy by the consumer.
      let code = "MIC_GENERIC";
      if (err instanceof Error) {
        if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
          code = "PERMISSION_DENIED";
        } else if (err.name === "NotFoundError" || err.name === "DevicesNotFoundError") {
          code = "MIC_NOT_FOUND";
        } else if (err.name === "NotReadableError" || err.name === "TrackStartError") {
          code = "MIC_IN_USE";
        } else if (err.name === "OverconstrainedError") {
          code = "MIC_CONSTRAINTS";
        }
      }
      setError(code);
    }
  }, [interrupt, releaseWakeLock, requestWakeLock, startLevelMeter, stopLevelMeter]);

  const stopRecording = useCallback((): Promise<Blob> => {
    return new Promise((resolve, reject) => {
      const recorder = mediaRecorderRef.current;
      if (!recorder || recorder.state === "inactive") {
        reject(new Error(NO_ACTIVE_RECORDING));
        return;
      }
      resolveRef.current = resolve;
      rejectRef.current = reject;
      recorder.stop();
    });
  }, []);

  return { isRecording, error, startRecording, stopRecording };
}
