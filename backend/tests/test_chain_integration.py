"""Real chain: deploys the compiled contract to a local ganache EVM and runs indexer, keeper and attestations against it.
Skipped automatically when ganache (contracts/node_modules) or the compiled artifact is missing."""
import json
import socket
import subprocess
import time
from pathlib import Path

import pytest
from eth_account import Account
from web3 import Web3

from app import chain, indexer, keeper
from app.config import settings
from conftest import PEOPLE

ROOT = Path(__file__).resolve().parents[2] / "contracts"
GANACHE = ROOT / "node_modules" / ".bin" / "ganache"
ARTIFACT = ROOT / "artifacts" / "ProofPayEscrow.json"
pytestmark = pytest.mark.skipif(not (GANACHE.exists() and ARTIFACT.exists()), reason="ganache or compiled artifact not available")
WINDOW, GRACE = 3600, 60  # contract minimum review window is 1 hour


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


@pytest.fixture
def evm(ctx, monkeypatch):
    port = free_port()
    proc = subprocess.Popen([str(GANACHE), "--wallet.deterministic", "--logging.quiet", "-p", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    w3 = Web3(Web3.HTTPProvider(f"http://127.0.0.1:{port}"))
    for _ in range(60):
        try:
            if w3.is_connected(): break
        except Exception: pass
        time.sleep(0.5)
    verifier = Account.create()
    acc = w3.eth.accounts  # 0 admin/arbitrator, 1 client, 2 freelancer
    w3.eth.send_transaction({"from": acc[0], "to": verifier.address, "value": 10**18})
    art = json.loads(ARTIFACT.read_text())
    deployed = w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"]).constructor(acc[0], verifier.address, acc[0], GRACE).transact({"from": acc[0]})
    address = w3.eth.wait_for_transaction_receipt(deployed).contractAddress
    monkeypatch.setattr(settings, "mst_rpc_url", f"http://127.0.0.1:{port}")
    monkeypatch.setattr(settings, "escrow_address", address)
    monkeypatch.setattr(settings, "verifier_private_key", verifier.key.hex())
    monkeypatch.setattr(settings, "indexer_start_block", 0)
    chain.w3.cache_clear()
    # map the app users onto the chain accounts
    ctx.db.table("profiles").update({"wallet": acc[1].lower()}).eq("id", PEOPLE["client"][0]).execute()
    ctx.db.table("profiles").update({"wallet": acc[2].lower()}).eq("id", PEOPLE["freelancer"][0]).execute()
    contract = w3.eth.contract(address=address, abi=art["abi"])
    yield type("E", (), {"w3": w3, "c": contract, "acc": acc, "ctx": ctx, "address": address})
    proc.terminate(); proc.wait(timeout=10); chain.w3.cache_clear()


def tx(w3, fn, sender, value=0):
    h = fn.transact({"from": sender, "value": value})
    assert w3.eth.wait_for_transaction_receipt(h).status == 1
    return h


def sync():
    while indexer.run_once():
        pass


def mk(evm, open_job=False, accept=True):
    """Creates the contract in the API, then locks the money on-chain (what the web app does when the buyer pays)."""
    ctx = evm.ctx
    over = {"freelancer_username": None} if open_job else {}
    body = ctx.contract_body(**over)
    for m in body["milestones"]:
        m["review_days"] = 1  # 24h on-chain; tests fast-forward the chain clock
    cid = ctx.post("/contracts", "client", body).json()["id"]
    p = ctx.get(f"/contracts/{cid}/chain-params", "client").json()
    eid = bytes.fromhex(p["escrow_id"][2:])
    tx(evm.w3, evm.c.functions.createEscrow(eid, Web3.to_checksum_address(p["freelancer"]), bytes.fromhex(p["contract_hash"][2:]), bytes.fromhex(p["hidden_tests_hash"][2:]),
                                            [int(x) for x in p["amounts_wei"]], p["deadlines"], p["windows"]), evm.acc[1], int(p["total_wei"]))
    if accept:
        tx(evm.w3, evm.c.functions.acceptContract(eid), evm.acc[2])
    return cid, p, eid


def status(ctx, cid):
    return ctx.db.table("contracts").select("*").eq("id", cid).execute().data[0]["status"]


def ms_status(ctx, cid, i):
    return ctx.db.table("milestones").select("*").eq("contract_id", cid).eq("idx", i).execute().data[0]["status"]


def advance(w3, secs):
    w3.provider.make_request("evm_increaseTime", [secs]); w3.provider.make_request("evm_mine", [])


DAY = 86400


def test_full_lifecycle_through_real_indexer_and_keeper(evm):
    ctx, w3 = evm.ctx, evm.w3
    cid, p, eid = mk(evm, accept=False)
    sync()
    assert status(ctx, cid) == "open" and ms_status(ctx, cid, 0) == "funded" and ctx.notifs("freelancer", kind="invite")
    assert w3.eth.get_balance(evm.address) == int(p["total_wei"])  # locked at creation
    tx(w3, evm.c.functions.acceptContract(eid), evm.acc[2]); sync()
    assert status(ctx, cid) == "active" and ctx.notifs("client", kind="contract")

    evidence = chain.sha256_hex("report-0")
    attest_tx = chain.attest(p["escrow_id"], 0, evidence, True); sync()
    assert ms_status(ctx, cid, 0) == "passed"
    assert ctx.db.table("milestones").select("*").eq("contract_id", cid).eq("idx", 0).execute().data[0]["review_ends_at"]
    assert any(e["name"] == "Attested" and e["tx_hash"] == attest_tx for e in ctx.get(f"/contracts/{cid}", "client").json()["events"])

    assert keeper.finalize_due() == 0  # never early
    before = w3.eth.get_balance(evm.acc[2])
    advance(w3, DAY + 5)
    assert keeper.finalize_due() == 1  # uses this milestone's own window
    assert w3.eth.get_balance(evm.acc[2]) - before == int(p["amounts_wei"][0])
    sync()
    assert ms_status(ctx, cid, 0) == "released" and status(ctx, cid) == "active"
    assert "1.5 MST" in ctx.notifs("freelancer", kind="payment")[0]["title"]

    tx(w3, evm.c.functions.approve(eid, 1), evm.acc[1]); sync()
    assert ms_status(ctx, cid, 1) == "released" and status(ctx, cid) == "completed"
    assert w3.eth.get_balance(evm.address) == 0
    done = ctx.get(f"/contracts/{cid}", "freelancer").json()
    assert done["hidden_reveal"]["salt"]
    assert [e["name"] for e in done["events"]][:2] == ["EscrowCreated", "Accepted"]


def test_open_job_any_worker_accepts_and_is_linked(evm):
    ctx, w3 = evm.ctx, evm.w3
    cid, p, eid = mk(evm, open_job=True, accept=False); sync()
    assert status(ctx, cid) == "open" and p["freelancer"] == "0x" + "0" * 40
    jobs = ctx.get("/jobs", "freelancer").json()
    assert [j["id"] for j in jobs] == [cid] and ctx.get("/jobs", "client").json() == []
    tx(w3, evm.c.functions.acceptContract(eid), evm.acc[2]); sync()
    c = ctx.db.table("contracts").select("*").eq("id", cid).execute().data[0]
    assert c["status"] == "active" and c["freelancer_id"] == PEOPLE["freelancer"][0] and c["freelancer_wallet"] == evm.acc[2].lower()
    assert ctx.get("/jobs", "freelancer").json() == []  # no longer open
    assert ctx.get(f"/contracts/{cid}", "stranger").status_code == 404


def test_revoke_before_acceptance_refunds_and_ends_cancelled(evm):
    ctx, w3 = evm.ctx, evm.w3
    cid, p, eid = mk(evm, open_job=True, accept=False); sync()
    c0 = w3.eth.get_balance(evm.acc[1])
    tx(w3, evm.c.functions.revoke(eid), evm.acc[1]); sync()
    assert w3.eth.get_balance(evm.address) == 0 and w3.eth.get_balance(evm.acc[1]) > c0
    assert status(ctx, cid) == "cancelled" and ms_status(ctx, cid, 0) == "refunded"
    assert ctx.get("/jobs", "freelancer").json() == []


def test_cancel_needs_worker_agreement_then_refunds(evm):
    ctx, w3 = evm.ctx, evm.w3
    cid, p, eid = mk(evm); sync()
    tx(w3, evm.c.functions.approve(eid, 0), evm.acc[1]); sync()
    tx(w3, evm.c.functions.requestCancel(eid), evm.acc[1]); sync()
    assert ctx.db.table("contracts").select("*").eq("id", cid).execute().data[0]["cancel_requested"] is True
    assert ctx.notifs("freelancer", title="The client asked to cancel")
    tx(w3, evm.c.functions.withdrawCancel(eid), evm.acc[1]); sync()
    assert ctx.db.table("contracts").select("*").eq("id", cid).execute().data[0]["cancel_requested"] is False
    tx(w3, evm.c.functions.requestCancel(eid), evm.acc[1])
    c0 = w3.eth.get_balance(evm.acc[1])
    tx(w3, evm.c.functions.acceptCancel(eid), evm.acc[2]); sync()
    assert w3.eth.get_balance(evm.acc[1]) - c0 == int(p["amounts_wei"][1])  # only the unreleased milestone comes back
    assert status(ctx, cid) == "cancelled" and ms_status(ctx, cid, 0) == "released" and ms_status(ctx, cid, 1) == "refunded"


def test_indexer_is_idempotent_and_resumes(evm):
    ctx = evm.ctx
    cid, p, eid = mk(evm, accept=False)
    sync(); sync()
    assert len(ctx.db.tables["chain_events"]) == 1
    assert ctx.db.tables["indexer_state"][0]["last_block"] == evm.w3.eth.block_number
    ctx.db.tables["indexer_state"][0]["last_block"] = 0  # force a full re-scan
    sync()
    assert len(ctx.db.tables["chain_events"]) == 1 and len(ctx.notifs("freelancer", kind="invite")) == 1


def test_escrow_created_by_someone_else_is_ignored(evm):
    ctx, w3 = evm.ctx, evm.w3
    body = ctx.contract_body()
    cid = ctx.post("/contracts", "client", body).json()["id"]
    p = ctx.get(f"/contracts/{cid}/chain-params", "client").json()
    # an attacker front-runs the same escrow id from a different account
    tx(w3, evm.c.functions.createEscrow(bytes.fromhex(p["escrow_id"][2:]), evm.acc[2], bytes.fromhex(p["contract_hash"][2:]), bytes.fromhex(p["hidden_tests_hash"][2:]),
                                        [10**15], p["deadlines"][:1], [3600]), evm.acc[3], 10**15)
    sync()
    assert status(ctx, cid) == "draft"


def test_dispute_and_arbitration_end_to_end(evm):
    ctx, w3 = evm.ctx, evm.w3
    cid, p, eid = mk(evm)
    chain.attest(p["escrow_id"], 0, chain.sha256_hex("r"), True); sync()
    why = {"reason": "Endpoint returns the wrong status code on delete."}
    h = ctx.post(f"/contracts/{cid}/milestones/0/dispute", "client", why).json()["reason_hash"]
    tx(w3, evm.c.functions.dispute(eid, 0, bytes.fromhex(h[2:])), evm.acc[1]); sync()
    assert ms_status(ctx, cid, 0) == "disputed" and ctx.db.tables["disputes"][0]["status"] == "open"
    advance(w3, DAY + 5)
    assert keeper.finalize_due() == 0  # disputed funds are never auto-released
    f0, c0 = w3.eth.get_balance(evm.acc[2]), w3.eth.get_balance(evm.acc[1])
    tx(w3, evm.c.functions.resolve(eid, 0, 7000), evm.acc[0]); sync()
    assert w3.eth.get_balance(evm.acc[2]) - f0 == int(p["amounts_wei"][0]) * 7 // 10
    assert w3.eth.get_balance(evm.acc[1]) - c0 == int(p["amounts_wei"][0]) * 3 // 10
    d = ctx.db.tables["disputes"][0]
    assert d["status"] == "resolved" and d["freelancer_bps"] == 7000 and ms_status(ctx, cid, 0) == "released"


def test_refund_after_expiry_updates_state(evm):
    ctx, w3 = evm.ctx, evm.w3
    cid, p, eid = mk(evm); sync()
    advance(w3, 6 * DAY + GRACE)
    tx(w3, evm.c.functions.refundExpired(eid, 0), evm.acc[1]); sync()
    assert ms_status(ctx, cid, 0) == "refunded" and ctx.notifs("freelancer", kind="payment")


def test_failed_attestation_leaves_milestone_open_then_admin_can_retry(evm):
    ctx, w3 = evm.ctx, evm.w3
    cid, p, eid = mk(evm); sync()
    ev = chain.sha256_hex("late")
    ctx.db.table("verification_runs").insert({"id": "run-1", "contract_id": cid, "milestone_idx": 0, "requested_by": PEOPLE["freelancer"][0],
                                              "repo_url": "https://github.com/a/b", "status": "passed", "evidence_hash": ev,
                                              "error": "Verified, but the on-chain attestation failed. An admin will retry it."}).execute()
    assert ctx.post("/admin/runs/run-1/retry-attest", "client").status_code == 403
    r = ctx.post("/admin/runs/run-1/retry-attest", "admin")
    assert r.status_code == 200
    sync()
    assert ms_status(ctx, cid, 0) == "passed"
    run = ctx.db.tables["verification_runs"][0]
    assert run["attest_tx"] == r.json()["tx"] and run["error"] is None
    assert ctx.post("/admin/runs/run-1/retry-attest", "admin").status_code == 400


def test_execute_run_attests_on_chain_and_notifies(evm, monkeypatch):
    from test_routes import GOOD, fake_repo, run
    ctx, w3 = evm.ctx, evm.w3
    fake_repo(monkeypatch, GOOD)
    cid, p, eid = mk(evm); sync()
    rid = run(ctx, cid).json()["run_id"]
    got = ctx.get(f"/runs/{rid}", "freelancer").json()
    assert got["status"] == "passed" and got["attest_tx"] and not got["error"]
    sync()
    assert ms_status(ctx, cid, 0) == "passed"
    on_chain = chain.milestone_state(p["escrow_id"], 0)
    assert on_chain["status"] == 1 and on_chain["evidence"] == got["evidence_hash"] and on_chain["window"] == DAY
    assert ctx.http.get(f"/verify/{got['evidence_hash']}").json()["attestations"]


def test_product_shipment_is_attested_and_buyer_can_confirm_receipt(evm):
    ctx, w3 = evm.ctx, evm.w3
    body = ctx.contract_body()
    body["milestones"] = [{"title": "Ceramic mug", "amount": "0.5", "deadline": body["milestones"][0]["deadline"], "delivery_type": "product", "review_days": 7,
                           "requirements": [{"title": "I received the mug", "kind": "manual", "spec": {"note": ""}}]}]
    cid = ctx.post("/contracts", "client", body).json()["id"]
    p = ctx.get(f"/contracts/{cid}/chain-params", "client").json()
    eid = bytes.fromhex(p["escrow_id"][2:])
    tx(w3, evm.c.functions.createEscrow(eid, Web3.to_checksum_address(p["freelancer"]), bytes.fromhex(p["contract_hash"][2:]), bytes.fromhex(p["hidden_tests_hash"][2:]),
                                        [int(x) for x in p["amounts_wei"]], p["deadlines"], p["windows"]), evm.acc[1], int(p["total_wei"]))
    tx(w3, evm.c.functions.acceptContract(eid), evm.acc[2]); sync()
    r = ctx.post(f"/contracts/{cid}/milestones/0/ship", "freelancer", {"carrier": "Delhivery", "tracking": "DL123", "note": "Packed in bubble wrap"})
    assert r.status_code == 200, r.text
    sync()
    assert ms_status(ctx, cid, 0) == "passed" and ctx.notifs("client", kind="verification")
    f0 = w3.eth.get_balance(evm.acc[2])
    tx(w3, evm.c.functions.approve(eid, 0), evm.acc[1]); sync()  # "I received it"
    assert w3.eth.get_balance(evm.acc[2]) - f0 == int(p["amounts_wei"][0]) and status(ctx, cid) == "completed"
