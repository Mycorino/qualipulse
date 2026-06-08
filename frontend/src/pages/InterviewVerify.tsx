import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { verifyInterviewToken } from "../api/interviews";

export default function InterviewVerify() {
  const { t } = useTranslation("shell");
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    verifyInterviewToken(token)
      .then(({ session_token, link_token }) => {
        // Store session so Interview.tsx can pick it up
        sessionStorage.setItem(`interview_session_${link_token}`, session_token);
        navigate(`/i/${link_token}`, { replace: true });
      })
      .catch(() => {
        setError(t("interviewVerify.expiredMessage"));
      });
  }, [token, navigate, t]);

  if (error) {
    return (
      <div className="interview-page">
        <div
          className="interview-container"
          style={{ textAlign: "center", paddingTop: 60 }}
        >
          <div
            style={{
              fontSize: 22,
              fontWeight: 700,
              color: "var(--primary, #6366f1)",
              marginBottom: 32,
            }}
          >
            QualiPulse
          </div>
          <div style={{ fontSize: 48, marginBottom: 16 }}>⏰</div>
          <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 10 }}>
            {t("interviewVerify.expiredTitle")}
          </h1>
          <p
            style={{
              color: "var(--text-secondary, #6b7280)",
              fontSize: 15,
              maxWidth: 380,
              margin: "0 auto",
            }}
          >
            {error}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="interview-page">
      <div className="interview-container" style={{ textAlign: "center" }}>
        <p className="muted-text">{t("interviewVerify.verifying")}</p>
      </div>
    </div>
  );
}
