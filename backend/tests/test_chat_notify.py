from datetime import datetime, timedelta, timezone

from app import keeper, notify
from conftest import PEOPLE


def say(ctx, cid, who, text="hello"):
    return ctx.post(f"/contracts/{cid}/messages", who, {"body": text})


# ---------- chat ----------

def test_chat_between_parties_only(ctx):
    cid = ctx.make_contract("open")
    assert say(ctx, cid, "client", "Hi, ready to start?").status_code == 200
    assert say(ctx, cid, "freelancer", "Yes, reviewing now.").status_code == 200
    for who in ("client", "freelancer"):
        msgs = ctx.get(f"/contracts/{cid}/messages", who).json()
        assert [m["body"] for m in msgs] == ["Hi, ready to start?", "Yes, reviewing now."]
        assert [m["mine"] for m in msgs] == ([True, False] if who == "client" else [False, True])
        assert msgs[0]["name"] == "@buyer" and msgs[1]["name"] == "@seller"
    assert ctx.get(f"/contracts/{cid}/messages", "stranger").status_code == 404
    assert say(ctx, cid, "stranger").status_code == 404
    assert say(ctx, cid, "admin").status_code == 404  # admins do not read private chats


def test_chat_closed_on_drafts_and_validates_input(ctx):
    d = ctx.make_contract("draft")
    assert say(ctx, d, "client").status_code == 400 and ctx.get(f"/contracts/{d}/messages", "client").status_code == 400
    cid = ctx.make_contract("open")
    assert say(ctx, cid, "client", "").status_code == 422
    assert say(ctx, cid, "client", "   ").status_code == 400
    assert say(ctx, cid, "client", "x" * 2001).status_code == 422
    assert say(ctx, cid, "client", "x" * 2000).status_code == 200


def test_chat_text_is_stored_verbatim_not_interpreted(ctx):
    cid = ctx.make_contract("open")
    say(ctx, cid, "client", "<script>alert(1)</script> https://x.test")
    assert ctx.get(f"/contracts/{cid}/messages", "freelancer").json()[0]["body"] == "<script>alert(1)</script> https://x.test"


def test_chat_rate_limit(ctx):
    cid = ctx.make_contract("open")
    assert all(say(ctx, cid, "client", f"m{i}").status_code == 200 for i in range(30))
    assert say(ctx, cid, "client", "one too many").status_code == 429
    assert say(ctx, cid, "freelancer", "different sender is fine").status_code == 200


def test_message_notifications_coalesce_until_read(ctx):
    cid = ctx.make_contract("open")
    base = len(ctx.notifs("freelancer", kind="message"))
    for t in ("one", "two", "three"):
        say(ctx, cid, "client", t)
    n = ctx.notifs("freelancer", kind="message")
    assert len(n) - base == 1 and n[-1]["body"] == "three" and n[-1]["link"] == f"/freelancer/{cid}"
    assert not ctx.notifs("client", kind="message")  # never notify the sender
    assert ctx.get("/notifications", "freelancer").json()["unread"] >= 1
    assert ctx.post(f"/contracts/{cid}/read", "freelancer").status_code == 200
    assert all(x["read_at"] for x in ctx.notifs("freelancer", kind="message"))
    say(ctx, cid, "client", "four")
    assert len(ctx.notifs("freelancer", kind="message")) - base == 2  # new unread after a read
    say(ctx, cid, "freelancer", "reply")
    assert ctx.notifs("client", kind="message")[-1]["link"] == f"/client/{cid}"


# ---------- notifications API ----------

