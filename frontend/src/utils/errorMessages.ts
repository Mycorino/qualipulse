import { AxiosError } from "axios";
import i18n from "../i18n";

/**
 * Extract a user-friendly error message from an API error.
 * Handles: network errors, rate limits, validation, server errors, and known API detail strings.
 * All generic copy resolves through i18n (common:errors.*) so it follows the UI language;
 * backend `detail` strings still pass through verbatim (API contract).
 */
export function getErrorMessage(err: unknown, fallback?: string): string {
  const genericFallback = fallback ?? i18n.t("common:errors.generic");
  if (!err) return genericFallback;

  const axiosErr = err as AxiosError<{
    detail?: string | { msg: string }[] | { code?: string; message?: string };
  }>;

  // Network error — no response at all
  if (axiosErr.code === "ERR_NETWORK" || !axiosErr.response) {
    return i18n.t("common:errors.network");
  }

  // Request timed out
  if (axiosErr.code === "ECONNABORTED") {
    return i18n.t("common:errors.timeout");
  }

  const status = axiosErr.response?.status;
  const detail = axiosErr.response?.data?.detail;

  // Pydantic validation errors come as an array
  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg).join(". ") || genericFallback;
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
      return i18n.t("common:errors.badRequest");
    case 401:
      return i18n.t("common:errors.unauthorized");
    case 403:
      return i18n.t("common:errors.forbidden");
    case 409:
      return i18n.t("common:errors.conflict");
    case 422:
      return i18n.t("common:errors.validation");
    case 429:
      return i18n.t("common:errors.rateLimited");
    case 500:
    case 502:
    case 503:
      return i18n.t("common:errors.serverUnavailable");
    default:
      return genericFallback;
  }
}
