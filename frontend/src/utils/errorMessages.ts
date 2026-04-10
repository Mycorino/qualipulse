import { AxiosError } from "axios";

/**
 * Extract a user-friendly error message from an API error.
 * Handles: network errors, rate limits, validation, server errors, and known API detail strings.
 */
export function getErrorMessage(err: unknown, fallback = "Something went wrong"): string {
  if (!err) return fallback;

  const axiosErr = err as AxiosError<{
    detail?: string | { msg: string }[] | { code?: string; message?: string };
  }>;

  // Network error — no response at all
  if (axiosErr.code === "ERR_NETWORK" || !axiosErr.response) {
    return "Unable to connect to the server. Please check your internet connection and try again.";
  }

  // Request timed out
  if (axiosErr.code === "ECONNABORTED") {
    return "The request timed out. Please try again.";
  }

  const status = axiosErr.response?.status;
  const detail = axiosErr.response?.data?.detail;

  // Pydantic validation errors come as an array
  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg).join(". ") || fallback;
  }

  // Known API detail string
  if (typeof detail === "string" && detail.length > 0) {
    return detail;
  }

  // Structured detail object: { code, message }
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const msg = (detail as { message?: string }).message;
    if (typeof msg === "string" && msg.length > 0) return msg;
  }

  // HTTP status-based fallbacks
  switch (status) {
    case 400:
      return "Invalid request. Please check your input and try again.";
    case 401:
      return "Invalid credentials. Please try again.";
    case 403:
      return "You don't have permission to do this.";
    case 409:
      return "This resource already exists.";
    case 422:
      return "Please check all fields are filled in correctly.";
    case 429:
      return "Too many attempts. Please wait a moment and try again.";
    case 500:
    case 502:
    case 503:
      return "Our servers are temporarily unavailable. Please try again in a few moments.";
    default:
      return fallback;
  }
}
