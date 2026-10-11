import logging
import re
import secrets
import shutil
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from . import ai, chain, compiler, util, verifier
from . import review as review_mod
from .auth import current_user
from .config import settings
from .db import audit, db, many, one
from .notify import notify_message, notify_parties
from .verifier import InfraError

log = logging.getLogger("routes")
router = APIRouter()
ADDR = re.compile(r"^0x[0-9a-fA-F]{40}$")
HANDLE = re.compile(r"^[a-z0-9_-]{3,24}$")
RESERVED = {"admin", "administrator", "support", "proofpay", "root", "system", "api", "help", "staff", "moderator", "null", "undefined"}
HEARD = ("instagram", "facebook", "youtube", "x", "linkedin", "whatsapp", "google", "friend", "other")
ZERO = "0x" + "0" * 40
DELIVERY = ("software", "live_site", "product")


def _now():
    return datetime.now(timezone.utc)


def _ai(user_id: str, fn, *args):
    """Runs an AI call under a per-user hourly allowance; a failed call gives the allowance back."""
    key = f"ai:{user_id}"
    util.rate_limit(key, settings.ai_calls_per_hour, 3600, f"AI limit reached ({settings.ai_calls_per_hour} per hour). Try again later.")
    try:
        return fn(*args)
    except ai.AIError as e:
        util.refund(key)
        raise HTTPException(503 if not ai.configured() else 502, str(e))


# ---------------- profile, usernames, wallet ----------------

@router.get("/me")
def me(user=Depends(current_user)):
    return one("profiles", id=user["id"])


def username_problem(u: str) -> str | None:
    if not HANDLE.match(u or ""):
        return "Use 3-24 letters, numbers, _ or - (lowercase)."
    if u in RESERVED:
        return "That username is reserved."
    return None


@router.get("/username-available")
def username_available(u: str, request: Request):
    """Public check used by the sign-up form."""
    util.rate_limit(f"uname:{request.client.host if request.client else '-'}", 60, 60, "Too many checks. Wait a moment.")
    u = (u or "").strip().lower()
    if (p := username_problem(u)):
        return {"available": False, "reason": p}
    if one("profiles", handle=u):
        return {"available": False, "reason": "Username already exists. Pick another."}
    return {"available": True}


class ProfileIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=60)
    last_name: str | None = Field(None, max_length=60)
    phone: str | None = Field(None, pattern=r"^\+?[0-9 ()-]{7,20}$")
    heard_from: str | None = None
    heard_other: str | None = Field(None, max_length=120)
    handle: str | None = None


@router.put("/me")
def update_me(body: ProfileIn, user=Depends(current_user)):
    if body.heard_from and body.heard_from not in HEARD:
        raise HTTPException(400, "Pick one of the listed options for 'How did you hear about us?'")
    cur = one("profiles", id=user["id"])
    vals = {"first_name": body.first_name.strip(), "last_name": (body.last_name or "").strip() or None, "phone": body.phone,
            "heard_from": body.heard_from, "heard_other": body.heard_other}
    vals["name"] = " ".join(x for x in (vals["first_name"], vals["last_name"]) if x)
    h = (body.handle or "").strip().lower() or None
    if h and h != cur["handle"]:
        if (p := username_problem(h)):
            raise HTTPException(400, p)
        if (o := one("profiles", handle=h)) and o["id"] != user["id"]:
            raise HTTPException(409, "Username already exists. Pick another.")
        vals["handle"] = h
    db().table("profiles").update(vals).eq("id", user["id"]).execute()
    return one("profiles", id=user["id"])


@router.get("/users/{handle}")
def lookup_user(handle: str, user=Depends(current_user)):
    """Used when creating a contract: confirms a username exists and can receive work."""
    p = one("profiles", handle=handle.strip().lower().lstrip("@"))
    if not p:
        raise HTTPException(404, "No user with that username. Check the spelling.")
    return {"handle": p["handle"], "name": p["name"], "has_wallet": bool(p["wallet"]), "is_you": p["id"] == user["id"]}


class WalletIn(BaseModel):
    address: str
    message: str
    signature: str


@router.post("/me/wallet")
def link_wallet(body: WalletIn, user=Depends(current_user)):
    """Proves control of the wallet: the user signs a message that names their account and a fresh timestamp."""
    if not ADDR.match(body.address):
        raise HTTPException(400, "Invalid wallet address")
    m = re.search(r"Issued: (\S+)", body.message)
    try:
        issued = datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(400, "Invalid message")
    if user["id"] not in body.message or body.address.lower() not in body.message.lower() or abs((_now() - issued).total_seconds()) > 600:
        raise HTTPException(400, "Signature request expired. Try again.")
    try:
        signer = Account.recover_message(encode_defunct(text=body.message), signature=body.signature)
    except Exception:
        raise HTTPException(400, "Invalid signature")
    if signer.lower() != body.address.lower():
        raise HTTPException(400, "Signature does not match this wallet")
    addr = body.address.lower()
    if (o := one("profiles", wallet=addr)) and o["id"] != user["id"]:
        raise HTTPException(409, "This wallet is linked to another account")
    db().table("profiles").update({"wallet": addr}).eq("id", user["id"]).execute()
    audit(user["id"], "wallet_linked", "profile", user["id"], wallet=addr)
    return one("profiles", id=user["id"])


