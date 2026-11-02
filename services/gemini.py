"""Direct Gemini API client -- replaces the Cloudflare Worker proxy this app
used to go through. Reimplements, in Python, exactly what that Worker did
for retrieval (ported from TGM-VAIP's worker/tgm-gemini-proxy.js, the actual
deployed source): embeds the recent conversation, retrieves the closest
knowledge-base chunks from Supabase (kb_chunks via the match_kb_chunks RPC),
and appends them to the system instruction -- instead of stuffing the whole
knowledge base into every request. The Worker's live web-search tool
(Gemini's google_search) is intentionally NOT reimplemented here yet.

Requires in .env:
  GEMINI_API_KEY         https://aistudio.google.com/app/apikey
  SUPABASE_SERVICE_KEY   the service_role key (Project Settings -> API) --
                         NOT the anon key. kb_chunks has RLS enabled with no
                         public policies (see TGM-VAIP's
                         supabase/kb_rag_setup.sql), so only service_role
                         can read it; match_kb_chunks has no SECURITY DEFINER
                         so it runs as whichever role calls it.
  SUPABASE_URL           same project services/knowledge_supplement.py reads
                         from -- shares its default here for the same reason.

Without GEMINI_API_KEY, every call fails fast with GeminiError. Without
SUPABASE_SERVICE_KEY, retrieval just degrades to no extra context -- it
never blocks the chat itself.
"""
import os

import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://zitcszgqcposnnjkhrii.supabase.co").strip()
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
# Truncated to 768 dims via outputDimensionality -- must match kb_chunks'
# embedding vector(768) column, same model/dimension the Worker used.
EMBED_MODEL = "gemini-embedding-001"
CHAT_MODEL = "gemini-2.5-flash"
MATCH_COUNT = 8
EMBED_DIMENSIONS = 768


class GeminiError(Exception):
    pass


def _embed_query(text):
    """Returns the embedding for a retrieval query, or None on any failure
    (missing key, network error, unexpected response shape)."""
    if not GEMINI_API_KEY:
        return None
    try:
        resp = requests.post(
            f"{GEMINI_API_BASE}/{EMBED_MODEL}:embedContent",
            params={"key": GEMINI_API_KEY},
            json={
                "content": {"parts": [{"text": text}]},
                "taskType": "RETRIEVAL_QUERY",
                "outputDimensionality": EMBED_DIMENSIONS,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("embedding", {}).get("values") or None
    except (requests.RequestException, ValueError):
        return None


def _match_kb_chunks(query_embedding):
    """Returns the matching kb_chunks rows (id, country, school, source_file,
    content, similarity), or [] on any failure -- including simply not
    having SUPABASE_SERVICE_KEY configured."""
    if not (SUPABASE_URL and SUPABASE_SERVICE_KEY):
        return []
    try:
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/rpc/match_kb_chunks",
            headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},
            json={"query_embedding": query_embedding, "match_count": MATCH_COUNT},
            timeout=10,
        )
        resp.raise_for_status()
        matches = resp.json()
        return matches if isinstance(matches, list) else []
    except (requests.RequestException, ValueError):
        return []


def _retrieve_kb_context(recent_history):
    """Mirrors the Worker's retrieveContext(): builds the retrieval query
    from the last 4 turns actually sent to Gemini (not just the latest
    message, so a bare follow-up like "which of our partner schools have
    the courses?" keeps its topic), embeds it, and retrieves + formats the
    closest chunks. Returns "" on any failure or empty result -- retrieval
    degrading to "no extra context" must never break the chat itself."""
    query_text = "\n".join(
        m["content"].strip() for m in recent_history[-4:] if (m.get("content") or "").strip()
    )
    if not query_text:
        return ""

    query_embedding = _embed_query(query_text)
    if not query_embedding:
        return ""

    matches = _match_kb_chunks(query_embedding)
    if not matches:
        return ""

    excerpts = "\n\n---\n\n".join(
        f"[{m.get('school') or m.get('country') or m.get('source_file')}]\n{m.get('content', '')}"
        for m in matches
    )
    return "\n\n=== RETRIEVED KNOWLEDGE BASE EXCERPTS (most relevant to the latest question) ===\n" + excerpts


def call_gemini(system_prompt, history, timeout=45):
    """history: list of {"role": "user"|"model", "content": str}, oldest first.
    Returns the assistant's full reply text as a single string."""
    if not GEMINI_API_KEY:
        raise GeminiError("GEMINI_API_KEY is not set.")

    recent = history[-10:]

    try:
        retrieved_context = _retrieve_kb_context(recent)
    except Exception:  # noqa: BLE001 -- retrieval failing must degrade, never break the chat
        retrieved_context = ""

    body = {
        "system_instruction": {"parts": [{"text": system_prompt + retrieved_context}]},
        "contents": [
            {"role": m["role"], "parts": [{"text": m["content"]}]}
            for m in recent
        ],
    }

    try:
        resp = requests.post(
            f"{GEMINI_API_BASE}/{CHAT_MODEL}:generateContent",
            params={"key": GEMINI_API_KEY},
            json=body,
            timeout=timeout,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise GeminiError(f"Could not reach the AI service: {exc}") from exc

    text_parts = []
    try:
        _collect_text(resp.json(), text_parts)
    except ValueError:
        pass

    reply = "".join(text_parts).strip()
    if not reply:
        raise GeminiError("The AI service returned an empty response.")
    return reply


def _collect_text(chunk, text_parts):
    candidates = chunk.get("candidates") or []
    if not candidates:
        return
    parts = (candidates[0].get("content") or {}).get("parts") or []
    for part in parts:
        if "text" in part:
            text_parts.append(part["text"])
