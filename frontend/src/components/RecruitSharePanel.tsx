import { useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import type { InterviewLink, ProjectResponse } from "../api/projects";
import InvitePastParticipantsModal from "./InvitePastParticipantsModal";
import { useToast } from "./Toast";

/** Channel glyphs for the invitation cards (inline so no icon dep is needed). */
const CHANNEL_ICONS: Record<string, ReactElement> = {
  email: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="2.5" y="4.5" width="19" height="15" rx="2.5" />
      <path d="m3 7 8.4 5.6a1.5 1.5 0 0 0 1.7 0L21.5 7" />
    </svg>
  ),
  post: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 11v2a1 1 0 0 0 1 1h3l7 4.5V5.5L7 10H4a1 1 0 0 0-1 1Z" />
      <path d="M18 9.5a4 4 0 0 1 0 5" />
      <path d="M6.5 14.5 7.5 20" />
    </svg>
  ),
  short: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M20.5 11.5a7.5 7.5 0 0 1-10.9 6.7L4 19.5l1.4-5.2A7.5 7.5 0 1 1 20.5 11.5Z" />
      <path d="M9 11h6M9 14h4" />
    </svg>
  ),
};

/**
 * Setup-tab "Recruit & share" section — the publication step that closes the
 * configure → collect gap. QualiPulse has no participant panel, so recruiting
 * is entirely on the researcher; this panel hands them the link, a
 * test-drive button, and ready-to-send invitation templates so a configured
 * study doesn't dead-end with zero responses.
 *
 * Section chrome follows the researcher's UI language; the invitation
 * templates follow the PROJECT language (participants read them), via
 * getFixedT — same principle as the guide content.
 */
export default function RecruitSharePanel({
  project,
  links,
}: {
  project: ProjectResponse;
  links: InterviewLink[];
}) {
  const { t, i18n } = useTranslation("project");
  const { toast } = useToast();
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [inviteModalOpen, setInviteModalOpen] = useState(false);

  const activeLink = links.find((l) => l.is_active) ?? null;
  const linkUrl = activeLink
    ? `${window.location.origin}/i/${activeLink.token}`
    : null;

  // Invitation bodies in the participants' language (project language),
  // falling back to the i18n fallback locale when untranslated.
  const tGuide = i18n.getFixedT(project.language || "en", "project");
  const duration = project.interview_duration_minutes;

  async function copy(key: string, text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedKey(key);
      setTimeout(() => setCopiedKey(null), 2000);
    } catch {
      toast(t("recruit.copyFailed", { defaultValue: "Couldn't copy. Select and copy manually." }), "error");
    }
  }

  const templates: { key: string; label: string; body: string }[] = linkUrl
    ? [
        {
          key: "email",
          label: t("recruit.emailLabel", { defaultValue: "Email to customers or contacts" }),
          body: tGuide("recruit.emailBody", { link: linkUrl, duration }),
        },
        {
          key: "post",
          label: t("recruit.postLabel", { defaultValue: "LinkedIn or community post" }),
          body: tGuide("recruit.postBody", { link: linkUrl, duration }),
        },
        {
          key: "short",
          label: t("recruit.shortLabel", { defaultValue: "Short message (support chat, in-app, WhatsApp)" }),
          body: tGuide("recruit.shortBody", { link: linkUrl, duration }),
        },
      ]
    : [];

  return (
    <section className="detail-section" id="recruit-share">
      <div className="section-header-row">
        <div>
          <h2>{t("recruit.title", { defaultValue: "Recruit & share" })}</h2>
          <p className="muted-text" style={{ fontSize: 13, marginTop: 2 }}>
            {t("recruit.subtitle", {
              defaultValue: "Your interview link plus ready-to-send invitations, everything you need to collect responses.",
            })}
          </p>
        </div>
      </div>

      {!linkUrl ? (
        <div className="empty-state-inline">
          <span>
            {t("recruit.noLink", {
              defaultValue: "No active interview link yet. Create one in the Overview tab and it will show up here.",
            })}
          </span>
        </div>
      ) : (
        <>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <code className="link-url" style={{ flex: "1 1 260px" }}>{linkUrl}</code>
            <button className="btn btn-secondary btn-sm" onClick={() => void copy("link", linkUrl)}>
              {copiedKey === "link"
                ? t("recruit.copied", { defaultValue: "Copied ✓" })
                : t("recruit.copyLink", { defaultValue: "Copy link" })}
            </button>
            <a
              className="btn btn-ghost btn-sm"
              href={linkUrl}
              target="_blank"
              rel="noopener noreferrer"
            >
              {t("recruit.testCta", { defaultValue: "Try the interview yourself" })}
            </a>
          </div>
          <p className="field-hint" style={{ fontSize: 12, marginTop: 6 }}>
            {t("recruit.testHint", {
              defaultValue:
                "The test opens your live interview in a new tab. It shows up under Responses (you can delete it), and a completed test counts like any completed interview.",
            })}
          </p>

          <p className="field-hint" style={{ fontSize: 13, marginTop: 14 }}>
            {t("recruit.expectations", {
              defaultValue:
                "Rule of thumb: expect roughly 1 completed interview per 10 to 20 invitations. A small thank-you (gift card, donation) noticeably lifts response rates.",
            })}
          </p>

          <h3 style={{ fontSize: 14, marginTop: 18, marginBottom: 2 }}>
            {t("recruit.templatesTitle", { defaultValue: "Ready-to-send invitations" })}
          </h3>
          <p className="muted-text" style={{ fontSize: 12, marginBottom: 10 }}>
            {t("recruit.templatesHint", {
              defaultValue:
                "Written in your study's language, with your link and duration filled in. Copy, tweak, send.",
            })}
          </p>
          <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" }}>
            {templates.map((tpl) => (
              <div key={tpl.key} className={`invite-card invite-card--${tpl.key}`}>
                <div className="invite-card__header">
                  <span className="invite-card__icon">{CHANNEL_ICONS[tpl.key]}</span>
                  <strong className="invite-card__label">{tpl.label}</strong>
                </div>
                <p className="invite-card__body">{tpl.body}</p>
                <button
                  className="btn btn-ghost btn-sm invite-card__copy"
                  onClick={() => void copy(tpl.key, tpl.body)}
                >
                  {copiedKey === tpl.key
                    ? t("recruit.copied", { defaultValue: "Copied ✓" })
                    : t("recruit.copyTemplate", { defaultValue: "Copy text" })}
                </button>
              </div>
            ))}
          </div>

          {!project.is_demo && (
            <>
              <h3 style={{ fontSize: 14, marginTop: 18, marginBottom: 2 }}>
                {t("recontact.sectionTitle")}
              </h3>
              <p className="muted-text" style={{ fontSize: 12, marginBottom: 10 }}>
                {t("recontact.sectionHint")}
              </p>
              <button className="btn btn-secondary btn-sm" onClick={() => setInviteModalOpen(true)}>
                {t("recontact.openCta")}
              </button>
            </>
          )}
        </>
      )}

      {inviteModalOpen && (
        <InvitePastParticipantsModal
          projectId={project.id}
          onClose={() => setInviteModalOpen(false)}
        />
      )}
    </section>
  );
}
