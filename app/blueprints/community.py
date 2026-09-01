import datetime
import re

from flask import Blueprint, abort, jsonify, redirect, render_template, request, session, url_for

from extensions import get_db, login_required
from services.gemini import GeminiError, call_gemini
from services.prompts import COMMUNITY_ROOMS, COMMUNITY_ROOM_META, build_community_system_prompt

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


def _initials(label):
    parts = [w for w in (label or "").split() if w]
    if not parts:
        return "M"
    return "".join(w[0] for w in parts[:2]).upper()


def _post_dict(row):
    return {
        "id": row["id"],
        "room": row["room"],
        "author_label": row["author_label"],
        "author_id": row["student_id"],
        "has_avatar": bool(_col(row, "author_avatar", None)),
        "initials": _initials(row["author_label"]),
        "is_ai": bool(row["is_ai"]),
        "parent_id": row["parent_id"],
        "content": row["content"],
        "created_at": row["created_at"],
        "score": _col(row, "score", 0),
        "my_vote": _col(row, "my_vote", 0),
        "reply_count": _col(row, "reply_count", 0),
        "mine": row["student_id"] is not None and row["student_id"] == session.get("student_id"),
    }


# Every post row is fetched with its author's avatar, vote tally, the
# current student's own vote, and (for top-level posts) a reply count -- so
# the UI can render the vote rail and comment count without extra
# round-trips. First `?` (student_id) must always be the first bound param.
_POST_SELECT = """
    SELECT p.*, s.avatar_path AS author_avatar,
        COALESCE((SELECT SUM(value) FROM community_votes v WHERE v.post_id = p.id), 0) AS score,
        COALESCE((SELECT value FROM community_votes v WHERE v.post_id = p.id AND v.student_id = ?), 0) AS my_vote,
        (SELECT COUNT(*) FROM community_posts c WHERE c.parent_id = p.id AND c.is_hidden = 0) AS reply_count
    FROM community_posts p
    LEFT JOIN students s ON s.id = p.student_id
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

    # Signed-in but not-yet-onboarded members finish their profile first.
    me = db.execute("SELECT onboarded FROM students WHERE id = ?", (session["student_id"],)).fetchone()
    if me is not None and not me["onboarded"]:
        return redirect(url_for("social.onboarding"))

    student_id = session["student_id"]
    top_posts = db.execute(
        _POST_SELECT + " WHERE p.room = ? AND p.parent_id IS NULL AND p.is_hidden = 0 ORDER BY p.id DESC LIMIT 50",
        (student_id, room),
    ).fetchall()

    thread = []
    for post in reversed(top_posts):
        replies = db.execute(
            _POST_SELECT + " WHERE p.parent_id = ? AND p.is_hidden = 0 ORDER BY p.id ASC",
            (student_id, post["id"]),
        ).fetchall()
        thread.append({"post": _post_dict(post), "replies": [_post_dict(r) for r in replies]})

    last_id = db.execute(
        "SELECT COALESCE(MAX(id), 0) AS m FROM community_posts WHERE room = ?", (room,)
    ).fetchone()["m"]

    room_label = COMMUNITY_ROOM_META.get(room, {}).get("label", room.title())
    member_count = db.execute(
        "SELECT COUNT(*) AS c FROM room_members WHERE room = ?", (room,)
    ).fetchone()["c"]
    joined = db.execute(
        "SELECT 1 FROM room_members WHERE room = ? AND student_id = ?", (room, session["student_id"])
    ).fetchone() is not None
    return render_template(
        "community_room.html", room=room, room_label=room_label, thread=thread,
        last_id=last_id, member_count=member_count, joined=joined,
    )


@community_bp.route("/api/community/<room>/posts")
@login_required
def api_list_posts(room):
    _room_or_404(room)
    since = request.args.get("since", type=int, default=0)
    db = get_db()
    rows = db.execute(
        _POST_SELECT + " WHERE p.room = ? AND p.id > ? AND p.is_hidden = 0 ORDER BY p.id ASC",
        (session["student_id"], room, since),
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

    post_row = db.execute(_POST_SELECT + " WHERE p.id = ?", (student_id, post_id)).fetchone()
    return jsonify({
        "ok": True,
        "post": _post_dict(post_row),
        "ai_reply": _post_dict(ai_reply_row) if ai_reply_row else None,
    })


@community_bp.route("/api/community/posts/<int:post_id>/vote", methods=["POST"])
@login_required
def vote_post(post_id):
    db = get_db()
    student_id = session["student_id"]

    student = db.execute("SELECT is_banned FROM students WHERE id = ?", (student_id,)).fetchone()
    if student and student["is_banned"]:
        return jsonify({"ok": False, "error": "Your account is restricted from voting."}), 403

    post = db.execute(
        "SELECT id, student_id FROM community_posts WHERE id = ? AND is_hidden = 0", (post_id,)
    ).fetchone()
    if not post:
        return jsonify({"ok": False, "error": "Post not found."}), 404
    if post["student_id"] == student_id:
        return jsonify({"ok": False, "error": "You can't upvote your own post."}), 400

    payload = request.get_json(silent=True) or {}
    # Upvote-only toggle (not full +/- voting) -- keeps this a "mark helpful"
    # signal rather than opening the door to downvote pile-ons in a support
    # community.
    value = 1 if payload.get("value") else 0

    existing = db.execute(
        "SELECT value FROM community_votes WHERE post_id = ? AND student_id = ?", (post_id, student_id)
    ).fetchone()
    now = datetime.datetime.utcnow().isoformat()
    if value == 0:
        db.execute("DELETE FROM community_votes WHERE post_id = ? AND student_id = ?", (post_id, student_id))
    elif existing:
        db.execute(
            "UPDATE community_votes SET value = ?, created_at = ? WHERE post_id = ? AND student_id = ?",
            (value, now, post_id, student_id),
        )
    else:
        db.execute(
            "INSERT INTO community_votes (post_id, student_id, value, created_at) VALUES (?, ?, ?, ?)",
            (post_id, student_id, value, now),
        )
    db.commit()

    score = db.execute(
        "SELECT COALESCE(SUM(value), 0) AS s FROM community_votes WHERE post_id = ?", (post_id,)
    ).fetchone()["s"]
    return jsonify({"ok": True, "score": score, "my_vote": value})


def _generate_ai_reply(db, room, thread_root_id):
    # Take the most recent 10 posts in this thread, not the oldest 10 --
    # otherwise a thread that's grown past 10 posts would hand Amara a
    # stale window that excludes recent messages (possibly including the
    # very message that just @mentioned her). Still handed to her oldest-
    # first so the conversation reads in order.
    context_rows = db.execute(
        """
        SELECT * FROM (
            SELECT * FROM community_posts
            WHERE (id = ? OR parent_id = ?) AND is_hidden = 0
            ORDER BY id DESC LIMIT 10
        ) recent
        ORDER BY id ASC
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
    # my_vote is always 0 for a post nobody has voted on yet, but _POST_SELECT
    # still needs a bound value for that placeholder regardless of whose
    # perspective this is fetched from.
    return db.execute(_POST_SELECT + " WHERE p.id = ?", (0, cur.lastrowid)).fetchone()


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
