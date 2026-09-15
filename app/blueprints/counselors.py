"""Student-facing: browse TGM's counselors and message one directly. This is
a separate channel from Amara's AI-escalation queue (human_handoff_queue) --
a student picking a counselor here is a deliberate, student-initiated
conversation with a specific named person, not a triage hand-off.
"""
import datetime

from flask import Blueprint, abort, jsonify, render_template, request, session

from extensions import get_db, login_required

counselors_bp = Blueprint("counselors", __name__)


def _initials(name):
    parts = [w for w in (name or "").split() if w]
    return ("".join(w[0] for w in parts[:2]).upper()) or "C"


def _get_counselor_or_404(db, counselor_id):
    row = db.execute("SELECT * FROM counselors WHERE id = ? AND is_active = 1", (counselor_id,)).fetchone()
    if not row:
        abort(404)
    return row


def _get_or_create_conversation(db, student_id, counselor_id):
    row = db.execute(
        "SELECT id FROM counselor_conversations WHERE student_id = ? AND counselor_id = ?",
        (student_id, counselor_id),
    ).fetchone()
    if row:
        return row["id"]
    now = datetime.datetime.utcnow().isoformat()
    cur = db.execute(
        "INSERT INTO counselor_conversations (student_id, counselor_id, created_at, last_message_at) VALUES (?, ?, ?, ?)",
        (student_id, counselor_id, now, now),
    )
    db.commit()
    return cur.lastrowid


@counselors_bp.route("/counselors")
@login_required
def directory():
    db = get_db()
    student_id = session["student_id"]
    rows = db.execute(
        """
        SELECT c.*,
            (SELECT conv.id FROM counselor_conversations conv WHERE conv.student_id = ? AND conv.counselor_id = c.id) AS conv_id,
            (SELECT COUNT(*) FROM counselor_messages m
                JOIN counselor_conversations conv ON conv.id = m.conversation_id
                WHERE conv.student_id = ? AND conv.counselor_id = c.id) AS message_count
        FROM counselors c
        WHERE c.is_active = 1
        ORDER BY c.full_name ASC
        """,
        (student_id, student_id),
    ).fetchall()
    counselors = [{**dict(r), "initials": _initials(r["full_name"])} for r in rows]
    return render_template("counselors_directory.html", counselors=counselors)


@counselors_bp.route("/counselors/<int:counselor_id>")
@login_required
def chat_page(counselor_id):
    db = get_db()
    student_id = session["student_id"]
    counselor = _get_counselor_or_404(db, counselor_id)
    conv_id = _get_or_create_conversation(db, student_id, counselor_id)
    history = db.execute(
        "SELECT id, sender_type, content, created_at FROM counselor_messages WHERE conversation_id = ? ORDER BY id ASC",
        (conv_id,),
    ).fetchall()
    last_id = history[-1]["id"] if history else 0
    counselor_dict = {**dict(counselor), "initials": _initials(counselor["full_name"])}
    return render_template("counselor_chat.html", counselor=counselor_dict, messages=history, last_id=last_id)


@counselors_bp.route("/api/counselors/<int:counselor_id>/messages")
@login_required
def api_poll(counselor_id):
    db = get_db()
    student_id = session["student_id"]
    since = request.args.get("since", type=int, default=0)
    conv = db.execute(
        "SELECT id FROM counselor_conversations WHERE student_id = ? AND counselor_id = ?",
        (student_id, counselor_id),
    ).fetchone()
    if not conv:
        return jsonify({"ok": True, "messages": []})
    # Excludes the student's own messages -- rendered optimistically
    # client-side the moment they're sent; re-including them here would risk
    # a duplicate bubble if a poll tick lands before the send() response
    # comes back (a slow counselor reply widens that window, same class of
    # bug fixed in community.py's api_list_posts / chat.py's poll).
    rows = db.execute(
        "SELECT id, sender_type, content, created_at FROM counselor_messages "
        "WHERE conversation_id = ? AND id > ? AND sender_type != 'student' ORDER BY id ASC",
        (conv["id"], since),
    ).fetchall()
    return jsonify({"ok": True, "messages": [dict(r) for r in rows]})


@counselors_bp.route("/api/counselors/<int:counselor_id>/messages", methods=["POST"])
@login_required
def api_send(counselor_id):
    db = get_db()
    student_id = session["student_id"]
    _get_counselor_or_404(db, counselor_id)

    payload = request.get_json(silent=True) or {}
    content = (payload.get("content") or "").strip()
    if not content:
        return jsonify({"ok": False, "error": "Message cannot be empty."}), 400
    if len(content) > 4000:
        return jsonify({"ok": False, "error": "Message is too long (max 4000 characters)."}), 400

    conv_id = _get_or_create_conversation(db, student_id, counselor_id)
    now = datetime.datetime.utcnow().isoformat()
    cur = db.execute(
        "INSERT INTO counselor_messages (conversation_id, sender_type, content, created_at) VALUES (?, 'student', ?, ?)",
        (conv_id, content, now),
    )
    db.execute("UPDATE counselor_conversations SET last_message_at = ? WHERE id = ?", (now, conv_id))
    db.commit()
    return jsonify({"ok": True, "message_id": cur.lastrowid})
