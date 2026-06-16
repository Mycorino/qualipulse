import { useTranslation } from "react-i18next";
import { SUPPORTED_LANGUAGES } from "../i18n";
import client from "../api/client";

/**
 * Participant-facing language picker. Unlike the 2-way `LanguageSwitcher`
 * (researcher chrome, EN↔FR), this offers all six supported interview
 * languages. Rendered as a native <select> on purpose — it maps to the OS
 * picker on mobile, which is the most reliable, accessible, grandma-proof
 * control across devices.
 */

const NATIVE_LABELS: Record<string, string> = {
  en: "English",
  fr: "Français",
  de: "Deutsch",
  es: "Español",
  it: "Italiano",
  pt: "Português",
};

interface LanguagePickerProps {
  onChange?: (lang: string) => void;
  className?: string;
  style?: React.CSSProperties;
}

export default function LanguagePicker({ onChange, className, style }: LanguagePickerProps) {
  const { i18n } = useTranslation();
  const current = (i18n.language || "en").slice(0, 2);
  const value = SUPPORTED_LANGUAGES.includes(current as (typeof SUPPORTED_LANGUAGES)[number])
    ? current
    : "en";

  function handleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const lang = e.target.value;
    i18n.changeLanguage(lang);
    // changeLanguage already caches to localStorage["qp_language"] via the
    // detector config. Persist to the account too if a researcher is logged in
    // (fire-and-forget; irrelevant for anonymous participants).
    const token = localStorage.getItem("token");
    if (token) {
      client.patch("/auth/me", { preferred_language: lang }).catch(() => {});
    }
    onChange?.(lang);
  }

  return (
    <label className={`language-picker ${className ?? ""}`} style={style}>
      <span className="language-picker__icon" aria-hidden="true">🌐</span>
      <select
        value={value}
        onChange={handleChange}
        aria-label="Choose your language"
        className="language-picker__select"
      >
        {SUPPORTED_LANGUAGES.map((lng) => (
          <option key={lng} value={lng}>
            {NATIVE_LABELS[lng] ?? lng.toUpperCase()}
          </option>
        ))}
      </select>
    </label>
  );
}
