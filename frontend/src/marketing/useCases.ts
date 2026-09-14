/**
 * The three problem-led entry points on the marketing site.
 *
 * Each one is a public landing page (/use-cases/<slug>), a card on the
 * homepage, and a deep link into a project template: the "Start this study"
 * CTA goes to /signup?template=<templateId>, Signup stashes the id, and the
 * onboarding handoff (or the studies home, for a returning user) creates the
 * first study from that template instead of dropping the user on a blank
 * dashboard. Copy lives under `useCases.*` in the marketing namespace.
 *
 * Template ids must exist in backend/app/services/templates.py; the backend
 * test_templates.py pins them.
 */
export interface UseCaseDef {
  /** URL segment: /use-cases/<slug> */
  slug: string;
  /** i18n block under marketing:useCases.items.<key> and useCases.pages.<key> */
  key: "churn" | "messageTesting" | "nps";
  /** Project template id created on first sign-in. */
  templateId: string;
}

export const USE_CASES: readonly UseCaseDef[] = [
  { slug: "churn", key: "churn", templateId: "customer-churn" },
  { slug: "message-testing", key: "messageTesting", templateId: "brand-perception" },
  { slug: "nps", key: "nps", templateId: "nps-deep-dive" },
] as const;

export function findUseCase(slug: string | undefined): UseCaseDef | undefined {
  return USE_CASES.find((u) => u.slug === slug);
}

export function signupPathForTemplate(templateId: string): string {
  return `/signup?template=${encodeURIComponent(templateId)}`;
}
