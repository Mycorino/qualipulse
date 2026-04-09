import { useTranslation } from "react-i18next";

interface LanguageSwitcherProps {
  style?: React.CSSProperties;
}

export default function LanguageSwitcher({ style }: LanguageSwitcherProps) {
  const { i18n } = useTranslation();
  const current = i18n.language?.startsWith("fr") ? "fr" : "en";

  function toggle() {
    const next = current === "fr" ? "en" : "fr";
    i18n.changeLanguage(next);
  }

  return (
    <button
      onClick={toggle}
      aria-label={current === "fr" ? "Switch to English" : "Passer en français"}
      style={{
        background: "none",
        border: "1px solid var(--border)",
        borderRadius: "6px",
        cursor: "pointer",
        fontSize: "13px",
        fontWeight: 500,
        padding: "4px 10px",
        color: "var(--text-secondary, #6b7280)",
        lineHeight: 1.4,
        minHeight: 30,
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        ...style,
      }}
    >
      {current === "fr" ? "EN" : "FR"}
    </button>
  );
}
