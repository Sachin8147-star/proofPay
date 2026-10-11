from fastapi import APIRouter, Depends, HTTPException

from . import ai, chain
from .auth import admin_user
from .config import settings
from .db import audit, db, many, one

router = APIRouter(prefix="/admin", dependencies=[Depends(admin_user)])


def _count(table, **eq):
    q = db().table(table).select("id", count="exact")
    for k, v in eq.items():
        q = q.eq(k, v)
    return q.limit(1).execute().count or 0


@router.get("/overview")
def overview():
    ms = db().table("milestones").select("amount,status").execute().data
    from decimal import Decimal
    s = lambda sts: str(sum(Decimal(m["amount"]) for m in ms if m["status"] in sts))
    runs = db().table("verification_runs").select("status").execute().data
    return {"users": _count("profiles"), "contracts": _count("contracts"), "active": _count("contracts", status="active"),
            "open_disputes": _count("disputes", status="open"), "open_jobs": _count("contracts", status="open"), "locked": s(("funded", "passed", "disputed")), "released": s(("released",)),
            "runs": len(runs), "runs_errored": sum(r["status"] == "error" for r in runs)}


@router.get("/contracts")
def contracts():
    return [{k: v for k, v in c.items() if k != "hidden_salt"} for c in many("contracts", order="created_at", desc=True, limit=200)]


@router.get("/runs")
def runs():
    return [{k: v for k, v in r.items() if k != "report"} for r in many("verification_runs", order="created_at", desc=True, limit=200)]


@router.get("/disputes")
def disputes():
    rows = many("disputes", order="created_at", desc=True, limit=200)
    for d in rows:
        c = db().table("contracts").select("title,escrow_id").eq("id", d["contract_id"]).execute().data
        d["contract"] = c[0] if c else None
        d["evidence_hash"] = (db().table("milestones").select("evidence_hash").eq("contract_id", d["contract_id"]).eq("idx", d["milestone_idx"]).execute().data or [{}])[0].get("evidence_hash")
    return rows


@router.get("/users")
def users():
    return many("profiles", order="created_at", desc=True, limit=200)


@router.get("/audit")
def audit_log():
    return many("audit_logs", order="id", desc=True, limit=200)


@router.get("/chain")
def chain_status():
    head = chain.w3().eth.block_number
    last = db().table("indexer_state").select("last_block").eq("id", 1).execute().data[0]["last_block"]
    v = chain.verifier_address()
    paused = None
    if settings.escrow_address:
        try:
            paused = chain.escrow().functions.paused().call()
        except Exception:
            pass
    return {"chain_id": chain.w3().eth.chain_id, "head": head, "indexed": last, "lag": head - last, "escrow": settings.escrow_address,
            "verifier": v, "verifier_balance_wei": str(chain.w3().eth.get_balance(v)) if v else None, "paused": paused,
            "explorer": settings.mst_explorer_url}


@router.post("/runs/{run_id}/retry-attest")
def retry_attest(run_id: str, admin=Depends(admin_user)):
    """Re-sends the on-chain attestation for a run whose original attestation failed."""
    r = one("verification_runs", id=run_id)
    if not r or r["dry_run"] or r["status"] not in ("passed", "failed") or r["attest_tx"] or not r["evidence_hash"]:
        raise HTTPException(400, "This run has nothing to retry")
    c = one("contracts", id=r["contract_id"])
    if chain.milestone_state(c["escrow_id"], r["milestone_idx"])["status"] != 0:
        raise HTTPException(400, "The milestone has already moved on-chain")
    tx = chain.attest(c["escrow_id"], r["milestone_idx"], r["evidence_hash"], r["status"] == "passed")
    db().table("verification_runs").update({"attest_tx": tx, "error": None}).eq("id", run_id).execute()
    audit(admin["id"], "attest_retried", "run", run_id, tx=tx)
    return {"tx": tx}


@router.get("/ai-check")
def ai_check():
    """Sends one tiny request to Gemini so the admin can see whether the AI features work (the key is never shown)."""
    if not ai.configured():
        return {"ok": False, "model": settings.gemini_model, "error": "GEMINI_API_KEY is not set in the root .env file."}
    try:
        ai.generate_text("Reply with the single word: ok", [{"role": "user", "content": "ping"}], max_tokens=16, temperature=0)
        return {"ok": True, "model": settings.gemini_model, "error": None}
    except ai.AIError as e:
        return {"ok": False, "model": settings.gemini_model, "error": str(e)}


@router.get("/disputes/{dispute_id}/transcript")
def dispute_transcript(dispute_id: str, admin=Depends(admin_user)):
    """Chat between the two parties, readable by admins only for a contract that has a dispute (every read is audited)."""
    d = one("disputes", id=dispute_id)
    if not d:
        raise HTTPException(404, "Dispute not found")
    audit(admin["id"], "transcript_read", "dispute", dispute_id, contract=d["contract_id"])
    rows = [m for m in many("messages", order="created_at", contract_id=d["contract_id"], limit=1000) if not m.get("thread_user")]
    names = {}
    for m in rows:
        if m["sender_id"] not in names:
            p = one("profiles", id=m["sender_id"]) or {}
            names[m["sender_id"]] = p.get("handle") or p.get("name") or "Member"
    return [{"who": names[m["sender_id"]], "body": m["body"], "created_at": m["created_at"]} for m in rows]
