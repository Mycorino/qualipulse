"""Suppression list — addresses we must stop emailing.

Fed by two sources:

* The SendGrid Event Webhook (``routers/email_events.py``) for hard
  bounces, drops, and spam reports.
* The one-click unsubscribe endpoint (RFC 8058) for recipient opt-outs.

Consulted by :func:`app.services.email.send_email` before every send.
Keeping this in our own table (rather than relying on SendGrid's internal
suppression list) means the decision is visible to the app: we can show it
in admin, reason about it in tests, and avoid burning an API call — and it
still works if we ever change ESP.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text

from app.database import Base


# Why an address is suppressed. The reason decides which mail is blocked —
# see ``services/email_suppression.is_suppressed``.
REASON_BOUNCE = "bounce"           # address does not exist; nothing is deliverable
REASON_SPAM_REPORT = "spam_report"  # recipient hit "report spam"
REASON_UNSUBSCRIBE = "unsubscribe"  # recipient opted out of bulk mail
REASON_MANUAL = "manual"            # support/admin added it by hand

ALL_REASONS = (
    REASON_BOUNCE,
    REASON_SPAM_REPORT,
    REASON_UNSUBSCRIBE,
    REASON_MANUAL,
)


class EmailSuppression(Base):
    """One row per suppressed address. ``email`` is unique and normalised.

    Rows are never silently overwritten: the first suppression wins, so a
    later unsubscribe can't downgrade an earlier hard bounce. Removal is a
    deliberate admin action (or a DELETE), not an automatic expiry.
    """

    __tablename__ = "email_suppressions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, nullable=False, unique=True, index=True)
    reason = Column(String, nullable=False)
    # Where the suppression came from: "sendgrid_webhook" | "recipient" | "admin".
    source = Column(String, nullable=False, default="sendgrid_webhook")
    # Raw provider payload (or a short note) for auditing a disputed suppression.
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<EmailSuppression {self.email} reason={self.reason}>"
