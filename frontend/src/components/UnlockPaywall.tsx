/**
 * V4 paywall UI — two components:
 *
 * 1. <PaywallCard> renders inline in place of a locked transcript or
 *    analysis result. Shows the participant metadata (so the user
 *    feels the volume of locked data) and a clear unlock CTA.
 *
 * 2. <UnlockModal> opens from a PaywallCard click. Shows two paths
 *    side-by-side: monthly subscription (recommended) and credit
 *    pack (one-off). The user picks the shape that fits their volume.
 *
 * Both are i18n'd under the new `paywall` namespace and tolerant of
 * the user dismissing without buying — onboarding stays a soft sell.
 */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import client from "../api/client";

interface PaywallCardProps {
  /** Optional context — display the locked participant's
   *  metadata (name, country, completed-at) so they FEEL what's
   *  locked. Omit on analysis paywall (no specific participant). */
  participantName?: string | null;
  participantCountry?: string | null;
  durationSeconds?: number | null;
  /** Total transcripts currently locked across the workspace. */
  lockedCount: number;
  /** Free preview budget (typically 3). */
  freePreviewCount: number;
  /** What's blocked — affects copy. */
  feature: "transcript" | "analysis";
  /** Click handler — open the unlock modal. */
  onUnlock: () => void;
}

export function PaywallCard({
  participantName,
  participantCountry,
  durationSeconds,
  lockedCount,
  freePreviewCount,
  feature,
  onUnlock,
}: PaywallCardProps) {
  const { t } = useTranslation("paywall");

  // Compose a participant blurb — "Sarah from Munich answered all
  // questions — 8 min 14s of voice" — to make the locked content
  // feel concrete, not abstract.
  let teaser: string | null = null;
  if (feature === "transcript" && (participantName || participantCountry)) {
    const name = participantName || t("anonymous_participant");
    const where = participantCountry ? ` ${t("from")} ${participantCountry}` : "";
    const dur =
      durationSeconds && durationSeconds > 0
        ? ` — ${formatDuration(durationSeconds)} ${t("of_voice")}`
        : "";
    teaser = `${name}${where} ${t("answered_all")}${dur}`;
  }

  return (
    <div className="unlock-paywall-card" role="region" aria-label={t("locked_aria")}>
      <div className="unlock-paywall-card__lock" aria-hidden>
        🔒
      </div>
      <div className="unlock-paywall-card__body">
        {teaser && <p className="unlock-paywall-card__teaser">{teaser}</p>}
        <p className="unlock-paywall-card__pitch">
          {feature === "analysis"
            ? t("pitch_analysis", { count: lockedCount, preview: freePreviewCount })
            : t("pitch_transcript", { count: lockedCount, preview: freePreviewCount })}
        </p>
        <button
          type="button"
          className="btn btn-primary btn-sm unlock-paywall-card__cta"
          onClick={onUnlock}
        >
          {t("unlock_cta")}
        </button>
      </div>
    </div>
  );
}

interface UnlockModalProps {
  /** Open/close controlled by parent so it can fire analytics. */
  open: boolean;
  onClose: () => void;
  /** Total transcripts to unlock — used in pricing math. */
  lockedCount: number;
}

interface CreditPack {
  id: string;
  credits: number;
  price_cents: number;
  currency: string;
}

