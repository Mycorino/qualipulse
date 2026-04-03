import { useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";

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
    navigate("/");
  }, [navigate]);

  return { isAuthenticated, token, saveToken, logout };
}
