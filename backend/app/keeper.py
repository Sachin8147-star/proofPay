"""Background duties: pay out milestones whose review window closed, and send deadline reminders."""
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from . import chain
from .config import settings
from .db import db, one
from .notify import notify, notify_parties

log = logging.getLogger("keeper")


def finalize_due() -> int:
    """Calls finalize() on every milestone whose challenge window has closed (payment is then automatic)."""
    if not (settings.escrow_address and settings.verifier_private_key):
        return 0
    rows = db().table("milestones").select("contract_id,idx").eq("status", "passed").execute().data
    if not rows:
        return 0
    now = chain.w3().eth.get_block("latest")["timestamp"]
    done = 0
    for r in rows:
        c = one("contracts", id=r["contract_id"])
        try:
            m = chain.milestone_state(c["escrow_id"], r["idx"])
            if m["status"] == 1 and now >= m["passed_at"] + m["window"]:
                chain.finalize(c["escrow_id"], r["idx"])
                done += 1
        except Exception:
            log.exception("finalize failed for %s #%s", r["contract_id"], r["idx"])
    return done


def reminders(now: datetime | None = None) -> int:
    """Deadline within 24h -> nudge the freelancer; deadline passed -> tell the client. Each sent once."""
    now = now or datetime.now(timezone.utc)
    sent = 0
    for m in db().table("milestones").select("*").eq("status", "funded").execute().data:
        c = one("contracts", id=m["contract_id"])
        if not c or c["status"] != "active":
            continue
        dl = datetime.fromisoformat(m["deadline"].replace("Z", "+00:00"))
        label = f"{c['title']}, milestone {m['idx'] + 1}"
        if now < dl <= now + timedelta(hours=24):
            notify_parties(c, "deadline", "Milestone due within 24 hours", label, who="freelancer", key=f"due24:{c['id']}:{m['idx']}")
            sent += 1
        elif dl < now:
            notify_parties(c, "deadline", "Milestone deadline passed", f"{label}. You can reclaim unverified funds after the grace period.", who="client", key=f"overdue:{c['id']}:{m['idx']}")
            sent += 1
    return sent


def loop():
    while True:
        for fn in (finalize_due, reminders):
            try:
                fn()
            except Exception:
                log.exception("%s failed", fn.__name__)
        time.sleep(30)


def start():
    if settings.run_keeper:
        threading.Thread(target=loop, daemon=True, name="keeper").start()
