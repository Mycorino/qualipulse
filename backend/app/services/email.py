"""
Email service — console logger in development, SendGrid in production.

Language support
----------------
Every template helper takes an optional ``lang`` argument (``"en"`` or
``"fr"``). The correct copy is picked from :data:`_COPY`. Call sites should
pass ``company.preferred_language`` (or the relevant project language for
participant-facing emails). Unknown languages fall back to English.

Deliverability
--------------
Every outgoing email includes:

* A **plain-text alternative** generated from the HTML body via
  :func:`_html_to_text`. Without this SpamAssassin triggers
  ``MIME_HTML_ONLY`` and ``HTML_IMAGE_ONLY_24`` (when the HTML is short
  relative to chrome), knocking ~1.4 points off the deliverability score.
* A ``List-Unsubscribe`` header pointing at a ``mailto:`` so Gmail/Outlook
  can surface a one-click unsubscribe affordance. We don't advertise
  one-click POST (RFC 8058) yet because we don't have a public POST
  endpoint to honour it; the mailto alone still clears Gmail's warning.

To enable SendGrid: set SENDGRID_API_KEY in .env
"""
import html as _html_stdlib
import logging
import re
from typing import Optional

from app.config import settings

logger = logging.getLogger("auto_interview.email")


# ── HTML → plain-text conversion ───────────────────────────────────────────

# Tags that should become a blank line in the plain-text version.
_BLOCK_TAGS = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6"}


