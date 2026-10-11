import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("SUPABASE_URL", "https://x.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "k")
sys.path.insert(0, str(Path(__file__).parent))

import pytest
from eth_account import Account
from fastapi import Header
from fastapi.testclient import TestClient

from app import db as app_db
from app.auth import current_user
from app.config import settings
from app.main import app
from fakedb import FakeDB

HANDLES = {"client": "buyer", "freelancer": "seller", "stranger": "stranger", "admin": "boss", "nowallet": "nowallet"}
PEOPLE = {  # name -> (id, email, wallet)
    "client": ("11111111-1111-1111-1111-111111111111", "client@example.com", "0x" + "c1" * 20),
    "freelancer": ("22222222-2222-2222-2222-222222222222", "free@example.com", "0x" + "f2" * 20),
    "stranger": ("33333333-3333-3333-3333-333333333333", "stranger@example.com", "0x" + "a3" * 20),
    "admin": ("44444444-4444-4444-4444-444444444444", "admin@example.com", "0x" + "ad" * 20),
    "nowallet": ("55555555-5555-5555-5555-555555555555", "nowallet@example.com", None),
}


def fake_user(x_test_user: str = Header()):
    pid, email, _ = PEOPLE[x_test_user]
    return {"id": pid, "email": email}


class Ctx:
    def __init__(self, db):
        self.db, self.http = db, TestClient(app)

    def h(self, who): return {"X-Test-User": who}
    def get(self, path, who): return self.http.get(path, headers=self.h(who))
    def post(self, path, who, json=None): return self.http.post(path, headers=self.h(who), json=json or {})
    def form(self, path, who, data=None, files=None): return self.http.post(path, headers=self.h(who), data=data or {}, files=files)
    def put(self, path, who, json=None): return self.http.put(path, headers=self.h(who), json=json or {})
    def delete(self, path, who): return self.http.delete(path, headers=self.h(who))

    def contract_body(self, **over):
        due = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        body = {
            "title": "Inventory API", "description": "Build an inventory REST API", "freelancer_username": "seller",
            "milestones": [
                {"title": "Core API", "amount": "1.5", "deadline": due, "requirements": [
                    {"title": "README exists", "kind": "file_exists", "spec": {"path": "README.md"}},
                    {"title": "Products route", "kind": "file_contains", "spec": {"path": "app.py", "pattern": "def list_products"}},
                    {"title": "Secret edge case", "kind": "file_contains", "spec": {"path": "app.py", "pattern": "def delete_product"}, "hidden": True}]},
                {"title": "Docs", "amount": "0.5", "deadline": due, "requirements": [
                    {"title": "License exists", "kind": "file_exists", "spec": {"path": "LICENSE"}}]},
            ],
        }
        body.update(over)
        return body

    def make_contract(self, status="active", worker="freelancer", **over):
        """status: draft | open (paid, waiting for a worker) | active (accepted). worker=None makes an open job."""
        if worker is None:
            over.setdefault("freelancer_username", None)
        r = self.post("/contracts", "client", self.contract_body(**over))
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        if status != "draft":
            self.chain_event("EscrowCreated", cid, client=PEOPLE["client"][2])
            if status == "active":
                self.chain_event("Accepted", cid, freelancer=PEOPLE[worker or "freelancer"][2])
        return cid

    def chain_event(self, name, cid, idx=None, **args):
        from app import indexer
        c = self.db.table("contracts").select("*").eq("id", cid).execute().data[0]
        self._n = getattr(self, "_n", 0) + 1
        a = {"id": bytes.fromhex(c["escrow_id"][2:]), **args}
        if idx is not None: a["idx"] = idx
        indexer.apply(name, a, f"0xtx{self._n}")

    def notifs(self, who, **eq):
        rows = [n for n in self.db.tables.get("notifications", []) if n["user_id"] == PEOPLE[who][0]]
        return [n for n in rows if all(n.get(k) == v for k, v in eq.items())]


@pytest.fixture
def ctx(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(app_db, "_client", db)
    monkeypatch.setattr(settings, "escrow_address", "")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "require_verified_email", False)
    monkeypatch.setattr(settings, "resend_api_key", "")
    from app import util
    util.reset()
    for name, (pid, email, wallet) in PEOPLE.items():
        db.table("profiles").insert({"id": pid, "email": email, "name": name.title(), "wallet": wallet.lower() if wallet else None,
                                     "handle": HANDLES[name], "is_admin": name == "admin"}).execute()
    app.dependency_overrides[current_user] = fake_user
    yield Ctx(db)
    app.dependency_overrides.clear()
