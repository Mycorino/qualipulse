import { useState, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { verifyEmail } from "../api/auth";

export default function VerifyEmail() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setErrorMsg("No verification token provided.");
      return;
    }

    verifyEmail(token)
      .then(() => setStatus("success"))
      .catch((err) => {
        setStatus("error");
        const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        setErrorMsg(detail || "This verification link is invalid or has expired.");
      });
  }, [token]);

  return (
    <div className="auth-page">
      <div className="auth-card" style={{ textAlign: "center" }}>
        <div className="auth-logo">QualiPulse</div>

        {status === "loading" && (
          <>
            <h1 className="auth-title">Verifying your email...</h1>
            <p className="auth-subtitle">Just a moment.</p>
          </>
        )}

        {status === "success" && (
          <>
            <div style={{ fontSize: 48, marginBottom: 16 }}>✓</div>
            <h1 className="auth-title">Email verified!</h1>
            <p className="auth-subtitle">
              Your email has been confirmed. You're all set.
            </p>
            <Link
              to="/dashboard"
              className="btn btn-primary btn-block"
              style={{ textAlign: "center", textDecoration: "none", marginTop: 24 }}
            >
              Go to Dashboard
            </Link>
          </>
        )}

        {status === "error" && (
          <>
            <div style={{ fontSize: 48, marginBottom: 16 }}>✕</div>
            <h1 className="auth-title">Verification failed</h1>
            <p className="auth-subtitle">{errorMsg}</p>
            <Link
              to="/dashboard"
              className="btn btn-primary btn-block"
              style={{ textAlign: "center", textDecoration: "none", marginTop: 24 }}
            >
              Go to Dashboard
            </Link>
            <p className="auth-footer">
              You can resend the verification email from your dashboard.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