def _html_to_text(html: str) -> str:
    """Turn our template HTML into a readable plain-text alternative.

    Not a general HTML→text converter — it's tuned for the specific shape
    of the templates below (no tables beyond simple layout, no lists,
    anchors with ``href`` attributes). Good enough to pass SpamAssassin's
    ``MIME_HTML_ONLY`` check and give non-HTML mail clients (mutt, screen
    readers) a sensible readable version.
    """
    # 1. Drop <style>/<script> blocks entirely — they leak CSS into the text.
    text = re.sub(
        r"<(style|script)[^>]*>.*?</\1>",
        "",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # 2. Rewrite anchors as ``label (url)`` so the URL survives tag stripping.
    def _anchor(match: re.Match) -> str:
        href = match.group(1)
        label = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        if not label:
            return href
        if label == href:
            return href
        return f"{label} ({href})"

    text = re.sub(
        r'<a\b[^>]*\bhref="([^"]+)"[^>]*>(.*?)</a>',
        _anchor,
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # 3. Block tags → newline.
    def _block(match: re.Match) -> str:
        return "\n"

    text = re.sub(
        r"</?(" + "|".join(_BLOCK_TAGS) + r")\b[^>]*>",
        _block,
        text,
        flags=re.IGNORECASE,
    )

    # 4. Strip remaining tags.
    text = re.sub(r"<[^>]+>", "", text)

    # 5. Decode HTML entities (&amp;, &nbsp;, …).
    text = _html_stdlib.unescape(text)

    # 6. Collapse runs of blank lines and trim.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── List-Unsubscribe header ────────────────────────────────────────────────

_UNSUBSCRIBE_MAILTO = "mailto:support@qualipulse.com?subject=Unsubscribe%20from%20QualiPulse"


def _unsubscribe_headers(email_type: str = "transactional") -> dict[str, str]:
    """Return the ``List-Unsubscribe`` (+ variants) headers for a message.

    Only marketing/bulk mail (newsletter, digests) gets ``List-Unsubscribe``.
    Transactional mail (verification, magic link, password reset, team
    invite, analysis-ready, welcome) intentionally does NOT — advertising
    "mailing list" on an account-lifecycle email trips spam filters (Apple
    Mail even renders a "This message is from a mailing list" banner) and
    confuses recipients who never opted into a list.

    For marketing we include ``mailto:`` because Gmail accepts that alone.
    We skip ``List-Unsubscribe-Post: List-Unsubscribe=One-Click`` (RFC 8058)
    because we don't have a POST endpoint to honour one-click yet —
    advertising one and returning 404 is worse than not advertising.
    """
    if email_type != "marketing":
        return {}
    return {"List-Unsubscribe": f"<{_UNSUBSCRIBE_MAILTO}>"}


# ── Language utilities ─────────────────────────────────────────────────────

_SUPPORTED_LANGS = ("en", "fr")


def _normalise_lang(lang: Optional[str]) -> str:
    """Return a supported language code. Unknown inputs fall back to 'en'."""
    if not lang:
        return "en"
    code = lang.lower().split("-")[0].strip()
    return code if code in _SUPPORTED_LANGS else "en"


# All translated copy lives here so we can see both languages side-by-side.
# Keys correspond 1:1 to the template helpers below.
_COPY: dict[str, dict[str, dict[str, str]]] = {
    "affiliate_received": {
        "en": {
            "subject": "We received your affiliate application",
            "heading": "Thanks for applying, {name}!",
            "body": (
                "Your application to the QualiPulse affiliate program is in. "
                "We review every application by hand and will get back to you "
                "within 2 to 3 business days."
            ),
            "foot": "Questions in the meantime? Just reply to this email.",
        },
        "fr": {
            "subject": "Nous avons bien reçu votre candidature d'affilié",
            "heading": "Merci pour votre candidature, {name} !",
            "body": (
                "Votre candidature au programme d'affiliation QualiPulse est "
                "bien enregistrée. Nous examinons chaque candidature à la main "
                "et vous répondrons sous 2 à 3 jours ouvrés."
            ),
            "foot": "Une question entre-temps ? Répondez simplement à cet email.",
        },
    },
    "affiliate_approved": {
        "en": {
            "subject": "You're in! Your QualiPulse affiliate account is live",
            "heading": "Welcome aboard, {name}!",
            "body": (
                "Your affiliate application was approved. Share your referral "
                "link and you earn {commission}% of each referred customer's "
                "first subscription payment."
            ),
            "link_label": "Your referral link:",
            "cta": "Open your affiliate dashboard",
            "foot": "Sign in any time with your email address; we send you a secure link.",
        },
        "fr": {
            "subject": "C'est parti ! Votre compte affilié QualiPulse est actif",
            "heading": "Bienvenue à bord, {name} !",
            "body": (
                "Votre candidature d'affilié a été approuvée. Partagez votre "
                "lien de parrainage et gagnez {commission}% du premier paiement "
                "d'abonnement de chaque client parrainé."
            ),
            "link_label": "Votre lien de parrainage :",
            "cta": "Ouvrir votre tableau de bord affilié",
            "foot": "Connectez-vous à tout moment avec votre adresse email ; nous vous envoyons un lien sécurisé.",
        },
    },
    "affiliate_rejected": {
        "en": {
            "subject": "About your QualiPulse affiliate application",
            "heading": "Thanks for your interest, {name}",
            "body": (
                "We reviewed your application to the QualiPulse affiliate "
                "program and can't accept it at this time. This is often about "
                "audience fit rather than quality, and you're welcome to apply "
                "again as your audience evolves."
            ),
            "foot": "If you think we got this wrong, reply to this email and tell us more.",
        },
        "fr": {
            "subject": "Au sujet de votre candidature d'affilié QualiPulse",
            "heading": "Merci de votre intérêt, {name}",
            "body": (
                "Nous avons examiné votre candidature au programme "
                "d'affiliation QualiPulse et ne pouvons pas l'accepter pour le "
                "moment. C'est souvent une question d'adéquation d'audience "
                "plutôt que de qualité, et vous pouvez repostuler quand votre "
                "audience évolue."
            ),
            "foot": "Si vous pensez que nous nous trompons, répondez à cet email pour nous en dire plus.",
        },
    },
    "affiliate_magic": {
        "en": {
            "subject": "Your affiliate dashboard sign-in link",
            "heading": "Sign in to your affiliate dashboard",
            "body": "Click the button below to open your QualiPulse affiliate dashboard.",
            "cta": "Open my dashboard",
            "foot": (
                "This link expires in {expiry_minutes} minutes and can only be "
                "used with this email address. If you didn't request it, you "
                "can safely ignore this email."
            ),
        },
        "fr": {
            "subject": "Votre lien de connexion au tableau de bord affilié",
            "heading": "Connectez-vous à votre tableau de bord affilié",
            "body": "Cliquez sur le bouton ci-dessous pour ouvrir votre tableau de bord affilié QualiPulse.",
            "cta": "Ouvrir mon tableau de bord",
            "foot": (
                "Ce lien expire dans {expiry_minutes} minutes et ne peut être "
                "utilisé qu'avec cette adresse email. Si vous n'en êtes pas à "
                "l'origine, vous pouvez ignorer cet email."
            ),
        },
    },
    "affiliate_conversion": {
        "en": {
            "subject": "You earned a commission: {amount}",
            "heading": "A referral just converted 🎉",
            "body": (
                "One of your referrals upgraded to a paid QualiPulse plan. "
                "You earned {amount} in commission. Your pending balance is "
                "now {pending}."
            ),
            "cta": "See your earnings",
            "foot": "Payouts unlock once your pending balance reaches {threshold}.",
        },
        "fr": {
            "subject": "Vous avez gagné une commission : {amount}",
            "heading": "Un parrainage vient de convertir 🎉",
            "body": (
                "Un de vos parrainages est passé sur une offre payante "
                "QualiPulse. Vous avez gagné {amount} de commission. Votre "
                "solde en attente est maintenant de {pending}."
            ),
            "cta": "Voir vos gains",
            "foot": "Les paiements se débloquent quand votre solde en attente atteint {threshold}.",
        },
    },
    "affiliate_payout": {
        "en": {
            "subject": "Your affiliate payout of {amount} is on its way",
            "heading": "Payout recorded, {name}",
            "body": (
                "We just recorded a payout of {amount} to you. Depending on "
                "the payment method it can take a few business days to arrive."
            ),
            "cta": "View payout history",
            "foot": "Thanks for spreading the word about QualiPulse.",
        },
        "fr": {
            "subject": "Votre paiement affilié de {amount} est en route",
            "heading": "Paiement enregistré, {name}",
            "body": (
                "Nous venons d'enregistrer un paiement de {amount} en votre "
                "faveur. Selon le moyen de paiement, il peut mettre quelques "
                "jours ouvrés à arriver."
            ),
            "cta": "Voir l'historique des paiements",
            "foot": "Merci de faire connaître QualiPulse.",
        },
    },
    "welcome": {
        "en": {
            "subject": "Welcome to QualiPulse",
            "heading": "Welcome, {name}!",
            "body": "Your QualiPulse account is ready. Start by creating your first research project.",
            "cta": "Create your first project",
            "foot": "Need help getting started? Just reply to this email.",
        },
        "fr": {
            "subject": "Bienvenue sur QualiPulse",
            "heading": "Bienvenue, {name} !",
            "body": "Votre compte QualiPulse est prêt. Commencez par créer votre premier projet de recherche.",
            "cta": "Créer votre premier projet",
            "foot": "Besoin d'aide pour démarrer ? Répondez simplement à cet email.",
        },
    },
    "verification": {
        "en": {
            "subject": "Confirm your email to activate QualiPulse",
            "heading": "Welcome to QualiPulse, {name} \u2014 one last step",
            "body": (
                "Thanks for signing up. Click the button below to confirm this "
                "is your email so we know account alerts, research analysis "
                "notifications, and your magic links are reaching the right "
                "inbox."
            ),
            "cta": "Verify my email",
            "subfoot": (
                "If the button doesn't work, copy and paste this link into "
                "your browser:"
            ),
            "foot": (
                "This link expires in 24 hours. If you didn't sign up for "
                "QualiPulse, you can safely ignore this email and the "
                "account will be deleted automatically."
            ),
        },
        "fr": {
            "subject": "Confirmez votre email pour activer QualiPulse",
            "heading": "Bienvenue sur QualiPulse, {name} \u2014 une derni\u00e8re \u00e9tape",
            "body": (
                "Merci pour votre inscription. Cliquez sur le bouton ci-dessous "
                "pour confirmer que cet email vous appartient : nous "
                "utiliserons cette adresse pour vos alertes de compte, les "
                "notifications d\u2019analyses de recherche et vos liens "
                "magiques."
            ),
            "cta": "Vérifier mon email",
            "subfoot": (
                "Si le bouton ne fonctionne pas, copiez-collez ce lien dans "
                "votre navigateur :"
            ),
            "foot": (
                "Ce lien expire dans 24 heures. Si vous n'avez pas créé de "
                "compte QualiPulse, vous pouvez ignorer cet email en toute "
                "sécurité — le compte sera supprimé automatiquement."
            ),
        },
    },
    "password_reset": {
        "en": {
            "subject": "Reset your QualiPulse password",
            "heading": "Reset your password",
            "body": "Click the button below to set a new password. This link expires in 1 hour.",
            "cta": "Reset password",
            "foot": "If you didn't request this, you can safely ignore this email. Your password won't change.",
        },
        "fr": {
            "subject": "Réinitialisez votre mot de passe QualiPulse",
            "heading": "Réinitialisez votre mot de passe",
            "body": "Cliquez sur le bouton ci-dessous pour définir un nouveau mot de passe. Ce lien expire dans 1 heure.",
            "cta": "Réinitialiser le mot de passe",
            "foot": "Si vous n'êtes pas à l'origine de cette demande, vous pouvez ignorer cet email. Votre mot de passe restera inchangé.",
        },
    },
    "analysis_ready": {
        "en": {
            "subject": "Analysis ready: {project_name}",
            "heading": "Your analysis is ready",
            "body": "The AI analysis for <strong>{project_name}</strong> has been completed. Themes, quotes, and recommendations are waiting for you.",
            "cta": "View analysis",
        },
        "fr": {
            "subject": "Analyse prête : {project_name}",
            "heading": "Votre analyse est prête",
            "body": "L'analyse IA pour <strong>{project_name}</strong> est terminée. Thèmes, citations et recommandations vous attendent.",
            "cta": "Voir l'analyse",
        },
    },
    "day_1_followup": {
        "en": {
            "subject": "Your study, day 1 — what to do today",
            "heading": "Day 1 — keep momentum",
            "body": (
                "Yesterday we drafted <strong>{study_name}</strong> together. "
                "Today the highest-leverage thing you can do is share your "
                "interview link with one real participant — even a teammate "
                "works. Voice interviews surface the why; the only way to "
                "feel that is to hear it."
            ),
            "cta": "Open your study",
            "foot": (
                "I'll let you know the moment your first response comes in."
            ),
        },
        "fr": {
            "subject": "Votre étude, jour 1 — quoi faire aujourd'hui",
            "heading": "Jour 1 — gardons l'élan",
            "body": (
                "Hier nous avons rédigé <strong>{study_name}</strong> "
                "ensemble. Aujourd'hui, le plus important : partager votre "
                "lien d'entretien avec un participant réel — même un collègue "
                "fait l'affaire. Les entretiens vocaux révèlent le pourquoi ; "
                "il faut l'entendre pour le sentir."
            ),
            "cta": "Ouvrir votre étude",
            "foot": (
                "Je vous préviendrai dès que votre première réponse arrive."
            ),
        },
    },
    "trial_half_over": {
        "en": {
            "subject": "Halfway through your QualiPulse trial",
            "heading": "{days_left} days left on your trial",
            "body": (
                "You're {days_left} days away from the end of your trial. "
                "{usage_line} The teams who renew tend to be the ones who "
                "shared their link with at least three participants by now — "
                "if you haven't yet, a quick share or two will tell you "
                "everything you need to know about whether voice interviews "
                "fit your research."
            ),
            "cta": "Open your study",
            "foot": (
                "Want to keep going past Day 14? {plan_line}"
            ),
        },
        "fr": {
            "subject": "Mi-parcours de votre essai QualiPulse",
            "heading": "Plus que {days_left} jours d'essai",
            "body": (
                "Il vous reste {days_left} jours d'essai. {usage_line} Les "
                "équipes qui restent sont celles qui ont partagé leur lien "
                "avec au moins trois participants à ce stade — si ce n'est "
                "pas encore fait, un ou deux partages vous diront si les "
                "entretiens vocaux conviennent à votre recherche."
            ),
            "cta": "Ouvrir votre étude",
            "foot": (
                "Envie de continuer après le 14e jour ? {plan_line}"
            ),
        },
    },
    "trial_ending": {
        "en": {
            "subject": "Your trial ends in {days_left} days",
            "heading": "Pick a plan to keep going",
            "body": (
                "Your trial wraps up in {days_left} days. You've run "
                "{interviews} interview{interviews_plural} so far. To keep "
                "your studies live past then, pick a plan — or grab a credit "
                "pack if you only need a handful more interviews."
            ),
            "cta": "Choose a plan",
            "foot": (
                "{plan_line} You can also continue on a credit pack — "
                "low-commitment, no monthly fee."
            ),
        },
        "fr": {
            "subject": "Votre essai se termine dans {days_left} jours",
            "heading": "Choisissez un plan pour continuer",
            "body": (
                "Votre essai se termine dans {days_left} jours. Vous avez "
                "lancé {interviews} entretien{interviews_plural} jusqu'ici. "
                "Pour garder vos études en ligne au-delà, choisissez un plan "
                "— ou prenez un pack de crédits si vous n'avez besoin que "
                "de quelques entretiens de plus."
            ),
            "cta": "Choisir un plan",
            "foot": (
                "{plan_line} Vous pouvez aussi continuer avec un pack de "
                "crédits — sans engagement mensuel."
            ),
        },
    },
    "free_preview_full": {
        "en": {
            "subject": "Your 3 free transcripts are unlocked — more waiting",
            "heading": "All 3 free transcripts are ready",
            "body": (
                "You've now collected 3+ responses for <strong>{project_name}"
                "</strong> — and you can listen to, tag, and annotate "
                "every one of them. Any further responses are waiting to "
                "be unlocked. Subscribe (or grab a credit pack) to read "
                "the rest and run AI analysis across the full study."
            ),
            "cta": "Unlock the rest",
            "foot": (
                "The first 3 stay free forever — no time pressure on the "
                "ones you've already explored."
            ),
        },
        "fr": {
            "subject": "Vos 3 transcriptions gratuites sont débloquées — d'autres attendent",
            "heading": "Vos 3 transcriptions gratuites sont prêtes",
            "body": (
                "Vous avez désormais collecté 3+ réponses pour <strong>"
                "{project_name}</strong> — et vous pouvez les écouter, "
                "les taguer et les annoter toutes. Les réponses "
                "supplémentaires attendent d'être débloquées. Abonnez-"
                "vous (ou prenez un pack de crédits) pour lire la suite "
                "et lancer l'analyse IA sur l'étude complète."
            ),
            "cta": "Débloquer le reste",
            "foot": (
                "Les 3 premières restent gratuites pour toujours — pas "
                "de pression sur celles que vous avez déjà explorées."
            ),
        },
    },
    "first_response_in": {
        "en": {
            "subject": "Your first response is in — {project_name}",
            "heading": "Your first interview is in",
            "body": (
                "Someone just completed your <strong>{project_name}</strong> "
                "interview. Listen to the transcript, tag a quote, or add a "
                "memo while it's fresh — these small touches are what turn "
                "responses into research insights."
            ),
            "cta": "Listen to the response",
            "foot": (
                "Once you have a few more responses, run an AI analysis to "
                "surface themes across all of them."
            ),
        },
        "fr": {
            "subject": "Votre première réponse est arrivée — {project_name}",
            "heading": "Votre premier entretien est arrivé",
            "body": (
                "Quelqu'un vient de compléter l'entretien <strong>"
                "{project_name}</strong>. Écoutez la transcription, taguez "
                "une citation ou ajoutez une note pendant que c'est frais — "
                "ces petits gestes transforment les réponses en insights."
            ),
            "cta": "Écouter la réponse",
            "foot": (
                "Une fois quelques réponses de plus, lancez une analyse IA "
                "pour faire émerger les thèmes transversaux."
            ),
        },
    },
    "interview_invite": {
        "en": {
            "subject": "You're invited to a research interview",
            "heading": "You're invited to participate",
            "body": "{sender_name} has invited you to a voice interview about <strong>{project_name}</strong>. It takes about 15-30 minutes and runs entirely in your browser.",
            "cta": "Start interview",
            "foot": "No account needed. Just click the button and speak naturally.",
        },
        "fr": {
            "subject": "Invitation à un entretien de recherche",
            "heading": "Vous êtes invité·e à participer",
            "body": "{sender_name} vous invite à un entretien vocal sur <strong>{project_name}</strong>. Cela prend environ 15 à 30 minutes et se déroule entièrement dans votre navigateur.",
            "cta": "Commencer l'entretien",
            "foot": "Aucun compte requis. Cliquez simplement sur le bouton et parlez naturellement.",
        },
    },
    "interview_magic": {
        "en": {
            "subject": "Your interview access link",
            "heading": "You're one click away",
            "body": "Click the button below to verify your email and start your interview.",
            "cta": "Start my interview →",
            "foot": "This link expires in {expiry_minutes} minutes. If you didn't request this, you can ignore this email.",
        },
        "fr": {
            "subject": "Votre lien d'accès à l'entretien",
            "heading": "Plus qu'un clic",
            "body": "Cliquez sur le bouton ci-dessous pour vérifier votre adresse email et démarrer l'entretien.",
            "cta": "Démarrer mon entretien →",
            "foot": "Ce lien expire dans {expiry_minutes} minutes. Si vous n'êtes pas à l'origine de cette demande, vous pouvez ignorer cet email.",
        },
    },
    "panel_join": {
        "en": {
            "subject": "Confirm your spot on the QualiPulse panel",
            "heading": "One click to join the panel",
            "body": "Thanks for signing up! Confirm your email to join the QualiPulse research panel. You'll be invited to paid studies that match your profile — most are short voice interviews you can do from any device.",
            "cta": "Confirm & join the panel →",
            "foot": "This link expires in 48 hours. If you didn't sign up, you can safely ignore this email — nothing is stored without your confirmation.",
        },
        "fr": {
            "subject": "Confirmez votre place sur le panel QualiPulse",
            "heading": "Un clic pour rejoindre le panel",
            "body": "Merci de votre inscription ! Confirmez votre email pour rejoindre le panel de recherche QualiPulse. Vous serez invité·e à des études rémunérées correspondant à votre profil — la plupart sont de courts entretiens vocaux, réalisables depuis n'importe quel appareil.",
            "cta": "Confirmer et rejoindre le panel →",
            "foot": "Ce lien expire dans 48 heures. Si vous n'êtes pas à l'origine de cette inscription, ignorez simplement cet email — rien n'est enregistré sans votre confirmation.",
        },
    },
    "panel_access": {
        "en": {
            "subject": "Get matched to more (paid) studies",
            "heading": "You're on the QualiPulse panel 🎉",
            "body": "Thanks for joining! The more you tell us about yourself, the more relevant — and paid — studies we can invite you to. Add a few details whenever you like, from any device.",
            "cta": "Add to my profile →",
            "foot": "Only you can use this link. You can update or opt out at any time.",
        },
        "fr": {
            "subject": "Soyez invité·e à plus d'études (rémunérées)",
            "heading": "Vous faites partie du panel QualiPulse 🎉",
            "body": "Merci de nous avoir rejoint ! Plus vous nous en dites sur vous, plus nous pourrons vous proposer d'études pertinentes — et rémunérées. Ajoutez quelques informations quand vous voulez, depuis n'importe quel appareil.",
            "cta": "Compléter mon profil →",
            "foot": "Ce lien n'est utilisable que par vous. Vous pouvez modifier vos informations ou vous désinscrire à tout moment.",
        },
    },
    "team_invite": {
        "en": {
            "subject": "{inviter_name} invited you to {workspace_name} on QualiPulse",
            "heading": "You've been invited to collaborate",
            "body1": "<strong>{inviter_name}</strong> has invited you to join <strong>{workspace_name}</strong> on QualiPulse as a <strong>{role}</strong>.",
            "body2": "QualiPulse is a research platform for running AI-driven voice interviews and turning transcripts into themes, quotes, and recommendations. You'll get access to all projects in the workspace.",
            "cta": "Accept invitation →",
            "foot": "This invitation expires in 7 days. If you weren't expecting it, you can safely ignore this email.",
        },
        "fr": {
            "subject": "{inviter_name} vous invite à {workspace_name} sur QualiPulse",
            "heading": "Vous êtes invité·e à collaborer",
            "body1": "<strong>{inviter_name}</strong> vous invite à rejoindre <strong>{workspace_name}</strong> sur QualiPulse en tant que <strong>{role}</strong>.",
            "body2": "QualiPulse est une plateforme de recherche pour mener des entretiens vocaux pilotés par l'IA et transformer les transcriptions en thèmes, citations et recommandations. Vous aurez accès à tous les projets de l'espace de travail.",
            "cta": "Accepter l'invitation →",
            "foot": "Cette invitation expire dans 7 jours. Si vous ne l'attendiez pas, vous pouvez ignorer cet email en toute sécurité.",
        },
    },
    "newsletter": {
        "en": {
            "subject": "Welcome to the QualiPulse newsletter",
            "heading": "You're on the list!",
            "body": "Thanks for subscribing. We'll send you occasional updates on qualitative research best practices, product updates, and tips for getting better insights from your interviews.",
            "foot": "No spam, ever. Unsubscribe anytime.",
        },
        "fr": {
            "subject": "Bienvenue dans la newsletter QualiPulse",
            "heading": "Vous êtes inscrit·e !",
            "body": "Merci pour votre abonnement. Nous vous enverrons occasionnellement des conseils sur les bonnes pratiques de la recherche qualitative, les nouveautés produit et des astuces pour tirer le meilleur de vos entretiens.",
            "foot": "Pas de spam, jamais. Désabonnement à tout moment.",
        },
    },
    "footer": {
        "en": {
            "tagline": "QualiPulse — AI-powered qualitative research",
            "reason": "You're receiving this because you signed up or were invited to QualiPulse.",
        },
        "fr": {
            "tagline": "QualiPulse — Recherche qualitative boostée à l'IA",
            "reason": "Vous recevez cet email parce que vous vous êtes inscrit·e ou avez été invité·e sur QualiPulse.",
        },
    },
    "usage_warning_80": {
        "en": {
            "subject": "{percent}% of your QualiPulse credits used",
            "heading": "You've used {percent}% of this month's credits",
            "body": "You've used <strong>{used} of {total}</strong> interview credits in your current period (ends {period_end}). Plan ahead so a great study doesn't run out of room.",
            "cta": "Manage billing",
            "portal": "Or manage your subscription directly",
        },
        "fr": {
            "subject": "{percent} % de vos crédits QualiPulse utilisés",
            "heading": "Vous avez utilisé {percent} % de vos crédits du mois",
            "body": "Vous avez utilisé <strong>{used} sur {total}</strong> crédits d'entretien sur la période en cours (jusqu'au {period_end}). Anticipez pour qu'une étude qui décolle ne soit pas bloquée.",
            "cta": "Gérer la facturation",
            "portal": "Ou gérez votre abonnement directement",
        },
    },
    "usage_warning_100": {
        "en": {
            "subject": "Your QualiPulse credits are exhausted",
            "heading": "Out of interview credits",
            "body": "You've used all <strong>{total}</strong> credits in your current period. New participants won't be able to start interviews until you upgrade or buy a credit pack.",
            "cta": "Buy more credits",
            "portal": "Or manage your subscription directly",
        },
        "fr": {
            "subject": "Vos crédits QualiPulse sont épuisés",
            "heading": "Plus de crédits d'entretien",
            "body": "Vous avez utilisé l'ensemble des <strong>{total}</strong> crédits sur la période en cours. Les nouveaux participants ne pourront pas démarrer d'entretien tant que vous n'aurez pas mis à niveau votre plan ou acheté un pack.",
            "cta": "Acheter des crédits",
            "portal": "Ou gérez votre abonnement directement",
        },
    },
}


def _c(section: str, lang: str, key: str, **fmt: object) -> str:
    """Look up a copy string, falling back to English, then format it."""
    lang = _normalise_lang(lang)
    block = _COPY.get(section, {})
    entry = block.get(lang) or block.get("en") or {}
    raw = entry.get(key, "")
    try:
        return raw.format(**fmt) if fmt else raw
    except (KeyError, IndexError):
        return raw


# ── Transport ───────────────────────────────────────────────────────────────


def _send_console(
    to: str,
    subject: str,
    body_html: str,
    body_text: Optional[str] = None,
    headers: Optional[dict[str, str]] = None,
) -> bool:
    """Development fallback — prints email to console. Always 'succeeds'."""
    logger.info(
        "📧 [EMAIL — not sent in dev] To: %s | Subject: %s",
        to,
        subject,
    )
    return True


def _send_sendgrid(
    to: str,
    subject: str,
    body_html: str,
    body_text: Optional[str] = None,
    headers: Optional[dict[str, str]] = None,
) -> bool:
    """Send via SendGrid. Returns True on HTTP 2xx, False otherwise.

    Any exception (missing SDK, network failure, bad API key, rejected
    recipient, etc.) is logged with ``logger.exception`` so the stack
    trace lands in Cloud Run logs — otherwise a silent swallow here
    caused participants to see "link sent" while nothing was actually
    delivered.

    ``body_text`` is the plain-text multipart alternative. If omitted
    we derive one from ``body_html`` via :func:`_html_to_text`, so
    callers never accidentally ship an HTML-only email.
    """
    try:
        import sendgrid  # type: ignore
        from sendgrid.helpers.mail import Mail, ReplyTo  # type: ignore
    except Exception as exc:  # pragma: no cover - import guard
        logger.exception("SendGrid SDK import failed: %s", exc)
        return False

    if not body_text:
        body_text = _html_to_text(body_html)

    try:
        sg = sendgrid.SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)
        message = Mail(
            from_email=(settings.EMAIL_FROM, settings.EMAIL_FROM_NAME),
            to_emails=to,
            subject=subject,
            plain_text_content=body_text,
            html_content=body_html,
        )
        message.reply_to = ReplyTo("support@qualipulse.com", "QualiPulse Support")

        # Custom headers (List-Unsubscribe, etc.). SendGrid's helper uses
        # a Header object keyed on name→value, added via add_header.
        for name, value in (headers or {}).items():
            try:
                from sendgrid.helpers.mail import Header  # type: ignore

                message.add_header(Header(name, value))
            except Exception:
                # If the SDK version doesn't expose Header, fall back to
                # the dict-style API that older versions accept.
                message.header = {name: value}  # type: ignore[attr-defined]

        response = sg.send(message)
        status_code = getattr(response, "status_code", None)
        if status_code is None or not (200 <= int(status_code) < 300):
            logger.error(
                "SendGrid rejected email to %s (subject=%r, status=%s, body=%s)",
                to,
                subject,
                status_code,
                getattr(response, "body", b"")[:500],
            )
            return False
        logger.info(
            "Email sent to %s (subject=%r, status=%s)", to, subject, status_code
        )
        return True
    except Exception as exc:
        logger.exception(
            "SendGrid send failed for %s (subject=%r): %s", to, subject, exc
        )
        return False


def send_email(
    to: str,
    subject: str,
    body_html: str,
    body_text: Optional[str] = None,
    email_type: str = "transactional",
) -> bool:
    """Dispatch email via the configured provider. Returns delivery status.

    ``email_type`` picks the ``List-Unsubscribe`` header flavour
    (``"transactional"`` or ``"marketing"``). All outgoing mail gets the
    header — Gmail rewards its presence even on transactional mail.
    """
    headers = _unsubscribe_headers(email_type)
    if settings.SENDGRID_API_KEY:
        return _send_sendgrid(to, subject, body_html, body_text, headers)
    return _send_console(to, subject, body_html, body_text, headers)


# ── Shared email wrapper ──────────────────────────────────────────────────


def _wrap_email(content: str, lang: str = "en") -> str:
    """Wrap content in a branded email template."""
    lang = _normalise_lang(lang)
    tagline = _c("footer", lang, "tagline")
    reason = _c("footer", lang, "reason")
    return f"""
    <!DOCTYPE html>
    <html lang="{lang}">
    <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
    <body style="margin:0;padding:0;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
      <div style="max-width:560px;margin:0 auto;padding:40px 24px;">
        <div style="text-align:center;margin-bottom:32px;">
          <span style="font-size:1.2rem;font-weight:700;color:#4f46e5;letter-spacing:-0.3px;">QualiPulse</span>
        </div>
        <div style="background:#fff;border-radius:12px;border:1px solid #e2e8f0;padding:32px;margin-bottom:24px;">
          {content}
        </div>
        <div style="text-align:center;font-size:0.75rem;color:#94a3b8;">
          <p>{tagline}</p>
          <p>{reason}</p>
        </div>
      </div>
    </body>
    </html>
    """


# ── Template helpers ────────────────────────────────────────────────────────


def send_welcome(to: str, name: str, lang: str = "en") -> bool:
    lang = _normalise_lang(lang)
    content = f"""
      <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">{_c("welcome", lang, "heading", name=name)}</h2>
      <p style="color:#475569;line-height:1.6;margin:0 0 24px;">{_c("welcome", lang, "body")}</p>
      <div style="text-align:center;margin:24px 0;">
        <a href="{settings.APP_BASE_URL}/dashboard" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:600;font-size:0.9rem;">{_c("welcome", lang, "cta")}</a>
      </div>
      <p style="color:#94a3b8;font-size:0.85rem;margin:0;">{_c("welcome", lang, "foot")}</p>
    """
    return send_email(
        to=to,
        subject=_c("welcome", lang, "subject"),
        body_html=_wrap_email(content, lang),
    )


def send_verification_email(to: str, name: str, verify_url: str, lang: str = "en") -> bool:
    """Send the "confirm your email" message.

    The HTML body is intentionally chunkier than most transactional mails.
    Short HTML-only emails trigger Gmail/Outlook's template-heuristic spam
    filters (high chrome-to-content ratio), and users — who were burned
    by the terse earlier version — need to understand *why* they're being
    asked to click. The explicit raw URL block below the button also
    gives the plain-text alternative real content so SpamAssassin's
    ``MIME_HTML_ONLY`` check doesn't fire.
    """
    lang = _normalise_lang(lang)
    # Use only the first word of whatever was passed (usually "Jean Dupont"
    # or a business name like "Leclerc SARL") so the greeting feels human.
    friendly_name = (name or "").strip().split()[0] if name else "there"
    content = f"""
      <h2 style="margin:0 0 12px;font-size:1.35rem;color:#0f172a;line-height:1.3;">{_c("verification", lang, "heading", name=friendly_name)}</h2>
      <p style="color:#475569;line-height:1.6;margin:0 0 24px;">{_c("verification", lang, "body")}</p>
      <div style="text-align:center;margin:28px 0;">
        <a href="{verify_url}" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:14px 32px;border-radius:8px;font-weight:600;font-size:1rem;">{_c("verification", lang, "cta")}</a>
      </div>
      <p style="color:#64748b;font-size:0.85rem;line-height:1.6;margin:0 0 8px;">{_c("verification", lang, "subfoot")}</p>
      <p style="background:#f1f5f9;border-radius:6px;padding:10px 12px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:0.78rem;color:#475569;word-break:break-all;margin:0 0 24px;">{verify_url}</p>
      <p style="color:#94a3b8;font-size:0.8rem;margin:0;line-height:1.6;">{_c("verification", lang, "foot")}</p>
    """
    return send_email(
        to=to,
        subject=_c("verification", lang, "subject"),
        body_html=_wrap_email(content, lang),
    )


def send_password_reset(to: str, reset_url: str, lang: str = "en") -> bool:
    lang = _normalise_lang(lang)
    content = f"""
      <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">{_c("password_reset", lang, "heading")}</h2>
      <p style="color:#475569;line-height:1.6;margin:0 0 24px;">{_c("password_reset", lang, "body")}</p>
      <div style="text-align:center;margin:24px 0;">
        <a href="{reset_url}" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:600;font-size:0.9rem;">{_c("password_reset", lang, "cta")}</a>
      </div>
      <p style="color:#94a3b8;font-size:0.85rem;margin:0;">{_c("password_reset", lang, "foot")}</p>
    """
    return send_email(
        to=to,
        subject=_c("password_reset", lang, "subject"),
        body_html=_wrap_email(content, lang),
    )


def send_google_link_notice(to: str, lang: str = "en") -> bool:
    """Security notice: a Google identity was just linked to this
    (previously password-only) account. Inline copy — this is a security
    notice, not marketing, so it stays deliberately plain."""
    lang = _normalise_lang(lang)
    if lang == "fr":
        subject = "Connexion Google ajoutée à votre compte QualiPulse"
        heading = "Connexion Google activée"
        body = (
            "Un compte Google vient d'être associé à votre compte QualiPulse. "
            "Vous pouvez désormais vous connecter avec Google en plus de votre mot de passe."
        )
        foot = (
            "Si vous n'êtes pas à l'origine de cette action, réinitialisez votre "
            "mot de passe immédiatement et contactez le support."
        )
    else:
        subject = "Google Sign-In was added to your QualiPulse account"
        heading = "Google Sign-In enabled"
        body = (
            "A Google account was just linked to your QualiPulse account. "
            "You can now sign in with Google in addition to your password."
        )
        foot = (
            "If this wasn't you, reset your password immediately and contact support."
        )
    content = f"""
      <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">{heading}</h2>
      <p style="color:#475569;line-height:1.6;margin:0 0 24px;">{body}</p>
      <p style="color:#94a3b8;font-size:0.85rem;margin:0;">{foot}</p>
    """
    return send_email(to=to, subject=subject, body_html=_wrap_email(content, lang))


def send_analysis_ready(to: str, project_name: str, project_url: str, lang: str = "en") -> bool:
    lang = _normalise_lang(lang)
    content = f"""
      <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">{_c("analysis_ready", lang, "heading")}</h2>
      <p style="color:#475569;line-height:1.6;margin:0 0 24px;">{_c("analysis_ready", lang, "body", project_name=project_name)}</p>
      <div style="text-align:center;margin:24px 0;">
        <a href="{project_url}" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:600;font-size:0.9rem;">{_c("analysis_ready", lang, "cta")}</a>
      </div>
    """
    return send_email(
        to=to,
        subject=_c("analysis_ready", lang, "subject", project_name=project_name),
        body_html=_wrap_email(content, lang),
    )


def send_free_preview_full(
    to: str,
    project_name: str,
    project_url: str,
    lang: str = "en",
) -> bool:
    """V4 paywall milestone — fires when the workspace's 3rd
    participant completes. Acknowledges the free-tier value delivered
    and pitches the unlock path for further transcripts."""
    lang = _normalise_lang(lang)
    content = f"""
      <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">{_c("free_preview_full", lang, "heading")}</h2>
      <p style="color:#475569;line-height:1.6;margin:0 0 24px;">{_c("free_preview_full", lang, "body", project_name=project_name)}</p>
      <div style="text-align:center;margin:24px 0;">
        <a href="{project_url}" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:600;font-size:0.9rem;">{_c("free_preview_full", lang, "cta")}</a>
      </div>
      <p style="color:#94a3b8;font-size:0.85rem;line-height:1.55;margin:24px 0 0;">{_c("free_preview_full", lang, "foot")}</p>
    """
    return send_email(
        to=to,
        subject=_c("free_preview_full", lang, "subject"),
        body_html=_wrap_email(content, lang),
    )


def send_first_response_in(
    to: str,
    project_name: str,
    project_url: str,
    lang: str = "en",
) -> bool:
    """Fires once company-wide, the first time any participant completes
    an interview. Pulls the researcher back into the product at the
    precise moment they can act — listen, tag, take a note — and turns
    "study created" into "study with insight"."""
    lang = _normalise_lang(lang)
    content = f"""
      <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">{_c("first_response_in", lang, "heading")}</h2>
      <p style="color:#475569;line-height:1.6;margin:0 0 24px;">{_c("first_response_in", lang, "body", project_name=project_name)}</p>
      <div style="text-align:center;margin:24px 0;">
        <a href="{project_url}" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:600;font-size:0.9rem;">{_c("first_response_in", lang, "cta")}</a>
      </div>
      <p style="color:#94a3b8;font-size:0.85rem;line-height:1.55;margin:24px 0 0;">{_c("first_response_in", lang, "foot")}</p>
    """
    return send_email(
        to=to,
        subject=_c("first_response_in", lang, "subject", project_name=project_name),
        body_html=_wrap_email(content, lang),
    )


def send_day_1_followup(
    to: str,
    study_name: str,
    project_url: str,
    lang: str = "en",
) -> bool:
    """Wave 3B — 18h after signup. One concrete action: share the
    interview link with one real participant."""
    lang = _normalise_lang(lang)
    content = f"""
      <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">{_c("day_1_followup", lang, "heading")}</h2>
      <p style="color:#475569;line-height:1.6;margin:0 0 24px;">{_c("day_1_followup", lang, "body", study_name=study_name)}</p>
      <div style="text-align:center;margin:24px 0;">
        <a href="{project_url}" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:600;font-size:0.9rem;">{_c("day_1_followup", lang, "cta")}</a>
      </div>
      <p style="color:#94a3b8;font-size:0.85rem;line-height:1.55;margin:24px 0 0;">{_c("day_1_followup", lang, "foot")}</p>
    """
    return send_email(
        to=to,
        subject=_c("day_1_followup", lang, "subject"),
        body_html=_wrap_email(content, lang),
    )


def send_trial_half_over(
    to: str,
    *,
    days_left: int,
    interviews_run: int,
    plan_name: str | None,
    plan_monthly: str | None,
    project_url: str,
    lang: str = "en",
) -> bool:
    """Wave 3B — Day 7 of a 14-day trial. Personalised by usage so far
    + soft-plan-suggest based on company size."""
    lang = _normalise_lang(lang)
    if interviews_run > 0:
        usage_line_en = (
            f"You've run {interviews_run} interview"
            f"{'s' if interviews_run != 1 else ''} so far — nice."
        )
        usage_line_fr = (
            f"Vous avez lancé {interviews_run} entretien"
            f"{'s' if interviews_run != 1 else ''} jusqu'ici — bravo."
        )
    else:
        usage_line_en = "You haven't run an interview yet — now's the time."
        usage_line_fr = (
            "Vous n'avez pas encore lancé d'entretien — c'est le moment."
        )
    usage_line = usage_line_en if lang == "en" else usage_line_fr

    if plan_name and plan_monthly:
        plan_line_en = (
            f"The {plan_name} plan ({plan_monthly}/mo) fits a team your size."
        )
        plan_line_fr = (
            f"Le plan {plan_name} ({plan_monthly}/mois) correspond à une "
            f"équipe de votre taille."
        )
        plan_line = plan_line_en if lang == "en" else plan_line_fr
    else:
        plan_line = "" if lang == "en" else ""

    content = f"""
      <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">{_c("trial_half_over", lang, "heading", days_left=days_left)}</h2>
      <p style="color:#475569;line-height:1.6;margin:0 0 24px;">{_c("trial_half_over", lang, "body", days_left=days_left, usage_line=usage_line)}</p>
      <div style="text-align:center;margin:24px 0;">
        <a href="{project_url}" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:600;font-size:0.9rem;">{_c("trial_half_over", lang, "cta")}</a>
      </div>
      <p style="color:#94a3b8;font-size:0.85rem;line-height:1.55;margin:24px 0 0;">{_c("trial_half_over", lang, "foot", plan_line=plan_line)}</p>
    """
    return send_email(
        to=to,
        subject=_c("trial_half_over", lang, "subject"),
        body_html=_wrap_email(content, lang),
    )


def send_trial_ending(
    to: str,
    *,
    days_left: int,
    interviews_run: int,
    plan_name: str | None,
    plan_monthly: str | None,
    billing_url: str,
    lang: str = "en",
) -> bool:
    """Wave 3B — Day 12 of a 14-day trial. Last warm nudge before the
    paywall lands. Always mentions the credit-pack alternative."""
    lang = _normalise_lang(lang)
    interviews_plural = "s" if interviews_run != 1 else ""

    if plan_name and plan_monthly:
        plan_line_en = (
            f"For your team size we'd suggest the {plan_name} plan "
            f"({plan_monthly}/mo)."
        )
        plan_line_fr = (
            f"Pour la taille de votre équipe, nous suggérons le plan "
            f"{plan_name} ({plan_monthly}/mois)."
        )
        plan_line = plan_line_en if lang == "en" else plan_line_fr
    else:
        plan_line = ""

    content = f"""
      <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">{_c("trial_ending", lang, "heading")}</h2>
      <p style="color:#475569;line-height:1.6;margin:0 0 24px;">{_c("trial_ending", lang, "body", days_left=days_left, interviews=interviews_run, interviews_plural=interviews_plural)}</p>
      <div style="text-align:center;margin:24px 0;">
        <a href="{billing_url}" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:600;font-size:0.9rem;">{_c("trial_ending", lang, "cta")}</a>
      </div>
      <p style="color:#94a3b8;font-size:0.85rem;line-height:1.55;margin:24px 0 0;">{_c("trial_ending", lang, "foot", plan_line=plan_line)}</p>
    """
    return send_email(
        to=to,
        subject=_c("trial_ending", lang, "subject", days_left=days_left),
        body_html=_wrap_email(content, lang),
    )


def send_usage_warning(
    to: str,
    *,
    percent: int,
    used: int,
    total: int,
    period_end: str,
    billing_url: str,
    lang: str = "en",
    portal_url: str | None = None,
) -> bool:
    """Send the 80% or 100% credit-usage warning email.

    ``percent`` selects the template (any value < 100 → ``usage_warning_80``,
    100+ → ``usage_warning_100``). ``period_end`` should already be a
    locale-friendly date string (the caller formats it).

    ``portal_url`` is the Stripe Customer Portal login page. Pass it only
    for workspaces that actually have a Stripe customer: for anyone else
    Stripe accepts the email and sends nothing, which reads as broken.
    """
    lang = _normalise_lang(lang)
    template_key = "usage_warning_100" if percent >= 100 else "usage_warning_80"
    portal_block = ""
    if portal_url:
        portal_block = f"""
      <p style="text-align:center;color:#94a3b8;font-size:0.85rem;margin:0 0 8px;">
        {_c(template_key, lang, "portal")}:
        <a href="{portal_url}" style="color:#4f46e5;text-decoration:underline;">{portal_url}</a>
      </p>
    """
    content = f"""
      <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">{_c(template_key, lang, "heading", percent=percent, used=used, total=total, period_end=period_end)}</h2>
      <p style="color:#475569;line-height:1.6;margin:0 0 24px;">{_c(template_key, lang, "body", percent=percent, used=used, total=total, period_end=period_end)}</p>
      <div style="text-align:center;margin:24px 0;">
        <a href="{billing_url}" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:600;font-size:0.9rem;">{_c(template_key, lang, "cta")}</a>
      </div>
      {portal_block}
    """
    return send_email(
        to=to,
        subject=_c(template_key, lang, "subject", percent=percent, used=used, total=total, period_end=period_end),
        body_html=_wrap_email(content, lang),
    )


def send_interview_invite(
    to: str,
    project_name: str,
    interview_url: str,
    sender_name: str,
    lang: str = "en",
) -> bool:
    lang = _normalise_lang(lang)
    content = f"""
      <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">{_c("interview_invite", lang, "heading")}</h2>
      <p style="color:#475569;line-height:1.6;margin:0 0 24px;">{_c("interview_invite", lang, "body", sender_name=sender_name, project_name=project_name)}</p>
      <div style="text-align:center;margin:24px 0;">
        <a href="{interview_url}" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:600;font-size:0.9rem;">{_c("interview_invite", lang, "cta")}</a>
      </div>
      <p style="color:#94a3b8;font-size:0.85rem;margin:0;">{_c("interview_invite", lang, "foot")}</p>
    """
    return send_email(
        to=to,
        subject=_c("interview_invite", lang, "subject"),
        body_html=_wrap_email(content, lang),
    )


def send_interview_magic_link(
    email: str,
    magic_url: str,
    expiry_minutes: int = 30,
    lang: str = "en",
) -> bool:
    lang = _normalise_lang(lang)
    content = f"""
      <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">{_c("interview_magic", lang, "heading")}</h2>
      <p style="color:#475569;line-height:1.6;margin:0 0 24px;">{_c("interview_magic", lang, "body")}</p>
      <div style="text-align:center;margin:32px 0;">
        <a href="{magic_url}" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:14px 28px;border-radius:8px;font-weight:600;font-size:1rem;">
          {_c("interview_magic", lang, "cta")}
        </a>
      </div>
      <p style="color:#94a3b8;font-size:0.8rem;margin:0;">
        {_c("interview_magic", lang, "foot", expiry_minutes=expiry_minutes)}
      </p>
    """
    return send_email(
        to=email,
        subject=_c("interview_magic", lang, "subject"),
        body_html=_wrap_email(content, lang),
    )


def send_panel_join_confirm(email: str, token: str, lang: str = "en") -> bool:
    """Double-opt-in confirmation for a public panel signup. Consent is only
    recorded when the link is clicked. The token rides in the URL fragment
    (never sent to the server in logs)."""
    lang = _normalise_lang(lang)
    confirm_url = f"{settings.APP_BASE_URL}/panel/confirm#token={token}"
    content = f"""
      <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">{_c("panel_join", lang, "heading")}</h2>
      <p style="color:#475569;line-height:1.6;margin:0 0 24px;">{_c("panel_join", lang, "body")}</p>
      <div style="text-align:center;margin:32px 0;">
        <a href="{confirm_url}" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:14px 28px;border-radius:8px;font-weight:600;font-size:1rem;">
          {_c("panel_join", lang, "cta")}
        </a>
      </div>
      <p style="color:#94a3b8;font-size:0.8rem;margin:0;">{_c("panel_join", lang, "foot")}</p>
    """
    return send_email(
        to=email,
        subject=_c("panel_join", lang, "subject"),
        body_html=_wrap_email(content, lang),
    )


def send_panel_access_link(email: str, token: str, lang: str = "en") -> bool:
    """Durable 'manage your panel profile' link for a consented panelist. The
    token rides in the URL fragment (never sent to the server in logs)."""
    lang = _normalise_lang(lang)
    panel_url = f"{settings.APP_BASE_URL}/panel#token={token}"
    content = f"""
      <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">{_c("panel_access", lang, "heading")}</h2>
      <p style="color:#475569;line-height:1.6;margin:0 0 24px;">{_c("panel_access", lang, "body")}</p>
      <div style="text-align:center;margin:32px 0;">
        <a href="{panel_url}" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:14px 28px;border-radius:8px;font-weight:600;font-size:1rem;">
          {_c("panel_access", lang, "cta")}
        </a>
      </div>
      <p style="color:#94a3b8;font-size:0.8rem;margin:0;">{_c("panel_access", lang, "foot")}</p>
    """
    return send_email(
        to=email,
        subject=_c("panel_access", lang, "subject"),
        body_html=_wrap_email(content, lang),
    )


def send_team_invite(
    to: str,
    *,
    workspace_name: str,
    inviter_name: str,
    role: str,
    accept_url: str,
    lang: str = "en",
) -> bool:
    """Invite someone to join a workspace as a team member."""
    lang = _normalise_lang(lang)
    content = f"""
      <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">{_c("team_invite", lang, "heading")}</h2>
      <p style="color:#475569;line-height:1.6;margin:0 0 16px;">
        {_c("team_invite", lang, "body1", inviter_name=inviter_name, workspace_name=workspace_name, role=role)}
      </p>
      <p style="color:#475569;line-height:1.6;margin:0 0 24px;">
        {_c("team_invite", lang, "body2")}
      </p>
      <div style="text-align:center;margin:32px 0;">
        <a href="{accept_url}" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:14px 28px;border-radius:8px;font-weight:600;font-size:1rem;">
          {_c("team_invite", lang, "cta")}
        </a>
      </div>
      <p style="color:#94a3b8;font-size:0.8rem;margin:0;">
        {_c("team_invite", lang, "foot")}
      </p>
    """
    return send_email(
        to=to,
        subject=_c(
            "team_invite",
            lang,
            "subject",
            inviter_name=inviter_name,
            workspace_name=workspace_name,
        ),
        body_html=_wrap_email(content, lang),
    )


def send_personalized_welcome(
    to: str,
    name: str,
    *,
    first_name: str | None = None,
    last_name: str | None = None,
    company_name: str | None = None,
    role_title: str | None = None,
    occupation_description: str | None = None,
    industry: str | None = None,
    selected_use_cases: list[str] | None = None,
    lang: str = "en",
    company_id: str | None = None,
) -> bool:
    """Send a Claude-generated personalised welcome email after onboarding.

    Falls back to the generic ``send_welcome`` if generation fails so the
    user always receives *something*.
    """
    lang = _normalise_lang(lang)
    try:
        from app.services.welcome_email_generator import generate_personalized_welcome

        body_html = generate_personalized_welcome(
            first_name=first_name,
            last_name=last_name,
            company_name=company_name,
            role_title=role_title,
            occupation_description=occupation_description,
            industry=industry,
            selected_use_cases=selected_use_cases,
            language=lang,
            company_id=company_id,
        )
        if not body_html:
            raise ValueError("Generator returned empty body")
    except Exception as exc:
        logger.warning(
            "Personalized welcome generation failed for %s, falling back: %s",
            to,
            exc,
        )
        return send_welcome(to, name, lang=lang)

    subject_map = {
        "en": "Your research brief is ready",
        "fr": "Votre brief recherche est pr\u00eat",
    }
    subject = subject_map.get(lang, subject_map["en"])

    return send_email(
        to=to,
        subject=subject,
        body_html=_wrap_email(body_html, lang),
    )


def send_newsletter_welcome(to: str, lang: str = "en") -> bool:
    lang = _normalise_lang(lang)
    content = f"""
      <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">{_c("newsletter", lang, "heading")}</h2>
      <p style="color:#475569;line-height:1.6;margin:0 0 16px;">{_c("newsletter", lang, "body")}</p>
      <p style="color:#94a3b8;font-size:0.85rem;margin:0;">{_c("newsletter", lang, "foot")}</p>
    """
    return send_email(
        to=to,
        subject=_c("newsletter", lang, "subject"),
        body_html=_wrap_email(content, lang),
        email_type="marketing",
    )


# ── Affiliate program ───────────────────────────────────────────────────────


def _fmt_eur(amount: float, lang: str) -> str:
    """€12.50 (en) / 12,50 € (fr) — the program pays in euros."""
    if lang == "fr":
        return f"{amount:.2f}".replace(".", ",") + " €"
    return f"€{amount:.2f}"


def send_affiliate_application_received(to: str, name: str, lang: str = "en") -> bool:
    lang = _normalise_lang(lang)
    content = f"""
      <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">{_c("affiliate_received", lang, "heading", name=name)}</h2>
      <p style="color:#475569;line-height:1.6;margin:0 0 24px;">{_c("affiliate_received", lang, "body")}</p>
      <p style="color:#94a3b8;font-size:0.85rem;margin:0;">{_c("affiliate_received", lang, "foot")}</p>
    """
    return send_email(
        to=to,
        subject=_c("affiliate_received", lang, "subject"),
        body_html=_wrap_email(content, lang),
    )


def send_affiliate_approved(
    to: str,
    name: str,
    referral_link: str,
    dashboard_url: str,
    commission_pct: float,
    lang: str = "en",
) -> bool:
    lang = _normalise_lang(lang)
    commission = f"{commission_pct:g}"
    content = f"""
      <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">{_c("affiliate_approved", lang, "heading", name=name)}</h2>
      <p style="color:#475569;line-height:1.6;margin:0 0 16px;">{_c("affiliate_approved", lang, "body", commission=commission)}</p>
      <p style="color:#475569;line-height:1.6;margin:0 0 4px;font-weight:600;">{_c("affiliate_approved", lang, "link_label")}</p>
      <p style="background:#f1f5f9;border-radius:8px;padding:12px 16px;font-family:monospace;font-size:0.85rem;color:#0f172a;word-break:break-all;margin:0 0 24px;">{referral_link}</p>
      <div style="text-align:center;margin:24px 0;">
        <a href="{dashboard_url}" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:600;font-size:0.9rem;">{_c("affiliate_approved", lang, "cta")}</a>
      </div>
      <p style="color:#94a3b8;font-size:0.85rem;margin:0;">{_c("affiliate_approved", lang, "foot")}</p>
    """
    return send_email(
        to=to,
        subject=_c("affiliate_approved", lang, "subject"),
        body_html=_wrap_email(content, lang),
    )


def send_affiliate_rejected(to: str, name: str, lang: str = "en") -> bool:
    lang = _normalise_lang(lang)
    content = f"""
      <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">{_c("affiliate_rejected", lang, "heading", name=name)}</h2>
      <p style="color:#475569;line-height:1.6;margin:0 0 24px;">{_c("affiliate_rejected", lang, "body")}</p>
      <p style="color:#94a3b8;font-size:0.85rem;margin:0;">{_c("affiliate_rejected", lang, "foot")}</p>
    """
    return send_email(
        to=to,
        subject=_c("affiliate_rejected", lang, "subject"),
        body_html=_wrap_email(content, lang),
    )


def send_affiliate_magic_link(
    to: str,
    magic_url: str,
    expiry_minutes: int = 30,
    lang: str = "en",
) -> bool:
    lang = _normalise_lang(lang)
    content = f"""
      <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">{_c("affiliate_magic", lang, "heading")}</h2>
      <p style="color:#475569;line-height:1.6;margin:0 0 24px;">{_c("affiliate_magic", lang, "body")}</p>
      <div style="text-align:center;margin:24px 0;">
        <a href="{magic_url}" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:600;font-size:0.9rem;">{_c("affiliate_magic", lang, "cta")}</a>
      </div>
      <p style="color:#94a3b8;font-size:0.85rem;margin:0;">{_c("affiliate_magic", lang, "foot", expiry_minutes=expiry_minutes)}</p>
    """
    return send_email(
        to=to,
        subject=_c("affiliate_magic", lang, "subject"),
        body_html=_wrap_email(content, lang),
    )


def send_affiliate_conversion(
    to: str,
    amount_eur: float,
    pending_eur: float,
    threshold_eur: float,
    dashboard_url: str,
    lang: str = "en",
) -> bool:
    lang = _normalise_lang(lang)
    amount = _fmt_eur(amount_eur, lang)
    pending = _fmt_eur(pending_eur, lang)
    threshold = _fmt_eur(threshold_eur, lang)
    content = f"""
      <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">{_c("affiliate_conversion", lang, "heading")}</h2>
      <p style="color:#475569;line-height:1.6;margin:0 0 24px;">{_c("affiliate_conversion", lang, "body", amount=amount, pending=pending)}</p>
      <div style="text-align:center;margin:24px 0;">
        <a href="{dashboard_url}" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:600;font-size:0.9rem;">{_c("affiliate_conversion", lang, "cta")}</a>
      </div>
      <p style="color:#94a3b8;font-size:0.85rem;margin:0;">{_c("affiliate_conversion", lang, "foot", threshold=threshold)}</p>
    """
    return send_email(
        to=to,
        subject=_c("affiliate_conversion", lang, "subject", amount=amount),
        body_html=_wrap_email(content, lang),
    )


def send_affiliate_payout(
    to: str,
    name: str,
    amount_eur: float,
    dashboard_url: str,
    lang: str = "en",
) -> bool:
    lang = _normalise_lang(lang)
    amount = _fmt_eur(amount_eur, lang)
    content = f"""
      <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">{_c("affiliate_payout", lang, "heading", name=name)}</h2>
      <p style="color:#475569;line-height:1.6;margin:0 0 24px;">{_c("affiliate_payout", lang, "body", amount=amount)}</p>
      <div style="text-align:center;margin:24px 0;">
        <a href="{dashboard_url}" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:600;font-size:0.9rem;">{_c("affiliate_payout", lang, "cta")}</a>
      </div>
      <p style="color:#94a3b8;font-size:0.85rem;margin:0;">{_c("affiliate_payout", lang, "foot")}</p>
    """
    return send_email(
        to=to,
        subject=_c("affiliate_payout", lang, "subject", amount=amount),
        body_html=_wrap_email(content, lang),
    )
