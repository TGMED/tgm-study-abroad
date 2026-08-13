import datetime
import re

from flask import Blueprint, abort, jsonify, render_template, request, session

from extensions import get_db, login_required
from services.gemini import GeminiError, call_gemini
from services.prompts import COMMUNITY_ROOMS, build_community_system_prompt

community_bp = Blueprint("community", __name__)

MENTION_RE = re.compile(r"(?<!\w)@(amara|ai)\b", re.IGNORECASE)


def _room_or_404(room):
    if room not in COMMUNITY_ROOMS:
        abort(404)


def _display_name(db, student_id):
    row = db.execute("SELECT email, display_name FROM students WHERE id = ?", (student_id,)).fetchone()
    if not row:
        return "Student"
    return row["display_name"] or row["email"].split("@")[0]


def _col(row, key, default=0):
    return row[key] if key in row.keys() else default


def _post_dict(row):
    return {
        "id": row["id"],
        "room": row["room"],
        "author_label": row["author_label"],
        "is_ai": bool(row["is_ai"]),
        "parent_id": row["parent_id"],
        "content": row["content"],
        "created_at": row["created_at"],
        "score": _col(row, "score", 0),
        "my_vote": _col(row, "my_vote", 0),
        "reply_count": _col(row, "reply_count", 0),
        "mine": row["student_id"] is not None and row["student_id"] == session.get("student_id"),
    }


# Every post row is fetched with its vote tally, the current student's own
# vote, and (for top-level posts) a reply count -- so the UI can render the
# vote rail and comment count without extra round-trips.
_POST_SELECT = """
    SELECT p.*,
        COALESCE((SELECT SUM(value) FROM community_votes v WHERE v.post_id = p.id), 0) AS score,
        COALESCE((SELECT value FROM community_votes v WHERE v.post_id = p.id AND v.student_id = ?), 0) AS my_vote,
        (SELECT COUNT(*) FROM community_posts c WHERE c.parent_id = p.id AND c.is_hidden = 0) AS reply_count
    FROM community_posts p
"""

SORTS = ("hot", "new", "top")


def _sort_key(sort):
    if sort == "new":
        return lambda p: -p["id"]
    if sort == "top":
        return lambda p: (-p["score"], -p["id"])
    # "hot": recency-weighted score (Hacker-News-style gravity).
    def hot(p):
        try:
            created = datetime.datetime.fromisoformat(p["created_at"])
        except (ValueError, TypeError):
            created = datetime.datetime.utcnow()
        age_h = max(0.0, (datetime.datetime.utcnow() - created).total_seconds() / 3600.0)
        return -((p["score"] + 1.0) / ((age_h + 2.0) ** 1.5))
    return hot


@community_bp.route("/community/<room>")
@login_required
def community_room(room):
    _room_or_404(room)
    db = get_db()
    top_posts = db.execute(
        """
        SELECT * FROM community_posts
        WHERE room = ? AND parent_id IS NULL AND is_hidden = 0
        ORDER BY id DESC LIMIT 50
        """,
        (room,),
    ).fetchall()

    thread = []
    for post in reversed(top_posts):
        replies = db.execute(
            "SELECT * FROM community_posts WHERE parent_id = ? AND is_hidden = 0 ORDER BY id ASC",
            (post["id"],),
        ).fetchall()
        thread.append({"post": _post_dict(post), "replies": [_post_dict(r) for r in replies]})

    last_id = db.execute(
        "SELECT COALESCE(MAX(id), 0) AS m FROM community_posts WHERE room = ?", (room,)
    ).fetchone()["m"]

    return render_template("community_room.html", room=room, thread=thread, last_id=last_id, rooms=COMMUNITY_ROOMS)


