from datetime import datetime, timedelta, timezone

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct

from app import chain, verifier
from conftest import PEOPLE

REPO = "https://github.com/someone/project"


def fake_repo(monkeypatch, files):
    monkeypatch.setattr(verifier, "resolve_commit", lambda repo, ref: "a" * 40)

    def dl(repo, sha, dest):
        root = dest / "repo"; root.mkdir()
        for p, t in files.items():
            (root / p).write_text(t)
        return root
    monkeypatch.setattr(verifier, "download", dl)


GOOD = {"README.md": "# hi", "app.py": "def list_products(): pass\ndef delete_product(): pass"}


# ---------- contract creation & visibility ----------

def test_create_contract_hashes_and_hidden_secret(ctx):
    cid = ctx.make_contract("draft")
    r = ctx.get(f"/contracts/{cid}", "client").json()
    assert r["status"] == "draft" and r["role"] == "client" and "hidden_salt" not in r
    assert r["contract_hash"].startswith("0x") and r["hidden_tests_hash"].startswith("0x")
    assert r["total_amount"] in ("2.000000000000000000", "2.0", 2, "2")  or float(r["total_amount"]) == 2.0
    assert len(r["milestones"]) == 2 and len(r["requirements"]) == 4


def test_hidden_commitment_changes_with_hidden_tests_only(ctx):
    a, b = ctx.make_contract("draft"), ctx.make_contract("draft")
    ca, cb = (ctx.get(f"/contracts/{x}", "client").json() for x in (a, b))
    assert ca["hidden_tests_hash"] != cb["hidden_tests_hash"]  # random salt per contract
    assert ca["escrow_id"] != cb["escrow_id"]


@pytest.mark.parametrize("over,code", [
    ({"freelancer_username": "nobody_here"}, 404),   # unknown username
    ({"freelancer_username": "buyer"}, 400),         # cannot hire yourself
    ({"freelancer_username": "nowallet"}, 400),      # worker has not linked a wallet yet
    ({"milestones": []}, 422),
])
def test_create_validation(ctx, over, code):
    r = ctx.post("/contracts", "client", ctx.contract_body(**over))
    assert r.status_code == code


def test_bad_spec_and_short_deadline_rejected(ctx):
    body = ctx.contract_body()
    body["milestones"][0]["requirements"][0]["spec"] = {"path": "../x"}
    assert ctx.post("/contracts", "client", body).status_code == 400
    body = ctx.contract_body()
    body["milestones"][0]["deadline"] = datetime.now(timezone.utc).isoformat()
    assert ctx.post("/contracts", "client", body).status_code == 400


def test_creating_requires_linked_wallet(ctx):
    assert ctx.post("/contracts", "nowallet", ctx.contract_body()).status_code == 400


def test_draft_is_private_and_strangers_get_404(ctx):
    cid = ctx.make_contract("draft")
    assert ctx.get(f"/contracts/{cid}", "freelancer").status_code == 404
    assert ctx.get(f"/contracts/{cid}", "stranger").status_code == 404
    ctx.chain_event("EscrowCreated", cid, client=PEOPLE["client"][2])
    assert ctx.get(f"/contracts/{cid}", "freelancer").status_code == 200
    assert ctx.get(f"/contracts/{cid}", "stranger").status_code == 404  # named contract: not visible to others


def test_named_worker_sees_contract_in_their_list_even_before_accepting(ctx):
    cid = ctx.make_contract("open")
    assert ctx.get(f"/contracts/{cid}", "freelancer").json()["role"] == "freelancer"
    assert [c["id"] for c in ctx.get("/contracts?role=freelancer", "freelancer").json()] == [cid]
    assert ctx.get("/contracts?role=freelancer", "stranger").json() == []


def test_hidden_tests_redacted_for_freelancer_until_completed(ctx):
    cid = ctx.make_contract("active")
    f = ctx.get(f"/contracts/{cid}", "freelancer").json()
    hidden = [r for r in f["requirements"] if r["hidden"]]
    assert hidden and all(r["spec"] is None and r["title"] == "Hidden test" for r in hidden)
    c = ctx.get(f"/contracts/{cid}", "client").json()
    assert any(r["spec"] and r["title"] == "Secret edge case" for r in c["requirements"])
    assert "hidden_reveal" not in f
    for i in (0, 1):
        ctx.chain_event("Released", cid, i, to="x", amount=1)
    done = ctx.get(f"/contracts/{cid}", "freelancer").json()
    assert done["status"] == "completed" and done["hidden_reveal"]["salt"]
    assert any(r["title"] == "Secret edge case" for r in done["requirements"])


