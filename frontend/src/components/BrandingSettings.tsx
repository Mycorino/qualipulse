import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import client from "../api/client";
import { patchProjectSettings, ProjectResponse } from "../api/projects";
import { useToast } from "./Toast";
import { BRAND_FONT_LABELS, BRAND_FONT_STACKS, shadeColor } from "../utils/branding";

type BrandingMode = "standard" | "branded" | "anonymous";

const DEFAULT_BRAND_COLOR = "#4369f5";

/**
 * Setup-tab "Branding & identity" section.
 *
 * Three participant-facing identity policies per study:
 *  - standard:  show researcher name/logo when set (default)
 *  - branded:   + brand color & font theme the interview page
 *               (custom_branding entitlement)
 *  - anonymous: the API strips company/researcher identity entirely
 */
export default function BrandingSettings({
  project,
  onUpdated,
}: {
  project: ProjectResponse;
  onUpdated: (p: ProjectResponse) => void;
}) {
  const { t } = useTranslation("project");
  const { toast } = useToast();
  const mode: BrandingMode = project.branding_mode ?? "standard";

  // Entitlement for the "branded" tier of the feature (legacy Lab/Enterprise,
  // credits Team/Agency/Enterprise). Fetched once, lazily.
  const [canBrand, setCanBrand] = useState<boolean | null>(null);
  useEffect(() => {
    let cancelled = false;
    client
      .get("/billing/status")
      .then((r) => {
        if (!cancelled) setCanBrand(Boolean(r.data?.limits?.custom_branding));
      })
      .catch(() => {
        if (!cancelled) setCanBrand(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const [saving, setSaving] = useState(false);
  const [savingDefault, setSavingDefault] = useState(false);
  const colorDebounceRef = useRef<number | null>(null);

  // Persist this study's branding as the workspace default — every NEW
  // study starts from it, and each study's Setup tab can still override.
  async function saveAsDefault() {
    setSavingDefault(true);
    try {
      await client.put("/auth/branding-defaults", {
        branding_mode: mode,
        brand_primary_color: mode === "branded" ? project.brand_primary_color ?? undefined : undefined,
        brand_font: mode === "branded" ? project.brand_font ?? undefined : undefined,
        researcher_name: project.researcher_name ?? undefined,
        researcher_logo_url: project.researcher_logo_url ?? undefined,
        privacy_policy_url: project.privacy_policy_url ?? undefined,
      });
      toast(
        t("setup.brandingDefaultSaved", {
          defaultValue: "Saved — new studies will start with this branding.",
        }),
        "success"
      );
    } catch {
      toast(t("setup.warmupSaveError", { defaultValue: "Couldn't save. Please try again." }), "error");
    } finally {
      setSavingDefault(false);
    }
  }

  async function save(settings: Parameters<typeof patchProjectSettings>[1]) {
    setSaving(true);
    try {
      onUpdated(await patchProjectSettings(project.id, settings));
      toast(t("setup.brandingSaved", { defaultValue: "Saved" }), "success");
    } catch (err: any) {
      const code = err?.response?.data?.detail;
      toast(
        code === "custom_branding_required"
          ? t("setup.brandingUpgrade", {
              defaultValue: "Custom branding is available on the Team plan and above.",
            })
          : t("setup.warmupSaveError", { defaultValue: "Couldn't save. Please try again." }),
        "error"
      );
    } finally {
      setSaving(false);
    }
  }

  function pickMode(next: BrandingMode) {
    if (next === mode) return;
    if (next === "branded" && canBrand === false) {
      toast(
        t("setup.brandingUpgrade", {
          defaultValue: "Custom branding is available on the Team plan and above.",
        }),
        "error"
      );
      return;
    }
    // First switch to branded: seed a colour so the preview shows something.
    if (next === "branded" && !project.brand_primary_color) {
      void save({ branding_mode: next, brand_primary_color: DEFAULT_BRAND_COLOR });
    } else {
      void save({ branding_mode: next });
    }
  }

  const previewColor = project.brand_primary_color || DEFAULT_BRAND_COLOR;
  const previewFont =
    (project.brand_font && BRAND_FONT_STACKS[project.brand_font]) || BRAND_FONT_STACKS.system;
  const initials = (project.researcher_name || "")
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  const modeOptions: { key: BrandingMode; label: string; help: string; locked?: boolean }[] = [
    {
      key: "standard",
      label: t("setup.brandingModeStandard", { defaultValue: "Standard" }),
      help: t("setup.brandingModeStandardHelp", {
        defaultValue: "Your researcher name and logo, default QualiPulse styling.",
      }),
    },
    {
      key: "branded",
      label: t("setup.brandingModeBranded", { defaultValue: "Branded" }),
      help: t("setup.brandingModeBrandedHelp", {
        defaultValue: "Your logo, brand color and font across the interview.",
      }),
      locked: canBrand === false,
    },
    {
      key: "anonymous",
      label: t("setup.brandingModeAnonymous", { defaultValue: "Anonymous" }),
      help: t("setup.brandingModeAnonymousHelp", {
        defaultValue: "Participants never see who is running the study (blind research).",
      }),
    },
  ];

  return (
    <section className="detail-section">
      <div className="section-header-row">
        <div>
          <h2>{t("setup.brandingTitle", { defaultValue: "Branding & identity" })}</h2>
          <p className="muted-text" style={{ fontSize: 13, marginTop: 2 }}>
            {t("setup.brandingSubtitle", {
              defaultValue: "What participants see about who is running this study.",
            })}
          </p>
        </div>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          disabled={saving || savingDefault}
          onClick={saveAsDefault}
          title={t("setup.brandingSaveDefaultHelp", {
            defaultValue: "New studies will start with these branding settings — each study can still change them.",
          })}
        >
          {savingDefault
            ? t("setup.brandingSavingDefault", { defaultValue: "Saving…" })
            : t("setup.brandingSaveDefault", { defaultValue: "Save as default for new studies" })}
        </button>
      </div>

      <div className="branding-mode-grid" role="radiogroup" aria-label={t("setup.brandingTitle", { defaultValue: "Branding & identity" })}>
        {modeOptions.map((opt) => (
          <button
            key={opt.key}
            type="button"
            role="radio"
            aria-checked={mode === opt.key}
            className={`branding-mode-card${mode === opt.key ? " branding-mode-card--active" : ""}`}
            disabled={saving}
            onClick={() => pickMode(opt.key)}
          >
            <span className="branding-mode-card__label">
              {opt.label}
              {opt.locked && (
                <span className="branding-mode-card__lock" title={t("setup.brandingUpgrade", { defaultValue: "Custom branding is available on the Team plan and above." })}>
                  {" "}🔒
                </span>
              )}
            </span>
            <span className="branding-mode-card__help">{opt.help}</span>
          </button>
        ))}
      </div>

      {mode === "anonymous" ? (
        <p className="field-hint" style={{ fontSize: 13, marginTop: 12 }}>
          {t("setup.brandingAnonymousNote", {
            defaultValue:
              "The interview page hides your company name, researcher name and logo. Participants see a neutral note that the study is run anonymously.",
          })}
        </p>
      ) : (
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap", marginTop: 16 }}>
          <div style={{ flex: "1 1 280px", minWidth: 260 }}>
            <label className="field-label" htmlFor="branding-researcher-name">
              {t("setup.brandingResearcherName", { defaultValue: "Researcher / team name" })}
            </label>
            <input
              id="branding-researcher-name"
              key={`rn-${project.researcher_name ?? ""}`}
              className="field-input"
              type="text"
              maxLength={255}
              placeholder={t("setup.brandingResearcherNamePlaceholder", { defaultValue: "e.g. Acme Research Team" })}
              defaultValue={project.researcher_name ?? ""}
              onBlur={(e) => {
                const v = e.target.value.trim();
                if (v !== (project.researcher_name ?? "")) void save({ researcher_name: v });
              }}
            />

            <label className="field-label" htmlFor="branding-logo-url" style={{ marginTop: 12 }}>
              {t("setup.brandingLogoUrl", { defaultValue: "Logo URL" })}
            </label>
            <input
              id="branding-logo-url"
              key={`lu-${project.researcher_logo_url ?? ""}`}
              className="field-input"
              type="url"
              maxLength={500}
              placeholder="https://…/logo.png"
              defaultValue={project.researcher_logo_url ?? ""}
              onBlur={(e) => {
                const v = e.target.value.trim();
                if (v !== (project.researcher_logo_url ?? "")) void save({ researcher_logo_url: v });
              }}
            />

            <label className="field-label" htmlFor="branding-privacy-url" style={{ marginTop: 12 }}>
              {t("setup.brandingPrivacyUrl", { defaultValue: "Privacy policy URL (optional)" })}
            </label>
            <input
              id="branding-privacy-url"
              key={`pu-${project.privacy_policy_url ?? ""}`}
              className="field-input"
              type="url"
              maxLength={500}
              placeholder="https://…/privacy"
              defaultValue={project.privacy_policy_url ?? ""}
              onBlur={(e) => {
                const v = e.target.value.trim();
                if (v !== (project.privacy_policy_url ?? "")) void save({ privacy_policy_url: v });
              }}
            />

            {mode === "branded" && (
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 12 }}>
                <div>
                  <label className="field-label" htmlFor="branding-color">
                    {t("setup.brandingColor", { defaultValue: "Brand color" })}
                  </label>
                  <input
                    id="branding-color"
                    type="color"
                    className="branding-color-input"
                    value={previewColor}
                    onChange={(e) => {
                      const v = e.target.value;
                      if (colorDebounceRef.current) window.clearTimeout(colorDebounceRef.current);
                      colorDebounceRef.current = window.setTimeout(() => {
                        if (v !== project.brand_primary_color) void save({ brand_primary_color: v });
                      }, 500);
                    }}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="branding-font">
                    {t("setup.brandingFont", { defaultValue: "Font" })}
                  </label>
                  <select
                    id="branding-font"
                    className="field-input"
                    value={project.brand_font ?? "system"}
                    onChange={(e) => void save({ brand_font: e.target.value })}
                  >
                    {Object.keys(BRAND_FONT_STACKS).map((key) => (
                      <option key={key} value={key}>
                        {t(`brandingFonts.${key}`, { defaultValue: BRAND_FONT_LABELS[key] ?? key })}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            )}
          </div>

          {/* Live mini-preview of the participant consent card */}
          <div style={{ flex: "1 1 240px", minWidth: 220 }}>
            <p className="field-label" style={{ marginBottom: 6 }}>
              {t("setup.brandingPreview", { defaultValue: "Participant preview" })}
            </p>
            <div
              className="branding-preview-card"
              style={{ fontFamily: mode === "branded" ? previewFont : undefined }}
              aria-hidden="true"
            >
              {project.researcher_logo_url ? (
                <img
                  src={project.researcher_logo_url}
                  alt=""
                  style={{ maxHeight: 32, maxWidth: 120, objectFit: "contain" }}
                />
              ) : initials ? (
                <div
                  className="branding-preview-avatar"
                  style={{ background: mode === "branded" ? previewColor : "var(--brand-500)" }}
                >
                  {initials}
                </div>
              ) : null}
              {project.researcher_name && (
                <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: "6px 0 2px" }}>
                  {project.researcher_name}
                </p>
              )}
              <p style={{ fontSize: 14, fontWeight: 700, margin: "4px 0 10px" }}>{project.name}</p>
              <span
                className="branding-preview-btn"
                style={{
                  background: mode === "branded" ? previewColor : "var(--brand-500)",
                  boxShadow: `0 1px 3px ${mode === "branded" ? shadeColor(previewColor, -15) : "var(--brand-600)"}55`,
                }}
              >
                {t("setup.brandingPreviewCta", { defaultValue: "I agree — start" })}
              </span>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
