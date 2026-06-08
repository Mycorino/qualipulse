import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

interface AudioClipProps {
  src: string;
  label: string;
  onTimeUpdate?: (e: React.SyntheticEvent<HTMLAudioElement>) => void;
  onEnded?: (e: React.SyntheticEvent<HTMLAudioElement>) => void;
  /**
   * Visual treatment of the progress track.
   * - "bar" (default): horizontal progress bar — used inside transcripts and turns.
   * - "waveform": procedural waveform bars — used inside VerbatimCard on the
   *   quanti surface. The waveform shape is deterministic per `src` so the
   *   same clip always renders identically.
   */
  variant?: "bar" | "waveform";
  /** Number of bars in the waveform variant. Defaults to 48. */
  waveformBars?: number;
}

/**
 * Deterministic pseudo-waveform — a stable hash of the src produces a
 * varying amplitude pattern so each clip looks distinct without requiring
 * real Web Audio API decoding (which is expensive on first paint).
 *
 * Real waveform decoding will land in a follow-up that decodes the audio
 * once via OfflineAudioContext and caches the peak buffer per src.
 */
function buildWaveformAmplitudes(src: string, n: number): number[] {
  let h = 2166136261;
  for (let i = 0; i < src.length; i++) {
    h ^= src.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  const amps: number[] = [];
  for (let i = 0; i < n; i++) {
    h ^= h << 13;
    h ^= h >>> 17;
    h ^= h << 5;
    const r = ((h >>> 0) % 1000) / 1000;
    // Bell-shape envelope so the middle is louder than the edges, like
    // most natural speech clips end up looking.
    const envelope = Math.sin((Math.PI * (i + 0.5)) / n);
    const amp = 0.18 + 0.82 * r * envelope;
    amps.push(amp);
  }
  return amps;
}

// Module-level registry: only one AudioClip plays at a time. When one starts,
// any other currently-playing element is paused.
let currentlyPlaying: HTMLAudioElement | null = null;

function formatTime(s: number): string {
  if (!isFinite(s) || s < 0) return "0:00";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

export const AudioClip = forwardRef<HTMLAudioElement | null, AudioClipProps>(
  ({ src, label, onTimeUpdate, onEnded, variant = "bar", waveformBars = 48 }, ref) => {
    const { t } = useTranslation("shell");
    const audioRef = useRef<HTMLAudioElement | null>(null);
    const [playing, setPlaying] = useState(false);
    const [duration, setDuration] = useState(0);
    const [currentTime, setCurrentTime] = useState(0);
    const [errored, setErrored] = useState(false);
    // Tracks our progress through the seek-to-end workaround for WebM files
    // recorded by MediaRecorder (which report duration: Infinity until played).
    const durationProbeRef = useRef<"idle" | "seeking" | "done">("idle");

    useImperativeHandle(ref, () => audioRef.current as HTMLAudioElement, []);

    useEffect(() => {
      setErrored(false);
      setPlaying(false);
      setCurrentTime(0);
      setDuration(0);
      durationProbeRef.current = "idle";
    }, [src]);

    const togglePlay = () => {
      const a = audioRef.current;
      if (!a) return;
      if (a.paused) {
        if (currentlyPlaying && currentlyPlaying !== a) {
          currentlyPlaying.pause();
        }
        a.play().catch(() => setErrored(true));
      } else {
        a.pause();
      }
    };

    const handleSeek = (e: React.MouseEvent<HTMLDivElement>) => {
      const a = audioRef.current;
      if (!a || !duration) return;
      const rect = e.currentTarget.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      a.currentTime = ratio * duration;
      setCurrentTime(a.currentTime);
    };

    const handleKey = (e: React.KeyboardEvent<HTMLDivElement>) => {
      const a = audioRef.current;
      if (!a) return;
      if (e.key === " " || e.key === "Enter") {
        e.preventDefault();
        togglePlay();
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        a.currentTime = Math.max(0, a.currentTime - 5);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        a.currentTime = Math.min(duration || a.duration || 0, a.currentTime + 5);
      } else if (e.key === "Home") {
        e.preventDefault();
        a.currentTime = 0;
      } else if (e.key === "End" && duration) {
        e.preventDefault();
        a.currentTime = duration;
      }
    };

    // For the waveform variant we keep the shell visible even on load
    // failure — a missing clip in a list shouldn't reflow the layout.
    // The bar variant retains the original error fallback for transcript views.
    if (errored && variant === "bar") {
      return (
        <div className="audio-clip audio-clip--error" aria-label={label}>
          {t("audio.unavailable")}
        </div>
      );
    }

    const progress = duration > 0 ? (currentTime / duration) * 100 : 0;
    const amps = variant === "waveform" ? buildWaveformAmplitudes(src, waveformBars) : null;

    return (
      <div
        className={`audio-clip${playing ? " audio-clip--playing" : ""}${variant === "waveform" ? " audio-clip--waveform" : ""}${errored ? " audio-clip--errored" : ""}`}
        role="group"
        aria-label={t("audio.labelWithDuration", { label, duration: formatTime(duration) })}
        onKeyDown={handleKey}
        tabIndex={0}
      >
        <button
          type="button"
          className="audio-clip__play"
          onClick={togglePlay}
          disabled={errored}
          aria-label={playing ? t("audio.pause") : t("audio.play")}
          aria-pressed={playing}
        >
          {playing ? (
            <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
              <rect x="2.5" y="2" width="2.5" height="8" rx="0.5" fill="currentColor" />
              <rect x="7" y="2" width="2.5" height="8" rx="0.5" fill="currentColor" />
            </svg>
          ) : (
            <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
              <path d="M3 1.8 L9.5 6 L3 10.2 Z" fill="currentColor" />
            </svg>
          )}
        </button>
        {amps ? (
          <div
            className="audio-clip__track audio-clip__track--waveform"
            onClick={handleSeek}
            role="slider"
            aria-label={t("audio.seek")}
            aria-valuemin={0}
            aria-valuemax={Math.round(duration)}
            aria-valuenow={Math.round(currentTime)}
          >
            <svg
              className="audio-clip__waveform"
              viewBox={`0 0 ${amps.length * 3} 32`}
              preserveAspectRatio="none"
              aria-hidden="true"
            >
              {amps.map((a, i) => {
                const h = Math.max(2, a * 32);
                const y = (32 - h) / 2;
                const fillProgress = ((i + 0.5) / amps.length) * 100;
                const filled = fillProgress <= progress;
                return (
                  <rect
                    key={i}
                    x={i * 3}
                    y={y}
                    width={2}
                    height={h}
                    rx={1}
                    className={filled ? "audio-clip__bar audio-clip__bar--filled" : "audio-clip__bar"}
                  />
                );
              })}
            </svg>
          </div>
        ) : (
          <div
            className="audio-clip__track"
            onClick={handleSeek}
            role="slider"
            aria-label={t("audio.seek")}
            aria-valuemin={0}
            aria-valuemax={Math.round(duration)}
            aria-valuenow={Math.round(currentTime)}
          >
            <div className="audio-clip__progress" style={{ width: `${progress}%` }} />
          </div>
        )}
        <span className="audio-clip__time">{formatTime(duration - currentTime)}</span>
        <audio
          ref={audioRef}
          src={src}
          preload="metadata"
          onPlay={(e) => {
            currentlyPlaying = e.currentTarget as HTMLAudioElement;
            setPlaying(true);
          }}
          onPause={(e) => {
            if (currentlyPlaying === e.currentTarget) currentlyPlaying = null;
            setPlaying(false);
          }}
          onEnded={(e) => {
            if (currentlyPlaying === e.currentTarget) currentlyPlaying = null;
            setPlaying(false);
            setCurrentTime(0);
            onEnded?.(e);
          }}
          onLoadedMetadata={(e) => {
            const a = e.currentTarget as HTMLAudioElement;
            // WebM files recorded by MediaRecorder report Infinity until we
            // seek to the end — then `durationchange` fires with the real value.
            if (!isFinite(a.duration) && durationProbeRef.current === "idle") {
              durationProbeRef.current = "seeking";
              a.currentTime = 1e101;
            } else {
              setDuration(a.duration);
            }
          }}
          onDurationChange={(e) => {
            const a = e.currentTarget as HTMLAudioElement;
            if (isFinite(a.duration)) {
              setDuration(a.duration);
              if (durationProbeRef.current === "seeking") {
                a.currentTime = 0;
                durationProbeRef.current = "done";
              }
            }
          }}
          onTimeUpdate={(e) => {
            // Suppress UI updates while the seek-to-end probe is in flight,
            // otherwise the scrubber jumps to the end before snapping back.
            if (durationProbeRef.current !== "seeking") {
              setCurrentTime((e.currentTarget as HTMLAudioElement).currentTime);
            }
            onTimeUpdate?.(e);
          }}
          onError={() => setErrored(true)}
        />
      </div>
    );
  }
);

AudioClip.displayName = "AudioClip";
