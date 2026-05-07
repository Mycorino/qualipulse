import { AudioClip } from "./AudioClip";

/**
 * VerbatimCard — the signature interaction.
 *
 * A pull-quote with optional audio playback and segment attribution. Defaults
 * to segment-only attribution (e.g. "PM · 31–40 · UK") for privacy; pass an
 * explicit `name` only when the participant has consented to being identified.
 *
 * Reuses the existing AudioClip component (frontend/src/components/AudioClip.tsx)
 * for playback. When no `audioSrc` is provided, the card degrades gracefully to
 * a text-only blockquote with the brand-tinted left border.
 */
interface VerbatimCardProps {
  /** The verbatim text. Always shown verbatim — never paraphrased. */
  quote: string;
  /** Optional URL to the source audio clip. */
  audioSrc?: string;
  /** Segment chips: role, age range, country, etc. Composable. */
  segments?: string[];
  /** Optional explicit name (only when consented). */
  name?: string;
  /** Compact density for use inside chart-card sidebars. */
  compact?: boolean;
}

export function VerbatimCard({ quote, audioSrc, segments, name, compact }: VerbatimCardProps) {
  return (
    <figure className={`verbatim-card${compact ? " verbatim-card--compact" : ""}`}>
      <blockquote className="verbatim-card__quote">{quote}</blockquote>
      {audioSrc && (
        <div className="verbatim-card__audio">
          <AudioClip
            src={audioSrc}
            label={`Verbatim audio${name ? ` — ${name}` : ""}`}
            variant="waveform"
          />
        </div>
      )}
      {(segments?.length || name) && (
        <figcaption className="verbatim-card__attribution">
          {name && <span style={{ fontWeight: "var(--weight-medium)", color: "var(--text-secondary)" }}>{name}</span>}
          {segments?.map((seg) => (
            <span key={seg} className="verbatim-card__segment-chip">
              {seg}
            </span>
          ))}
        </figcaption>
      )}
    </figure>
  );
}
