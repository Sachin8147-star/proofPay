"""Wallet page data: real on-chain balance, money locked in escrow (and why), and a plain-language activity history."""
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from fastapi import APIRouter, Depends, HTTPException

from . import chain
from .auth import current_user
from .config import settings
from .db import db, many, one

log = logging.getLogger("wallet")
router = APIRouter()
ADDR = re.compile(r"^0x[0-9a-fA-F]{40}$")


def _fmt(d) -> str:
    return f"{Decimal(str(d)).normalize():f} {settings.symbol}"


def lock_reason(role: str, c: dict, m: dict) -> dict:
    """Explains, in plain words, why money is locked and what releases it."""
    st = m["status"]
    if c["status"] == "open":
        why = "You paid up front. The money is held safely until someone accepts your job." if role == "client" else "Locked for you once you accept."
        unlock = "You can take it back any time until someone accepts." if role == "client" else "Accept the contract to start."
    elif st == "funded" and m.get("delivery_type") == "product":
        why = "Held in escrow until the buyer confirms the item arrived." if role == "freelancer" else "Held in escrow so the seller is only paid once you confirm you received the item."
        unlock = "Released when the buyer presses \"I received it\" (or the review window ends after shipping)."
    elif st == "funded":
        why = "Held in escrow while the work is delivered and checked." if role == "freelancer" else "Held in escrow so the worker is only paid for work that passes the agreed checks."
        unlock = "Released after the delivered work passes its checks and the review window ends, or earlier if the buyer approves."
    elif st == "passed":
        ends = m.get("review_ends_at")
        why = "The checks passed. The buyer has a short window to review before payment is released."
        unlock = f"Releases automatically after {ends[:16].replace('T', ' ')} UTC unless the buyer disputes." if ends else "Releases automatically when the review window ends."
    elif st == "disputed":
        why, unlock = "The buyer disputed this milestone. An arbitrator is reviewing the evidence.", "Released according to the arbitrator's decision."
    else:
        why, unlock = "", ""
    if c.get("cancel_requested"):
        unlock += " The buyer has asked to cancel; the money returns only if the worker agrees."
    return {"why": why, "unlock": unlock.strip()}


def _event_text(e: dict, c: dict, mine_as: str) -> tuple[str, str | None, Decimal | None]:
    n, a = e["name"], e["args"]
    amt = chain.from_wei(int(a["amount"])) if a.get("amount") is not None else None
    t = c["title"]
    if n == "EscrowCreated":
        return (f"You locked money for \"{t}\"" if mine_as == "client" else f"Money was locked for you on \"{t}\""), ("out" if mine_as == "client" else None), None
    if n == "Accepted":
        return f"\"{t}\" was accepted and work started", None, None
    if n == "Released":
        return (f"Payment released to the worker on \"{t}\"" if mine_as == "client" else f"You were paid for \"{t}\""), ("out" if mine_as == "client" else "in"), amt
    if n == "Refunded":
        return (f"Money returned to you from \"{t}\"" if mine_as == "client" else f"Money on \"{t}\" was returned to the buyer"), ("in" if mine_as == "client" else None), amt
    if n in ("Cancelled", "CancelAgreed"):
        return f"\"{t}\" was cancelled", None, None
    if n == "CancelRequested":
        return f"Cancel requested on \"{t}\"", None, None
    if n == "CancelWithdrawn":
        return f"Cancel request withdrawn on \"{t}\"", None, None
    if n == "Attested":
        return f"Work on \"{t}\" was checked ({'passed' if a.get('passed') else 'not passed yet'})", None, None
    if n == "Disputed":
        return f"A dispute was opened on \"{t}\"", None, None
    if n == "Resolved":
        return f"Dispute on \"{t}\" resolved: {a.get('freelancerBps', 0) / 100:g}% to the worker", None, None
    return n, None, None


@router.get("/me/wallet-summary")
def wallet_summary(user=Depends(current_user)):
    p = one("profiles", id=user["id"])
    if not p["wallet"]:
        return {"address": None}
    from .routes import list_contracts
    out = {"address": p["wallet"], "symbol": settings.symbol, "balance_wei": None, "locked": [], "activity": []}
    try:
        out["balance_wei"] = str(chain.w3().eth.get_balance(chain.Web3.to_checksum_address(p["wallet"])))
    except Exception:
        log.warning("balance unavailable", exc_info=True)
    contracts = {}
    for role in ("client", "freelancer"):
        for c in list_contracts(role, user):
            contracts[c["id"]] = (role, c)
    for role, c in contracts.values():
        for m in c["milestones"]:
            if m["status"] in ("funded", "passed", "disputed") and c["status"] in ("open", "active"):
                full = one("milestones", contract_id=c["id"], idx=m["idx"])
                out["locked"].append({"contract_id": c["id"], "title": c["title"], "milestone": full["title"], "milestone_idx": m["idx"], "amount": m["amount"], "role": role,
                                      "status": m["status"], "delivery_type": full["delivery_type"], **lock_reason(role, c, full)})
    key = lambda x: Decimal(x["amount"])
    out["locked_total"] = str(sum((key(x) for x in out["locked"] if x["role"] == "client"), Decimal(0)))
    out["incoming_total"] = str(sum((key(x) for x in out["locked"] if x["role"] == "freelancer"), Decimal(0)))
    by_escrow = {c["escrow_id"]: (role, c) for role, c in contracts.values() if c.get("escrow_id")}
    events = db().table("chain_events").select("*").in_("escrow_id", list(by_escrow)).order("id", desc=True).limit(100).execute().data if by_escrow else []
    for e in events:
        role, c = by_escrow[e["escrow_id"]]
        text, direction, amt = _event_text(e, c, role)
        out["activity"].append({"when": e["created_at"], "text": text, "direction": direction, "amount": str(amt) if amt is not None else None,
                                "tx_hash": e["tx_hash"], "contract_id": c["id"]})
    return out


@router.get("/wallet/{address}")
def wallet(address: str):
    """Public view of any address: live balance and recent network transactions (from the MST explorer)."""
    if not ADDR.match(address):
        raise HTTPException(400, "Invalid address")
    out = {"address": address, "balance_wei": None, "transactions": [], "explorer_ok": False}
    try:
        out["balance_wei"] = str(chain.w3().eth.get_balance(chain.Web3.to_checksum_address(address)))
    except Exception:
        log.warning("wallet balance unavailable", exc_info=True)
    try:
        r = httpx.get(f"{settings.mst_explorer_url}/api/v2/addresses/{address}/transactions", timeout=10)
        r.raise_for_status()
        out["transactions"] = [{"hash": t["hash"], "from": (t.get("from") or {}).get("hash"), "to": (t.get("to") or {}).get("hash"),
                                "value": t.get("value"), "status": t.get("status"), "timestamp": t.get("timestamp"), "method": t.get("method")}
                               for t in r.json().get("items", [])[:50]]
        out["explorer_ok"] = True
    except Exception:
        log.warning("explorer history unavailable", exc_info=True)
    return out
