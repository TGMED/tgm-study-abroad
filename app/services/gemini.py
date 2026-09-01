"""Server-side client for the same Cloudflare Worker (Gemini proxy) the
Counselor app's askGemini() calls from the browser (Desktop/Counselor/app.js).

Verified directly: a plain server-to-server POST with this exact body shape
returns HTTP 200 with real streamed Gemini output -- the Worker has no
CORS/Origin gating, so calling it from Python `requests` instead of a browser
`fetch` is safe.
"""
import json
import os

import requests

WORKER_URL = os.environ.get("GEMINI_WORKER_URL", "https://tgm-gemini-proxy.lagosoffice3.workers.dev").strip()


class GeminiError(Exception):
    pass


def call_gemini(system_prompt, history, timeout=45):
    """history: list of {"role": "user"|"model", "content": str}, oldest first.

    Returns the assistant's full reply text as a single string. v1 is
    non-streaming: the Worker's response is SSE (`data: {...}` lines) even for
    a server call, so we read the whole body and concatenate every chunk's
    text rather than rendering progressively to the browser (see PLAN.md for
    the streaming upgrade path).
    """
    recent = history[-10:]
    body = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [
            {"role": m["role"], "parts": [{"text": m["content"]}]}
            for m in recent
        ],
        # The Worker retrieves matching knowledge-base chunks from Supabase
        # automatically based on `contents` above; this just lets it fall
        # back to a live web search (Gemini's google_search tool) when the
        # knowledge base doesn't cover the question, instead of Amara
        # refusing or guessing. Explicit rather than relying on the Worker's
        # own default for this.
        "web_search_enabled": True,
    }

    try:
        resp = requests.post(WORKER_URL, json=body, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise GeminiError(f"Could not reach the AI service: {exc}") from exc

    text_parts = []
    saw_sse_line = False
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
        # Fallback: maybe the Worker returned one plain (non-streamed) JSON body.
        try:
            chunk = json.loads(resp.text)
            _collect_text(chunk, text_parts)
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
    parts = (candidates[0].get("content") or {}).get("parts") or []
    for part in parts:
        if "text" in part:
            text_parts.append(part["text"])
