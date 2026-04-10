import { useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";

const ONBOARDED_KEY = "onboarding_completed";

export function getCachedOnboarded(): boolean | null {
  const v = localStorage.getItem(ONBOARDED_KEY);
  if (v === "true") return true;
  if (v === "false") return false;
  return null;
}

export function setCachedOnboarded(value: boolean): void {
  localStorage.setItem(ONBOARDED_KEY, value ? "true" : "false");
}

export function clearCachedOnboarded(): void {
  localStorage.removeItem(ONBOARDED_KEY);
}

export function useAuth() {
  const navigate = useNavigate();

  const token = localStorage.getItem("token");
  const isAuthenticated = useMemo(() => !!token, [token]);

  const saveToken = useCallback((accessToken: string, refreshTokenValue?: string) => {
    localStorage.setItem("token", accessToken);
    if (refreshTokenValue) {
      localStorage.setItem("refresh_token", refreshTokenValue);
    }
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("token");
    localStorage.removeItem("refresh_token");
    clearCachedOnboarded();
    navigate("/");
  }, [navigate]);

  return { isAuthenticated, token, saveToken, logout };
}
