"""Weekly community-activity digest: summarizes the last 7 days of posts per
room and emails every onboarded member. Sent to everyone, unconditionally --
no per-member pause/opt-out. Falls back to console logging per recipient if
EmailJS isn't configured (see services/emailer.py). Run via
scripts/send_weekly_digest.py on a schedule (cron / Windows Task Scheduler --
this app has no built-in job scheduler), or trigger on demand from /admin.
"""
import datetime

from services.emailer import EmailSendError, send_digest_email
from services.prompts import COMMUNITY_ROOMS, COMMUNITY_ROOM_META


def _room_highlights(db, since_iso):
    """One entry per room that had top-level activity in the window, each
    naming that room's highest-scoring post as the highlight."""
    highlights = []
    for room in COMMUNITY_ROOMS:
        posts = db.execute(
            """
            SELECT p.id, p.content, p.author_label,
                COALESCE((SELECT SUM(value) FROM community_votes v WHERE v.post_id = p.id), 0) AS score,
                (SELECT COUNT(*) FROM community_posts c WHERE c.parent_id = p.id AND c.is_hidden = 0) AS replies
            FROM community_posts p
            WHERE p.room = ? AND p.parent_id IS NULL AND p.is_hidden = 0 AND p.is_ai = 0
                  AND p.created_at >= ?
            ORDER BY score DESC, p.id DESC
            """,
            (room, since_iso),
        ).fetchall()
        if not posts:
            continue
        top = posts[0]
        highlights.append({
            "room": room,
            "room_label": COMMUNITY_ROOM_META.get(room, {}).get("label", room.title()),
            "post_count": len(posts),
            "top_author": top["author_label"],
            "top_excerpt": (top["content"] or "")[:180],
            "top_replies": top["replies"],
        })
    return highlights


def _format_highlights_text(highlights):
    lines = []
    for h in highlights:
        lines.append(
            f"#{h['room_label']} — {h['post_count']} new post{'s' if h['post_count'] != 1 else ''} this week. "
            f"Top: \"{h['top_excerpt']}\" — {h['top_author']} "
            f"({h['top_replies']} repl{'y' if h['top_replies'] == 1 else 'ies'})"
        )
    return "\n".join(lines)


def send_weekly_digest(db, community_url):
    """Returns (sent_count, skipped_count, highlights). Best-effort per
    recipient -- one failed/unconfigured send never blocks the rest of the
    batch. highlights is empty (and nothing is sent) if there was no
    community activity in the last 7 days."""
    since = (datetime.datetime.utcnow() - datetime.timedelta(days=7)).isoformat()
    highlights = _room_highlights(db, since)
    if not highlights:
        return 0, 0, highlights

    highlights_text = _format_highlights_text(highlights)
    today = datetime.datetime.utcnow()
    week_range = f"{(today - datetime.timedelta(days=7)).strftime('%d %b')} – {today.strftime('%d %b')}"

    recipients = db.execute("SELECT email, display_name FROM students WHERE onboarded = 1").fetchall()

    sent, skipped = 0, 0
    for r in recipients:
        if not r["email"]:
            skipped += 1
            continue
        try:
            send_digest_email(r["email"], {
                "to_name": r["display_name"] or r["email"].split("@")[0],
                "week_range": week_range,
                "highlights_text": highlights_text,
                "community_url": community_url,
            })
            sent += 1
        except EmailSendError as exc:
            print(f"Weekly digest email failed for {r['email']}: {exc}")
            skipped += 1
    return sent, skipped, highlights
