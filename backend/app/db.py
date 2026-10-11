from supabase import create_client

from .config import settings

_client = None  # tests replace this with an in-memory fake


def db():
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _client


def one(table: str, **eq):
    q = db().table(table).select("*")
    for k, v in eq.items():
        q = q.eq(k, v)
    rows = q.limit(1).execute().data
    return rows[0] if rows else None


def many(table: str, order: str | None = None, desc: bool = False, limit: int | None = None, **eq):
    q = db().table(table).select("*")
    for k, v in eq.items():
        q = q.eq(k, v)
    if order:
        q = q.order(order, desc=desc)
    if limit:
        q = q.limit(limit)
    return q.execute().data


def audit(actor, action, entity=None, entity_id=None, **meta):
    db().table("audit_logs").insert(
        {"actor": actor, "action": action, "entity": entity, "entity_id": str(entity_id) if entity_id else None, "meta": meta}
    ).execute()