export function UnlockModal({ open, onClose, lockedCount }: UnlockModalProps) {
  const { t } = useTranslation("paywall");
  const [packs, setPacks] = useState<CreditPack[]>([]);
  const [working, setWorking] = useState<string | null>(null);

  // Load the available credit packs when the modal opens.
  useEffect(() => {
    if (!open) return;
    client
      .get<CreditPack[]>("/billing/credit-packs")
      .then((r: { data: CreditPack[] }) => setPacks(r.data))
      .catch(() => setPacks([]));
  }, [open]);

  // Escape closes.
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  const handleSubscribe = async (planId: string) => {
    setWorking(`plan:${planId}`);
    try {
      const { data } = await client.post<{ checkout_url: string }>(
        "/billing/checkout",
        { plan_id: planId, billing_interval: "monthly" },
      );
      if (data.checkout_url) window.location.href = data.checkout_url;
    } catch {
      setWorking(null);
    }
  };
  const handlePack = async (packId: string) => {
    setWorking(`pack:${packId}`);
    try {
      const { data } = await client.post<{ checkout_url: string }>(
        "/billing/checkout/credits",
        { pack_id: packId },
      );
      if (data.checkout_url) window.location.href = data.checkout_url;
    } catch {
      setWorking(null);
    }
  };

  // Pick a recommended credit pack — the smallest one that covers
  // the locked count, falling back to the largest if none do.
  const sortedPacks = [...packs].sort((a, b) => a.credits - b.credits);
  const recommendedPack =
    sortedPacks.find((p) => p.credits >= lockedCount) ||
    sortedPacks[sortedPacks.length - 1];

  return (
    <div
      className="unlock-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="unlock-modal-title"
      onClick={(e) => {
        if (e.currentTarget === e.target) onClose();
      }}
    >
      <div className="unlock-modal__card">
        <button
          type="button"
          className="unlock-modal__close"
          onClick={onClose}
          aria-label={t("close")}
        >
          ×
        </button>
        <div className="unlock-modal__eyebrow">✦ {t("modal_eyebrow")}</div>
        <h2 id="unlock-modal-title" className="unlock-modal__title">
          {t("modal_title", { count: lockedCount })}
        </h2>
        <p className="unlock-modal__body">{t("modal_body")}</p>

        <div className="unlock-modal__paths">
          <div className="unlock-modal__path unlock-modal__path--featured">
            <div className="unlock-modal__path-eyebrow">
              {t("subscription_eyebrow")}
            </div>
            <div className="unlock-modal__path-title">
              {t("subscription_title")}
            </div>
            <p className="unlock-modal__path-body">
              {t("subscription_body")}
            </p>
            <ul className="unlock-modal__path-list">
              <li>{t("subscription_perk_1")}</li>
              <li>{t("subscription_perk_2")}</li>
              <li>{t("subscription_perk_3")}</li>
            </ul>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => handleSubscribe("exploration")}
              disabled={working !== null}
            >
              {working === "plan:exploration"
                ? t("redirecting")
                : t("subscription_cta_exploration")}
            </button>
            <button
              type="button"
              className="btn btn-secondary unlock-modal__secondary-plan"
              onClick={() => handleSubscribe("team")}
              disabled={working !== null}
            >
              {working === "plan:team"
                ? t("redirecting")
                : t("subscription_cta_team")}
            </button>
          </div>

          <div className="unlock-modal__path">
            <div className="unlock-modal__path-eyebrow">
              {t("pack_eyebrow")}
            </div>
            <div className="unlock-modal__path-title">
              {t("pack_title")}
            </div>
            <p className="unlock-modal__path-body">{t("pack_body")}</p>
            <ul className="unlock-modal__path-list">
              <li>{t("pack_perk_1")}</li>
              <li>{t("pack_perk_2")}</li>
            </ul>
            {recommendedPack && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => handlePack(recommendedPack.id)}
                disabled={working !== null}
              >
                {working === `pack:${recommendedPack.id}`
                  ? t("redirecting")
                  : t("pack_cta", {
                      credits: recommendedPack.credits,
                      price: formatPrice(
                        recommendedPack.price_cents,
                        recommendedPack.currency,
                      ),
                    })}
              </button>
            )}
            {sortedPacks.length > 1 && (
              <div className="unlock-modal__pack-list">
                <span className="unlock-modal__pack-list-label">
                  {t("other_packs")}
                </span>
                {sortedPacks
                  .filter((p) => p.id !== recommendedPack?.id)
                  .map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      className="unlock-modal__pack-chip"
                      onClick={() => handlePack(p.id)}
                      disabled={working !== null}
                    >
                      {p.credits} {t("credits_label")} —{" "}
                      {formatPrice(p.price_cents, p.currency)}
                    </button>
                  ))}
              </div>
            )}
          </div>
        </div>

        <button
          type="button"
          className="unlock-modal__dismiss"
          onClick={onClose}
        >
          {t("dismiss")}
        </button>
      </div>
    </div>
  );
}

// ── Helpers ────────────────────────────────────────────────────────

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m} min ${s.toString().padStart(2, "0")}s`;
}

function formatPrice(cents: number, currency: string): string {
  const value = (cents / 100).toFixed(0);
  const symbol = currency === "EUR" ? "€" : currency === "USD" ? "$" : currency;
  return `${symbol}${value}`;
}
