"""W2.5 — domain-based website pre-fetch at signup.

When the researcher signs up with a corporate email (``corino@stripe.com``),
fire ``fetch_website_summary`` against the email's domain in a background
thread so the Research Copilot walks into the very first turn already
knowing what the company does. Big wow moment, measurable activation lift
(the agent's first response references the user's company specifically).

Skips freemail providers (gmail, outlook, etc.) — those domains tell us
nothing about the user's employer and the fetch would just burn Claude
tokens summarising consumer email portals.

Fire-and-forget contract: every code path swallows its own exceptions
and returns. Signup must never block, fail, or surface a 500 because
the prefetch couldn't reach a website.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Optional

from app.database import SessionLocal
from app.models.company import Company
from app.services.analytics import emit_event

logger = logging.getLogger(__name__)


# ── Freemail / disposable provider list ──────────────────────────────────────
# Curated, not exhaustive — false negatives (rare provider missed) just mean
# we burn a few Claude tokens summarising a personal email site, which is
# tolerable. False positives (mistakenly treating a real corp domain as
# freemail) would cost us the wow moment, so we keep this list tight.
_FREEMAIL_DOMAINS = frozenset(
    {
        # English-speaking giants
        "gmail.com",
        "googlemail.com",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "msn.com",
        "yahoo.com",
        "ymail.com",
        "rocketmail.com",
        "icloud.com",
        "me.com",
        "mac.com",
        "aol.com",
        "mail.com",
        "gmx.com",
        "gmx.us",
        "fastmail.com",
        "fastmail.fm",
        "zoho.com",
        "tutanota.com",
        "protonmail.com",
        "proton.me",
        "pm.me",
        # French + Belgian + Swiss
        "free.fr",
        "orange.fr",
        "wanadoo.fr",
        "laposte.net",
        "sfr.fr",
        "bbox.fr",
        "neuf.fr",
        "club-internet.fr",
        "voila.fr",
        "gmx.fr",
        "yahoo.fr",
        "hotmail.fr",
        "live.fr",
        "outlook.fr",
        "skynet.be",
        "telenet.be",
        "bluewin.ch",
        "sunrise.ch",
        # Spanish + Italian + German + Dutch + Portuguese
        "yahoo.es",
        "hotmail.es",
        "libero.it",
        "tin.it",
        "alice.it",
        "yahoo.it",
        "web.de",
        "gmx.de",
        "t-online.de",
        "freenet.de",
        "yahoo.de",
        "hotmail.de",
        "hotmail.nl",
        "live.nl",
        "ziggo.nl",
        "kpnmail.nl",
        "sapo.pt",
        "iol.pt",
        # Russia / Eastern Europe / Asia (light coverage)
        "yandex.ru",
        "mail.ru",
        "qq.com",
        "163.com",
        "126.com",
        "naver.com",
        "daum.net",
        # Disposable / privacy (mirrored in _DISPOSABLE_DOMAINS — those
        # are REJECTED at signup, not just skipped for prefetch)
        "duck.com",
        "anonaddy.me",
        "simplelogin.com",
        "guerrillamail.com",
        "mailinator.com",
        "yopmail.com",
        "tempmail.com",
        "10minutemail.com",
    }
)


# Disposable / throwaway providers. We BLOCK signup from these (vs
# freemail above which is just allowed-but-skipped-for-prefetch). Keep
# this list focused on widely-known disposable services — false
# positives reject real users and feel arbitrary. The fraud-floor
# arithmetic: each fake account costs ~$5 in Whisper/Claude/TTS, so
# even imperfect coverage pays off.
_DISPOSABLE_DOMAINS = frozenset(
    {
        # 10minutemail family
        "10minutemail.com",
        "10minutemail.net",
        "10minutemail.co.uk",
        "20minutemail.com",
        "20email.eu",
        "30minutemail.com",
        # mailinator family
        "mailinator.com",
        "mailinator.net",
        "mailinator2.com",
        "binkmail.com",
        "bobmail.info",
        # yopmail family
        "yopmail.com",
        "yopmail.fr",
        "yopmail.net",
        # guerrillamail family
        "guerrillamail.com",
        "guerrillamail.net",
        "guerrillamail.org",
        "sharklasers.com",
        "grr.la",
        # tempmail family
        "tempmail.com",
        "temp-mail.org",
        "tempr.email",
        "throwawaymail.com",
        "throwawaymail.net",
        "trashmail.com",
        "trash-mail.com",
        "trashmail.de",
        "trashmail.net",
        # Others
        "fakeinbox.com",
        "dispostable.com",
        "spamgourmet.com",
        "getairmail.com",
        "maildrop.cc",
        "mintemail.com",
        "mytemp.email",
        "mytrashmail.com",
        "owlymail.com",
        "spamex.com",
        "tempinbox.com",
        "tempemail.com",
        "tempmailaddress.com",
        "tempmail.de",
        "tempmail.net",
        "tempmail.us",
        "throwaway.email",
        "yopmail.org",
        # Russian disposables
        "mail-tester.com",
        # Asian disposables
        "mailcatch.com",
        "rmqkr.net",
    }
)


def is_disposable_email_domain(domain: str | None) -> bool:
    """Check if a domain is on the disposable-email blocklist.

    Returns False for None / empty / unknown — only blocks domains
    we explicitly flagged. False negatives (a disposable provider we
    haven't listed) just mean the abuser pays the ~$5 cost for one
    extra account before we notice and add the domain."""
    if not domain:
        return False
    return domain.strip().lower() in _DISPOSABLE_DOMAINS


def extract_domain(email: str | None) -> Optional[str]:
    """Pull the lowercase domain off an email address. Returns ``None``
    for missing / malformed input rather than raising."""
    if not email or "@" not in email:
        return None
    try:
        domain = email.rsplit("@", 1)[1].strip().lower()
    except IndexError:
        return None
    if not domain or "." not in domain:
        return None
    return domain


def is_freemail(domain: str | None) -> bool:
    if not domain:
        return True  # treat unknown as freemail-equivalent (skip)
    return domain in _FREEMAIL_DOMAINS


def _run_async(coro):
    """Run an async coroutine to completion from a sync background thread.

    Spawning a fresh event loop is the right pattern here — we're inside a
    one-shot worker thread, so we own the loop and tear it down when done.
    """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def _prefetch_in_background(company_id: str, domain: str, language: str) -> None:
    """Do the actual fetch + DB write. Lives in a worker thread; never
    raises out. Opens its own DB session because the signup-request
    session is gone by the time this fires."""
    from app.services.website_intelligence import (
        WebsiteIntelligenceError,
        fetch_website_summary,
    )

    url = f"https://{domain}/"
    try:
        result = _run_async(
            fetch_website_summary(url, language=language)
        )
    except WebsiteIntelligenceError as err:
        logger.info(
            "signup_prefetch.miss domain=%s reason=%s", domain, err.args[0] if err.args else "unknown"
        )
        emit_event("domain_prefetch_miss", company_id=company_id, domain=domain)
        return
    except Exception:
        # The network, the AI, or anything else — never propagate.
        logger.exception("signup_prefetch.error domain=%s", domain)
        emit_event("domain_prefetch_error", company_id=company_id, domain=domain)
        return

    summary = (result.get("summary") or "").strip()
    industry = (result.get("industry") or "").strip()
    if not summary:
        emit_event("domain_prefetch_empty", company_id=company_id, domain=domain)
        return

    db = SessionLocal()
    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        if company is None:
            return
        # Belt-and-braces: never overwrite anything the user already set
        # (e.g. they ran the in-chat website lookup before the background
        # thread finished). The agent's lookup is more authoritative
        # because the user picked the URL.
        wrote = False
        if not (company.website_url or "").strip():
            company.website_url = url
            wrote = True
        if not (company.business_summary or "").strip():
            company.business_summary = summary
            wrote = True
        if industry and not (company.industry or "").strip():
            company.industry = industry
            wrote = True
        if wrote:
            db.commit()
            emit_event(
                "domain_prefetch_hit",
                company=company,
                domain=domain,
                wrote_industry=bool(industry and not (company.industry or "").strip()),
            )
    except Exception:
        logger.exception(
            "signup_prefetch.write_failed company_id=%s domain=%s",
            company_id,
            domain,
        )
        db.rollback()
    finally:
        db.close()


def prefetch_company_intel(
    company_id: str,
    email: str,
    language: str = "en",
) -> None:
    """Public entry — schedules the background fetch unless the email
    is freemail. Returns immediately; the thread is daemonised so a
    container shutdown won't hang on it.

    Emits one of three analytics events: ``domain_prefetch_skipped``
    (freemail / bad email), ``domain_prefetch_hit`` (wrote fields),
    ``domain_prefetch_miss`` / ``domain_prefetch_error`` (fetch failed).
    """
    domain = extract_domain(email)
    if is_freemail(domain):
        emit_event(
            "domain_prefetch_skipped",
            company_id=company_id,
            domain=domain or "",
            reason="freemail" if domain else "bad_email",
        )
        return

    # `assert` for type-narrowing — is_freemail returned False so domain
    # is definitely not None here.
    assert domain is not None
    thread = threading.Thread(
        target=_prefetch_in_background,
        args=(company_id, domain, language),
        daemon=True,
        name=f"signup-prefetch-{company_id[:8]}",
    )
    thread.start()
