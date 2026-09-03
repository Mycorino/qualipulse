import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { verifyInterviewToken } from "../api/interviews";
import { normaliseInterviewLang, setInterviewLangPick } from "../utils/interviewLanguage";

export default function InterviewVerify() {
  const { t, i18n } = useTranslation("shell");
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  // The chosen interview language is carried in the magic-link URL. Apply it
  // immediately — before redirecting to /i — so the pre-interview screens
  // (email/consent/questionnaire/screening) render natively even in a fresh
  // webview that never saw the original tab's language pick.
  const urlLang = normaliseInterviewLang(new URLSearchParams(window.location.search).get("lang"));
  useEffect(() => {
    if (urlLang) {
      setInterviewLangPick(urlLang);
      if (i18n.language?.slice(0, 2) !== urlLang) i18n.changeLanguage(urlLang);
    }
  }, [urlLang, i18n]);

  useEffect(() => {
    if (!token) return;
    verifyInterviewToken(token)
      .then(({ session_token, link_token, profile_complete, first_name, preferred_language }) => {
        // Store session so Interview.tsx can pick it up
        sessionStorage.setItem(`interview_session_${link_token}`, session_token);
        // Stash returning-participant meta so Interview.tsx can skip the
        // profiling questionnaire and restore the participant's language.
        // The URL lang is the language they chose for THIS interview, so it
        // outranks whatever their panel profile remembers; the profile value
        // only fills in when the link carried no choice.
        sessionStorage.setItem(
          `interview_profile_meta_${link_token}`,
          JSON.stringify({ profile_complete, first_name, preferred_language: urlLang || preferred_language || null })
        );
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
