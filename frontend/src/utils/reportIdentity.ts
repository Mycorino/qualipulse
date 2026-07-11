import type { CSSProperties } from "react";

/**
 * Report colour identities — the same three families the PDF exports use
 * (backend services/report_export.py `_PALETTES`): qualitative interview
 * findings are forest green, quantitative survey results are ink blue, and
 * mixed-methods artifacts are bordeaux.
 *
 * The interview Analysis tab and the survey Results tab are interactive
 * *workbenches* (annotate / filter / refine / bridge-to-interview), so we
 * don't embed the static PDF there. Instead we give each surface its
 * report identity by scope-overriding the `--brand-*` scale on the report
 * content wrapper. Because `--viz-positive` is defined as `var(--brand-500)`,
 * this cascades into the charts too — promoter/positive bars follow the
 * family colour while NPS detractor-red and passive-grey (hard-coded viz
 * tokens) stay put, exactly like the PDF's NPS band. Neutral action buttons
 * (btn-secondary / btn-ai) don't key off `--brand`, so they're untouched.
 */

// Forest green — qualitative interview findings. `--primary*` is overridden
// too so report links/accents that key off the primary token follow the
// family colour, not the app indigo.
export const QUAL_BRAND_SCALE = {
  "--brand-50": "#eef4ef",
  "--brand-100": "#dce8e0",
  "--brand-300": "#7fae95",
  "--brand-400": "#4e8f6f",
  "--brand-500": "#2f7a57",
  "--brand-600": "#1d5c3f",
  "--brand-700": "#16452f",
  "--brand-800": "#10382a",
  "--primary": "#2f7a57",
  "--primary-hover": "#1d5c3f",
} as CSSProperties;

// Ink blue — quantitative survey results.
export const QUANT_BRAND_SCALE = {
  "--brand-50": "#edf2f8",
  "--brand-100": "#dbe7f1",
  "--brand-300": "#8fb0d0",
  "--brand-400": "#5a89b8",
  "--brand-500": "#2f6ba0",
  "--brand-600": "#1e4a73",
  "--brand-700": "#163a5c",
  "--brand-800": "#0f2c46",
  "--primary": "#2f6ba0",
  "--primary-hover": "#1e4a73",
} as CSSProperties;
