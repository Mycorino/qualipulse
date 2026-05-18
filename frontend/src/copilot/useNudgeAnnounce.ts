import { useEffect, useRef, useState } from "react";

import type { Nudge } from "./signals";

/**
 * Announces each new nudge exactly once via an `aria-live="polite"`
 * region. Returns the message string to render inside a visually-hidden
 * live region; re-announcing on every render is avoided by tracking the
 * ids already spoken.
 */
export function useNudgeAnnounce(nudges: Nudge[] | undefined): string {
  const announced = useRef<Set<string>>(new Set());
  const [message, setMessage] = useState("");

  useEffect(() => {
    const fresh = (nudges ?? []).filter((n) => !announced.current.has(n.id));
    if (fresh.length === 0) return;
    fresh.forEach((n) => announced.current.add(n.id));
    setMessage(fresh[fresh.length - 1].text);
  }, [nudges]);

  return message;
}
