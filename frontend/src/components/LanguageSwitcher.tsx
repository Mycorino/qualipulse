import { useTranslation } from "react-i18next";

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
  }

  const isDark = variant === "dark";

  return (
    <button
      onClick={toggle}
      aria-label={current === "fr" ? "Switch to English" : "Passer en français"}
      style={{
        background: isDark ? "rgba(255,255,255,0.12)" : "rgba(0,0,0,0.06)",
        border: isDark ? "1px solid rgba(255,255,255,0.25)" : "1px solid rgba(0,0,0,0.15)",
        borderRadius: "20px",
        cursor: "pointer",
        fontSize: "12px",
        fontWeight: 700,
        letterSpacing: "0.05em",
        padding: "0 14px",
        color: isDark ? "#ffffff" : "#374151",
        minHeight: "44px",
        minWidth: "52px",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        transition: "background 0.15s, border-color 0.15s",
        flexShrink: 0,
        ...style,
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLButtonElement).style.background = isDark
          ? "rgba(255,255,255,0.22)"
          : "rgba(0,0,0,0.11)";
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLButtonElement).style.background = isDark
          ? "rgba(255,255,255,0.12)"
          : "rgba(0,0,0,0.06)";
      }}
    >
      {next.toUpperCase()}
    </button>
  );
}
