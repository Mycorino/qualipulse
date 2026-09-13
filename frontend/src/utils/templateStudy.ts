import { getTemplate } from "../api/templates";
import { createProject, type ProjectResponse } from "../api/projects";
import { clearPendingTemplate, getPendingTemplate } from "./pendingTemplate";

/** Researcher UI language → participant-facing project language. */
export function projectLanguageFor(uiLanguage: string | undefined): "en" | "fr" {
  return (uiLanguage || "en").toLowerCase().startsWith("fr") ? "fr" : "en";
}

/**
 * Create an interview round pre-filled from a project template: objective,
 * audience, screener and the full guide. Its Study auto-creates (Decision 8),
 * so the caller can drop straight into /projects/<id>?tab=setup where the
 * copilot picks up with a populated guide instead of a blank one.
 */
export async function createProjectFromTemplate(
  templateId: string,
  uiLanguage: string | undefined,
): Promise<ProjectResponse> {
  const language = projectLanguageFor(uiLanguage);
  const tpl = await getTemplate(templateId, language);
  return createProject({
    name: tpl.name,
    language,
    interview_duration_minutes: tpl.duration_minutes,
    research_objective: tpl.research_objective,
    target_customer_description: tpl.target_audience,
    questions: tpl.questions.map((q) => ({
      section_index: q.section_index,
      section_title: q.section_title,
      question_index: q.question_index,
      main_question: q.main_question,
      interview_notes: q.interview_notes,
      desired_learning: q.desired_learning,
    })),
    screening_questions: tpl.screening_questions,
  });
}

function isEmailUnverifiedError(err: unknown): boolean {
  const resp = (err as { response?: { status?: number; data?: { detail?: { code?: string } } } })?.response;
  return resp?.status === 403 && resp?.data?.detail?.code === "email_unverified";
}

/**
 * If a marketing deep link stashed a template, create the study from it and
 * return the new project id. Returns null when there was nothing pending or
 * creation failed, so callers fall through to their normal landing.
 *
 * The stash is cleared on success and on any hard failure (unknown template,
 * plan limit, network): a failed attempt must not retry on every page load.
 * The one exception is ``email_unverified``: study creation is gated on a
 * verified address, and a password signup reaches the onboarding handoff
 * before clicking the verification link. The stash survives that so the
 * studies home can create the study the first time the user lands there
 * verified. The TTL in pendingTemplate.ts bounds how long it can wait.
 */
export async function consumePendingTemplateStudy(
  uiLanguage: string | undefined,
): Promise<string | null> {
  const templateId = getPendingTemplate();
  if (!templateId) return null;
  try {
    const project = await createProjectFromTemplate(templateId, uiLanguage);
    clearPendingTemplate();
    return project.id;
  } catch (err) {
    if (!isEmailUnverifiedError(err)) clearPendingTemplate();
    return null;
  }
}
