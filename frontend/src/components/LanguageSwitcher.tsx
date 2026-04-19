import { useTranslation } from "react-i18next";
import client from "../api/client";

interface LanguageSwitcherProps {
  variant?: "light" | "dark";
  style?: React.CSSProperties;
}

export default function LanguageSwitcher({ variant = "light", style }: LanguageSwitcherProps) {
  const { i18n } = useTranslation();
  const current = i18n.language?.startsWith("fr") ? "fr" : "en";
  const next = current === "fr" ? "en" : "fr";

  function toggle() {
    i18n.changeLanguage(next);
    // Persist to backend if logged in (fire-and-forget, ignore errors)
    const token = localStorage.getItem("token");
    if (token) {
      client.patch("/auth/me", { preferred_language: next }).catch(() => {});
    }
  }

  const className =
    variant === "dark" ? "lang-switcher lang-switcher--dark" : "lang-switcher";

  return (
    <button
      onClick={toggle}
      aria-label={current === "en" ? "Passer en français" : "Switch to English"}
      className={className}
      style={style}
    >
      {next.toUpperCase()}
    </button>
  );
}
