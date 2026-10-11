"""Open jobs board: contracts that are already paid (money locked) and waiting for any worker to accept."""
from decimal import Decimal

from fastapi import APIRouter, Depends

from .auth import current_user
from .db import db, one

router = APIRouter()


@router.get("/jobs")
def jobs(q: str = "", user=Depends(current_user)):
    """Open, funded jobs from other people. Workers can read the offer, chat with the poster, and accept on-chain."""
    rows = db().table("contracts").select("*").eq("status", "open").eq("is_open", True).neq("client_id", user["id"]).order("created_at", desc=True).limit(100).execute().data
    term = q.strip().lower()
    ids = [r["id"] for r in rows]
    ms = db().table("milestones").select("contract_id,idx,title,amount,delivery_type,deadline").in_("contract_id", ids).execute().data if ids else []
    if term:
        searchable = {r["id"]: " ".join([r["title"], r["description"], *[m["title"] for m in ms if m["contract_id"] == r["id"]], *[m["delivery_type"] for m in ms if m["contract_id"] == r["id"]]]) for r in rows}
        rows = [r for r in rows if term in searchable[r["id"]].lower()]
    out = []
    for r in rows:
        mine = sorted([m for m in ms if m["contract_id"] == r["id"]], key=lambda m: m["idx"])
        poster = one("profiles", id=r["client_id"]) or {}
        out.append({"id": r["id"], "title": r["title"], "description": r["description"][:400], "total_amount": r["total_amount"], "created_at": r["created_at"],
                    "poster": {"handle": poster.get("handle"), "name": poster.get("name")},
                    "milestones": [{k: m[k] for k in ("title", "amount", "delivery_type", "deadline")} for m in mine],
                    "types": sorted({m["delivery_type"] for m in mine}),
                    "earliest_deadline": min((m["deadline"] for m in mine), default=None),
                    "total": str(sum(Decimal(m["amount"]) for m in mine))})
    return out