# ---------------- AI: understand the idea, draft the contract ----------------

class IdeaIn(BaseModel):
    text: str = Field(min_length=10, max_length=4000)
    budget: str | None = Field(None, max_length=60)


@router.post("/ai/idea")
def ai_idea(body: IdeaIn, user=Depends(current_user)):
    """Explains the idea back, suggests improvements and says how each part will be checked."""
    return _ai(user["id"], compiler.analyze_idea, body.text, body.budget)


class CompileIn(BaseModel):
    description: str = Field(min_length=10, max_length=4000)
    budget: str | None = None


@router.post("/compile")
def compile_brief(body: CompileIn, user=Depends(current_user)):
    d = _ai(user["id"], compiler.draft, body.description, body.budget)
    out = []
    for m in d.get("milestones", []) if isinstance(d.get("milestones"), list) else []:
        if not isinstance(m, dict):
            continue
        dt = m.get("delivery_type") if m.get("delivery_type") in DELIVERY else "software"
        reqs = [r for r in m.get("requirements", []) if isinstance(r, dict) and _valid(r)]
        if dt == "product":
            reqs = [r for r in reqs if r["kind"] == "manual"][:1] or [{"title": "I received the item as described", "criteria": "", "kind": "manual", "spec": {"note": ""}, "hidden": False}]
        elif not any(r["kind"] != "manual" for r in reqs):
            continue  # a code/site milestone needs at least one automatic check
        try:
            days = min(max(int(m.get("review_days") or (7 if dt == "product" else 3)), 1), 30)
        except (TypeError, ValueError):
            days = 3
        out.append({**{k: m.get(k) for k in ("title", "share_pct")}, "delivery_type": dt, "review_days": days, "requirements": reqs})
    if not out:
        raise HTTPException(502, "The AI could not draft usable checks. Describe the work in a bit more detail and try again.")
    return {"title": str(d.get("title", ""))[:200], "milestones": out}


def _valid(r) -> bool:
    try:
        r["spec"] = verifier.validate_spec(r["kind"], r["spec"])
        r.setdefault("title", "Requirement")
        return True
    except Exception:
        return False


# ---------------- contracts ----------------