@community_bp.route("/api/community/<room>/posts")
@login_required
def api_list_posts(room):
    _room_or_404(room)
    since = request.args.get("since", type=int, default=0)
    db = get_db()
    rows = db.execute(
        "SELECT * FROM community_posts WHERE room = ? AND id > ? AND is_hidden = 0 ORDER BY id ASC",
        (room, since),
    ).fetchall()
    return jsonify({"ok": True, "posts": [_post_dict(r) for r in rows]})


@community_bp.route("/api/community/<room>/posts", methods=["POST"])
@login_required
def api_create_post(room):
    _room_or_404(room)
    student_id = session["student_id"]
    db = get_db()

    student = db.execute("SELECT is_banned FROM students WHERE id = ?", (student_id,)).fetchone()
    if student and student["is_banned"]:
        return jsonify({"ok": False, "error": "Your account is restricted from posting."}), 403

    payload = request.get_json(silent=True) or {}
    content = (payload.get("content") or "").strip()
    raw_parent_id = payload.get("parent_id")
    parent_id = int(raw_parent_id) if raw_parent_id not in (None, "") else None

    if not content:
        return jsonify({"ok": False, "error": "Message cannot be empty."}), 400
    if len(content) > 2000:
        return jsonify({"ok": False, "error": "Message is too long (max 2000 characters)."}), 400

    author_label = _display_name(db, student_id)
    now = datetime.datetime.utcnow().isoformat()
    cur = db.execute(
        """
        INSERT INTO community_posts (room, student_id, author_label, is_ai, parent_id, content, created_at)
        VALUES (?, ?, ?, 0, ?, ?, ?)
        """,
        (room, student_id, author_label, parent_id, content, now),
    )
    post_id = cur.lastrowid
    db.commit()

    ai_reply_row = None
    if MENTION_RE.search(content):
        ai_reply_row = _generate_ai_reply(db, room, thread_root_id=parent_id or post_id)

    post_row = db.execute("SELECT * FROM community_posts WHERE id = ?", (post_id,)).fetchone()
    return jsonify({
        "ok": True,
        "post": _post_dict(post_row),
        "ai_reply": _post_dict(ai_reply_row) if ai_reply_row else None,
    })


def _generate_ai_reply(db, room, thread_root_id):
    context_rows = db.execute(
        """
        SELECT * FROM community_posts
        WHERE (id = ? OR parent_id = ?) AND is_hidden = 0
        ORDER BY id ASC LIMIT 10
        """,
        (thread_root_id, thread_root_id),
    ).fetchall()
    history = [
        {"role": "model" if r["is_ai"] else "user", "content": f"{r['author_label']}: {r['content']}"}
        for r in context_rows
    ]

    system_prompt = build_community_system_prompt(room)
    try:
        reply_text = call_gemini(system_prompt, history)
    except GeminiError as exc:
        reply_text = f"(Amara couldn't respond just now: {exc})"

    now = datetime.datetime.utcnow().isoformat()
    cur = db.execute(
        """
        INSERT INTO community_posts (room, student_id, author_label, is_ai, parent_id, content, created_at)
        VALUES (?, NULL, 'Amara', 1, ?, ?, ?)
        """,
        (room, thread_root_id, reply_text, now),
    )
    db.commit()
    return db.execute("SELECT * FROM community_posts WHERE id = ?", (cur.lastrowid,)).fetchone()


@community_bp.route("/api/community/posts/<int:post_id>/report", methods=["POST"])
@login_required
def api_report_post(post_id):
    db = get_db()
    payload = request.get_json(silent=True) or {}
    reason = (payload.get("reason") or "")[:500]

    post = db.execute("SELECT id FROM community_posts WHERE id = ?", (post_id,)).fetchone()
    if not post:
        return jsonify({"ok": False, "error": "Post not found."}), 404

    db.execute(
        "INSERT INTO community_reports (post_id, reported_by, reason, created_at) VALUES (?, ?, ?, ?)",
        (post_id, session["student_id"], reason, datetime.datetime.utcnow().isoformat()),
    )
    db.commit()
    return jsonify({"ok": True})
