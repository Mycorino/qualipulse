// Participant-facing branding helpers.
//
// Fonts are a curated set of SYSTEM font stacks — participants never download
// an external font (no CSP exception, no FOUT, no tracking request).
export const BRAND_FONT_STACKS: Record<string, string> = {
  system:
    '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  humanist: 'Seravek, "Gill Sans Nova", Ubuntu, Calibri, "Segoe UI", Verdana, sans-serif',
  serif: 'Georgia, "Times New Roman", Times, serif',
  elegant: '"Palatino Linotype", Palatino, "Book Antiqua", "URW Palladio L", Georgia, serif',
};

export const BRAND_FONT_LABELS: Record<string, string> = {
  system: "Modern (default)",
  humanist: "Humanist",
  serif: "Classic serif",
  elegant: "Elegant serif",
};

export interface ParticipantBranding {
  mode: "standard" | "branded" | "anonymous";
  primary_color?: string | null;
  font?: string | null;
}

/** Mix a #rrggbb color toward white (pct > 0) or black (pct < 0). */
export function shadeColor(hex: string, pct: number): string {
  const m = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!m) return hex;
  const num = parseInt(m[1], 16);
  const target = pct > 0 ? 255 : 0;
  const p = Math.min(Math.abs(pct), 100) / 100;
  const mix = (c: number) => Math.round(c + (target - c) * p);
  const r = mix((num >> 16) & 0xff);
  const g = mix((num >> 8) & 0xff);
  const b = mix(num & 0xff);
  return `#${((1 << 24) | (r << 16) | (g << 8) | b).toString(16).slice(1)}`;
}

/**
 * Apply a project's branded theme by overriding the design-system CSS
 * variables on :root. Returns a cleanup that restores the previous values —
 * call it on unmount so SPA navigation never leaks the participant theme
 * into the researcher app.
 */
export function applyParticipantBranding(branding: ParticipantBranding | undefined | null): () => void {
  if (!branding || branding.mode !== "branded") return () => {};
  const root = document.documentElement;
  const prev = new Map<string, string>();
  const set = (key: string, value: string) => {
    prev.set(key, root.style.getPropertyValue(key));
    root.style.setProperty(key, value);
  };

  const color = branding.primary_color;
  if (color && /^#[0-9a-f]{6}$/i.test(color)) {
    set("--brand-400", shadeColor(color, 20));
    set("--brand-500", color);
    set("--brand-600", shadeColor(color, -15));
    set("--brand-50", shadeColor(color, 94));
    set("--brand-100", shadeColor(color, 88));
    set("--primary", color);
    set("--primary-hover", shadeColor(color, -15));
  }

  const stack = branding.font ? BRAND_FONT_STACKS[branding.font] : undefined;
  if (stack) set("--brand-font-family", stack);

  return () => {
    prev.forEach((value, key) => {
      if (value) root.style.setProperty(key, value);
      else root.style.removeProperty(key);
    });
  };
}
