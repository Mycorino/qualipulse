import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { getWorkspacePanel, type PoolProfile, type WorkspacePanelResponse } from "../api/recontact";
import { HubShell } from "../components/HubShell";
import { getErrorMessage } from "../utils/errorMessages";

/**
 * Participant pool (V2) — the workspace's consented recontact panel.
 *
 * Read-oriented: browse who agreed to future studies, filter by profile
 * attributes, and see each person's participation + invite history. Sending
 * invites happens from a study's Recruit & share panel, because an invite
 * always targets a specific study.
 */

function fmtDate(iso: string | null | undefined, locale: string): string {
  if (!iso) return "-";
  try {
    return new Date(iso).toLocaleDateString(locale, { day: "numeric", month: "short", year: "numeric" });
  } catch {
    return "-";
  }
}

type FilterKey = "country" | "job_function" | "age_range";
const FILTER_KEYS: FilterKey[] = ["country", "job_function", "age_range"];

export default function ParticipantPool() {
  const { t, i18n } = useTranslation("dashboard");
  const [data, setData] = useState<WorkspacePanelResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<Partial<Record<FilterKey, string>>>({});

  useEffect(() => {
    getWorkspacePanel().then(setData).catch((err) => setError(getErrorMessage(err)));
  }, []);

  const options = useMemo(() => {
    const out: Record<FilterKey, string[]> = { country: [], job_function: [], age_range: [] };
    for (const key of FILTER_KEYS) {
      const values = new Set<string>();
      for (const p of data?.profiles ?? []) {
        const v = p[key];
        if (v) values.add(v);
      }
      out[key] = Array.from(values).sort();
    }
    return out;
  }, [data]);

  const filtered = useMemo(() => {
    return (data?.profiles ?? []).filter((p) =>
      FILTER_KEYS.every((key) => !filters[key] || p[key] === filters[key]),
    );
  }, [data, filters]);

  const locale = i18n.language?.startsWith("fr") ? "fr-FR" : "en-GB";

  function profileName(p: PoolProfile) {
    return p.first_name?.trim() || p.email.split("@")[0];
  }

  const loading = data === null && error === null;

  return (
    <HubShell active="pool">
      <div className="hub-canvas">
        <header className="hub-head">
          <div className="hub-head__text">
            <h1 className="hub-head__title">{t("pool.title")}</h1>
            <p className="hub-head__sub">{t("pool.subtitle")}</p>
          </div>
        </header>

        {error && <p style={{ color: "var(--danger, #dc2626)", fontSize: 13 }}>{error}</p>}

        {loading && (
          <div className="hub-table-wrap" aria-hidden="true">
            {[0, 1, 2].map((i) => (
              <div key={i} className="hub-skel-row">
                <span className="hub-skel" style={{ width: "32%", height: 12 }} />
                <span className="hub-skel" style={{ width: "24%", height: 10 }} />
                <span className="hub-skel" style={{ width: 60, height: 10 }} />
              </div>
            ))}
          </div>
        )}

        {data && (
          <>
            <div style={{ display: "flex", gap: 24, flexWrap: "wrap", margin: "4px 0 18px" }}>
              <div>
                <div style={{ fontSize: 24, fontWeight: 700, lineHeight: 1.1 }}>{data.stats.pool_size}</div>
                <div className="muted-text" style={{ fontSize: 12 }}>{t("pool.statPool")}</div>
              </div>
              <div>
                <div style={{ fontSize: 24, fontWeight: 700, lineHeight: 1.1 }}>{data.stats.invited_30d}</div>
                <div className="muted-text" style={{ fontSize: 12 }}>{t("pool.statInvited30d")}</div>
              </div>
            </div>

            {data.profiles.length === 0 ? (
              <div
                style={{
                  border: "1px dashed var(--border-color, #e2e8f0)",
                  borderRadius: 12,
                  padding: 32,
                  textAlign: "center",
                }}
              >
                <p className="muted-text" style={{ maxWidth: 520, margin: "0 auto", lineHeight: 1.5 }}>
                  {t("pool.empty")}
                </p>
              </div>
            ) : (
              <>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
                  {FILTER_KEYS.map((key) =>
                    options[key].length > 1 ? (
                      <select
                        key={key}
                        value={filters[key] ?? ""}
                        onChange={(e) =>
                          setFilters((prev) => ({ ...prev, [key]: e.target.value || undefined }))
                        }
                        aria-label={t(`pool.filter.${key}`)}
                        style={{ fontSize: 13, padding: "6px 10px", borderRadius: 8 }}
                      >
                        <option value="">{t(`pool.filter.${key}`)}</option>
                        {options[key].map((v) => (
                          <option key={v} value={v}>{v}</option>
                        ))}
                      </select>
                    ) : null,
                  )}
                  {Object.values(filters).some(Boolean) && (
                    <button className="btn btn-ghost btn-sm" onClick={() => setFilters({})}>
                      {t("pool.clearFilters")}
                    </button>
                  )}
                </div>

                <div className="hub-table-wrap">
                  <table className="hub-table">
                    <thead>
                      <tr>
                        <th>{t("pool.col.person")}</th>
                        <th>{t("pool.col.profile")}</th>
                        <th>{t("pool.col.studies")}</th>
                        <th>{t("pool.col.invites")}</th>
                        <th>{t("pool.col.lastInvited")}</th>
                        <th>{t("pool.col.lastActive")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filtered.map((p) => (
                        <tr key={p.profile_id}>
                          <td>
                            <div style={{ fontWeight: 600 }}>{profileName(p)}</div>
                            <div className="muted-text" style={{ fontSize: 12 }}>{p.email}</div>
                          </td>
                          <td className="muted-text">
                            {[p.job_function, p.country, p.age_range].filter(Boolean).join(" · ") || "-"}
                          </td>
                          <td>{p.studies_participated ?? 0}</td>
                          <td>{p.invites_sent ?? 0}</td>
                          <td>{fmtDate(p.last_invited_at, locale)}</td>
                          <td>{fmtDate(p.last_active, locale)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {filtered.length === 0 && (
                  <p className="muted-text" style={{ fontSize: 13, marginTop: 10 }}>
                    {t("pool.noMatch")}
                  </p>
                )}
                <p className="muted-text" style={{ fontSize: 12, marginTop: 16, maxWidth: 640 }}>
                  {t("pool.inviteHint")}
                </p>
              </>
            )}
          </>
        )}
      </div>
    </HubShell>
  );
}
