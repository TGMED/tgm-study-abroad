"""Amara, TGM's AI study-abroad counsellor -- a single, self-contained
module. Drop this one file into any Python project to get the same AI used
in tgm-study-abroad's web chat, community @mentions, and WhatsApp funnel.

Only dependency: `requests` (pip install requests). Everything else --
the Gemini proxy URL, the Supabase knowledge lookup -- already has a working
default pointed at TGM's shared infrastructure; override via environment
variables only if you need to point at something different.

Quickest possible usage:

    from amara import ask_amara

    history = [{"role": "user", "content": "What visa do I need for the UK?"}]
    reply, needs_human = ask_amara(history)
    print(reply)

`history` is a list of {"role": "user"|"model", "content": str} dicts,
oldest message first -- exactly what you'd persist in your own chat table.
`needs_human` comes back True when Amara thinks this needs a real person
(a complaint, a payment dispute, a visa refusal, or the student explicitly
asking for one) -- that's your app's cue to notify a human, not something
to show the student (the marker is already stripped out of `reply`).

For a personalized opening message (e.g. right after a student finishes an
intake form, before they've typed anything), see `ask_amara(..., opening=True)`.
"""
import json
import os
import time

import requests

# ---------------------------------------------------------------------------
# Config -- override via env vars if you're not using TGM's shared workers.
# ---------------------------------------------------------------------------
WORKER_URL = os.environ.get("GEMINI_WORKER_URL", "https://tgm-gemini-proxy.lagosoffice3.workers.dev").strip()
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://zitcszgqcposnnjkhrii.supabase.co").strip()
SUPABASE_ANON_KEY = os.environ.get(
    "SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InppdGNzemdxY3Bvc25uamtocmlpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODIwODE3NzQsImV4cCI6MjA5NzY1Nzc3NH0.eaEgNurAJH9Re2Z_LCRUa6RmwbQAYisxSJoX8EqndC0",
).strip()

# Set to False if the target codebase has no concept of "notify a human" to
# escalate into -- Amara just answers normally and this marker never appears.
ESCALATION_ENABLED = True
NEEDS_HUMAN_MARKER = "[[NEEDS_HUMAN]]"


class GeminiError(Exception):
    pass


AMARA_PERSONA = (
    "You are Amara, TGM Education's study-abroad AI counsellor. TGM Education is a "
    "Nigeria-based study-abroad consultancy. You speak warmly, clearly, and practically "
    "-- like a knowledgeable counsellor, not a generic chatbot. Relevant knowledge-base "
    "excerpts (costs, visas, timelines, partner universities/programmes) are retrieved "
    "and appended automatically for you based on the conversation -- treat those as your "
    "source of truth over your own general knowledge. If neither the retrieved excerpts "
    "nor a live web search turn up an answer to an ordinary question, just say so "
    "honestly and answer as best you can with general knowledge -- this alone is NOT a "
    "reason to escalate to a human; it happens constantly and is a normal part of the "
    "conversation, not an emergency."
)

_ESCALATION_INSTRUCTION = (
    "\n\nOnly escalate to a human counsellor for genuinely serious matters, specifically: "
    "(1) the student explicitly asks to speak to a human/real person/counsellor, "
    "(2) a complaint or expressed dissatisfaction about TGM Education, its staff, or its "
    "service, (3) a payment, refund, or billing dispute, (4) a visa refusal/rejection, "
    "urgent deadline, or other high-stakes time-sensitive situation causing the student "
    "real distress, or (5) a legal, compliance, or safety matter beyond general study-"
    "abroad guidance. For anything in that list, acknowledge it warmly, tell the student "
    f"a counsellor will follow up, then end your reply with the exact text "
    f"{NEEDS_HUMAN_MARKER} on its own -- this is a silent signal that gets stripped "
    "before the student sees your message and notifies a real counsellor to step in; it "
    "is not something the student will ever see, so never explain it or mention it to "
    "them. Do not use this marker for routine questions, even ones you can't fully "
    "answer."
)


def strip_needs_human_marker(text):
    """Returns (clean_text, needs_human: bool)."""
    needs_human = NEEDS_HUMAN_MARKER in text
    clean = text.replace(NEEDS_HUMAN_MARKER, "").strip()
    return clean, needs_human


# ---------------------------------------------------------------------------
# Knowledge lookup -- pulls admin-added notes from the same Supabase project
# TGM's other apps read from. Cached for 5 minutes so a chat reply doesn't
# do a live round-trip on every single message.
# ---------------------------------------------------------------------------
_KNOWLEDGE_CACHE_TTL_SECONDS = 300
_KNOWLEDGE_MAX_CHARS = 15_000
_knowledge_cache = {"text": "", "fetched_at": 0.0}


