"""Fetches admin-added knowledge updates from the same Supabase project the
Counselor app reads client-side (see Counselor/app.js loadKnowledgeSupplement)
so anything added through Counselor's admin panel also reaches Amara here,
not just TGM Assist.

Read with the anon key against the `knowledge_supplement` table -- same
access Counselor's browser client uses, so this relies on that table's
existing RLS policy allowing public reads.
"""
import os
import time

import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://zitcszgqcposnnjkhrii.supabase.co").strip()
SUPABASE_ANON_KEY = os.environ.get(
    "SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InppdGNzemdxY3Bvc25uamtocmlpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODIwODE3NzQsImV4cCI6MjA5NzY1Nzc3NH0.eaEgNurAJH9Re2Z_LCRUa6RmwbQAYisxSJoX8EqndC0",
).strip()

_CACHE_TTL_SECONDS = 300
_cache = {"text": "", "fetched_at": 0.0}

# `knowledge_supplement` was designed for small admin-added notes, but in
# practice has ended up holding full legacy country/university knowledge-base
# dumps (one entry alone is 600K+ characters). Sending all of that on every
# single chat turn would balloon latency/cost and defeat the point of RAG, so
# entries are included newest-first only up to this budget -- anything past
# it is silently skipped rather than truncated mid-entry.
_MAX_CHARS = 15_000


def _fetch():
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/knowledge_supplement",
        params={"select": "title,content", "order": "created_at.desc"},
        headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {SUPABASE_ANON_KEY}"},
        timeout=5,
    )
    resp.raise_for_status()
    rows = resp.json()
    if not rows:
        return ""
    entries = []
    budget = _MAX_CHARS
    for r in rows:
        entry = f"--- {r['title']} ---\n{r['content']}"
        if len(entry) > budget:
            continue
        entries.append(entry)
        budget -= len(entry)
    if not entries:
        return ""
    return "\n\n=== KNOWLEDGE BASE UPDATES (ADDED BY ADMIN) ===\n" + "\n\n".join(entries)


def get_knowledge_supplement_block():
    """Returns the formatted supplement block, or "" if there's nothing to
    add or the fetch fails. Cached for _CACHE_TTL_SECONDS so a chat reply
    doesn't do a live Supabase round-trip on every single message -- admin
    updates are infrequent enough that a few minutes' staleness is fine."""
    now = time.time()
    if now - _cache["fetched_at"] < _CACHE_TTL_SECONDS:
        return _cache["text"]
    try:
        text = _fetch()
    except (requests.RequestException, ValueError, KeyError):
        # Stale cache (even if empty) beats breaking chat over a Supabase hiccup.
        return _cache["text"]
    _cache["text"] = text
    _cache["fetched_at"] = now
    return text
