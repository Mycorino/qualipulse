/**
 * Dependency-free client error reporting.
 *
 * Uncaught errors and unhandled promise rejections are POSTed to the
 * backend (/telemetry/client-error), which logs them at ERROR level so
 * they land in the backend's Sentry + Cloud Logging. Deduped and capped
 * per session so a render loop can't hammer the endpoint.
 */

const MAX_REPORTS_PER_SESSION = 10;
const seen = new Set<string>();
let sent = 0;

function report(kind: string, message: string, stack?: string) {
  if (sent >= MAX_REPORTS_PER_SESSION) return;
  const key = `${kind}:${message}`.slice(0, 300);
  if (seen.has(key)) return;
  seen.add(key);
  sent += 1;

  const payload = JSON.stringify({
    kind,
    message: String(message).slice(0, 2000),
    stack: stack ? String(stack).slice(0, 8000) : undefined,
    url: window.location.href.slice(0, 500),
    user_agent: navigator.userAgent.slice(0, 500),
  });

  // fetch keepalive over axios: must survive page unloads and never
  // trigger the auth/refresh interceptor chain.
  fetch("/api/telemetry/client-error", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload,
    keepalive: true,
  }).catch(() => {});
}

export function installErrorReporting() {
  window.addEventListener("error", (event) => {
    report("error", event.message || "unknown error", event.error?.stack);
  });
  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason;
    report(
      "unhandledrejection",
      reason?.message || String(reason ?? "unknown rejection"),
      reason?.stack
    );
  });
}
