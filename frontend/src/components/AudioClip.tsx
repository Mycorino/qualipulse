import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";

interface AudioClipProps {
  src: string;
  label: string;
  onTimeUpdate?: (e: React.SyntheticEvent<HTMLAudioElement>) => void;
  onEnded?: (e: React.SyntheticEvent<HTMLAudioElement>) => void;
}

function formatTime(s: number): string {
  if (!isFinite(s) || s < 0) return "0:00";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

export const AudioClip = forwardRef<HTMLAudioElement | null, AudioClipProps>(
  ({ src, label, onTimeUpdate, onEnded }, ref) => {
    const audioRef = useRef<HTMLAudioElement | null>(null);
    const [playing, setPlaying] = useState(false);
    const [duration, setDuration] = useState(0);
    const [currentTime, setCurrentTime] = useState(0);
    const [errored, setErrored] = useState(false);

    useImperativeHandle(ref, () => audioRef.current as HTMLAudioElement, []);

    useEffect(() => {
      setErrored(false);
      setPlaying(false);
      setCurrentTime(0);
      setDuration(0);
    }, [src]);

    const togglePlay = () => {
      const a = audioRef.current;
      if (!a) return;
      if (a.paused) {
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

    if (errored) {
      return (
        <div className="audio-clip audio-clip--error" aria-label={label}>
          Audio unavailable
        </div>
      );
    }

    const progress = duration > 0 ? (currentTime / duration) * 100 : 0;

    return (
      <div
        className={`audio-clip${playing ? " audio-clip--playing" : ""}`}
        role="group"
        aria-label={`${label}, ${formatTime(duration)}`}
        onKeyDown={handleKey}
        tabIndex={0}
      >
        <button
          type="button"
          className="audio-clip__play"
          onClick={togglePlay}
          aria-label={playing ? "Pause" : "Play"}
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
        <div
          className="audio-clip__track"
          onClick={handleSeek}
          role="slider"
          aria-label="Seek"
          aria-valuemin={0}
          aria-valuemax={Math.round(duration)}
          aria-valuenow={Math.round(currentTime)}
        >
          <div className="audio-clip__progress" style={{ width: `${progress}%` }} />
        </div>
        <span className="audio-clip__time">{formatTime(duration - currentTime)}</span>
        <audio
          ref={audioRef}
          src={src}
          preload="metadata"
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={(e) => {
            setPlaying(false);
            setCurrentTime(0);
            onEnded?.(e);
          }}
          onLoadedMetadata={(e) => setDuration((e.currentTarget as HTMLAudioElement).duration)}
          onTimeUpdate={(e) => {
            setCurrentTime((e.currentTarget as HTMLAudioElement).currentTime);
            onTimeUpdate?.(e);
          }}
          onError={() => setErrored(true)}
        />
      </div>
    );
  }
);

AudioClip.displayName = "AudioClip";
