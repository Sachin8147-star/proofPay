"""Open jobs board, private pre-acceptance chat threads, locked-funds explanations, cancel flow state, shipping."""
from datetime import datetime, timedelta, timezone

from conftest import PEOPLE

REPO = "https://github.com/someone/project"


def open_job(ctx):
    return ctx.make_contract("open", worker=None)


# ---------- open jobs board ----------

def test_jobs_board_lists_only_funded_open_jobs_from_others(ctx):
    cid = open_job(ctx)
    ctx.make_contract("draft", worker=None)                 # unpaid: not listed
    ctx.make_contract("open")                               # named worker: not listed
    jobs = ctx.get("/jobs", "stranger").json()
    assert [j["id"] for j in jobs] == [cid]
    j = jobs[0]
    assert j["poster"]["handle"] == "buyer" and float(j["total"]) == 2.0 and len(j["milestones"]) == 2 and j["types"] == ["software"]
    assert ctx.get("/jobs", "client").json() == []          # you never see your own posts here


def test_jobs_search_and_removal_once_accepted(ctx):
    cid = open_job(ctx)
    assert len(ctx.get("/jobs?q=inventory", "stranger").json()) == 1 and ctx.get("/jobs?q=wedding", "stranger").json() == []
    ctx.chain_event("Accepted", cid, freelancer=PEOPLE["stranger"][2])
    assert ctx.get("/jobs", "freelancer").json() == []


def test_viewer_sees_the_offer_but_not_hidden_tests_or_history(ctx):
    cid = open_job(ctx)
    v = ctx.get(f"/contracts/{cid}", "stranger").json()
    assert v["role"] == "viewer" and v["status"] == "open" and v["escrow_id"] and v["client"]["handle"] == "buyer"
    hidden = [r for r in v["requirements"] if r["hidden"]]
    assert hidden and all(r["spec"] is None for r in hidden)
    for k in ("runs", "events", "disputes", "hidden_salt", "idea", "ai_notes"):
        assert k not in v or not v[k], k
    assert ctx.get(f"/runs/nope", "stranger").status_code == 404


def test_accepted_open_job_is_private_again(ctx):
    cid = open_job(ctx)
    ctx.chain_event("Accepted", cid, freelancer=PEOPLE["freelancer"][2])
    assert ctx.get(f"/contracts/{cid}", "stranger").status_code == 404
    assert ctx.get(f"/contracts/{cid}", "freelancer").json()["role"] == "freelancer"
    assert ctx.get(f"/contracts/{cid}/chain-params", "freelancer").status_code == 200


# ---------- pre-acceptance chat threads ----------

def say(ctx, cid, who, text, to=None):
    return ctx.post(f"/contracts/{cid}/messages", who, {"body": text, **({"to": to} if to else {})})


def test_each_interested_worker_has_a_private_thread(ctx):
    cid = open_job(ctx)
    s_id, f_id = PEOPLE["stranger"][0], PEOPLE["freelancer"][0]
    assert say(ctx, cid, "stranger", "I can do this in 5 days").status_code == 200
    assert say(ctx, cid, "freelancer", "Can you share a budget range?").status_code == 200
    assert say(ctx, cid, "client", "Yes, 2 MST is fixed", to=s_id).status_code == 200
    assert [m["body"] for m in ctx.get(f"/contracts/{cid}/messages", "stranger").json()] == ["I can do this in 5 days", "Yes, 2 MST is fixed"]
    assert [m["body"] for m in ctx.get(f"/contracts/{cid}/messages", "freelancer").json()] == ["Can you share a budget range?"]  # cannot read the other thread
    assert [m["body"] for m in ctx.get(f"/contracts/{cid}/messages?with={f_id}", "client").json()] == ["Can you share a budget range?"]
    th = ctx.get(f"/contracts/{cid}/threads", "client").json()
    assert {t["user_id"] for t in th} == {s_id, f_id} and all(t["unread"] >= 1 for t in th if t["user_id"] == f_id)
    assert ctx.get(f"/contracts/{cid}/threads", "stranger").status_code == 403


def test_poster_must_choose_a_thread_and_cannot_start_one(ctx):
    cid = open_job(ctx)
    assert say(ctx, cid, "client", "hello?").status_code == 400                                   # who to?
    assert say(ctx, cid, "client", "hello?", to=PEOPLE["stranger"][0]).status_code == 400          # they never wrote first
    assert ctx.get(f"/contracts/{cid}/messages", "client").status_code == 400


def test_thread_notifications_link_to_the_right_page(ctx):
    cid = open_job(ctx)
    say(ctx, cid, "stranger", "interested!")
    n = ctx.notifs("client", kind="message")[0]
    assert n["link"] == f"/client/{cid}"
    say(ctx, cid, "client", "great, tell me more", to=PEOPLE["stranger"][0])
    assert ctx.notifs("stranger", kind="message")[0]["link"] == f"/jobs/{cid}"
    assert not ctx.notifs("freelancer", kind="message")  # other candidates are not told