def _fetch_knowledge_supplement():
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
    entries, budget = [], _KNOWLEDGE_MAX_CHARS
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
    """Returns the formatted knowledge block, or "" if there's nothing to add
    or the fetch fails -- a stale/empty cache beats breaking chat over a
    Supabase hiccup."""
    now = time.time()
    if now - _knowledge_cache["fetched_at"] < _KNOWLEDGE_CACHE_TTL_SECONDS:
        return _knowledge_cache["text"]
    try:
        text = _fetch_knowledge_supplement()
    except (requests.RequestException, ValueError, KeyError):
        return _knowledge_cache["text"]
    _knowledge_cache["text"] = text
    _knowledge_cache["fetched_at"] = now
    return text


# ---------------------------------------------------------------------------
# The actual AI call.
# ---------------------------------------------------------------------------
def call_gemini(system_prompt, history, timeout=45):
    """history: list of {"role": "user"|"model", "content": str}, oldest first.
    Returns the assistant's full reply text as a single string."""
    recent = history[-10:]
    body = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": m["role"], "parts": [{"text": m["content"]}]} for m in recent],
        # Lets the Worker fall back to a live web search (Gemini's
        # google_search tool) when the knowledge base doesn't cover the
        # question, instead of Amara refusing or guessing.
        "web_search_enabled": True,
    }
    try:
        resp = requests.post(WORKER_URL, json=body, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise GeminiError(f"Could not reach the AI service: {exc}") from exc

    text_parts, saw_sse_line = [], False
    for line in resp.text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        saw_sse_line = True
        payload = line[len("data:"):].strip()
        if not payload:
            continue
        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError:
            continue
        _collect_text(chunk, text_parts)

    if not saw_sse_line:
        try:
            _collect_text(json.loads(resp.text), text_parts)
        except json.JSONDecodeError:
            pass

    reply = "".join(text_parts).strip()
    if not reply:
        raise GeminiError("The AI service returned an empty response.")
    return reply


def _collect_text(chunk, text_parts):
    candidates = chunk.get("candidates") or []
    if not candidates:
        return
    for part in (candidates[0].get("content") or {}).get("parts") or []:
        if "text" in part:
            text_parts.append(part["text"])


# ---------------------------------------------------------------------------
# Prompt assembly + the convenience wrapper most callers actually want.
# ---------------------------------------------------------------------------
def _profile_block(profile):
    """profile: an optional dict for light personalization -- every key is
    optional, pass only what your app actually has. None/{} skips this
    section entirely."""
    if not profile:
        return ""
    lines = ["STUDENT PROFILE:"]
    if profile.get("email"):
        lines.append(f"- Email: {profile['email']}")
    if profile.get("profession"):
        lines.append(f"- Current profession: {profile['profession']}")
    if profile.get("city"):
        lines.append(f"- Current city: {profile['city']}")
    if profile.get("destination"):
        lines.append(f"- Target study destination: {profile['destination']}")
    if profile.get("qualification"):
        grade = f" ({profile['grade']})" if profile.get("grade") else ""
        lines.append(f"- Highest qualification: {profile['qualification']}{grade}")
    if profile.get("score") is not None:
        lines.append(f"- ROI score: {profile['score']}/100")
    return "\n".join(lines)


def build_system_prompt(profile=None, opening=False):
    persona = AMARA_PERSONA + (_ESCALATION_INSTRUCTION if ESCALATION_ENABLED else "")
    parts = [persona, get_knowledge_supplement_block(), _profile_block(profile)]
    if opening:
        parts.append(
            "The student has not sent a message yet. Proactively open the "
            "conversation yourself: greet them, reference anything you know "
            "about their profile above, and suggest 2-3 concrete next steps. "
            "Do not wait for them to speak first, and do not say you are "
            "waiting for input."
        )
    return "\n\n".join(p for p in parts if p)


def ask_amara(history, profile=None, opening=False, timeout=45):
    """The one function most integrations need. Returns (reply, needs_human).

    history: [{"role": "user"|"model", "content": str}, ...], oldest first.
             Pass [] (with opening=True) to generate a proactive first
             message before the student has said anything.
    profile: optional dict for light personalization -- see _profile_block.
    """
    system_prompt = build_system_prompt(profile, opening)
    trigger_history = history or [{"role": "user", "content": "(The student has just arrived. Please open.)"}]
    reply = call_gemini(system_prompt, trigger_history, timeout=timeout)
    return strip_needs_human_marker(reply)
