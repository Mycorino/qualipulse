// Detection for in-app webviews (Instagram, Facebook, TikTok…) where the
// voice interview cannot run: those browsers don't grant getUserMedia, so a
// participant would sail through consent and screening only to hit a dead-end
// mic error. We detect up front and steer them to a real browser instead.

export interface InAppBrowserInfo {
  /** UA matches a known in-app webview (Instagram, FB, TikTok, …). */
  inApp: boolean;
  /** Which app matched, for display/analytics ("Instagram", "TikTok", …). */
  appName: string | null;
  /** The APIs the interview needs are actually present. */
  canRecord: boolean;
  os: "ios" | "android" | "other";
}

const IN_APP_PATTERNS: Array<[RegExp, string]> = [
  [/Instagram/i, "Instagram"],
  [/FBAN|FBAV|FB_IAB|FBIOS/i, "Facebook"],
  [/TikTok|musical_ly|Bytedance/i, "TikTok"],
  [/Snapchat/i, "Snapchat"],
  [/\bLine\//i, "LINE"],
  [/MicroMessenger/i, "WeChat"],
  [/LinkedInApp/i, "LinkedIn"],
  [/Pinterest/i, "Pinterest"],
];

export function detectInAppBrowser(ua: string = navigator.userAgent): InAppBrowserInfo {
  const match = IN_APP_PATTERNS.find(([re]) => re.test(ua));
  const os: InAppBrowserInfo["os"] = /iPad|iPhone|iPod/.test(ua)
    ? "ios"
    : /Android/i.test(ua)
      ? "android"
      : "other";
  // Belt and suspenders: even if the UA sniff misses a webview, a missing
  // getUserMedia/MediaRecorder means the interview cannot work here.
  const canRecord =
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof MediaRecorder !== "undefined";
  return {
    inApp: !!match,
    appName: match ? match[1] : null,
    canRecord,
    os,
  };
}

/**
 * On Android, an intent:// URL force-opens the link in Chrome, escaping the
 * webview. There is no iOS equivalent — iOS users get copy-link instructions.
 */
export function androidChromeIntentUrl(href: string = window.location.href): string | null {
  try {
    const u = new URL(href);
    if (u.protocol !== "https:" && u.protocol !== "http:") return null;
    return `intent://${u.host}${u.pathname}${u.search}#Intent;scheme=${u.protocol.replace(":", "")};package=com.android.chrome;end`;
  } catch {
    return null;
  }
}
