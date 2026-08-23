"""Participant-facing link preview for interview links.

Interview links are shared with *participants*, over iMessage, WhatsApp,
Slack, email. Unfurled from the SPA shell they used to show the marketing
card ("Stop guessing what your users want"), which is copy aimed at the
researcher buying the product, not at the person being invited to speak.

The frontend nginx therefore routes `/i/{token}` and `/interview/{token}`
to `GET /interview/{token}/preview` **for link unfurlers only** (UA match);
real participants keep getting the untouched SPA. What we render here is a
small standalone document whose <head> carries participant-facing Open
Graph tags in the study's own language, plus a readable body in case a
human ever lands on it (the "open the interview" link carries `?app=1`,
which nginx never routes here, so there is no loop).

Rules:
- Every interpolated value is HTML-escaped. Study names are researcher
  input.
- No <script>: the API serves HTML under a strict CSP (see main.py) that
  allows inline <style> and nothing else.
- Anonymous studies (`branding_mode == "anonymous"`) must not leak who is
  running the research, exactly like `GET /interview/{token}` does.
"""

from __future__ import annotations

import html

_SUPPORTED_LANGS = ("en", "fr", "de", "es", "it", "pt")

# Participant-facing copy, one block per interview language. No em dashes
# (see the Copy Conventions section of CLAUDE.md).
_COPY: dict[str, dict[str, str]] = {
    "en": {
        "invite": "You're invited to a voice interview",
        "by": "{inviter} invites you to a voice interview.",
        "anonymous": "You're invited to take part in a research interview.",
        "duration": "It takes about {minutes} minutes and runs entirely in your browser.",
        "no_account": "No account, no download, just your microphone.",
        "cta": "Open the interview",
        "expired_title": "This interview link is no longer active",
        "expired_body": "Contact the researcher who shared it with you, they can send a new link.",
        "site": "Voice interview by QualiPulse",
    },
    "fr": {
        "invite": "Vous êtes invité·e à un entretien vocal",
        "by": "{inviter} vous invite à un entretien vocal.",
        "anonymous": "Vous êtes invité·e à participer à un entretien de recherche.",
        "duration": "Cela prend environ {minutes} minutes et se déroule entièrement dans votre navigateur.",
        "no_account": "Aucun compte, aucune installation, seulement votre micro.",
        "cta": "Ouvrir l'entretien",
        "expired_title": "Ce lien d'entretien n'est plus actif",
        "expired_body": "Contactez la personne qui vous l'a envoyé, elle peut vous transmettre un nouveau lien.",
        "site": "Entretien vocal avec QualiPulse",
    },
    "de": {
        "invite": "Sie sind zu einem Sprachinterview eingeladen",
        "by": "{inviter} lädt Sie zu einem Sprachinterview ein.",
        "anonymous": "Sie sind eingeladen, an einem Forschungsinterview teilzunehmen.",
        "duration": "Es dauert etwa {minutes} Minuten und läuft vollständig in Ihrem Browser.",
        "no_account": "Kein Konto, keine Installation, nur Ihr Mikrofon.",
        "cta": "Interview öffnen",
        "expired_title": "Dieser Interview-Link ist nicht mehr aktiv",
        "expired_body": "Wenden Sie sich an die Person, die ihn geteilt hat, sie kann Ihnen einen neuen Link schicken.",
        "site": "Sprachinterview mit QualiPulse",
    },
    "es": {
        "invite": "Te invitamos a una entrevista de voz",
        "by": "{inviter} te invita a una entrevista de voz.",
        "anonymous": "Te invitamos a participar en una entrevista de investigación.",
        "duration": "Dura unos {minutes} minutos y se realiza íntegramente en tu navegador.",
        "no_account": "Sin cuenta, sin instalación, solo tu micrófono.",
        "cta": "Abrir la entrevista",
        "expired_title": "Este enlace de entrevista ya no está activo",
        "expired_body": "Contacta con la persona que te lo envió, puede darte un enlace nuevo.",
        "site": "Entrevista de voz con QualiPulse",
    },
    "it": {
        "invite": "Sei invitato a un'intervista vocale",
        "by": "{inviter} ti invita a un'intervista vocale.",
        "anonymous": "Sei invitato a partecipare a un'intervista di ricerca.",
        "duration": "Dura circa {minutes} minuti e si svolge interamente nel browser.",
        "no_account": "Nessun account, nessuna installazione, basta il microfono.",
        "cta": "Apri l'intervista",
        "expired_title": "Questo link all'intervista non è più attivo",
        "expired_body": "Contatta chi te lo ha inviato, può mandarti un nuovo link.",
        "site": "Intervista vocale con QualiPulse",
    },
    "pt": {
        "invite": "Está convidado(a) para uma entrevista de voz",
        "by": "{inviter} convida-o(a) para uma entrevista de voz.",
        "anonymous": "Está convidado(a) a participar numa entrevista de investigação.",
        "duration": "Demora cerca de {minutes} minutos e decorre inteiramente no seu navegador.",
        "no_account": "Sem conta, sem instalação, apenas o seu microfone.",
        "cta": "Abrir a entrevista",
        "expired_title": "Este link de entrevista já não está ativo",
        "expired_body": "Contacte quem o partilhou consigo, pode enviar-lhe um novo link.",
        "site": "Entrevista de voz com QualiPulse",
    },
}

