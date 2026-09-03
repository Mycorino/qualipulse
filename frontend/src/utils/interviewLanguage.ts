import { SUPPORTED_LANGUAGES } from "../i18n";

/**
 * Interview-language precedence helpers.
 *
 * Two storage slots, on purpose:
 *
 * - `qp_interview_lang` (localStorage) — the last interview language we know
 *   about on this device. Survives visits, used as the pre-fetch guess so the
 *   study name comes back localized on the very first request.
 * - `qp_interview_lang_pick` (sessionStorage) — the language chosen for THIS
 *   visit, either by the participant using the picker or by the backend once
 *   the interview is running. It outranks anything the server remembers about
 *   the person: a returning panelist whose profile says `en` but who selects
 *   Français gets a French interview, not their old default.
 *
 * Every access is guarded — participants open these links inside in-app
 * webviews (Instagram, TikTok) and private windows where storage throws.
 */

const PERSISTED_KEY = "qp_interview_lang";
const SESSION_PICK_KEY = "qp_interview_lang_pick";

/** Normalise to a supported 2-letter code, or null if we can't run it. */
export function normaliseInterviewLang(lang?: string | null): string | null {
  const code = (lang || "").slice(0, 2).toLowerCase();
  return (SUPPORTED_LANGUAGES as readonly string[]).includes(code) ? code : null;
}

export function getPersistedInterviewLang(): string | null {
  try {
    return normaliseInterviewLang(localStorage.getItem(PERSISTED_KEY));
  } catch {
    return null;
  }
}

/** The language chosen for this visit, if any. Beats the stored profile. */
export function getInterviewLangPick(): string | null {
  try {
    return normaliseInterviewLang(sessionStorage.getItem(SESSION_PICK_KEY));
  } catch {
    return null;
  }
}

/** Remember a language for this device without claiming it was chosen. */
export function rememberInterviewLang(lang?: string | null): string | null {
  const code = normaliseInterviewLang(lang);
  if (!code) return null;
  try {
    localStorage.setItem(PERSISTED_KEY, code);
  } catch { /* storage unavailable — in-memory i18n state still holds */ }
  return code;
}

/**
 * Record an explicit choice for this visit (participant pick, magic-link
 * `?lang`, or the backend-authoritative language of a running interview).
 */
export function setInterviewLangPick(lang?: string | null): string | null {
  const code = rememberInterviewLang(lang);
  if (!code) return null;
  try {
    sessionStorage.setItem(SESSION_PICK_KEY, code);
  } catch { /* ditto */ }
  return code;
}
