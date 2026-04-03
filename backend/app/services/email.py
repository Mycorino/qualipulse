"""
Email service — console logger in development, SendGrid in production.
To enable SendGrid: set SENDGRID_API_KEY in .env
"""
import logging

from app.config import settings

logger = logging.getLogger("auto_interview.email")


def _send_console(to: str, subject: str, body_html: str) -> None:
    """Development fallback — prints email to console."""
    logger.info(
        "📧 [EMAIL — not sent in dev] To: %s | Subject: %s",
        to,
        subject,
    )


def _send_sendgrid(to: str, subject: str, body_html: str) -> None:
    """Send via SendGrid. Requires SENDGRID_API_KEY."""
    try:
        import sendgrid  # type: ignore
        from sendgrid.helpers.mail import Mail  # type: ignore

        sg = sendgrid.SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)
        message = Mail(
            from_email=(settings.EMAIL_FROM, settings.EMAIL_FROM_NAME),
            to_emails=to,
            subject=subject,
            html_content=body_html,
        )
        sg.send(message)
        logger.info("Email sent to %s: %s", to, subject)
    except Exception as exc:
        logger.error("SendGrid error: %s", exc)


def send_email(to: str, subject: str, body_html: str) -> None:
    """Dispatch email via the configured provider."""
    if settings.SENDGRID_API_KEY:
        _send_sendgrid(to, subject, body_html)
    else:
        _send_console(to, subject, body_html)


# ── Template helpers ────────────────────────────────────────────────────────

def send_welcome(to: str, name: str) -> None:
    send_email(
        to=to,
        subject="Welcome to AutoInterview",
        body_html=f"""
        <p>Hi {name},</p>
        <p>Your AutoInterview account is ready. Start by creating your first project.</p>
        <p><a href="https://app.autointerview.com">Open AutoInterview →</a></p>
        """,
    )


def send_password_reset(to: str, reset_url: str) -> None:
    send_email(
        to=to,
        subject="Reset your AutoInterview password",
        body_html=f"""
        <p>Click the link below to reset your password. This link expires in 1 hour.</p>
        <p><a href="{reset_url}">Reset password →</a></p>
        <p>If you didn't request this, you can safely ignore this email.</p>
        """,
    )


def send_analysis_ready(to: str, project_name: str, project_url: str) -> None:
    send_email(
        to=to,
        subject=f"Analysis ready: {project_name}",
        body_html=f"""
        <p>Your AI analysis for <strong>{project_name}</strong> is ready to view.</p>
        <p><a href="{project_url}">View analysis →</a></p>
        """,
    )


def send_interview_invite(to: str, project_name: str, interview_url: str, sender_name: str) -> None:
    send_email(
        to=to,
        subject=f"You're invited to an interview: {project_name}",
        body_html=f"""
        <p>{sender_name} has invited you to participate in a research interview about <strong>{project_name}</strong>.</p>
        <p><a href="{interview_url}">Start interview →</a></p>
        <p>This is a voice interview that takes approximately 15-30 minutes.</p>
        """,
    )
