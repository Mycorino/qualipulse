"""Shared SlowAPI rate limiter instance."""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


def participant_rate_key(request) -> str:
    """Rate-limit in-session interview routes per participant, not per IP.

    A university lab, a call centre, or any corporate NAT puts every
    participant behind one address: a per-IP cap on /respond throttles real
    interviews. The participant id is in the path and is a UUID4, so it is a
    stable per-session bucket. Falls back to the client IP when the path has
    no participant id.
    """
    pid = (request.path_params or {}).get("participant_id")
    if pid:
        return f"participant:{pid}"
    return get_remote_address(request)
