import { useState, useRef, useCallback } from "react";

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

export function useAudioRecorder() {
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const mimeTypeRef = useRef<string>("");
  const resolveRef = useRef<((blob: Blob) => void) | null>(null);
  const rejectRef = useRef<((err: Error) => void) | null>(null);

  const startRecording = useCallback(async () => {
    setError(null);
    chunksRef.current = [];
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = getSupportedMimeType();
      mimeTypeRef.current = mimeType;

      const recorder = new MediaRecorder(
        stream,
        mimeType ? { mimeType } : undefined
      );

      // Collect data every 250ms — ensures chunks are populated on Safari
      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      recorder.onstop = () => {
        recorder.stream.getTracks().forEach((t) => t.stop());
        setIsRecording(false);

        const mimeType = mimeTypeRef.current || "audio/webm";
        const ext = getFileExtension(mimeType);
        const blob = new Blob(chunksRef.current, { type: mimeType });

        if (blob.size < 500) {
          rejectRef.current?.(new Error("Recording too short — please speak for at least 1 second."));
        } else {
          // Rename hint for server
          const named = new File([blob], `recording.${ext}`, { type: mimeType });
          resolveRef.current?.(named);
        }

        resolveRef.current = null;
        rejectRef.current = null;
      };

      mediaRecorderRef.current = recorder;
      recorder.start(250); // timeslice: fire ondataavailable every 250ms
      setIsRecording(true);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Could not access microphone";
      setError(message);
    }
  }, []);

  const stopRecording = useCallback((): Promise<Blob> => {
    return new Promise((resolve, reject) => {
      const recorder = mediaRecorderRef.current;
      if (!recorder || recorder.state === "inactive") {
        reject(new Error("No active recording"));
        return;
      }
      resolveRef.current = resolve;
      rejectRef.current = reject;
      recorder.stop();
    });
  }, []);

  return { isRecording, error, startRecording, stopRecording };
}
