"""Slack webhook notification service.

Sends incoming-webhook-style messages to a company's Slack channel when
research events happen (analysis ready, interview completed, etc.).

Webhook URL format: https://hooks.slack.com/services/T.../B.../xxxx
The URL is set per-company in account settings.

All functions are fire-and-forget: failures are logged but never raised.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib import error, request

logger = logging.getLogger("auto_interview.slack")

_TIMEOUT = 5  # seconds — keep low so webhook failures can't stall a request


def _post(webhook_url: str, payload: dict[str, Any]) -> bool:
    """Send a JSON payload to a Slack webhook. Returns True on success."""
    if not webhook_url or not webhook_url.startswith("https://hooks.slack.com/"):
        logger.warning("Slack webhook URL missing or invalid, skipping post")
        return False
    try:
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=_TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            if resp.status == 200 and body.strip() == "ok":
                return True
            logger.warning("Slack webhook returned status=%s body=%s", resp.status, body[:200])
            return False
    except error.HTTPError as exc:
        logger.warning("Slack webhook HTTPError: %s", exc)
        return False
    except error.URLError as exc:
        logger.warning("Slack webhook URLError: %s", exc)
        return False
    except Exception as exc:  # pragma: no cover — defensive catch-all
        logger.warning("Slack webhook unexpected error: %s", exc)
        return False


def _is_fr(lang: str | None) -> bool:
    return bool(lang) and lang.lower().startswith("fr")


def send_test_message(webhook_url: str, *, lang: str | None = None) -> bool:
    """Post a test confirmation message. Used by Account Settings → Test button."""
    if _is_fr(lang):
        text = ":white_check_mark: QualiPulse est connecté à ce canal Slack."
        block_text = (
            ":white_check_mark: *QualiPulse est connecté !*\n"
            "Vous recevrez une notification ici dès qu'une analyse IA sera terminée."
        )
    else:
        text = ":white_check_mark: QualiPulse is connected to this Slack channel."
        block_text = (
            ":white_check_mark: *QualiPulse is connected!*\n"
            "You'll get a notification here whenever an AI analysis finishes."
        )
    payload = {
        "text": text,
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": block_text},
            },
        ],
    }
    return _post(webhook_url, payload)


def send_analysis_ready(
    webhook_url: str,
    *,
    project_name: str,
    project_url: str,
    participant_count: int,
    top_themes: list[str] | None = None,
    lang: str | None = None,
) -> bool:
    """Notify a channel that an AI analysis has just finished for a project."""
    themes = top_themes or []
    theme_lines = "\n".join(f"• {t}" for t in themes[:5]) if themes else ""

    if _is_fr(lang):
        text = (
            f":sparkles: Analyse prête pour *{project_name}* "
            f"({participant_count} participant{'s' if participant_count != 1 else ''})"
        )
        summary = (
            f":sparkles: *Analyse IA prête*\n"
            f"*Étude :* {project_name}\n"
            f"*Participants :* {participant_count}"
        )
        themes_title = "*Thèmes principaux*"
        button_label = "Ouvrir dans QualiPulse"
    else:
        text = (
            f":sparkles: Analysis ready for *{project_name}* "
            f"({participant_count} participant{'s' if participant_count != 1 else ''})"
        )
        summary = (
            f":sparkles: *AI analysis ready*\n"
            f"*Project:* {project_name}\n"
            f"*Participants:* {participant_count}"
        )
        themes_title = "*Top themes*"
        button_label = "Open in QualiPulse"

    blocks: list[dict[str, Any]] = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": summary},
        },
    ]

    if theme_lines:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"{themes_title}\n{theme_lines}"},
            }
        )

    blocks.append(
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": button_label},
                    "url": project_url,
                    "style": "primary",
                }
            ],
        }
    )

    return _post(webhook_url, {"text": text, "blocks": blocks})


def send_interview_completed(
    webhook_url: str,
    *,
    project_name: str,
    participant_name: str,
    project_url: str,
    lang: str | None = None,
) -> bool:
    """Notify when a participant finishes an interview. Kept for future use."""
    if _is_fr(lang):
        text = f":speech_balloon: Nouvel entretien terminé pour *{project_name}* par {participant_name}"
        summary = (
            f":speech_balloon: *Nouvelle réponse*\n"
            f"*Étude :* {project_name}\n"
            f"*Participant :* {participant_name}"
        )
        button_label = "Voir la transcription"
    else:
        text = f":speech_balloon: New interview completed for *{project_name}* by {participant_name}"
        summary = (
            f":speech_balloon: *New response*\n"
            f"*Project:* {project_name}\n"
            f"*Participant:* {participant_name}"
        )
        button_label = "View transcript"
    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": summary},
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": button_label},
                    "url": project_url,
                }
            ],
        },
    ]
    return _post(webhook_url, {"text": text, "blocks": blocks})
