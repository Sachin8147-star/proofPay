"""Reads ProofPayEscrow events from the chain into Postgres and keeps contract/milestone status in sync."""
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from .chain import ABI, escrow, from_wei, w3
from .config import settings
from .db import db, one
from .notify import notify_admins, notify_parties

log = logging.getLogger("indexer")
EVENTS = [e["name"] for e in ABI if e["type"] == "event" and e["name"] in (
    "EscrowCreated", "Accepted", "Cancelled", "CancelRequested", "CancelWithdrawn", "CancelAgreed", "Attested", "Released", "Disputed", "Resolved", "Refunded")]


def _hex(b) -> str:
    return "0x" + bytes(b).hex()


def _set_contract(cid, **vals):
    db().table("contracts").update(vals).eq("id", cid).execute()


def _set_milestone(cid, idx, **vals):
    db().table("milestones").update(vals).eq("contract_id", cid).eq("idx", idx).execute()


def _maybe_complete(cid):
    rows = db().table("milestones").select("status").eq("contract_id", cid).execute().data
    if rows and all(r["status"] in ("released", "refunded") for r in rows):
        _set_contract(cid, status="completed")


def apply(name: str, a: dict, tx_hash: str):
    c = one("contracts", escrow_id=_hex(a["id"]))
    if not c:
        return
    cid, idx = c["id"], a.get("idx")
    key = f"{name}:{tx_hash}"
    label = f"{c['title']}" + (f", milestone {idx + 1}" if idx is not None else "")
    if name == "EscrowCreated":
        owner = one("profiles", id=c["client_id"])
        if "client" in a and owner and owner["wallet"] and owner["wallet"] != str(a["client"]).lower():
            log.warning("ignoring EscrowCreated for %s: creator is not the contract owner", cid)
            return
        _set_contract(cid, status="open", created_tx=tx_hash)
        db().table("milestones").update({"status": "funded"}).eq("contract_id", cid).execute()  # funds are locked at creation
        total = f"{float(c['total_amount']):g} {settings.symbol}"
        notify_parties(c, "payment", f"{total} locked in escrow", f"{c['title']}. You can take it back until someone accepts.", who="client", key=key)
        if not c.get("is_open"):
            notify_parties(c, "invite", "New contract: the money is already locked", f"{c['title']} ({total}). Open it to review and accept.", who="freelancer", key=key)
    elif name == "Accepted":
        wallet = str(a.get("freelancer", "")).lower() or c.get("freelancer_wallet")
        w = one("profiles", wallet=wallet) if wallet else None
        _set_contract(cid, status="active", freelancer_wallet=wallet, cancel_requested=False, **({"freelancer_id": w["id"]} if w else {}))
        c = one("contracts", id=cid)
        who = (w or {}).get("handle") or "The worker"
        notify_parties(c, "contract", f"{who} accepted your contract", f"{c['title']}. Work has started and the money stays locked until it is delivered.", who="client", key=key)
    elif name == "Cancelled":
        _set_contract(cid, status="cancelled", cancel_requested=False)
        notify_parties(c, "payment", "Contract cancelled: money returned", f"{c['title']}. The locked amount went back to the client.", key=key)
    elif name == "CancelRequested":
        _set_contract(cid, cancel_requested=True)
        notify_parties(c, "contract", "The client asked to cancel", f"{c['title']}. If you agree, the unreleased money goes back to the client. Talk it over in the chat first.", who="freelancer", key=key)
    elif name == "CancelWithdrawn":
        _set_contract(cid, cancel_requested=False)
        notify_parties(c, "contract", "Cancel request withdrawn", c["title"], who="freelancer", key=key)
    elif name == "CancelAgreed":
        _set_contract(cid, status="cancelled", cancel_requested=False)
        notify_parties(c, "payment", "Cancelled by agreement: money returned", f"{c['title']}. The unreleased money went back to the client.", key=key)
    elif name == "Attested":
        vals = {"evidence_hash": _hex(a["evidence"])}
        if a["passed"]:
            vals["status"] = "passed"
            m0 = one("milestones", contract_id=cid, idx=idx)
            vals["review_ends_at"] = (datetime.now(timezone.utc) + timedelta(seconds=(m0 or {}).get("window_secs") or 172800)).isoformat()
        _set_milestone(cid, idx, **vals)
    elif name == "Released":
        _set_milestone(cid, idx, status="released")
        m = one("milestones", contract_id=cid, idx=idx)
        amt = f"{float(m['amount']):g} {settings.symbol}" if m else ""
        notify_parties(c, "payment", f"Payment released: {amt}", label, who="freelancer", key=key)
        notify_parties(c, "payment", "Milestone paid", f"{label}: {amt}", who="client", key=key)
        _maybe_complete(cid)
    elif name == "Disputed":
        _set_milestone(cid, idx, status="disputed")
        db().table("disputes").update({"status": "open"}).eq("contract_id", cid).eq("milestone_idx", idx).eq("status", "pending").execute()
        notify_parties(c, "dispute", "The client opened a dispute", label, who="freelancer", key=key)
        notify_admins("dispute", "New dispute to review", label, "/admin/disputes", key=key)
    elif name == "Resolved":
        _set_milestone(cid, idx, status="released")
        db().table("disputes").update(
            {"status": "resolved", "freelancer_bps": a["freelancerBps"], "resolved_at": datetime.now(timezone.utc).isoformat()}
        ).eq("contract_id", cid).eq("milestone_idx", idx).eq("status", "open").execute()
        notify_parties(c, "dispute", "Dispute resolved", f"{label}: {a['freelancerBps'] / 100:g}% to the worker.", key=key)
        _maybe_complete(cid)
    elif name == "Refunded":
        _set_milestone(cid, idx, status="refunded")
        if c["status"] == "active" and not c.get("cancel_requested"):  # a plain expiry refund (revoke/cancel notify on their own)
            notify_parties(c, "payment", "Milestone refunded to the client", label, who="freelancer", key=key)
        _maybe_complete(cid)


def run_once() -> bool:
    """Indexes one chunk. Returns True while there are more blocks to catch up on."""
    st = db().table("indexer_state").select("last_block").eq("id", 1).execute().data[0]
    start = max(st["last_block"] + 1, settings.indexer_start_block)
    head = w3().eth.block_number
    if start > head:
        return False
    end = min(head, start + 1999)
    c, logs = escrow(), []
    for name in EVENTS:
        logs += getattr(c.events, name)().get_logs(from_block=start, to_block=end)
    for lg in sorted(logs, key=lambda l: (l["blockNumber"], l["logIndex"])):
        args = dict(lg["args"])
        tx = _hex(lg["transactionHash"])
        json_args = {k: (_hex(v) if isinstance(v, (bytes, bytearray)) else (str(v) if isinstance(v, int) and v > 2**53 else v)) for k, v in args.items()}
        db().table("chain_events").upsert(
            {"tx_hash": tx, "log_index": lg["logIndex"], "block_number": lg["blockNumber"], "name": lg["event"],
             "escrow_id": _hex(args["id"]), "idx": args.get("idx"), "args": json_args},
            on_conflict="tx_hash,log_index",
        ).execute()
        apply(lg["event"], args, tx)
    db().table("indexer_state").update({"last_block": end}).eq("id", 1).execute()
    return end < head


def loop():
    while True:
        try:
            while run_once():
                pass
        except Exception:
            log.exception("indexer error")
        time.sleep(8)


def start():
    if settings.run_indexer and settings.escrow_address:
        threading.Thread(target=loop, daemon=True, name="indexer").start()
