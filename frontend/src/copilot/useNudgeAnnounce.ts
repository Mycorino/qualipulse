import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { Nudge } from "./signals";

/**
 * Announces each new nudge exactly once via an `aria-live="polite"`
 * region. Returns the message string to render inside a visually-hidden
 * live region; re-announcing on every render is avoided by tracking the
 * ids already spoken.
 */
export function useNudgeAnnounce(nudges: Nudge[] | undefined): string {
  const { t } = useTranslation("dashboard");
  const announced = useRef<Set<string>>(new Set());
  const [message, setMessage] = useState("");

  useEffect(() => {
    const fresh = (nudges ?? []).filter((n) => !announced.current.has(n.id));
    if (fresh.length === 0) return;
    fresh.forEach((n) => announced.current.add(n.id));
    const latest = fresh[fresh.length - 1];
    setMessage(
      latest.textKey ? t(latest.textKey, latest.textParams) : latest.text ?? "",
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nudges]);

  return message;
}
