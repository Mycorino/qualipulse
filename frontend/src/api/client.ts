import axios from "axios";

const client = axios.create({
  baseURL: "/api",
  timeout: 30000,
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Coalesce concurrent 401s into a single refresh. Without this, N parallel
// requests that all 401 fire N independent /auth/refresh calls, each racing to
// write a new refresh_token to localStorage — last write wins and the others'
// rotated tokens are lost, which can log the user out. All callers now await
// the same in-flight promise instead.
let refreshPromise: Promise<string> | null = null;

function refreshAccessToken(storedRefreshToken: string): Promise<string> {
  if (!refreshPromise) {
    refreshPromise = axios
      .post("/api/auth/refresh", { refresh_token: storedRefreshToken })
      .then(({ data }) => {
        localStorage.setItem("token", data.access_token);
        if (data.refresh_token) {
          localStorage.setItem("refresh_token", data.refresh_token);
        }
        return data.access_token as string;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // A 401 from the login endpoints means "wrong credentials", not "session
    // expired" — let the page show the error instead of hard-redirecting to /.
    const isCredentialCheck =
      originalRequest.url?.includes("/auth/login") ||
      originalRequest.url?.includes("/auth/refresh");

    if (
      error.response?.status === 401 &&
      !originalRequest._retried &&
      !isCredentialCheck
    ) {
      originalRequest._retried = true;

      if (localStorage.getItem("impersonation") === "true") {
        localStorage.removeItem("token");
        localStorage.removeItem("impersonation");
        localStorage.removeItem("impersonation_name");
        localStorage.removeItem("impersonation_email");
        window.close();
        window.location.href = "/admin";
        return Promise.reject(error);
      }

      const storedRefreshToken = localStorage.getItem("refresh_token");

      if (storedRefreshToken) {
        try {
          const accessToken = await refreshAccessToken(storedRefreshToken);
          originalRequest.headers.Authorization = `Bearer ${accessToken}`;
          return client(originalRequest);
        } catch {
          // Refresh failed — fall through to logout
        }
      }

      localStorage.removeItem("token");
      localStorage.removeItem("refresh_token");
      if (!window.location.pathname.startsWith("/i/")) {
        window.location.href = "/";
      }
    }

    return Promise.reject(error);
  }
);

export default client;
