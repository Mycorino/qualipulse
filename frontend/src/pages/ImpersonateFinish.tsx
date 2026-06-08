import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";

export default function ImpersonateFinish() {
  const navigate = useNavigate();
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;

    const hash = window.location.hash.startsWith("#")
      ? window.location.hash.slice(1)
      : window.location.hash;
    const params = new URLSearchParams(hash);
    const access = params.get("access_token");
    const name = params.get("name") || "";
    const email = params.get("email") || "";

    if (!access) {
      navigate("/login", { replace: true });
      return;
    }

    localStorage.setItem("token", access);
    localStorage.removeItem("refresh_token");
    localStorage.setItem("impersonation", "true");
    localStorage.setItem("impersonation_name", name);
    localStorage.setItem("impersonation_email", email);

    window.history.replaceState(null, "", window.location.pathname);
    navigate("/dashboard", { replace: true });
  }, [navigate]);

  return (
    <div className="auth-page">
      <div className="auth-card" style={{ textAlign: "center" }}>
        <p>Loading account view…</p>
      </div>
    </div>
  );
}
