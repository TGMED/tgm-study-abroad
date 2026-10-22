"""Generates a study-abroad/scholarship update post and queues it for admin
approval (see /admin/updates) rather than posting straight to the room --
scholarship and visa details are exactly the kind of content where a
confidently wrong AI claim actively harms a student, so nothing from here
reaches #general without a human clicking Approve.
"""
import datetime

from services.gemini import call_gemini
from services.prompts import build_study_update_prompt

RECENT_LOOKBACK = 10


def generate_and_queue_update(db, room="general"):
    """Returns (queue_id, content). Raises GeminiError on failure -- the
    caller decides whether that's worth alerting on."""
    recent = db.execute(
        "SELECT content FROM ai_post_queue ORDER BY id DESC LIMIT ?", (RECENT_LOOKBACK,)
    ).fetchall()
    recent_posts = [r["content"] for r in recent]

    system_prompt = build_study_update_prompt(recent_posts)
    trigger_history = [{"role": "user", "content": "(Write today's update now.)"}]
    content = call_gemini(system_prompt, trigger_history, timeout=90)

    now = datetime.datetime.utcnow().isoformat()
    cur = db.execute(
        "INSERT INTO ai_post_queue (room, content, status, created_at) VALUES (?, ?, 'pending', ?)",
        (room, content, now),
    )
    db.commit()
    return cur.lastrowid, content