def test_notifications_list_and_mark_read(ctx):
    cid = ctx.make_contract("open")  # client: "money locked"; the named worker gets an invite
    r = ctx.get("/notifications", "freelancer").json()
    assert r["unread"] == 1 and r["items"][0]["kind"] == "invite" and r["items"][0]["link"] == f"/freelancer/{cid}"
    ctx.chain_event("Accepted", cid, freelancer=PEOPLE["freelancer"][2])
    assert ctx.get("/notifications", "client").json()["unread"] == 2
    nid = r["items"][0]["id"]
    assert ctx.post("/notifications/read", "client", {"ids": [nid]}).status_code == 200  # someone else's id: ignored
    assert ctx.get("/notifications", "freelancer").json()["unread"] == 1
    ctx.post("/notifications/read", "freelancer", {"ids": [nid]})
    assert ctx.get("/notifications", "freelancer").json()["unread"] == 0
    assert ctx.get("/notifications", "client").json()["unread"] == 2
    ctx.post("/notifications/read", "client", {})
    assert ctx.get("/notifications", "client").json()["unread"] == 0


def test_notifications_are_private_per_user(ctx):
    ctx.make_contract("open")
    assert ctx.get("/notifications", "stranger").json() == {"items": [], "unread": 0}


def test_lifecycle_notifications_reach_the_right_people(ctx):
    cid = ctx.make_contract("open")
    assert [n["kind"] for n in ctx.notifs("freelancer")] == ["invite"] and [n["kind"] for n in ctx.notifs("client")] == ["payment"]
    ctx.chain_event("Accepted", cid, freelancer=PEOPLE["freelancer"][2])
    assert "accepted" in ctx.notifs("client", kind="contract")[0]["title"]
    ctx.chain_event("Released", cid, 0, to="x", amount=1)
    assert "1.5 MST" in ctx.notifs("freelancer", kind="payment")[0]["title"]
    assert ctx.notifs("client", kind="payment")
    ctx.chain_event("Cancelled", cid)
    assert "cancelled" in ctx.notifs("client")[-1]["title"] and "cancelled" in ctx.notifs("freelancer")[-1]["title"]


def test_replayed_chain_events_do_not_duplicate_notifications(ctx):
    cid = ctx.make_contract("open")
    from app import indexer
    c = ctx.db.table("contracts").select("*").eq("id", cid).execute().data[0]
    for _ in range(3):
        indexer.apply("Accepted", {"id": bytes.fromhex(c["escrow_id"][2:])}, "0xsame")
    assert len(ctx.notifs("client", kind="contract")) == 1


def test_open_job_payment_notice_goes_to_client_only(ctx):
    cid = ctx.make_contract("open", worker=None)
    assert "locked in escrow" in ctx.notifs("client", kind="payment")[0]["title"]
    assert not ctx.notifs("freelancer") and not ctx.notifs("stranger")  # nobody is invited to an open job


def test_notify_never_raises(ctx, monkeypatch):
    monkeypatch.setattr(ctx.db, "table", lambda *_: (_ for _ in ()).throw(RuntimeError("db down")))
    notify.notify("some-user", "x", "t")  # must not raise


# ---------- reminders ----------

def test_deadline_reminders_sent_once(ctx):
    cid = ctx.make_contract("active")
    soon = datetime.now(timezone.utc) + timedelta(hours=3)
    ctx.db.table("milestones").update({"deadline": soon.isoformat()}).eq("contract_id", cid).eq("idx", 0).execute()
    assert keeper.reminders() == 1 and keeper.reminders() == 1  # re-evaluated, but deduped
    assert len(ctx.notifs("freelancer", kind="deadline")) == 1 and not ctx.notifs("client", kind="deadline")


def test_overdue_notifies_client_once_and_ignores_inactive(ctx):
    cid = ctx.make_contract("active")
    ctx.db.table("milestones").update({"deadline": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()}).eq("contract_id", cid).eq("idx", 0).execute()
    keeper.reminders(); keeper.reminders()
    assert len(ctx.notifs("client", kind="deadline")) == 1 and "passed" in ctx.notifs("client", kind="deadline")[0]["title"]
    ctx.db.table("contracts").update({"status": "cancelled"}).eq("id", cid).execute()
    ctx.db.table("notifications").delete().eq("kind", "deadline").execute()
    keeper.reminders()
    assert not ctx.notifs("client", kind="deadline")
