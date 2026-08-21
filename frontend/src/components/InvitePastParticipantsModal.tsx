import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";

import {
  getInviteCandidates,
  getProjectInvites,
  sendInvites,
  type InviteCandidatesResponse,
  type InviteFunnel,
  type PoolProfile,
} from "../api/recontact";
import { getErrorMessage } from "../utils/errorMessages";
import { useToast } from "./Toast";

/**
 * "Invite past participants" — recontact modal on the study's Recruit panel.
 *
 * Lists the workspace's consented pool with per-person eligibility (blocked
 * rows stay visible with the reason, so the list never silently shrinks),
 * lets the researcher select recipients, and shows the study's invite
 * funnel (sent → started → completed) once invites exist.
 *
 * Rendered through a portal on document.body: the panel that opens it lives
 * inside `.tab-content`, whose enter animation leaves a transform on the
 * element, and a transformed ancestor becomes the containing block for
 * `position: fixed` children. Without the portal the overlay was sized to
 * the tab panel instead of the viewport, so the dialog opened somewhere in
 * the middle of a long page rather than in front of the researcher.
 */
export default function InvitePastParticipantsModal({
  projectId,
  onClose,
}: {
  projectId: string;
  onClose: () => void;
}) {
  const { t } = useTranslation("project");
  const { toast } = useToast();
  const [data, setData] = useState<InviteCandidatesResponse | null>(null);
  const [funnel, setFunnel] = useState<InviteFunnel | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [sending, setSending] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getInviteCandidates(projectId), getProjectInvites(projectId)])
      .then(([candidates, invites]) => {
        if (cancelled) return;
        setData(candidates);
        setFunnel(invites);
      })
      .catch((err) => {
        if (!cancelled) setLoadError(getErrorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  const eligible = useMemo(
    () => (data?.candidates ?? []).filter((c) => !c.blocked_reason),
    [data],
  );
  const blocked = useMemo(
    () => (data?.candidates ?? []).filter((c) => c.blocked_reason),
    [data],
  );

  const maxSelectable = data
    ? Math.min(data.batch_max, data.daily_remaining)
    : 0;

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else if (next.size < maxSelectable) {
        next.add(id);
      }
      return next;
    });
  }

  function selectAll() {
    setSelected(new Set(eligible.slice(0, maxSelectable).map((c) => c.profile_id)));
  }

  async function handleSend() {
    if (selected.size === 0 || sending) return;
    setSending(true);
    try {
      const result = await sendInvites(projectId, Array.from(selected));
      toast(t("recontact.sentToast", { count: result.sent }), "success");
      if (result.skipped.length > 0 && result.sent === 0) {
        toast(t("recontact.allSkipped"), "error");
      }
      onClose();
    } catch (err) {
      toast(getErrorMessage(err), "error");
      setSending(false);
    }
  }

  function personLabel(c: PoolProfile) {
    const bits = [c.job_function, c.country, c.age_range].filter(Boolean);
    return bits.join(" · ");
  }

  const blockedLabel: Record<string, string> = {
    already_participated: t("recontact.blockedParticipated"),
    already_invited: t("recontact.blockedInvited"),
    cooldown: t("recontact.blockedCooldown", { days: data?.cooldown_days ?? 7 }),
  };

  return createPortal(
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="recontact-modal-title"
      onClick={onClose}
    >
      <div
        className="modal-content"
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: 560 }}
      >
        <button className="modal-close" onClick={onClose} aria-label={t("a11y.close")}>
          ×
        </button>
        <h3 id="recontact-modal-title" style={{ marginTop: 0, marginBottom: 4 }}>
          {t("recontact.modalTitle")}
        </h3>
        <p className="muted-text" style={{ fontSize: 13, marginTop: 0 }}>
          {t("recontact.modalSubtitle")}
        </p>

        {funnel && funnel.summary.invited > 0 && (
          <p style={{ fontSize: 13, margin: "10px 0" }}>
            <strong>{t("recontact.funnelLine", funnel.summary)}</strong>
          </p>
        )}

        {loadError && <p style={{ color: "var(--danger, #dc2626)", fontSize: 13 }}>{loadError}</p>}
        {!data && !loadError && <p className="muted-text" style={{ fontSize: 13 }}>{t("recontact.loading")}</p>}

        {data && eligible.length === 0 && blocked.length === 0 && (
          <div className="empty-state-inline" style={{ marginTop: 8 }}>
            <span>{t("recontact.emptyPool")}</span>
          </div>
        )}

        {eligible.length > 0 && (
          <>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", margin: "10px 0 6px" }}>
              <span style={{ fontSize: 13, fontWeight: 600 }}>
                {t("recontact.eligibleCount", { count: eligible.length })}
              </span>
              <button className="btn btn-ghost btn-sm" onClick={selectAll}>
                {t("recontact.selectAll")}
              </button>
            </div>
            <div style={{ maxHeight: 260, overflowY: "auto", display: "grid", gap: 4 }}>
              {eligible.map((c) => (
                <label
                  key={c.profile_id}
                  style={{
                    display: "flex", gap: 10, alignItems: "center", padding: "6px 8px",
                    borderRadius: 8, cursor: "pointer",
                    background: selected.has(c.profile_id) ? "var(--brand-50, #eef2ff)" : "transparent",
                  }}
                >
                  <input
                    type="checkbox"
                    checked={selected.has(c.profile_id)}
                    onChange={() => toggle(c.profile_id)}
                  />
                  <span style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
                    <span style={{ fontSize: 13, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis" }}>
                      {c.first_name ? `${c.first_name} · ${c.email}` : c.email}
                    </span>
                    {personLabel(c) && (
                      <span className="muted-text" style={{ fontSize: 12 }}>{personLabel(c)}</span>
                    )}
                  </span>
                </label>
              ))}
            </div>
          </>
        )}

        {blocked.length > 0 && (
          <details style={{ marginTop: 10 }}>
            <summary style={{ fontSize: 12.5, color: "var(--text-secondary)", cursor: "pointer" }}>
              {t("recontact.blockedCount", { count: blocked.length })}
            </summary>
            <div style={{ display: "grid", gap: 2, marginTop: 6 }}>
              {blocked.map((c) => (
                <div key={c.profile_id} style={{ fontSize: 12.5, display: "flex", justifyContent: "space-between", gap: 8 }}>
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{c.email}</span>
                  <span className="muted-text" style={{ whiteSpace: "nowrap" }}>
                    {blockedLabel[c.blocked_reason ?? ""] ?? c.blocked_reason}
                  </span>
                </div>
              ))}
            </div>
          </details>
        )}

        <p className="field-hint" style={{ fontSize: 12, marginTop: 12 }}>
          {t("recontact.guardrailsHint", {
            days: data?.cooldown_days ?? 7,
            remaining: data?.daily_remaining ?? 0,
          })}
        </p>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 14 }}>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>
            {t("recontact.cancel")}
          </button>
          <button
            className="btn btn-primary btn-sm"
            disabled={selected.size === 0 || sending}
            onClick={() => void handleSend()}
          >
            {sending
              ? t("recontact.sending")
              : t("recontact.sendCta", { count: selected.size })}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
