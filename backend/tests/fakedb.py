"""Minimal in-memory stand-in for the supabase-py query builder (only what the app uses)."""
import copy
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

DEFAULTS = {
    "profiles": {"is_admin": False, "name": None, "handle": None, "wallet": None, "first_name": None, "last_name": None, "phone": None, "heard_from": None, "heard_other": None},
    "contracts": {"status": "draft", "freelancer_id": None, "freelancer_wallet": None, "freelancer_handle": None, "freelancer_email": None, "description": "", "created_tx": None,
                  "is_open": False, "cancel_requested": False, "idea": "", "ai_notes": None},
    "milestones": {"status": "pending", "evidence_hash": None, "delivery_type": "software", "window_secs": 172800, "review_ends_at": None, "shipment": None},
    "requirements": {"position": 0, "criteria": "", "hidden": False},
    "messages": {"thread_user": None},
    "verification_runs": {"status": "running", "passed": 0, "total": 0, "dry_run": False, "evidence_hash": None, "report": None,
                          "attest_tx": None, "error": None, "finished_at": None, "deploy_url": None, "commit_sha": None, "repo_url": None,
                          "source": "github", "file_name": None, "file_path": None, "ai_summary": None},
    "disputes": {"status": "pending", "freelancer_bps": None, "resolved_at": None, "requirement_id": None},
    "notifications": {"read_at": None, "body": "", "link": None, "dedupe_key": None},
    "audit_logs": {"meta": {}},
}
NO_ID = {"indexer_state", "contract_reads"}
UNIQUE = {"notifications": [("user_id", "dedupe_key")], "milestones": [("contract_id", "idx")], "profiles": [("wallet",), ("handle",)],
          "contracts": [("escrow_id",)], "chain_events": [("tx_hash", "log_index")]}
_BASE = datetime.now(timezone.utc)


def _get(row, key):
    if "->>" in key:
        k, sub = key.split("->>")
        v = (row.get(k) or {}).get(sub)
        return None if v is None else str(v)
    return row.get(key)


def _split_or(expr):
    parts, cur, q = [], "", False
    for ch in expr:
        if ch == '"':
            q = not q
        if ch == "," and not q:
            parts.append(cur); cur = ""
        else:
            cur += ch
    return parts + [cur]


class Query:
    def __init__(self, db, table):
        self.db, self.t, self.mode = db, table, "select"
        self.filters, self.cols, self.want_count, self._order, self._limit, self.payload, self.conflict = [], "*", False, None, None, None, None

    # builders
    def select(self, cols="*", count=None):
        self.cols, self.want_count = cols, count == "exact"; return self
    def insert(self, rows): self.mode, self.payload = "insert", rows; return self
    def update(self, vals): self.mode, self.payload = "update", vals; return self
    def delete(self): self.mode = "delete"; return self
    def upsert(self, rows, on_conflict=None): self.mode, self.payload, self.conflict = "upsert", rows, on_conflict; return self
    def eq(self, k, v): self.filters.append(lambda r: _get(r, k) == v); return self
    def neq(self, k, v): self.filters.append(lambda r: _get(r, k) != v); return self
    def in_(self, k, vals): vals = list(vals); self.filters.append(lambda r: _get(r, k) in vals); return self
    def is_(self, k, v): self.filters.append(lambda r: (_get(r, k) is None) == (v == "null")); return self
    def order(self, col, desc=False): self._order = (col, desc); return self
    def limit(self, n): self._limit = n; return self
    def or_(self, expr):
        conds = []
        for part in _split_or(expr):
            col, op, val = part.split(".", 2)
            assert op == "eq", op
            conds.append((col, val.strip('"')))
        self.filters.append(lambda r: any(str(_get(r, c)) == v for c, v in conds)); return self

    # execution
    def _rows(self): return self.db.tables.setdefault(self.t, [])
    def _match(self): return [r for r in self._rows() if all(f(r) for f in self.filters)]

    def _new(self, row):
        row = {**DEFAULTS.get(self.t, {}), **copy.deepcopy(row)}
        if self.t not in NO_ID:
            row.setdefault("id", str(uuid.uuid4()) if self.t not in ("chain_events", "audit_logs") else self.db.next_id())
        self.db.tick += 1
        row.setdefault("created_at", (_BASE + timedelta(microseconds=self.db.tick)).isoformat())
        for cols in UNIQUE.get(self.t, []):
            vals = [row.get(c) for c in cols]
            if None in vals:
                continue
            if any([r.get(c) for c in cols] == vals for r in self._rows()):
                raise Exception(f"duplicate key value violates unique constraint on {self.t}{cols}")
        return row

    def execute(self):
        rows = self._rows()
        if self.mode == "insert":
            new = [self._new(r) for r in (self.payload if isinstance(self.payload, list) else [self.payload])]
            rows.extend(new); return SimpleNamespace(data=copy.deepcopy(new), count=len(new))
        if self.mode == "update":
            hit = self._match()
            for r in hit: r.update(copy.deepcopy(self.payload))
            return SimpleNamespace(data=copy.deepcopy(hit), count=len(hit))
        if self.mode == "delete":
            hit = self._match(); ids = {id(r) for r in hit}
            self.db.tables[self.t] = [r for r in rows if id(r) not in ids]
            return SimpleNamespace(data=copy.deepcopy(hit), count=len(hit))
        if self.mode == "upsert":
            keys = (self.conflict or "id").split(",")
            out = []
            for p in (self.payload if isinstance(self.payload, list) else [self.payload]):
                ex = next((r for r in rows if all(r.get(k) == p.get(k) for k in keys)), None)
                if ex: ex.update(copy.deepcopy(p)); out.append(ex)
                else: n = self._new(p); rows.append(n); out.append(n)
            return SimpleNamespace(data=copy.deepcopy(out), count=len(out))
        hit = self._match()
        if self._order:
            col, desc = self._order
            hit = sorted(hit, key=lambda r: (r.get(col) is None, r.get(col)), reverse=desc)
        total = len(hit)
        if self._limit is not None: hit = hit[: self._limit]
        if self.cols != "*":
            keep = [c.strip() for c in self.cols.split(",")]
            hit = [{k: r.get(k) for k in keep} for r in hit]
        return SimpleNamespace(data=copy.deepcopy(hit), count=total if self.want_count else None)


class _Storage:
    def __init__(self): self.uploads = []
    def from_(self, _): return self
    def upload(self, path, data, opts=None): self.uploads.append(path); return {}
    def create_signed_url(self, path, secs): return {"signedURL": f"https://files.example/{path}?t=1"}


class FakeDB:
    def __init__(self):
        self.tables, self.tick, self._id, self.storage = {"indexer_state": [{"id": 1, "last_block": 0}]}, 0, 0, _Storage()
    def next_id(self): self._id += 1; return self._id
    def table(self, name): return Query(self, name)
