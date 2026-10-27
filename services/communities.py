"""Community rooms are admin-managed data, not a hardcoded list -- every
room lives in the `communities` table (seeded once with the original 8 on
first run, see extensions.py's _DEFAULT_COMMUNITIES) and admins create or
delete rooms from /admin/communities. This module is the one place that
reads the table, so every caller (sidebar nav, the room switcher, the
digest, Amara's community prompt, post validation) sees the same list.
"""


def list_communities(db):
    """Ordered list of {key, label, code, blurb} dicts."""
    # `key` is backtick-quoted because it's a reserved word in MySQL --
    # SQLite accepts backticks too (a deliberate compatibility shim), so
    # this works unchanged on either backend.
    rows = db.execute("SELECT `key`, label, code, blurb FROM communities ORDER BY created_at, `key`").fetchall()
    return [{"key": r["key"], "label": r["label"], "code": r["code"], "blurb": r["blurb"] or ""} for r in rows]


def community_keys(db):
    return [c["key"] for c in list_communities(db)]


def community_meta(db):
    """key -> {label, code, blurb} -- the same shape the old hardcoded
    COMMUNITY_ROOM_META dict had, for any caller built against that shape."""
    return {c["key"]: {"label": c["label"], "code": c["code"], "blurb": c["blurb"]} for c in list_communities(db)}


def room_exists(db, key):
    return db.execute("SELECT 1 FROM communities WHERE `key` = ?", (key,)).fetchone() is not None


def room_label(db, key):
    row = db.execute("SELECT label FROM communities WHERE `key` = ?", (key,)).fetchone()
    return row["label"] if row else (key or "").title()
