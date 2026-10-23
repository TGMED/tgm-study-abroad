"""Counselor-facing: each counselor only ever sees their own conversations
-- every query below is scoped by counselor_id = session['counselor_id'],
so one counselor can never see another's inbox.
"""
import datetime

from flask import Blueprint, abort, jsonify, render_template, request, session

from extensions import counselor_login_required, get_db

counselor_portal_bp = Blueprint("counselor_portal", __name__)


@counselor_portal_bp.route("/counselor")
@counselor_login_required
def dashboard():
    db = get_db()
    counselor_id = session["counselor_id"]
    rows = db.execute(
        """
        SELECT conv.id AS conv_id, s.id AS student_id, s.display_name, s.email, conv.last_message_at,
            (SELECT content FROM counselor_messages m WHERE m.conversation_id = conv.id ORDER BY m.id DESC LIMIT 1) AS last_message,
            (SELECT sender_type FROM counselor_messages m WHERE m.conversation_id = conv.id ORDER BY m.id DESC LIMIT 1) AS last_sender
        FROM counselor_conversations conv
        JOIN students s ON s.id = conv.student_id
        WHERE conv.counselor_id = ?
        ORDER BY conv.last_message_at DESC
        """,
        (counselor_id,),
    ).fetchall()
    conversations = [dict(r) for r in rows]
    return render_template("counselor_dashboard.html", conversations=conversations)


@counselor_portal_bp.route("/counselor/chat/<int:student_id>")
@counselor_login_required
def chat_page(student_id):
    db = get_db()
    counselor_id = session["counselor_id"]
    student = db.execute("SELECT id, display_name, email FROM students WHERE id = ?", (student_id,)).fetchone()
    if not student:
        abort(404)
    conv = db.execute(
        "SELECT id FROM counselor_conversations WHERE student_id = ? AND counselor_id = ?",
        (student_id, counselor_id),
    ).fetchone()
    if not conv:
        abort(404)
    history = db.execute(
        "SELECT id, sender_type, content, created_at FROM counselor_messages WHERE conversation_id = ? ORDER BY id ASC",
        (conv["id"],),
    ).fetchall()
    last_id = history[-1]["id"] if history else 0
    return render_template("counselor_portal_chat.html", student=dict(student), messages=history, last_id=last_id)


@counselor_portal_bp.route("/api/counselor/chat/<int:student_id>/messages")
@counselor_login_required
def api_poll(student_id):
    db = get_db()
    counselor_id = session["counselor_id"]
    since = request.args.get("since", type=int, default=0)
    conv = db.execute(
        "SELECT id FROM counselor_conversations WHERE student_id = ? AND counselor_id = ?",
        (student_id, counselor_id),
    ).fetchone()
    if not conv:
        return jsonify({"ok": True, "messages": []})
    # Excludes the counselor's own messages -- same optimistic-render reason
    # as counselors.py's api_poll on the student side.
    rows = db.execute(
        "SELECT id, sender_type, content, created_at FROM counselor_messages "
        "WHERE conversation_id = ? AND id > ? AND sender_type != 'counselor' ORDER BY id ASC",
        (conv["id"], since),
    ).fetchall()
    return jsonify({"ok": True, "messages": [dict(r) for r in rows]})


@counselor_portal_bp.route("/api/counselor/chat/<int:student_id>/messages", methods=["POST"])
@counselor_login_required
def api_reply(student_id):
    db = get_db()
    counselor_id = session["counselor_id"]
    conv = db.execute(
        "SELECT id FROM counselor_conversations WHERE student_id = ? AND counselor_id = ?",
        (student_id, counselor_id),
    ).fetchone()
    if not conv:
        abort(404)

    payload = request.get_json(silent=True) or {}
    content = (payload.get("content") or "").strip()
    if not content:
        return jsonify({"ok": False, "error": "Message cannot be empty."}), 400
    if len(content) > 4000:
        return jsonify({"ok": False, "error": "Message is too long (max 4000 characters)."}), 400

    now = datetime.datetime.utcnow().isoformat()
    cur = db.execute(
        "INSERT INTO counselor_messages (conversation_id, sender_type, content, created_at) VALUES (?, 'counselor', ?, ?)",
        (conv["id"], content, now),
    )
    db.execute("UPDATE counselor_conversations SET last_message_at = ? WHERE id = ?", (now, conv["id"]))
    db.commit()
    return jsonify({"ok": True, "message_id": cur.lastrowid})