def test_thread_messages_do_not_leak_into_the_contract_chat(ctx):
    cid = open_job(ctx)
    say(ctx, cid, "stranger", "private pitch")
    ctx.chain_event("Accepted", cid, freelancer=PEOPLE["freelancer"][2])
    assert ctx.get(f"/contracts/{cid}/messages", "client").json() == []
    assert ctx.get(f"/contracts/{cid}/messages", "freelancer").json() == []
    assert ctx.get(f"/contracts/{cid}/messages", "stranger").status_code == 404


def test_viewer_cannot_chat_on_drafts(ctx):
    d = ctx.make_contract("draft", worker=None)
    assert say(ctx, d, "stranger", "hi").status_code == 404


# ---------- creation rules ----------

def test_creation_rules_for_product_and_site_milestones(ctx):
    due = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    base = ctx.contract_body()
    prod = {"title": "Mug", "amount": "0.2", "deadline": due, "delivery_type": "product", "review_days": 7, "requirements": [{"title": "Mug arrives", "kind": "manual", "spec": {"note": ""}}]}
    site = {"title": "Site", "amount": "1", "deadline": due, "delivery_type": "live_site", "requirements": [{"title": "Contact form", "kind": "ai_review", "spec": {"claim": "The site has a contact form"}}]}
    ok = ctx.post("/contracts", "client", {**base, "milestones": [site, prod]})
    assert ok.status_code == 200
    cid = ok.json()["id"]
    ms = ctx.get(f"/contracts/{cid}", "client").json()["milestones"]
    assert [(m["delivery_type"], m["window_secs"]) for m in ms] == [("live_site", 3 * 86400), ("product", 7 * 86400)]
    bad_prod = {**prod, "requirements": [{"title": "xx", "kind": "file_exists", "spec": {"path": "a.txt"}}]}
    assert ctx.post("/contracts", "client", {**base, "milestones": [bad_prod]}).status_code == 400
    only_manual = {**site, "requirements": [{"title": "I look at it", "kind": "manual", "spec": {}}]}
    assert ctx.post("/contracts", "client", {**base, "milestones": [only_manual]}).status_code == 400
    assert ctx.post("/contracts", "client", {**base, "milestones": [{**site, "delivery_type": "teleport"}]}).status_code == 400
    assert ctx.post("/contracts", "client", {**base, "milestones": [{**site, "review_days": 90}]}).status_code == 422
    bad_ai = {**site, "requirements": [{"title": "xx", "kind": "ai_review", "spec": {"claim": "no"}}]}
    assert ctx.post("/contracts", "client", {**base, "milestones": [bad_ai]}).status_code == 400


def test_buyer_idea_and_ai_notes_stay_private_to_the_buyer(ctx):
    cid = ctx.make_contract("active", idea="mujhe ek bakery website chahiye", ai_notes={"understood": "A bakery site"})
    assert ctx.get(f"/contracts/{cid}", "client").json()["idea"].startswith("mujhe")
    f = ctx.get(f"/contracts/{cid}", "freelancer").json()
    assert not f["idea"] and not f["ai_notes"]


def test_worker_can_not_be_hired_twice_over_open_flag(ctx):
    cid = ctx.make_contract("open")
    c = ctx.get(f"/contracts/{cid}", "client").json()
    assert c["is_open"] is False and c["freelancer_handle"] == "seller"


# ---------- locked funds and wallet page ----------

def test_wallet_summary_explains_locked_money(ctx):
    cid = ctx.make_contract("open", worker=None)
    s = ctx.get("/me/wallet-summary", "client").json()
    assert s["address"] == PEOPLE["client"][2] and float(s["locked_total"]) == 2.0 and float(s["incoming_total"]) == 0
    first = s["locked"][0]
    assert "until someone accepts" in first["why"] and "take it back" in first["unlock"].lower() and first["role"] == "client"
    ctx.chain_event("Accepted", cid, freelancer=PEOPLE["freelancer"][2])
    s = ctx.get("/me/wallet-summary", "client").json()
    assert "worker is only paid" in s["locked"][0]["why"]
    f = ctx.get("/me/wallet-summary", "freelancer").json()
    assert float(f["incoming_total"]) == 2.0 and float(f["locked_total"]) == 0 and f["locked"][0]["role"] == "freelancer"
    ctx.chain_event("Attested", cid, 0, evidence=b"\x01" * 32, passed=True)
    s = ctx.get("/me/wallet-summary", "client").json()
    passed = next(x for x in s["locked"] if x["milestone_idx"] == 0)
    assert "review" in passed["why"].lower() and "UTC" in passed["unlock"]


