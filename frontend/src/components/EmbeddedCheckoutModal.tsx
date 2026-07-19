import { useEffect, useRef, useState } from "react";
import { loadStripe } from "@stripe/stripe-js";
import { useTranslation } from "react-i18next";

interface Props {
  publishableKey: string;
  clientSecret: string;
  /** Fired by Stripe when the payment completes — navigate/refresh here. */
  onComplete: () => void;
  onClose: () => void;
}

/**
 * Stripe Embedded Checkout in a modal — the payment form renders in a
 * Stripe-managed iframe inside the app instead of redirecting to
 * checkout.stripe.com. Sessions are created server-side with
 * ui_mode="embedded" + redirect_on_completion="never", so completion is
 * handled entirely through onComplete (fulfilment stays webhook-driven).
 */
export default function EmbeddedCheckoutModal({ publishableKey, clientSecret, onComplete, onClose }: Props) {
  const { t } = useTranslation(["settings", "common"]);
  const containerRef = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<"loading" | "ready" | "failed">("loading");
  // Stripe's iframe holds the callback for the whole payment — track the
  // latest one without re-initialising checkout on re-renders.
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  useEffect(() => {
    let cancelled = false;
    let checkout: { destroy: () => void; mount: (el: HTMLElement) => void } | null = null;

    (async () => {
      try {
        const stripe = await loadStripe(publishableKey);
        if (!stripe) throw new Error("stripe.js failed to load");
        const init = () =>
          stripe.createEmbeddedCheckoutPage({
            clientSecret,
            onComplete: () => onCompleteRef.current(),
          });
        let instance;
        try {
          instance = await init();
        } catch {
          // Stripe allows a single embedded instance per page. Under React
          // StrictMode the effect double-fires and the first instance may
          // not be destroyed yet — wait a beat and retry once.
          await new Promise((r) => setTimeout(r, 400));
          instance = await init();
        }
        if (cancelled) {
          instance.destroy();
          return;
        }
        checkout = instance;
        if (containerRef.current) {
          instance.mount(containerRef.current);
          setState("ready");
        }
      } catch {
        if (!cancelled) setState("failed");
      }
    })();

    return () => {
      cancelled = true;
      checkout?.destroy();
    };
  }, [publishableKey, clientSecret]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div className="embedded-checkout-overlay" role="dialog" aria-modal="true">
      <div className="embedded-checkout-modal">
        <button
          type="button"
          className="embedded-checkout-close"
          onClick={onClose}
          aria-label={t("common:close", { defaultValue: "Close" })}
        >
          ✕
        </button>
        {state === "loading" && (
          <p className="muted-text embedded-checkout-status">
            {t("settings:billing.embeddedLoading", { defaultValue: "Loading secure checkout…" })}
          </p>
        )}
        {state === "failed" && (
          <p className="muted-text embedded-checkout-status">
            {t("settings:billing.embeddedFailed", {
              defaultValue: "Could not load the payment form — please close and try again.",
            })}
          </p>
        )}
        <div ref={containerRef} className="embedded-checkout-frame" />
      </div>
    </div>
  );
}
