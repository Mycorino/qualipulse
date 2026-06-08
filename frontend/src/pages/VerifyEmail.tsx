import { useState, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { verifyEmail } from "../api/auth";

export default function VerifyEmail() {
  const { t } = useTranslation("shell");
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setErrorMsg(t("verifyEmail.noToken"));
      return;
    }

    verifyEmail(token)
      .then(() => setStatus("success"))
      .catch((err) => {
        setStatus("error");
        const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        setErrorMsg(detail || t("verifyEmail.invalidOrExpired"));
      });
  }, [token, t]);

  return (
    <div className="auth-page">
      <div className="auth-card" style={{ textAlign: "center" }}>
        <div className="auth-logo">QualiPulse</div>

        {status === "loading" && (
          <>
            <h1 className="auth-title">{t("verifyEmail.verifyingTitle")}</h1>
            <p className="auth-subtitle">{t("verifyEmail.verifyingSubtitle")}</p>
          </>
        )}

        {status === "success" && (
          <>
            <div style={{ fontSize: 48, marginBottom: 16 }}>✓</div>
            <h1 className="auth-title">{t("verifyEmail.successTitle")}</h1>
            <p className="auth-subtitle">
              {t("verifyEmail.successSubtitle")}
            </p>
            <Link
              to="/dashboard"
              className="btn btn-primary btn-block"
              style={{ textAlign: "center", textDecoration: "none", marginTop: 24 }}
            >
              {t("verifyEmail.goToDashboard")}
            </Link>
          </>
        )}

        {status === "error" && (
          <>
            <div style={{ fontSize: 48, marginBottom: 16 }}>✕</div>
            <h1 className="auth-title">{t("verifyEmail.failedTitle")}</h1>
            <p className="auth-subtitle">{errorMsg}</p>
            <Link
              to="/dashboard"
              className="btn btn-primary btn-block"
              style={{ textAlign: "center", textDecoration: "none", marginTop: 24 }}
            >
              {t("verifyEmail.goToDashboard")}
            </Link>
            <p className="auth-footer">
              {t("verifyEmail.resendHint")}
            </p>
          </>
        )}
      </div>
    </div>
  );
}
