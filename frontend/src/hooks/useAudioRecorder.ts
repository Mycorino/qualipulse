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
      onInterruptedRef.current?.(null, reason);
    }
  }, [releaseWakeLock]);

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

  // Never leave the wake lock held past unmount.
  useEffect(() => () => releaseWakeLock(), [releaseWakeLock]);

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
        } else {
          resolveRef.current?.(named);
        }

        resolveRef.current = null;
        rejectRef.current = null;
      };

      mediaRecorderRef.current = recorder;
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
  }, [interrupt, releaseWakeLock, requestWakeLock]);

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
