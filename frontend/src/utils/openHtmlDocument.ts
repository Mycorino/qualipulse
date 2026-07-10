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
 *      browsers), fall back to a same-tab anchor download.
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
    } else {
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      a.remove();
    }
    // Revoked after the tab has had ample time to load the document.
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  } catch (err) {
    if (win && !win.closed) win.close();
    throw err;
  }
}
