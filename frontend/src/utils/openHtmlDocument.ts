/**
 * Open a fetched HTML document (report export) in a new tab.
 *
 * Mobile Safari (and Chrome on iOS) only allows window.open synchronously
 * inside the user gesture — once an `await` has passed, the popup is
 * silently blocked, which is why "Export PDF" did nothing on phones. So:
 *
 *   1. Open a blank tab immediately, before any network round-trip, with a
 *      minimal "preparing" note so the user sees something happen.
 *   2. Fetch the document, then point the tab at the blob URL.
 *   3. If the popup was blocked anyway (aggressive blockers, in-app
 *      browsers, embedded webviews), render the document in a full-screen
 *      iframe overlay instead — a forced .html download just leaves the
 *      user with a mystery file.
 *
 * Throws on fetch failure so callers can toast; the placeholder tab is
 * closed first so the user isn't left staring at a blank page.
 */
export async function openHtmlDocument(
  fetchBlob: () => Promise<Blob>,
  filename = "report.html",
): Promise<void> {
  const win = window.open("", "_blank");
  if (win) {
    try {
      win.document.write(
        '<p style="font-family:sans-serif;color:#4c5852;padding:2rem">…</p>',
      );
    } catch {
      // Some in-app browsers deny document access on the fresh tab — the
      // blob navigation below still works, so ignore.
    }
  }
  try {
    const data = await fetchBlob();
    const url = URL.createObjectURL(new Blob([data], { type: "text/html" }));
    if (win && !win.closed) {
      win.location.replace(url);
      // Revoked after the tab has had ample time to load the document.
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } else {
      showHtmlOverlay(url, filename);
    }
  } catch (err) {
    if (win && !win.closed) win.close();
    throw err;
  }
}

/**
 * Popup-blocked fallback: a full-screen dialog overlay with the document in
 * an iframe and a close bar on top. Plain DOM (no React) because this util
 * is called from many surfaces and the overlay outlives no component.
 */
function showHtmlOverlay(url: string, title: string): void {
  const fr = document.documentElement.lang === "fr";

  const overlay = document.createElement("div");
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-label", title);
  overlay.style.cssText =
    "position:fixed;inset:0;z-index:10000;display:flex;flex-direction:column;background:#fcfcfa;";

  const bar = document.createElement("div");
  bar.style.cssText =
    "display:flex;justify-content:flex-end;align-items:center;padding:8px 12px;" +
    "border-bottom:1px solid #dfe5e0;background:#fff;flex:none;";

  const close = document.createElement("button");
  close.type = "button";
  close.textContent = fr ? "✕ Fermer" : "✕ Close";
  close.style.cssText =
    "font:600 14px/1.2 inherit;color:#17201b;background:none;border:1px solid #dfe5e0;" +
    "border-radius:8px;padding:8px 14px;cursor:pointer;min-height:38px;";

  const iframe = document.createElement("iframe");
  iframe.src = url;
  iframe.title = title;
  iframe.style.cssText = "flex:1;width:100%;border:0;background:#fcfcfa;";

  const prevOverflow = document.body.style.overflow;
  const dismiss = () => {
    overlay.remove();
    document.body.style.overflow = prevOverflow;
    document.removeEventListener("keydown", onKeydown);
    URL.revokeObjectURL(url);
  };
  const onKeydown = (e: KeyboardEvent) => {
    if (e.key === "Escape") dismiss();
  };

  close.addEventListener("click", dismiss);
  document.addEventListener("keydown", onKeydown);
  document.body.style.overflow = "hidden";

  bar.appendChild(close);
  overlay.appendChild(bar);
  overlay.appendChild(iframe);
  document.body.appendChild(overlay);
  close.focus();
}
