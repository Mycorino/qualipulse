import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth, setCachedOnboarded } from "../hooks/useAuth";

// Reads tokens that the backend bounced back via URL fragment (so they
// don't appear in server logs / Referer headers), persists them, then
// routes the user to /welcome (new account / not onboarded) or to the
// `next` path encoded in the state (typically /dashboard).
export default function GoogleFinish() {
  const navigate = useNavigate();
  const { saveToken } = useAuth();
  const { t } = useTranslation("shell");
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;

    const hash = window.location.hash.startsWith("#")
      ? window.location.hash.slice(1)
      : window.location.hash;
    const params = new URLSearchParams(hash);
    const access = params.get("access_token");
    const refresh = params.get("refresh_token") || undefined;
    const onboarded = params.get("onboarded") === "1";
    const next = params.get("next") || "/dashboard";

    if (!access) {
      navigate("/login?google_error=missing_token", { replace: true });
      return;
    }

    // Fresh Google accounts get a placeholder company name derived from the
    // email local-part. Flag it so /welcome starts on the "Your company"
    // step where the user can correct it (Welcome.tsx consumes this flag).
    if (params.get("is_new") === "1") {
      localStorage.setItem("qp_google_new_signup", "1");
    }

    saveToken(access, refresh);
    setCachedOnboarded(onboarded);
    // Clear the fragment so the tokens aren't left in browser history.
    window.history.replaceState(null, "", window.location.pathname);
    navigate(onboarded ? next : "/welcome", { replace: true });
  }, [navigate, saveToken]);

  return (
    <div className="auth-page">
      <div className="auth-card" style={{ textAlign: "center" }}>
        <p>{t("googleFinish.signingIn")}</p>
      </div>
    </div>
  );
}
