import { useTranslation } from "react-i18next";

export default function ImpersonationBanner() {
  const { t } = useTranslation("shell");
  const active = localStorage.getItem("impersonation") === "true";
  if (!active) return null;

  const name = localStorage.getItem("impersonation_name") || "";
  const email = localStorage.getItem("impersonation_email") || "";

  function handleExit() {
    localStorage.removeItem("token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("impersonation");
    localStorage.removeItem("impersonation_name");
    localStorage.removeItem("impersonation_email");
    window.close();
    // If window.close() is blocked (not opened by script), redirect
    window.location.href = "/admin";
  }

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        zIndex: 9999,
        background: "#d97706",
        color: "#fff",
        padding: "6px 16px",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 16,
        fontSize: 13,
        fontWeight: 500,
      }}
    >
      <span>
        {t("impersonation.viewingAs")} <strong>{name}</strong> — {email}
      </span>
      <button
        onClick={handleExit}
        style={{
          background: "rgba(255,255,255,0.2)",
          border: "1px solid rgba(255,255,255,0.4)",
          color: "#fff",
          borderRadius: 4,
          padding: "3px 12px",
          fontSize: 12,
          fontWeight: 600,
          cursor: "pointer",
        }}
      >
        {t("impersonation.exit")}
      </button>
    </div>
  );
}
