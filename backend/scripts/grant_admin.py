"""Grant, revoke, or list admin access for /admin. The ONLY way to flip
``Company.is_admin``: there is deliberately no API for it.

    python scripts/grant_admin.py --list
    python scripts/grant_admin.py --email you@qualipulse.com
    python scripts/grant_admin.py --email you@qualipulse.com --revoke
    python scripts/grant_admin.py --email you@qualipulse.com --reset-2fa   # break-glass

Run it wherever DATABASE_URL points at the database you mean (locally for
SQLite, or with the Neon URL exported for production). Every change is
written to admin_audit_log with identity "script:grant_admin" so it shows
up in the panel's Audit tab.

``--reset-2fa`` is the lost-phone-and-lost-backup-codes path: it clears
the TOTP enrolment so the person can re-enrol from Account → Security.
It does not grant anything; admin access still requires re-enrolling.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal  # noqa: E402
from app.models.admin_audit import AdminAuditLog  # noqa: E402
from app.models.company import Company  # noqa: E402

SCRIPT_IDENTITY = "script:grant_admin"


def _audit(db, action: str, company: Company, details: dict | None = None) -> None:
    db.add(AdminAuditLog(
        id=str(uuid.uuid4()),
        admin_identity=SCRIPT_IDENTITY,
        action=action,
        target_company_id=company.id,
        target_company_email=company.email,
        details=json.dumps(details) if details else None,
        is_impersonation=False,
    ))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", help="Account email (case-insensitive)")
    parser.add_argument("--revoke", action="store_true", help="Remove admin access")
    parser.add_argument("--reset-2fa", action="store_true", help="Clear the TOTP enrolment (break-glass)")
    parser.add_argument("--list", action="store_true", help="List current admins and exit")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.list:
            rows = db.query(Company).filter(Company.is_admin.is_(True)).order_by(Company.email).all()
            if not rows:
                print("No admin accounts.")
            for c in rows:
                state = "2FA on" if c.totp_enabled else "2FA OFF (cannot open admin session)"
                print(f"  {c.email:40s} {state}")
            return 0

        if not args.email:
            parser.error("--email is required (or use --list)")
        company = db.query(Company).filter(Company.email.ilike(args.email.strip())).first()
        if company is None:
            print(f"No account with email {args.email!r}", file=sys.stderr)
            return 1

        if args.reset_2fa:
            company.totp_secret = None
            company.totp_enabled = False
            company.totp_backup_codes = None
            company.token_version = (company.token_version or 0) + 1  # kill live sessions too
            _audit(db, "admin_2fa_reset", company)
            db.commit()
            print(f"2FA cleared for {company.email}. They must re-enrol before opening an admin session.")
            return 0

        if args.revoke:
            if not company.is_admin:
                print(f"{company.email} is not an admin; nothing to do.")
                return 0
            company.is_admin = False
            _audit(db, "admin_revoked", company)
            db.commit()
            print(f"Admin access revoked for {company.email}. Any live admin session is now refused.")
            return 0

        if company.is_admin:
            print(f"{company.email} is already an admin.")
        else:
            company.is_admin = True
            _audit(db, "admin_granted", company)
            db.commit()
            print(f"Admin access granted to {company.email}.")
        if not company.totp_enabled:
            print("  Note: this account has no 2FA yet. They must enable it (Account > Security) before /admin will open.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
