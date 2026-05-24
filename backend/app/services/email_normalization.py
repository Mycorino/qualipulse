"""Email canonicalization for de-duplication at signup.

Gmail-family providers (gmail.com + googlemail.com) treat
``alice+study1@gmail.com`` and ``alice@gmail.com`` as the same mailbox.
A motivated user can therefore harvest infinite "free" credit grants
by varying the +tag. We strip the +tag and lowercase the address
before the uniqueness check at signup.

We deliberately do NOT touch the local part for non-gmail providers —
some servers do treat ``user+x@`` as distinct (rare but real), and
breaking that would hurt deliverability for the long tail of
self-hosted business mail.

We also normalise dots in gmail local parts (``a.lice@gmail.com`` ==
``alice@gmail.com``), which is gmail's documented behaviour.
"""

from __future__ import annotations

from typing import Optional

# Providers where ``+`` aliasing is documented to route to the same
# mailbox. Keep this list conservative — false positives merge real
# distinct mailboxes which is a worse failure mode than missing some
# abuse.
_PLUS_ALIASING_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        # Microsoft consumer (Outlook, Hotmail, Live, MSN) all support
        # +aliasing per their docs.
        "outlook.com",
        "hotmail.com",
        "live.com",
        "msn.com",
        # iCloud documents +aliasing too.
        "icloud.com",
        "me.com",
        "mac.com",
        # Yahoo, Proton, Fastmail all support +aliasing.
        "yahoo.com",
        "ymail.com",
        "proton.me",
        "protonmail.com",
        "pm.me",
        "fastmail.com",
        "fastmail.fm",
    }
)

# Only gmail.com / googlemail.com strip dots in the local part — that's
# a documented gmail quirk specifically, not a general SMTP behaviour.
_GMAIL_DOTLESS_DOMAINS = frozenset({"gmail.com", "googlemail.com"})


def canonicalize_email(email: str | None) -> Optional[str]:
    """Return the deduplication-key form of an email address.

    - Lowercases the whole address.
    - For gmail / outlook / yahoo / proton / fastmail / icloud, strips
      everything from the first ``+`` to the ``@`` (alias tag).
    - For gmail specifically, also removes ``.`` from the local part.

    Returns ``None`` for malformed input — callers should treat that as
    "reject" at signup, not as "accept anything."
    """
    if not email:
        return None
    address = email.strip().lower()
    if "@" not in address or address.count("@") != 1:
        return None
    local, domain = address.rsplit("@", 1)
    if not local or not domain or "." not in domain:
        return None

    if domain in _PLUS_ALIASING_DOMAINS:
        local = local.split("+", 1)[0]
    if domain in _GMAIL_DOTLESS_DOMAINS:
        local = local.replace(".", "")
        # Treat googlemail.com as gmail.com for dedup purposes — Google
        # routes them interchangeably.
        domain = "gmail.com"

    if not local:
        return None
    return f"{local}@{domain}"


__all__ = ["canonicalize_email"]
