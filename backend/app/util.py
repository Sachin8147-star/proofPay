"""Tiny in-memory rate limiter (per process). Good enough for one API instance; use Redis if you scale out."""
import time

from fastapi import HTTPException

_hits: dict[str, list[float]] = {}


def rate_limit(key: str, limit: int, per_secs: int, msg: str = "Too many requests. Please wait a moment."):
    now = time.time()
    hits = [t for t in _hits.get(key, []) if t > now - per_secs]
    if len(hits) >= limit:
        _hits[key] = hits
        raise HTTPException(429, msg)
    _hits[key] = hits + [now]
    if len(_hits) > 20000:
        _hits.clear()


def refund(key: str):
    """Gives back the last slot (used when an AI call failed through no fault of the user)."""
    if _hits.get(key):
        _hits[key].pop()


def reset():
    _hits.clear()
