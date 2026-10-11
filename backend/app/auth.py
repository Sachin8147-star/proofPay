import time

import httpx
from fastapi import Depends, Header, HTTPException

from .config import settings
from .db import one

_cache: dict[str, tuple[float, dict]] = {}


def current_user(authorization: str | None = Header(None)) -> dict:
    """Validates the Supabase access token by asking Supabase Auth (works for any JWT signing setup)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Sign in required")
    token = authorization[7:]
    hit = _cache.get(token)
    if hit and hit[0] > time.time():
        return hit[1]
    try:
        r = httpx.get(
            f"{settings.supabase_url}/auth/v1/user",
            headers={"Authorization": f"Bearer {token}", "apikey": settings.supabase_service_role_key},
            timeout=10,
        )
    except httpx.HTTPError:
        raise HTTPException(503, "Unable to reach Supabase Auth. Check SUPABASE_URL in the root .env file and your internet connection.")
    if r.status_code != 200:
        raise HTTPException(401, "Session expired. Sign in again.")
    data = r.json()
    if settings.require_verified_email and not data.get("email_confirmed_at"):
        raise HTTPException(403, "Confirm your email first: open the link we sent you, then sign in again.")
    user = {"id": data["id"], "email": (data.get("email") or "").lower()}
    _cache[token] = (time.time() + 30, user)
    if len(_cache) > 2000:
        _cache.clear()
    return user


def admin_user(user: dict = Depends(current_user)) -> dict:
    p = one("profiles", id=user["id"])
    if not p or not p["is_admin"]:
        raise HTTPException(403, "Admin access required")
    return user