_OG_LOCALES = {
    "en": "en_US",
    "fr": "fr_FR",
    "de": "de_DE",
    "es": "es_ES",
    "it": "it_IT",
    "pt": "pt_PT",
}


def normalise_lang(lang: str | None) -> str:
    code = (lang or "").lower().split("-")[0].strip()
    return code if code in _SUPPORTED_LANGS else "en"


def _e(value: str | None) -> str:
    return html.escape(value or "", quote=True)


_STYLE = """
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100vh; display: flex; align-items: center;
         justify-content: center; padding: 32px;
         background: linear-gradient(135deg, #4369f5, #2d53e8); color: #fff;
         font-family: system-ui, -apple-system, 'Segoe UI', sans-serif; }
  .card { max-width: 560px; text-align: center; }
  .brand { font-size: 15px; font-weight: 600; letter-spacing: 0.04em;
           text-transform: uppercase; opacity: 0.75; margin: 0 0 20px; }
  h1 { font-size: 32px; line-height: 1.25; margin: 0 0 16px; }
  p { font-size: 17px; line-height: 1.6; margin: 0 0 8px; opacity: 0.92; }
  .cta { display: inline-block; margin-top: 28px; background: #fff; color: #2d53e8;
         text-decoration: none; font-weight: 600; font-size: 17px;
         padding: 14px 32px; border-radius: 10px; }
  @media (max-width: 480px) { h1 { font-size: 26px; } }
"""


def render_link_preview_html(
    *,
    lang: str,
    study_name: str | None,
    inviter: str | None,
    minutes: int | None,
    canonical_url: str,
    image_url: str,
    active: bool = True,
) -> str:
    """Standalone HTML whose head carries the participant-facing OG tags.

    `inviter` is the researcher or company name, already stripped by the
    caller for anonymous studies. `study_name` leads the card when present:
    it is the same participant-facing title the landing screen shows.
    """
    lang = normalise_lang(lang)
    c = _COPY[lang]

    if not active:
        title = c["expired_title"]
        description = c["expired_body"]
    else:
        title = study_name.strip() if study_name and study_name.strip() else c["invite"]
        lead = c["by"].format(inviter=inviter.strip()) if inviter and inviter.strip() else c["anonymous"]
        parts = [lead]
        if minutes:
            parts.append(c["duration"].format(minutes=minutes))
        parts.append(c["no_account"])
        description = " ".join(parts)

    body_cta = ""
    if active:
        # `?app=1` is the escape hatch: nginx only routes unfurler traffic
        # here and never when that param is set, so a human who somehow
        # landed on this page reaches the real interview instead of looping.
        separator = "&" if "?" in canonical_url else "?"
        body_cta = (
            f'<a class="cta" href="{_e(canonical_url + separator + "app=1")}">'
            f'{_e(c["cta"])}</a>'
        )

    return f"""<!DOCTYPE html>
<html lang="{_e(lang)}">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{_e(title)}</title>
<meta name="description" content="{_e(description)}" />
<meta name="robots" content="noindex, nofollow" />
<meta name="theme-color" content="#4369f5" />
<link rel="icon" type="image/svg+xml" href="/favicon.svg" />
<meta property="og:site_name" content="{_e(c['site'])}" />
<meta property="og:type" content="website" />
<meta property="og:locale" content="{_e(_OG_LOCALES[lang])}" />
<meta property="og:title" content="{_e(title)}" />
<meta property="og:description" content="{_e(description)}" />
<meta property="og:url" content="{_e(canonical_url)}" />
<meta property="og:image" content="{_e(image_url)}" />
<meta property="og:image:width" content="1200" />
<meta property="og:image:height" content="630" />
<meta property="og:image:alt" content="{_e(c['invite'])}" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="{_e(title)}" />
<meta name="twitter:description" content="{_e(description)}" />
<meta name="twitter:image" content="{_e(image_url)}" />
<style>{_STYLE}</style>
</head>
<body>
<div class="card">
  <p class="brand">QualiPulse</p>
  <h1>{_e(title)}</h1>
  <p>{_e(description)}</p>
  {body_cta}
</div>
</body>
</html>
"""
