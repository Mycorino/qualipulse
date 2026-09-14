/**
 * Share tokens of the example study's report, one per language, embedded
 * under the evidence section of the homepage ("open the real report").
 *
 * They belong to a house account whose demo study was seeded in that
 * language; the report is read-only and public by design (share tokens are
 * the product's own sharing mechanism). Rotating a token here is the only
 * change needed if the house account is ever re-seeded.
 *
 * Empty string = no report for that language, the button is not rendered.
 */
export const DEMO_REPORT_TOKENS: Record<"en" | "fr", string> = {
  // TODO(prod): replace with the production house account's tokens before
  // merging. These are the local preview database's tokens, so the panel
  // works on localhost:5196 but will 404 in production until swapped.
  en: "3isxN5_h_-yGgLmiagZOgtmYcfu1yKkDovMb4ldnaZI",
  fr: "emgeAP4rW_IPKrgiOquzzWNZuq4LmyORiD-ounB0oFE",
};

export function demoReportToken(language: string | undefined): string {
  return (language || "en").toLowerCase().startsWith("fr") ? DEMO_REPORT_TOKENS.fr : DEMO_REPORT_TOKENS.en;
}
