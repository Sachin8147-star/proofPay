"""In-app notifications (+ optional email via Resend). Never raises: a failed notification must not break a payment flow."""
import logging
import threading
from datetime import datetime, timezone

import httpx

from .config import settings
from .db import db, many, one

log = logging.getLogger("notify")


def _email(to: str | None, title: str, body: str, link: str | None):
    if not settings.resend_api_key or not to:
        return
    text = f"{body}\n\n{settings.app_url.rstrip('/')}{link}" if link else body

    def send():
        try:
            httpx.post("https://api.resend.com/emails", headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                       json={"from": settings.email_from, "to": [to], "subject": title, "text": text}, timeout=10)
        except Exception:
            log.warning("email send failed", exc_info=True)

    threading.Thread(target=send, daemon=True).start()


def notify(user_id, kind, title, body="", link=None, dedupe_key=None, email=True):
    if not user_id:
        return
    try:
        if dedupe_key and db().table("notifications").select("id").eq("user_id", user_id).eq("dedupe_key", dedupe_key).limit(1).execute().data:
            return
        db().table("notifications").insert({"user_id": user_id, "kind": kind, "title": title, "body": body, "link": link, "dedupe_key": dedupe_key}).execute()
        if email:
            p = one("profiles", id=user_id)
            _email(p["email"] if p else None, title, body, link)
    except Exception:
        log.warning("notification failed", exc_info=True)


def freelancer_user(c: dict):
    """The freelancer's user id, found by id, then wallet, then invite email (they may not have an account yet)."""
    if c.get("freelancer_id"):
        return c["freelancer_id"]
    p = (one("profiles", wallet=c["freelancer_wallet"]) if c.get("freelancer_wallet") else None) \
        or (one("profiles", handle=c["freelancer_handle"]) if c.get("freelancer_handle") else None) \
        or (one("profiles", email=c["freelancer_email"]) if c.get("freelancer_email") else None)
    return p["id"] if p else None


def link_for(c: dict, uid: str) -> str:
    if uid == c["client_id"]:
        return f"/client/{c['id']}"
    if c["status"] == "open" and c.get("is_open") and uid != freelancer_user(c):
        return f"/jobs/{c['id']}"  # an interested worker, not (yet) the assigned one
    return f"/freelancer/{c['id']}"


def notify_parties(c: dict, kind: str, title: str, body: str = "", who: str = "both", key: str | None = None):
    k = lambda uid: f"{key}:{uid}" if key else None
    if who in ("both", "client"):
        notify(c["client_id"], kind, title, body, f"/client/{c['id']}", k(c["client_id"]))
    if who in ("both", "freelancer"):
        fid = freelancer_user(c)
        if fid:
            notify(fid, kind, title, body, f"/freelancer/{c['id']}", k(fid))
        elif kind == "invite":  # no account yet: email the invite so they can sign up
            _email(c.get("freelancer_email"), title, body, "/login?next=/freelancer")


def notify_admins(kind: str, title: str, body: str = "", link: str | None = None, key: str | None = None):
    for a in many("profiles", is_admin=True):
        notify(a["id"], kind, title, body, link, f"{key}:{a['id']}" if key else None)


def notify_message(c: dict, sender_id: str, text: str, to: str | None = None):
    """One unread 'message' notification per contract and recipient; later messages update it instead of piling up.
    `to` is set for pre-acceptance threads on open jobs (the poster and one interested worker)."""
    if to is None:
        fid = freelancer_user(c)
        to = fid if sender_id == c["client_id"] else c["client_id"]
    if not to or to == sender_id:
        return
    link, title, preview = link_for(c, to), f"New message on {c['title']}", text[:140]
    try:
        last = db().table("notifications").select("*").eq("user_id", to).eq("kind", "message").eq("link", link).order("created_at", desc=True).limit(1).execute().data
        if last and last[0]["read_at"] is None:
            db().table("notifications").update({"body": preview, "title": title, "created_at": datetime.now(timezone.utc).isoformat()}).eq("id", last[0]["id"]).execute()
            return
        db().table("notifications").insert({"user_id": to, "kind": "message", "title": title, "body": preview, "link": link}).execute()
    except Exception:
        log.warning("message notification failed", exc_info=True)
