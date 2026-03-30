import { useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";

export function useAuth() {
  const navigate = useNavigate();

  const token = localStorage.getItem("token");
  const isAuthenticated = useMemo(() => !!token, [token]);

  const saveToken = useCallback((accessToken: string) => {
    localStorage.setItem("token", accessToken);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("token");
    navigate("/");
  }, [navigate]);

  return { isAuthenticated, token, saveToken, logout };
}
