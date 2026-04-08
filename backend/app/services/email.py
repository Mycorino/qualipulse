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
        from sendgrid.helpers.mail import Mail, ReplyTo  # type: ignore

        sg = sendgrid.SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)
        message = Mail(
            from_email=(settings.EMAIL_FROM, settings.EMAIL_FROM_NAME),
            to_emails=to,
            subject=subject,
            html_content=body_html,
        )
        message.reply_to = ReplyTo("support@qualipulse.com", "QualiPulse Support")
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


# ── Shared email wrapper ──────────────────────────────────────────────────

def _wrap_email(content: str) -> str:
    """Wrap content in a branded email template."""
    return f"""
    <!DOCTYPE html>
    <html>
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
          <p>QualiPulse — AI-powered qualitative research</p>
          <p>You're receiving this because you signed up or were invited to QualiPulse.</p>
        </div>
      </div>
    </body>
    </html>
    """


# ── Template helpers ────────────────────────────────────────────────────────

def send_welcome(to: str, name: str) -> None:
    send_email(
        to=to,
        subject="Welcome to QualiPulse",
        body_html=_wrap_email(f"""
          <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">Welcome, {name}!</h2>
          <p style="color:#475569;line-height:1.6;margin:0 0 24px;">Your QualiPulse account is ready. Start by creating your first research project.</p>
          <div style="text-align:center;margin:24px 0;">
            <a href="{settings.APP_BASE_URL}/dashboard" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:600;font-size:0.9rem;">Create your first project</a>
          </div>
          <p style="color:#94a3b8;font-size:0.85rem;margin:0;">Need help getting started? Just reply to this email.</p>
        """),
    )


def send_verification_email(to: str, name: str, verify_url: str) -> None:
    send_email(
        to=to,
        subject="Verify your QualiPulse email",
        body_html=_wrap_email(f"""
          <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">Verify your email</h2>
          <p style="color:#475569;line-height:1.6;margin:0 0 24px;">Hi {name}, please confirm your email address to complete your account setup.</p>
          <div style="text-align:center;margin:24px 0;">
            <a href="{verify_url}" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:600;font-size:0.9rem;">Verify email address</a>
          </div>
          <p style="color:#94a3b8;font-size:0.85rem;margin:0;">This link expires in 24 hours. If you didn't create an account, you can ignore this email.</p>
        """),
    )


def send_password_reset(to: str, reset_url: str) -> None:
    send_email(
        to=to,
        subject="Reset your QualiPulse password",
        body_html=_wrap_email(f"""
          <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">Reset your password</h2>
          <p style="color:#475569;line-height:1.6;margin:0 0 24px;">Click the button below to set a new password. This link expires in 1 hour.</p>
          <div style="text-align:center;margin:24px 0;">
            <a href="{reset_url}" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:600;font-size:0.9rem;">Reset password</a>
          </div>
          <p style="color:#94a3b8;font-size:0.85rem;margin:0;">If you didn't request this, you can safely ignore this email. Your password won't change.</p>
        """),
    )


def send_analysis_ready(to: str, project_name: str, project_url: str) -> None:
    send_email(
        to=to,
        subject=f"Analysis ready: {project_name}",
        body_html=_wrap_email(f"""
          <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">Your analysis is ready</h2>
          <p style="color:#475569;line-height:1.6;margin:0 0 24px;">The AI analysis for <strong>{project_name}</strong> has been completed. Themes, quotes, and recommendations are waiting for you.</p>
          <div style="text-align:center;margin:24px 0;">
            <a href="{project_url}" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:600;font-size:0.9rem;">View analysis</a>
          </div>
        """),
    )


def send_interview_invite(to: str, project_name: str, interview_url: str, sender_name: str) -> None:
    send_email(
        to=to,
        subject=f"You're invited to a research interview",
        body_html=_wrap_email(f"""
          <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">You're invited to participate</h2>
          <p style="color:#475569;line-height:1.6;margin:0 0 24px;">{sender_name} has invited you to a voice interview about <strong>{project_name}</strong>. It takes about 15-30 minutes and runs entirely in your browser.</p>
          <div style="text-align:center;margin:24px 0;">
            <a href="{interview_url}" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:600;font-size:0.9rem;">Start interview</a>
          </div>
          <p style="color:#94a3b8;font-size:0.85rem;margin:0;">No account needed. Just click the button and speak naturally.</p>
        """),
    )


def send_interview_magic_link(email: str, magic_url: str, expiry_minutes: int = 30) -> None:
    send_email(
        to=email,
        subject="Your interview access link",
        body_html=_wrap_email(f"""
          <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">You're one click away</h2>
          <p style="color:#475569;line-height:1.6;margin:0 0 24px;">Click the button below to verify your email and start your interview.</p>
          <div style="text-align:center;margin:32px 0;">
            <a href="{magic_url}" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:14px 28px;border-radius:8px;font-weight:600;font-size:1rem;">
              Start my interview →
            </a>
          </div>
          <p style="color:#94a3b8;font-size:0.8rem;margin:0;">
            This link expires in {expiry_minutes} minutes. If you didn't request this, you can ignore this email.
          </p>
        """),
    )


def send_newsletter_welcome(to: str) -> None:
    send_email(
        to=to,
        subject="Welcome to the QualiPulse newsletter",
        body_html=_wrap_email("""
          <h2 style="margin:0 0 8px;font-size:1.25rem;color:#0f172a;">You're on the list!</h2>
          <p style="color:#475569;line-height:1.6;margin:0 0 16px;">Thanks for subscribing. We'll send you occasional updates on qualitative research best practices, product updates, and tips for getting better insights from your interviews.</p>
          <p style="color:#94a3b8;font-size:0.85rem;margin:0;">No spam, ever. Unsubscribe anytime.</p>
        """),
    )
