import { useState } from "react";
import { useTranslation } from "react-i18next";
import QRCode from "qrcode";

import { createHandoff } from "../api/interviews";

interface DeviceHandoffProps {
  token: string;
  participantId: string;
}

/** "Continue on another device" panel: mints a short-lived handoff token and
 *  shows it as a QR code plus a copyable/shareable link. Rendered wherever
 *  the current device's mic has proven unreliable (mic re-test screen,
 *  permission-denied panel). The link opens /i/{token}?handoff=... which
 *  adopts the in-progress interview on the new device. */
export default function DeviceHandoff({ token, participantId }: DeviceHandoffProps) {
  const { t } = useTranslation("interview");
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);

  async function handleOpen() {
    setOpen(true);
    setFailed(false);
    setLoading(true);
    try {
      const res = await createHandoff(token, participantId);
      const handoffUrl = `${window.location.origin}/i/${token}?handoff=${encodeURIComponent(res.handoff_token)}`;
      setUrl(handoffUrl);
      setQrDataUrl(await QRCode.toDataURL(handoffUrl, { width: 220, margin: 1 }));
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }

  async function handleCopy() {
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2500);
    } catch {
      /* clipboard denied: the participant can still scan the QR */
    }
  }

  async function handleShare() {
    if (!url) return;
    try {
      await navigator.share({ url });
    } catch {
      /* share sheet dismissed */
    }
  }

  if (!open) {
    return (
      <button
        className="btn btn-secondary"
        style={{ minHeight: 44, minWidth: 220 }}
        onClick={handleOpen}
      >
        {t("handoff.button")}
      </button>
    );
  }

  return (
    <div
      style={{
        marginTop: 12,
        padding: 16,
        borderRadius: 12,
        border: "1px solid var(--border, #e2e8f0)",
        background: "var(--surface, #fff)",
        maxWidth: 320,
        marginLeft: "auto",
        marginRight: "auto",
      }}
    >
      <p style={{ fontSize: 14, margin: "0 0 12px", color: "var(--text-secondary, #475569)" }}>
        {t("handoff.desc")}
      </p>
      {loading && <p style={{ fontSize: 13 }}>{t("handoff.loading")}</p>}
      {failed && (
        <>
          <p style={{ fontSize: 13, color: "var(--warning-text, #b45309)" }}>{t("handoff.error")}</p>
          <button className="btn btn-secondary" style={{ minHeight: 44 }} onClick={handleOpen}>
            {t("handoff.retry")}
          </button>
        </>
      )}
      {qrDataUrl && (
        <img
          src={qrDataUrl}
          alt={t("handoff.qrAlt")}
          width={200}
          height={200}
          style={{ display: "block", margin: "0 auto 10px", borderRadius: 8 }}
        />
      )}
      {url && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <button className="btn btn-secondary" style={{ minHeight: 44 }} onClick={handleCopy}>
            {copied ? t("handoff.copied") : t("handoff.copy")}
          </button>
          {typeof navigator.share === "function" && (
            <button className="btn btn-secondary" style={{ minHeight: 44 }} onClick={handleShare}>
              {t("handoff.share")}
            </button>
          )}
          <p style={{ fontSize: 12, margin: 0, color: "var(--text-secondary, #64748b)" }}>
            {t("handoff.expires")}
          </p>
        </div>
      )}
    </div>
  );
}