class Req(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    criteria: str = Field("", max_length=1000)
    kind: str
    spec: dict
    hidden: bool = False


class Ms(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    amount: Decimal = Field(gt=0, max_digits=24, decimal_places=6)
    deadline: datetime
    delivery_type: str = "software"
    review_days: int = Field(3, ge=1, le=30)
    requirements: list[Req] = Field(min_length=1, max_length=20)


class NewContract(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field("", max_length=4000)
    idea: str = Field("", max_length=4000)
    freelancer_username: str | None = Field(None, max_length=40)  # empty = open job anyone can accept
    ai_notes: dict | None = None
    milestones: list[Ms] = Field(min_length=1, max_length=20)


@router.post("/contracts")
def create_contract(body: NewContract, user=Depends(current_user)):
    me_ = one("profiles", id=user["id"])
    if not me_["wallet"]:
        raise HTTPException(400, "Link your wallet before creating a contract (Settings > Wallet).")
    worker = None
    handle = (body.freelancer_username or "").strip().lower().lstrip("@")
    if handle:
        worker = one("profiles", handle=handle)
        if not worker:
            raise HTTPException(404, f"No user with the username @{handle}. Check the spelling or leave it empty to post an open job.")
        if worker["id"] == user["id"]:
            raise HTTPException(400, "You cannot hire yourself. Enter the other person's username.")
        if not worker["wallet"]:
            raise HTTPException(400, f"@{handle} has not connected a wallet yet. Ask them to open Settings > Wallet, then try again.")
    for m in body.milestones:
        if m.delivery_type not in DELIVERY:
            raise HTTPException(400, f"Milestone '{m.title}': unknown delivery type")
        if m.deadline.astimezone(timezone.utc) < _now() + timedelta(hours=1):
            raise HTTPException(400, f"Milestone '{m.title}' needs a deadline at least an hour from now")
        for r in m.requirements:
            try:
                r.spec = verifier.validate_spec(r.kind, r.spec)
            except Exception as e:
                raise HTTPException(400, f"Requirement '{r.title}': {e}")
        auto = [r for r in m.requirements if r.kind != "manual"]
        if m.delivery_type == "product" and auto:
            raise HTTPException(400, f"'{m.title}' is a physical product: it is confirmed by you on receipt, so it cannot have automatic checks.")
        if m.delivery_type != "product" and not auto:
            raise HTTPException(400, f"'{m.title}' needs at least one automatic check (files, website, or AI review).")
    cid, salt = str(uuid.uuid4()), secrets.token_hex(16)
    ms = [{"idx": i, "title": m.title, "amount": format(m.amount, "f"), "deadline": m.deadline.astimezone(timezone.utc).isoformat(),
           "delivery_type": m.delivery_type, "window_secs": m.review_days * 86400} for i, m in enumerate(body.milestones)]
    reqs = [{"milestone_idx": i, "position": p, "title": r.title, "criteria": r.criteria, "kind": r.kind, "spec": r.spec, "hidden": r.hidden}
            for i, m in enumerate(body.milestones) for p, r in enumerate(m.requirements)]
    hidden = [{k: x[k] for k in ("milestone_idx", "title", "kind", "spec")} for x in reqs if x["hidden"]]
    hidden_hash = chain.sha256_hex(chain.canonical(hidden) + salt)
    wallet = worker["wallet"] if worker else None
    payload = {"title": body.title, "description": body.description, "freelancer": wallet, "milestones": ms,
               "requirements": [x for x in reqs if not x["hidden"]], "hidden_tests_hash": hidden_hash}
    db().table("contracts").insert({
        "id": cid, "client_id": user["id"], "freelancer_id": worker["id"] if worker else None, "freelancer_wallet": wallet,
        "freelancer_handle": worker["handle"] if worker else None, "is_open": worker is None, "title": body.title, "description": body.description,
        "idea": body.idea, "ai_notes": body.ai_notes, "escrow_id": chain.sha256_hex(cid), "contract_hash": chain.sha256_hex(chain.canonical(payload)),
        "hidden_tests_hash": hidden_hash, "hidden_salt": salt, "total_amount": format(sum(m.amount for m in body.milestones), "f"),
    }).execute()
    db().table("milestones").insert([{**m, "contract_id": cid} for m in ms]).execute()
    db().table("requirements").insert([{**r, "contract_id": cid} for r in reqs]).execute()
    audit(user["id"], "contract_created", "contract", cid)
    return {"id": cid}


def load(cid: str, user: dict):
    """Returns (contract, role). Roles: client, freelancer, or viewer (anyone, for an open job nobody has accepted yet)."""
    c = one("contracts", id=cid)
    if not c:
        raise HTTPException(404, "Contract not found")
    if c["client_id"] == user["id"]:
        return c, "client"
    p = one("profiles", id=user["id"])
    if c["status"] != "draft" and (c["freelancer_id"] == user["id"] or (p["wallet"] and p["wallet"] == c["freelancer_wallet"])
                                   or (c.get("freelancer_handle") and c["freelancer_handle"] == p["handle"])):
        if not c["freelancer_id"]:
            db().table("contracts").update({"freelancer_id": user["id"]}).eq("id", cid).execute()
        return c, "freelancer"
    if c["status"] == "open" and c.get("is_open"):
        return c, "viewer"
    raise HTTPException(404, "Contract not found")


def _who(uid):
    p = one("profiles", id=uid) if uid else None
    return {"name": p["name"], "handle": p["handle"], "wallet": p["wallet"]} if p else None


def view(c: dict, role: str) -> dict:
    done = c["status"] == "completed"
    reqs = many("requirements", order="position", contract_id=c["id"])
    if role != "client" and not done:
        reqs = [{**r, "criteria": "", "kind": "hidden", "spec": None, "title": "Hidden test"} if r["hidden"] else r for r in reqs]
    out = {k: v for k, v in c.items() if k not in ("hidden_salt", "ai_notes", "idea")}
    out.update(role=role, milestones=many("milestones", order="idx", contract_id=c["id"]), requirements=reqs,
               client=_who(c["client_id"]), freelancer=_who(c["freelancer_id"]))
    if role == "viewer":  # a prospective worker sees the offer, not the history
        return out
    out.update(
        idea=c.get("idea", "") if role == "client" else "", ai_notes=c.get("ai_notes") if role == "client" else None,
        runs=[{k: v for k, v in r.items() if k != "report"} for r in many("verification_runs", order="created_at", desc=True, contract_id=c["id"])
              if not (role == "client" and r["dry_run"])],
        events=many("chain_events", order="id", escrow_id=c["escrow_id"]), disputes=many("disputes", order="created_at", contract_id=c["id"]),
    )
    if done:
        out["hidden_reveal"] = {"salt": c["hidden_salt"], "specs": [{k: r[k] for k in ("milestone_idx", "title", "kind", "spec")} for r in reqs if r["hidden"]]}
    return out


@router.get("/contracts")
def list_contracts(role: str = "client", user=Depends(current_user)):
    q = db().table("contracts").select("*").order("created_at", desc=True)
    if role == "client":
        q = q.eq("client_id", user["id"])
    else:
        p = one("profiles", id=user["id"])
        conds = [f"freelancer_id.eq.{user['id']}"]
        if p["wallet"]:
            conds.append(f"freelancer_wallet.eq.{p['wallet']}")
        if p["handle"]:
            conds.append(f"freelancer_handle.eq.{p['handle']}")
        q = q.neq("status", "draft").or_(",".join(conds))
    rows = q.execute().data
    if rows:
        ms = db().table("milestones").select("contract_id,idx,status,amount").in_("contract_id", [r["id"] for r in rows]).execute().data
        for r in rows:
            r["milestones"] = [m for m in ms if m["contract_id"] == r["id"]]
            for k in ("hidden_salt", "idea", "ai_notes"):
                r.pop(k, None)
    return rows


@router.get("/contracts/{cid}")
def get_contract(cid: str, user=Depends(current_user)):
    return view(*load(cid, user))


@router.delete("/contracts/{cid}")
def delete_draft(cid: str, user=Depends(current_user)):
    c, role = load(cid, user)
    if role != "client" or c["status"] != "draft":
        raise HTTPException(400, "Only unpaid drafts can be deleted. Paid contracts are cancelled on-chain (Revoke, or Request cancel).")
    db().table("contracts").delete().eq("id", cid).execute()
    return {"ok": True}


@router.get("/contracts/{cid}/chain-params")
def chain_params(cid: str, user=Depends(current_user)):
    """Everything the client's wallet needs for createEscrow (which locks the money). Also used by a worker to accept."""
    c, role = load(cid, user)
    ms = many("milestones", order="idx", contract_id=cid)
    wei = [chain.to_wei(m["amount"]) for m in ms]
    return {"escrow_id": c["escrow_id"], "freelancer": c["freelancer_wallet"] or ZERO, "contract_hash": c["contract_hash"],
            "hidden_tests_hash": c["hidden_tests_hash"], "amounts_wei": [str(w) for w in wei], "total_wei": str(sum(wei)),
            "deadlines": [int(datetime.fromisoformat(m["deadline"]).timestamp()) for m in ms], "windows": [int(m["window_secs"]) for m in ms],
            "status": c["status"], "role": role}


# ---------------- delivering work: zip / GitHub / published site / shipment ----------------

def _save_upload(file: UploadFile, limit_mb: int) -> Path:
    """Streams an upload to a private temp file, enforcing the size limit."""
    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(400, "Upload a .zip file.")
    d = Path(tempfile.mkdtemp(prefix="pp-up-"))
    p, n = d / "delivery.zip", 0
    with open(p, "wb") as out:
        while chunk := file.file.read(1 << 20):
            n += len(chunk)
            if n > limit_mb * 1024 * 1024:
                shutil.rmtree(d, ignore_errors=True)
                raise HTTPException(413, f"That zip is larger than {limit_mb} MB.")
            out.write(chunk)
    with open(p, "rb") as f:
        if f.read(2) != b"PK":
            shutil.rmtree(d, ignore_errors=True)
            raise HTTPException(400, "That file is not a valid zip archive.")
    return p


def _submit(cid, idx, user, bg, dry, source, repo_url, ref, deploy_url, file):
    c, role = load(cid, user)
    m = one("milestones", contract_id=cid, idx=idx)
    if role != "freelancer" or not m:
        raise HTTPException(400, "Only the person doing the work can submit it")
    if m["delivery_type"] == "product":
        raise HTTPException(400, "A physical product is delivered by marking it as shipped, not by uploading files.")
    open_ok = ("open", "active") if dry else ("active",)
    if c["status"] not in open_ok or m["status"] != "funded":
        raise HTTPException(400, "This milestone is not open for " + ("practice runs" if dry else "verification") + ("" if c["status"] == "active" or dry else ": accept the contract first"))
    runs = many("verification_runs", contract_id=cid, milestone_idx=idx)
    if any(r["status"] == "running" for r in runs):
        raise HTTPException(409, "A check is already running")
    if dry:
        hour_ago = _now() - timedelta(hours=1)
        if len([r for r in runs if r["dry_run"] and r["requested_by"] == user["id"] and datetime.fromisoformat(r["created_at"]) > hour_ago]) >= 10:
            raise HTTPException(429, "Practice run limit reached (10 per hour)")
    else:  # our own failures never use up the worker's attempts
        real = [r for r in runs if not r["dry_run"]]
        if len([r for r in real if r["status"] != "error"]) >= settings.max_runs_per_milestone or len(real) >= 20:
            raise HTTPException(429, f"Submission limit reached ({settings.max_runs_per_milestone} per milestone)")
    source = (source or "").lower()
    try:
        if source == "github":
            verifier.parse_repo(repo_url or "")
        elif source == "zip":
            if file is None:
                raise ValueError("Choose a .zip file to upload.")
        elif source == "site":
            if not deploy_url:
                raise ValueError("Enter the address of your published website.")
        else:
            raise ValueError("Choose how you are delivering: zip file, GitHub link, or published website.")
        if m["delivery_type"] == "live_site" and not deploy_url:
            raise ValueError("This milestone needs the address of your published website.")
        if deploy_url:
            verifier.safe_url(deploy_url)
    except ValueError as e:
        raise HTTPException(400, str(e))
    zip_path = _save_upload(file, settings.max_upload_mb) if source == "zip" else None
    run_id = str(uuid.uuid4())
    db().table("verification_runs").insert({
        "id": run_id, "contract_id": cid, "milestone_idx": idx, "requested_by": user["id"], "dry_run": dry, "source": source,
        "repo_url": repo_url if source == "github" else None, "deploy_url": deploy_url or None,
        "file_name": (file.filename or "")[:200] if source == "zip" else None}).execute()
    if not dry:
        audit(user["id"], "run_started", "contract", cid, milestone=idx, source=source)
    bg.add_task(execute_run, run_id, ref, zip_path)
    return {"run_id": run_id}


@router.post("/contracts/{cid}/milestones/{idx}/submit")
def submit_work(cid: str, idx: int, bg: BackgroundTasks, source: str = Form(""), repo_url: str | None = Form(None), ref: str | None = Form(None),
                deploy_url: str | None = Form(None), file: UploadFile | None = File(None), user=Depends(current_user)):
    return _submit(cid, idx, user, bg, False, source, repo_url, ref, deploy_url, file)


@router.post("/contracts/{cid}/milestones/{idx}/dry-run")
def dry_run(cid: str, idx: int, bg: BackgroundTasks, source: str = Form(""), repo_url: str | None = Form(None), ref: str | None = Form(None),
            deploy_url: str | None = Form(None), file: UploadFile | None = File(None), user=Depends(current_user)):
    """Practice run of the visible checks. Never sent on-chain, never shown to the client."""
    return _submit(cid, idx, user, bg, True, source, repo_url, ref, deploy_url, file)


def execute_run(run_id: str, ref: str | None, zip_path: Path | None = None):
    run = one("verification_runs", id=run_id)
    c = one("contracts", id=run["contract_id"])
    idx, dry = run["milestone_idx"], run["dry_run"]
    reqs = [r for r in many("requirements", order="position", contract_id=c["id"]) if r["milestone_idx"] == idx and not (dry and r["hidden"])]
    upd = db().table("verification_runs").update
    label = f"{c['title']}, milestone {idx + 1}"
    try:
        report = verifier.run_milestone(reqs, run["repo_url"], ref, run["deploy_url"], {"contract_id": c["id"], "milestone_idx": idx, "dry_run": dry}, zip_path)
        n = report["summary"]
        status = "passed" if report["passed"] else "failed"
        summary = None
        if ai.configured():  # plain-language explanation for both people; never affects the result
            try:
                summary = compiler.summarize_run(report)
            except Exception:
                log.info("run summary unavailable", exc_info=True)
        if dry:  # practice run: nothing is hashed, stored as evidence, or sent on-chain
            upd({"status": status, "passed": n["passed"], "total": n["total"], "report": report, "commit_sha": report["commit_sha"], "ai_summary": summary,
                 "finished_at": _now().isoformat()}).eq("id", run_id).execute()
            return
        h = chain.sha256_hex(chain.canonical(report))
        upd({"status": status, "passed": n["passed"], "total": n["total"], "evidence_hash": h, "report": report, "ai_summary": summary,
             "commit_sha": report["commit_sha"], "finished_at": _now().isoformat()}).eq("id", run_id).execute()
        try:
            db().storage.from_("evidence").upload(f"{c['id']}/{run_id}.json", chain.canonical(report).encode(), {"content-type": "application/json"})
            if zip_path and Path(zip_path).exists():
                path = f"{c['id']}/{run_id}.zip"
                db().storage.from_("evidence").upload(path, Path(zip_path).read_bytes(), {"content-type": "application/zip"})
                upd({"file_path": path}).eq("id", run_id).execute()
        except Exception:
            log.warning("evidence upload failed", exc_info=True)
        if settings.escrow_address and settings.verifier_private_key:
            try:
                upd({"attest_tx": chain.attest(c["escrow_id"], idx, h, report["passed"])}).eq("id", run_id).execute()
            except Exception:
                log.exception("attestation failed")
                upd({"error": "Verified, but the on-chain attestation failed. An admin will retry it."}).eq("id", run_id).execute()
        if report["passed"]:
            notify_parties(c, "verification", "Verification passed", f"{label}: {n['passed']}/{n['total']} checks. Payment releases when the review window closes.", who="freelancer", key=f"run:{run_id}")
            notify_parties(c, "verification", "Work delivered and verified: review it", f"{label} passed all checks. You can dispute it until the review window closes, or release the payment now.", who="client", key=f"run:{run_id}")
        else:
            notify_parties(c, "verification", "Verification failed", f"{label}: {n['passed']}/{n['total']} checks passed. Fix the failing checks and submit again.", who="freelancer", key=f"run:{run_id}")
    except InfraError as e:
        upd({"status": "error", "error": str(e), "finished_at": _now().isoformat()}).eq("id", run_id).execute()
        if not dry:
            notify_parties(c, "verification", "Verification could not run", f"{label}: {e}", who="freelancer", key=f"run:{run_id}")
    except Exception:
        log.exception("run crashed")
        upd({"status": "error", "error": "Unexpected verifier error", "finished_at": _now().isoformat()}).eq("id", run_id).execute()
    finally:
        if zip_path:
            shutil.rmtree(Path(zip_path).parent, ignore_errors=True)


class ShipIn(BaseModel):
    carrier: str = Field(min_length=2, max_length=60)
    tracking: str = Field("", max_length=100)
    note: str = Field("", max_length=500)


@router.post("/contracts/{cid}/milestones/{idx}/ship")
def mark_shipped(cid: str, idx: int, body: ShipIn, user=Depends(current_user)):
    """Seller declares a physical product shipped. The record is attested on-chain, which starts the buyer's review window;
    the buyer can press 'I received it' any time to release the money immediately."""
    c, role = load(cid, user)
    m = one("milestones", contract_id=cid, idx=idx)
    if role != "freelancer" or not m or m["delivery_type"] != "product" or c["status"] != "active" or m["status"] != "funded":
        raise HTTPException(400, "This milestone cannot be marked as shipped")
    if m.get("shipment"):
        raise HTTPException(409, "Already marked as shipped")
    ship = {"carrier": body.carrier.strip(), "tracking": body.tracking.strip(), "note": body.note.strip(), "shipped_at": _now().isoformat()}
    report = {"v": 2, "source": "shipment", "contract_id": cid, "milestone_idx": idx, "shipment": ship, "passed": True,
              "summary": {"passed": 1, "total": 1}, "results": [{"title": "Seller declared the item shipped", "kind": "manual", "passed": True, "detail": f"{ship['carrier']} {ship['tracking']}".strip()}]}
    h = chain.sha256_hex(chain.canonical(report))
    run_id = str(uuid.uuid4())
    db().table("milestones").update({"shipment": ship}).eq("contract_id", cid).eq("idx", idx).execute()
    db().table("verification_runs").insert({"id": run_id, "contract_id": cid, "milestone_idx": idx, "requested_by": user["id"], "source": "shipment", "status": "passed",
                                            "passed": 1, "total": 1, "evidence_hash": h, "report": report, "finished_at": _now().isoformat()}).execute()
    tx = None
    if settings.escrow_address and settings.verifier_private_key:
        try:
            tx = chain.attest(c["escrow_id"], idx, h, True)
            db().table("verification_runs").update({"attest_tx": tx}).eq("id", run_id).execute()
        except Exception:
            log.exception("shipment attestation failed")
            db().table("verification_runs").update({"error": "Marked as shipped, but the on-chain record failed. An admin will retry it."}).eq("id", run_id).execute()
    notify_parties(c, "verification", "Your item has been shipped", f"{c['title']}, milestone {idx + 1}: {ship['carrier']} {ship['tracking']}. When it arrives, press \"I received it\" to release the payment.", who="client", key=f"ship:{cid}:{idx}")
    audit(user["id"], "shipped", "contract", cid, milestone=idx)
    return {"run_id": run_id, "evidence_hash": h}


@router.get("/runs/{run_id}")
def get_run(run_id: str, user=Depends(current_user)):
    r = one("verification_runs", id=run_id)
    if not r:
        raise HTTPException(404, "Run not found")
    _, role = load(r["contract_id"], user)
    if role == "viewer" or (r["dry_run"] and role == "client"):
        raise HTTPException(404, "Run not found")
    return r


@router.get("/runs/{run_id}/download")
def download_delivery(run_id: str, user=Depends(current_user)):
    """Short-lived link to the zip the worker delivered (client and worker only)."""
    r = one("verification_runs", id=run_id)
    if not r or not r.get("file_path"):
        raise HTTPException(404, "No delivered file for this submission")
    _, role = load(r["contract_id"], user)
    if role not in ("client", "freelancer"):
        raise HTTPException(404, "No delivered file for this submission")
    res = db().storage.from_("evidence").create_signed_url(r["file_path"], 300)
    url = res.get("signedURL") or res.get("signedUrl") if isinstance(res, dict) else None
    if not url:
        raise HTTPException(502, "Could not prepare the download. Try again.")
    return {"url": url, "file_name": r.get("file_name")}


class DisputeIn(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)
    requirement_id: str | None = None


@router.post("/contracts/{cid}/milestones/{idx}/dispute")
def prepare_dispute(cid: str, idx: int, body: DisputeIn, user=Depends(current_user)):
    """Stores the reason, returns its hash. The client then sends the on-chain dispute() with that hash."""
    c, role = load(cid, user)
    m = one("milestones", contract_id=cid, idx=idx)
    if role != "client" or not m or m["status"] != "passed":
        raise HTTPException(400, "Only a verified milestone inside its review window can be disputed")
    if any(d["milestone_idx"] == idx and d["status"] == "open" for d in many("disputes", contract_id=cid)):
        raise HTTPException(409, "A dispute already exists for this milestone")
    db().table("disputes").delete().eq("contract_id", cid).eq("milestone_idx", idx).eq("status", "pending").execute()  # retry after a failed tx
    h = chain.sha256_hex(body.reason)
    db().table("disputes").insert({"contract_id": cid, "milestone_idx": idx, "opened_by": user["id"], "requirement_id": body.requirement_id,
                                   "reason": body.reason, "reason_hash": h}).execute()
    audit(user["id"], "dispute_prepared", "contract", cid, milestone=idx)
    return {"reason_hash": h}


# ---------------- summary, public verification, passport ----------------

@router.get("/me/summary")
def summary(user=Depends(current_user)):
    out = {"client": {"contracts": 0, "locked": "0", "released": "0"}, "freelancer": {"contracts": 0, "incoming": "0", "earned": "0"}}
    for role in ("client", "freelancer"):
        rows = list_contracts(role, user)
        key = "locked" if role == "client" else "incoming"
        ms = [m for r in rows for m in r["milestones"]]
        out[role]["contracts"] = len(rows)
        out[role][key] = str(sum(Decimal(m["amount"]) for m in ms if m["status"] in ("funded", "passed", "disputed")))
        out[role]["released" if role == "client" else "earned"] = str(sum(Decimal(m["amount"]) for m in ms if m["status"] == "released"))
    return out


@router.get("/verify/{evidence_hash}")
def verify(evidence_hash: str):
    run = one("verification_runs", evidence_hash=evidence_hash)
    if not run:
        raise HTTPException(404, "No evidence with this hash")
    recomputed = chain.sha256_hex(chain.canonical(run["report"]))
    c = one("contracts", id=run["contract_id"])
    on_chain = db().table("chain_events").select("tx_hash,block_number").eq("name", "Attested").eq("args->>evidence", evidence_hash).execute().data
    return {"hash": evidence_hash, "recomputed_hash": recomputed, "matches": recomputed == evidence_hash, "report": run["report"], "source": run.get("source"),
            "attestations": on_chain, "contract": {"title": c["title"], "escrow_id": c["escrow_id"]}}


@router.get("/passport/{handle}")
def passport(handle: str):
    p = one("profiles", handle=handle)
    if not p:
        raise HTTPException(404, "No such profile")
    cs = many("contracts", freelancer_id=p["id"])
    ids = [c["id"] for c in cs]
    ms = db().table("milestones").select("*").in_("contract_id", ids).execute().data if ids else []
    runs = db().table("verification_runs").select("status,evidence_hash,contract_id,milestone_idx,dry_run,source").in_("contract_id", ids).execute().data if ids else []
    runs = [r for r in runs if not r["dry_run"] and r.get("source") != "shipment"]
    disputes = db().table("disputes").select("id").in_("contract_id", ids).execute().data if ids else []
    done = [r for r in runs if r["status"] in ("passed", "failed")]
    rel = [m for m in ms if m["status"] == "released"]
    return {
        "name": p["name"], "handle": p["handle"], "wallet": p["wallet"],
        "stats": {"contracts_completed": sum(c["status"] == "completed" for c in cs), "milestones_released": len(rel),
                  "earned": str(sum(Decimal(m["amount"]) for m in rel)), "verification_runs": len(done),
                  "pass_rate": round(100 * sum(r["status"] == "passed" for r in done) / len(done)) if done else None,
                  "disputes": len(disputes)},
        "records": [{"title": next(c["title"] for c in cs if c["id"] == m["contract_id"]), "milestone": m["title"], "amount": m["amount"], "evidence_hash": m["evidence_hash"]} for m in rel][:50],
    }


# ---------------- requirement review ----------------

class ReviewMs(BaseModel):
    title: str = ""
    requirements: list[Req] = Field(default_factory=list, max_length=20)


class ReviewIn(BaseModel):
    description: str = Field("", max_length=4000)
    milestones: list[ReviewMs] = Field(max_length=20)


@router.post("/compile/review")
def review_requirements(body: ReviewIn, user=Depends(current_user)):
    ms = [m.model_dump() for m in body.milestones]
    issues, used_ai = review_mod.review(ms), False
    if ai.configured():
        try:
            issues += [i for i in _ai(user["id"], compiler.review_ai, body.description, ms) if isinstance(i.get("milestone"), int)]
            used_ai = True
        except Exception:
            log.info("AI review unavailable", exc_info=True)
    return {"issues": issues, "ai": used_ai}


# ---------------- chat ----------------

class MsgIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    to: str | None = None  # poster replying to one interested worker on an open job


def _threaded(c: dict, role: str) -> bool:
    """Open job nobody has accepted: the poster talks to each interested worker in a separate private thread."""
    return c["status"] == "open" and bool(c.get("is_open")) and role in ("client", "viewer")


def _chat_contract(cid: str, user: dict):
    c, role = load(cid, user)
    if c["status"] == "draft":
        raise HTTPException(400, "Chat opens once the contract is paid and created")
    return c, role


def _thread_user(c, role, user, other):
    if not _threaded(c, role):
        return None
    if role == "viewer":
        return user["id"]
    if not other:
        raise HTTPException(400, "Choose which person you are talking to")
    return other


def _name(uid):
    p = one("profiles", id=uid) if uid else None
    return (p.get("handle") and "@" + p["handle"]) or (p or {}).get("name") or "Member"


@router.get("/contracts/{cid}/threads")
def list_threads(cid: str, user=Depends(current_user)):
    """The poster's inbox of interested workers for an open job."""
    c, role = _chat_contract(cid, user)
    if role != "client":
        raise HTTPException(403, "Only the person who posted the job can see its conversations")
    rows = [m for m in many("messages", order="created_at", contract_id=cid) if m.get("thread_user")]
    reads = one("contract_reads", contract_id=cid, user_id=user["id"])
    seen = reads["last_read_at"] if reads else ""
    out = {}
    for m in rows:
        t = out.setdefault(m["thread_user"], {"user_id": m["thread_user"], "name": _name(m["thread_user"]), "unread": 0})
        t.update(last_body=m["body"][:140], last_at=m["created_at"])
        if m["sender_id"] != user["id"] and m["created_at"] > seen:
            t["unread"] += 1
    return sorted(out.values(), key=lambda t: t["last_at"], reverse=True)


@router.get("/contracts/{cid}/messages")
def list_messages(cid: str, with_: str | None = Query(None, alias="with"), user=Depends(current_user)):
    c, role = _chat_contract(cid, user)
    tu = _thread_user(c, role, user, with_)
    rows = [m for m in many("messages", order="created_at", contract_id=cid, limit=1000) if m.get("thread_user") == tu][-500:]
    names = {}
    return [{"id": m["id"], "mine": m["sender_id"] == user["id"], "name": names.setdefault(m["sender_id"], _name(m["sender_id"])), "body": m["body"],
             "created_at": m["created_at"]} for m in rows]


@router.post("/contracts/{cid}/messages")
def send_message(cid: str, body: MsgIn, user=Depends(current_user)):
    c, role = _chat_contract(cid, user)
    text = body.body.strip()
    if not text:
        raise HTTPException(400, "Message is empty")
    tu = _thread_user(c, role, user, body.to)
    if role == "client" and tu and not any(m.get("thread_user") == tu for m in many("messages", contract_id=cid)):
        raise HTTPException(400, "That person has not written to you about this job")
    util.rate_limit(f"msg:{user['id']}", 30, 60, "You're sending messages too fast. Wait a moment.")
    row = db().table("messages").insert({"contract_id": cid, "sender_id": user["id"], "body": text, "thread_user": tu}).execute().data[0]
    to = (c["client_id"] if role == "viewer" else tu) if tu else None
    notify_message(c, user["id"], text, to)
    return {"id": row["id"], "created_at": row["created_at"]}


@router.post("/contracts/{cid}/read")
def mark_chat_read(cid: str, user=Depends(current_user)):
    c, _ = _chat_contract(cid, user)
    now = _now().isoformat()
    db().table("contract_reads").upsert({"contract_id": cid, "user_id": user["id"], "last_read_at": now}, on_conflict="contract_id,user_id").execute()
    from .notify import link_for
    db().table("notifications").update({"read_at": now}).eq("user_id", user["id"]).eq("kind", "message").eq("link", link_for(c, user["id"])).is_("read_at", "null").execute()
    return {"ok": True}


# ---------------- notifications ----------------

@router.get("/notifications")
def list_notifications(user=Depends(current_user)):
    items = many("notifications", order="created_at", desc=True, limit=50, user_id=user["id"])
    unread = db().table("notifications").select("id", count="exact").eq("user_id", user["id"]).is_("read_at", "null").limit(1).execute().count or 0
    return {"items": items, "unread": unread}


class ReadIn(BaseModel):
    ids: list[str] | None = None


@router.post("/notifications/read")
def read_notifications(body: ReadIn, user=Depends(current_user)):
    q = db().table("notifications").update({"read_at": _now().isoformat()}).eq("user_id", user["id"]).is_("read_at", "null")
    if body.ids is not None:
        q = q.in_("id", body.ids)
    q.execute()
    return {"ok": True}