def test_wallet_summary_activity_and_release(ctx):
    cid = ctx.make_contract("active")
    ctx.db.table("chain_events").insert({"tx_hash": "0xaa", "log_index": 0, "block_number": 1, "name": "Released", "escrow_id": ctx.db.table("contracts").select("*").eq("id", cid).execute().data[0]["escrow_id"],
                                         "idx": 0, "args": {"amount": str(15 * 10**17), "to": "x"}}).execute()
    ctx.chain_event("Released", cid, 0, to="x", amount=15 * 10**17)
    a = ctx.get("/me/wallet-summary", "freelancer").json()["activity"][0]
    assert a["direction"] == "in" and float(a["amount"]) == 1.5 and "You were paid" in a["text"]
    a = ctx.get("/me/wallet-summary", "client").json()["activity"][0]
    assert a["direction"] == "out" and "Payment released" in a["text"]
    locked = ctx.get("/me/wallet-summary", "client").json()
    assert [x["milestone_idx"] for x in locked["locked"]] == [1]  # released money is no longer locked


def test_wallet_summary_without_a_wallet(ctx):
    assert ctx.get("/me/wallet-summary", "nowallet").json() == {"address": None}


def test_cancel_request_is_reflected_in_lock_reason(ctx):
    cid = ctx.make_contract("active")
    ctx.chain_event("CancelRequested", cid)
    assert "asked to cancel" in ctx.notifs("freelancer", kind="contract")[-1]["title"]
    s = ctx.get("/me/wallet-summary", "client").json()
    assert "worker agrees" in s["locked"][0]["unlock"]
    ctx.chain_event("CancelWithdrawn", cid)
    assert "worker agrees" not in ctx.get("/me/wallet-summary", "client").json()["locked"][0]["unlock"]


def test_revoke_and_cancel_end_as_cancelled_not_completed(ctx):
    cid = ctx.make_contract("open", worker=None)
    for i in (0, 1):
        ctx.chain_event("Refunded", cid, i, amount=1)
    ctx.chain_event("Cancelled", cid, refunded=1)
    assert ctx.get(f"/contracts/{cid}", "client").json()["status"] == "cancelled"
    assert not ctx.notifs("freelancer")                       # an open job has no worker to bother
    assert ctx.get("/me/wallet-summary", "client").json()["locked"] == []


# ---------- physical products ----------

def make_product(ctx):
    due = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    body = ctx.contract_body(milestones=[{"title": "Mug", "amount": "0.4", "deadline": due, "delivery_type": "product", "review_days": 7,
                                          "requirements": [{"title": "Mug arrives", "kind": "manual", "spec": {"note": ""}}]}])
    cid = ctx.post("/contracts", "client", body).json()["id"]
    ctx.chain_event("EscrowCreated", cid, client=PEOPLE["client"][2])
    ctx.chain_event("Accepted", cid, freelancer=PEOPLE["freelancer"][2])
    return cid


def test_mark_shipped_records_evidence_and_tells_the_buyer(ctx):
    cid = make_product(ctx)
    ship = {"carrier": "Delhivery", "tracking": "DL123"}
    assert ctx.post(f"/contracts/{cid}/milestones/0/ship", "client", ship).status_code == 400    # buyer cannot ship
    assert ctx.post(f"/contracts/{cid}/milestones/0/ship", "freelancer", {"carrier": "x"}).status_code == 422
    r = ctx.post(f"/contracts/{cid}/milestones/0/ship", "freelancer", ship)
    assert r.status_code == 200 and r.json()["evidence_hash"].startswith("0x")
    assert "shipped" in ctx.notifs("client", kind="verification")[0]["title"]
    run = ctx.db.tables["verification_runs"][0]
    assert run["source"] == "shipment" and run["status"] == "passed" and run["report"]["shipment"]["tracking"] == "DL123"
    assert ctx.post(f"/contracts/{cid}/milestones/0/ship", "freelancer", ship).status_code == 409
    assert ctx.http.get(f"/verify/{r.json()['evidence_hash']}").json()["matches"] is True
    assert ctx.get(f"/contracts/{cid}", "client").json()["milestones"][0]["shipment"]["carrier"] == "Delhivery"


def test_products_cannot_be_delivered_as_files_and_software_cannot_be_shipped(ctx):
    cid = make_product(ctx)
    r = ctx.form(f"/contracts/{cid}/milestones/0/submit", "freelancer", {"source": "github", "repo_url": REPO})
    assert r.status_code == 400 and "shipped" in r.json()["detail"]
    sw = ctx.make_contract("active")
    assert ctx.post(f"/contracts/{sw}/milestones/0/ship", "freelancer", {"carrier": "DHL"}).status_code == 400


def test_review_window_ends_at_is_set_when_work_passes(ctx):
    cid = ctx.make_contract("active")
    ctx.chain_event("Attested", cid, 0, evidence=b"\x01" * 32, passed=True)
    m = ctx.get(f"/contracts/{cid}", "client").json()["milestones"][0]
    ends = datetime.fromisoformat(m["review_ends_at"])
    assert timedelta(days=2, hours=23) < ends - datetime.now(timezone.utc) < timedelta(days=3, minutes=1)