def test_delete_only_drafts_by_client(ctx):
    d, a = ctx.make_contract("draft"), ctx.make_contract("open")
    assert ctx.delete(f"/contracts/{d}", "stranger").status_code == 404
    assert ctx.delete(f"/contracts/{a}", "client").status_code == 400
    assert ctx.delete(f"/contracts/{d}", "client").status_code == 200
    assert ctx.get(f"/contracts/{d}", "client").status_code == 404


def test_chain_params(ctx):
    cid = ctx.make_contract("draft")
    p = ctx.get(f"/contracts/{cid}/chain-params", "client").json()
    assert p["amounts_wei"] == [str(10**18 * 3 // 2), str(10**18 // 2)] and p["total_wei"] == str(2 * 10**18)
    assert len(p["deadlines"]) == 2 and p["freelancer"] == PEOPLE["freelancer"][2] and p["windows"] == [259200, 259200]
    open_ = ctx.make_contract("draft", worker=None)
    assert ctx.get(f"/contracts/{open_}/chain-params", "client").json()["freelancer"] == "0x" + "0" * 40


def test_summary_and_lists(ctx):
    cid = ctx.make_contract("active")
    s = ctx.get("/me/summary", "client").json()
    assert s["client"]["contracts"] == 1 and float(s["client"]["locked"]) == 2.0
    assert float(ctx.get("/me/summary", "freelancer").json()["freelancer"]["incoming"]) == 2.0
    ctx.chain_event("Released", cid, 0, to="x", amount=1)
    assert float(ctx.get("/me/summary", "freelancer").json()["freelancer"]["earned"]) == 1.5


# ---------- verification runs ----------

def run(ctx, cid, who="freelancer", path="submit", idx=0, **body):
    return ctx.form(f"/contracts/{cid}/milestones/{idx}/{path}", who, {"source": "github", "repo_url": REPO, **body})


def test_real_run_passes_and_evidence_is_verifiable(ctx, monkeypatch):
    fake_repo(monkeypatch, GOOD)
    cid = ctx.make_contract("active")
    assert run(ctx, cid, "client").status_code == 400  # only the freelancer
    r = run(ctx, cid)
    assert r.status_code == 200
    got = ctx.get(f"/runs/{r.json()['run_id']}", "freelancer").json()
    assert got["status"] == "passed" and (got["passed"], got["total"]) == (3, 3)
    assert got["evidence_hash"] == chain.sha256_hex(chain.canonical(got["report"]))
    v = ctx.http.get(f"/verify/{got['evidence_hash']}").json()
    assert v["matches"] is True and v["report"]["commit_sha"] == "a" * 40
    hidden = [t for t in got["report"]["results"] if t["hidden"]]
    assert hidden and hidden[0]["title"] == "Hidden test" and hidden[0]["detail"] == ""
    assert ctx.db.storage.uploads  # evidence stored
    assert ctx.notifs("freelancer", kind="verification") and ctx.notifs("client", kind="verification")


def test_failing_run_reports_which_test_failed(ctx, monkeypatch):
    fake_repo(monkeypatch, {"README.md": "x", "app.py": "def list_products(): pass"})
    cid = ctx.make_contract("active")
    got = ctx.get(f"/runs/{run(ctx, cid).json()['run_id']}", "freelancer").json()
    assert got["status"] == "failed" and (got["passed"], got["total"]) == (2, 3)
    assert [t["passed"] for t in got["report"]["results"]] == [True, True, False]
    assert not ctx.notifs("client", kind="verification")  # clients only hear about passes
    assert "Verification failed" in ctx.notifs("freelancer", kind="verification")[0]["title"]


def test_run_requires_funded_milestone_and_respects_cap_and_concurrency(ctx, monkeypatch):
    fake_repo(monkeypatch, GOOD)
    cid = ctx.make_contract("open")
    assert run(ctx, cid).status_code == 400  # not accepted yet
    ctx.chain_event("Accepted", cid, freelancer=PEOPLE["freelancer"][2])
    from app.config import settings
    for _ in range(settings.max_runs_per_milestone):
        assert run(ctx, cid).status_code == 200
    assert run(ctx, cid).status_code == 429
    assert run(ctx, cid, idx=1).status_code == 200  # cap is per milestone
    cid2 = ctx.make_contract("active")
    ctx.db.table("verification_runs").insert({"contract_id": cid2, "milestone_idx": 0, "requested_by": PEOPLE["freelancer"][0], "repo_url": REPO}).execute()  # status defaults to running
    assert run(ctx, cid2).status_code == 409  # one already running


def test_non_github_repo_and_private_deploy_url_rejected(ctx):
    cid = ctx.make_contract("active")
    assert run(ctx, cid, repo_url="https://evil.com/a/b").status_code == 400
    assert run(ctx, cid, deploy_url="http://127.0.0.1:8000").status_code == 400


def test_infra_error_is_not_a_failed_attempt(ctx, monkeypatch):
    def boom(*a, **k): raise verifier.InfraError("GitHub returned 500")
    monkeypatch.setattr(verifier, "resolve_commit", boom)
    cid = ctx.make_contract("active")
    got = ctx.get(f"/runs/{run(ctx, cid).json()['run_id']}", "freelancer").json()
    assert got["status"] == "error" and "GitHub" in got["error"] and got["evidence_hash"] is None


# ---------- dry runs ----------

def test_dry_run_excludes_hidden_tests_and_leaves_no_evidence(ctx, monkeypatch):
    fake_repo(monkeypatch, {"README.md": "x", "app.py": "def list_products(): pass"})  # would fail the hidden test
    cid = ctx.make_contract("active")
    rid = run(ctx, cid, path="dry-run").json()["run_id"]
    got = ctx.get(f"/runs/{rid}", "freelancer").json()
    assert got["dry_run"] and got["status"] == "passed" and got["total"] == 2
    assert got["evidence_hash"] is None and got["attest_tx"] is None and not ctx.db.storage.uploads
    assert not ctx.notifs("client", kind="verification")


def test_dry_run_hidden_from_client_and_not_counted(ctx, monkeypatch):
    fake_repo(monkeypatch, GOOD)
    cid = ctx.make_contract("active")
    rid = run(ctx, cid, path="dry-run").json()["run_id"]
    assert ctx.get(f"/runs/{rid}", "client").status_code == 404
    assert ctx.get(f"/contracts/{cid}", "client").json()["runs"] == []
    assert len(ctx.get(f"/contracts/{cid}", "freelancer").json()["runs"]) == 1
    from app.config import settings
    for _ in range(settings.max_runs_per_milestone):
        assert run(ctx, cid).status_code == 200  # dry run did not use up a slot


def test_dry_run_rules(ctx, monkeypatch):
    fake_repo(monkeypatch, GOOD)
    cid = ctx.make_contract("active")
    assert run(ctx, cid, "client", path="dry-run").status_code == 400
    assert run(ctx, cid, "stranger", path="dry-run").status_code == 404
    for _ in range(10):
        assert run(ctx, cid, path="dry-run").status_code == 200
    assert run(ctx, cid, path="dry-run").status_code == 429


def test_dry_run_allowed_before_accepting_but_not_on_draft(ctx, monkeypatch):
    fake_repo(monkeypatch, GOOD)
    assert run(ctx, ctx.make_contract("open"), path="dry-run").status_code == 200
    assert run(ctx, ctx.make_contract("draft"), path="dry-run").status_code == 404


# ---------- disputes ----------

def test_dispute_flow(ctx):
    cid = ctx.make_contract("active")
    why = {"reason": "The delete endpoint returns 500 on a missing id."}
    assert ctx.post(f"/contracts/{cid}/milestones/0/dispute", "client", why).status_code == 400  # not verified yet
    ctx.chain_event("Attested", cid, 0, evidence=b"\x01" * 32, passed=True)
    assert ctx.post(f"/contracts/{cid}/milestones/0/dispute", "freelancer", why).status_code == 400
    r = ctx.post(f"/contracts/{cid}/milestones/0/dispute", "client", why).json()
    assert r["reason_hash"] == chain.sha256_hex(why["reason"])
    assert ctx.post(f"/contracts/{cid}/milestones/0/dispute", "client", why).status_code == 200  # pending one is replaced (failed tx retry)
    assert len(ctx.db.tables["disputes"]) == 1
    ctx.chain_event("Disputed", cid, 0, reasonHash=b"\x02" * 32)
    assert ctx.db.tables["disputes"][0]["status"] == "open"
    assert ctx.post(f"/contracts/{cid}/milestones/0/dispute", "client", why).status_code == 400  # milestone no longer 'passed'
    assert ctx.notifs("freelancer", kind="dispute") and ctx.notifs("admin", kind="dispute")
    ctx.chain_event("Resolved", cid, 0, freelancerBps=6000)
    d = ctx.db.tables["disputes"][0]
    assert d["status"] == "resolved" and d["freelancer_bps"] == 6000
    assert "60% to the worker" in ctx.notifs("client", kind="dispute")[-1]["body"]


def test_short_dispute_reason_rejected(ctx):
    cid = ctx.make_contract("active")
    assert ctx.post(f"/contracts/{cid}/milestones/0/dispute", "client", {"reason": "bad"}).status_code == 422


# ---------- profile & wallet linking ----------

def sign_link(acct, user_id, issued=None, address=None):
    address = address or acct.address
    msg = f"Link this wallet to my ProofPay account.\nUser: {user_id}\nAddress: {address}\nIssued: {(issued or datetime.now(timezone.utc)).isoformat()}"
    return {"address": address, "message": msg, "signature": acct.sign_message(encode_defunct(text=msg)).signature.hex()}


def test_wallet_link_success_and_rejections(ctx):
    me = PEOPLE["nowallet"][0]
    acct, other = Account.create(), Account.create()
    assert ctx.post("/me/wallet", "nowallet", sign_link(acct, me)).json()["wallet"] == acct.address.lower()
    assert ctx.post("/me/wallet", "stranger", sign_link(acct, PEOPLE["stranger"][0])).status_code == 409  # already linked elsewhere
    bad = sign_link(acct, me); bad["address"] = other.address
    assert ctx.post("/me/wallet", "nowallet", bad).status_code == 400
    old = sign_link(other, me, issued=datetime.now(timezone.utc) - timedelta(minutes=30))
    assert ctx.post("/me/wallet", "nowallet", old).status_code == 400
    assert ctx.post("/me/wallet", "nowallet", sign_link(other, PEOPLE["client"][0])).status_code == 400  # message names another user
    forged = sign_link(other, me); forged["signature"] = sign_link(acct, me)["signature"]
    assert ctx.post("/me/wallet", "nowallet", forged).status_code == 400


def test_profile_update_and_handle_uniqueness(ctx):
    me = ctx.put("/me", "client", {"first_name": "Cee", "last_name": "Dev", "handle": "cee_dev", "phone": "+91 98765 43210", "heard_from": "instagram"}).json()
    assert me["handle"] == "cee_dev" and me["name"] == "Cee Dev" and me["heard_from"] == "instagram"
    r = ctx.put("/me", "freelancer", {"first_name": "Eff", "handle": "cee_dev"})
    assert r.status_code == 409 and "already exists" in r.json()["detail"]
    assert ctx.put("/me", "freelancer", {"first_name": "Eff", "handle": "X"}).status_code == 400
    assert ctx.put("/me", "freelancer", {"first_name": "Eff", "handle": "admin"}).status_code == 400  # reserved
    assert ctx.put("/me", "freelancer", {"first_name": "Eff", "heard_from": "carrier-pigeon"}).status_code == 400
    assert ctx.put("/me", "freelancer", {"first_name": "Eff", "phone": "abc"}).status_code == 422
    assert ctx.put("/me", "client", {"first_name": "Cee", "handle": "cee_dev"}).status_code == 200  # keeping your own username is fine


# ---------- public pages ----------

def test_passport_counts_real_runs_only(ctx, monkeypatch):
    fake_repo(monkeypatch, GOOD)
    ctx.put("/me", "freelancer", {"first_name": "Eff", "handle": "eff_dev"})
    cid = ctx.make_contract("active", freelancer_username="eff_dev")
    ctx.get(f"/contracts/{cid}", "freelancer")  # links freelancer_id
    run(ctx, cid, path="dry-run"); run(ctx, cid)
    ctx.chain_event("Released", cid, 0, to="x", amount=1)
    p = ctx.http.get("/passport/eff_dev").json()
    assert p["stats"]["verification_runs"] == 1 and p["stats"]["pass_rate"] == 100 and p["stats"]["milestones_released"] == 1
    assert float(p["stats"]["earned"]) == 1.5 and p["records"][0]["title"] == "Inventory API"
    assert ctx.http.get("/passport/nobody").status_code == 404


def test_verify_unknown_hash_404(ctx):
    assert ctx.http.get("/verify/0xdeadbeef").status_code == 404


# ---------- admin ----------

def test_admin_endpoints_need_admin(ctx):
    ctx.make_contract("active")
    for path in ("overview", "contracts", "runs", "disputes", "users", "audit", "ai-check"):
        assert ctx.get(f"/admin/{path}", "client").status_code == 403, path
        assert ctx.get(f"/admin/{path}", "admin").status_code == 200, path
    o = ctx.get("/admin/overview", "admin").json()
    assert o["contracts"] == 1 and o["active"] == 1 and float(o["locked"]) == 2.0
    assert all("hidden_salt" not in c for c in ctx.get("/admin/contracts", "admin").json())


def test_admin_retry_attest_rejects_nothing_to_retry(ctx):
    r = ctx.post("/admin/runs/nope/retry-attest", "admin")
    assert r.status_code == 400


# ---------- AI compiler endpoints ----------

def test_compile_needs_api_key_and_review_works_without_it(ctx):
    assert ctx.post("/compile", "client", {"description": "x" * 30}).status_code == 503
    r = ctx.post("/compile/review", "client", {"description": "", "milestones": [{"title": "M", "requirements": [
        {"title": "Looks modern", "kind": "file_exists", "spec": {"path": "a.css"}}]}]}).json()
    assert r["ai"] is False and r["issues"] and r["issues"][0]["severity"] == "warn"


def test_compile_filters_invalid_ai_tests(ctx, monkeypatch):
    from app import compiler
    monkeypatch.setattr(compiler, "draft", lambda d, b: {"title": "T", "milestones": [{"title": "M", "share_pct": 100, "requirements": [
        {"title": "ok", "kind": "file_exists", "spec": {"path": "README.md"}},
        {"title": "evil", "kind": "command", "spec": {"cmd": "ls", "image": "evil:latest"}}]}]})
    from app.config import settings
    monkeypatch.setattr(settings, "gemini_api_key", "k")
    out = ctx.post("/compile", "client", {"description": "x" * 30}).json()
    assert [r["title"] for r in out["milestones"][0]["requirements"]] == ["ok"]
    assert out["milestones"][0]["delivery_type"] == "software" and out["milestones"][0]["review_days"] == 3


def test_review_ai_issues_are_merged_when_available(ctx, monkeypatch):
    from app import compiler
    from app.config import settings
    monkeypatch.setattr(settings, "gemini_api_key", "k")
    monkeypatch.setattr(compiler, "review_ai", lambda d, m: [{"milestone": 0, "requirement": None, "severity": "info", "issue": "No test covers pagination.", "suggestion": "Add one."}])
    r = ctx.post("/compile/review", "client", {"description": "x", "milestones": [{"title": "M", "requirements": [
        {"title": "Tests pass", "kind": "command", "spec": {"cmd": "pytest -q"}}]}]}).json()
    assert r["ai"] is True and any("pagination" in i["issue"] for i in r["issues"])
    monkeypatch.setattr(compiler, "review_ai", lambda d, m: (_ for _ in ()).throw(RuntimeError("down")))
    assert ctx.post("/compile/review", "client", {"description": "x", "milestones": []}).json()["ai"] is False
