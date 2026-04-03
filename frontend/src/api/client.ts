import axios from "axios";

const client = axios.create({
  baseURL: "/api",
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (
      error.response?.status === 401 &&
      !originalRequest._retried &&
      !originalRequest.url?.includes("/auth/refresh")
    ) {
      originalRequest._retried = true;
      const storedRefreshToken = localStorage.getItem("refresh_token");

      if (storedRefreshToken) {
        try {
          const { data } = await axios.post("/api/auth/refresh", {
            refresh_token: storedRefreshToken,
          });
          localStorage.setItem("token", data.access_token);
          if (data.refresh_token) {
            localStorage.setItem("refresh_token", data.refresh_token);
          }
          originalRequest.headers.Authorization = `Bearer ${data.access_token}`;
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
