import datetime
import os
import secrets

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from extensions import get_db, requires_admin_auth
from blueprints.roi import GOOGLE_FORM_ACTION_URL, HUBSPOT_ACCESS_TOKEN
from services.digest import send_weekly_digest
from services.prompts import COMMUNITY_ROOM_META
from services.whatsapp import WhatsAppSendError, send_text_message

admin_bp = Blueprint("admin", __name__)

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "uploads")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now():
    return datetime.datetime.utcnow().isoformat()


def _initials(name):
    parts = [w for w in (name or "").split() if w]
    return ("".join(w[0] for w in parts[:2]).upper()) or "M"


def _room_label(room):
    return COMMUNITY_ROOM_META.get(room, {}).get("label", (room or "").title())


def _ago(iso):
    try:
        t = datetime.datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return "—"
    s = max(0, (datetime.datetime.utcnow() - t).total_seconds())
    if s < 60:
        return "just now"
    m = int(s // 60)
    if m < 60:
        return f"{m}m ago"
    h = int(m // 60)
    if h < 24:
        return f"{h}h ago"
    d = int(h // 24)
    if d == 1:
        return "yesterday"
    if d < 30:
        return f"{d}d ago"
    return t.strftime("%d %b %Y")


def _name(row):
    return row["display_name"] or (row["email"].split("@")[0] if row["email"] else "Member")


@admin_bp.app_context_processor
def _inject_admin():
    if not (request.path or "").startswith("/admin"):
        return {}
    db = get_db()
    try:
        n = db.execute(
            "SELECT COUNT(*) AS c FROM community_reports WHERE resolved_at IS NULL"
        ).fetchone()["c"]
    except Exception:
        n = 0
    try:
        h = db.execute(
            "SELECT COUNT(*) AS c FROM human_handoff_queue WHERE status = 'open'"
        ).fetchone()["c"]
    except Exception:
        h = 0
    return {"open_reports": n, "open_handoffs": h}


def _delete_post_cascade(db, pid):
    """Hard-delete a post (or comment) plus its replies, votes, and resolve reports."""
    reply_ids = [r["id"] for r in db.execute("SELECT id FROM community_posts WHERE parent_id = ?", (pid,)).fetchall()]
    ids = [pid] + reply_ids
    placeholders = ",".join("?" * len(ids))
    db.execute(f"DELETE FROM community_votes WHERE post_id IN ({placeholders})", ids)
    db.execute(
        f"UPDATE community_reports SET resolved_at = ?, resolved_action = 'deleted' "
        f"WHERE post_id IN ({placeholders}) AND resolved_at IS NULL",
        [_now(), *ids],
    )
    db.execute(f"DELETE FROM community_posts WHERE id IN ({placeholders})", ids)


# ---------------------------------------------------------------------------
# Members + analytics
# ---------------------------------------------------------------------------
@admin_bp.route("/admin")
@requires_admin_auth
def admin_home():
    return redirect(url_for("admin.admin_members"))


@admin_bp.route("/admin/members")
@requires_admin_auth
def admin_members():
    db = get_db()
    rows = db.execute(
        """
        SELECT s.*,
          (SELECT COUNT(*) FROM community_posts p WHERE p.student_id = s.id AND p.parent_id IS NULL AND p.is_hidden = 0) AS posts,
          (SELECT COUNT(*) FROM community_posts p WHERE p.student_id = s.id AND p.parent_id IS NOT NULL AND p.is_hidden = 0) AS comments,
          (SELECT COUNT(*) FROM room_members rm WHERE rm.student_id = s.id) AS channels
        FROM students s WHERE s.onboarded = 1
        """
    ).fetchall()
    members = [{
        "id": r["id"], "name": _name(r), "initials": _initials(_name(r)), "email": r["email"],
        "user_type": r["user_type"] or "aspiring", "is_banned": bool(r["is_banned"]),
        "has_avatar": bool(r["avatar_path"]), "posts": r["posts"], "comments": r["comments"],
        "channels": r["channels"], "last_seen": _ago(r["last_seen_at"] or r["created_at"]),
        "_activity": r["posts"] + r["comments"],
    } for r in rows]
    members.sort(key=lambda m: (-m["_activity"], -m["id"]))
    totals = {
        "members": len(members),
        "posts": sum(m["posts"] for m in members),
        "comments": sum(m["comments"] for m in members),
        "frozen": sum(1 for m in members if m["is_banned"]),
    }
    return render_template("admin_members.html", members=members, totals=totals)


@admin_bp.route("/admin/digest/send", methods=["POST"])
@requires_admin_auth
def admin_send_digest():
    db = get_db()
    sent, skipped, highlights = send_weekly_digest(db, url_for("social.communities", _external=True))
    if not highlights:
        msg = "no-activity"
    else:
        msg = f"sent-{sent}-skipped-{skipped}"
    return redirect(url_for("admin.admin_members", digest=msg))


@admin_bp.route("/admin/members/<int:sid>")
@requires_admin_auth
def admin_member(sid):
    db = get_db()
    row = db.execute("SELECT * FROM students WHERE id = ?", (sid,)).fetchone()
    if not row:
        return redirect(url_for("admin.admin_members"))

    posts = db.execute("SELECT COUNT(*) AS c FROM community_posts WHERE student_id = ? AND parent_id IS NULL AND is_hidden = 0", (sid,)).fetchone()["c"]
    comments = db.execute("SELECT COUNT(*) AS c FROM community_posts WHERE student_id = ? AND parent_id IS NOT NULL AND is_hidden = 0", (sid,)).fetchone()["c"]
    votes = db.execute("SELECT COALESCE(SUM(v.value), 0) AS s FROM community_votes v JOIN community_posts p ON p.id = v.post_id WHERE p.student_id = ?", (sid,)).fetchone()["s"]
    amara = db.execute("SELECT COUNT(*) AS c FROM community_posts WHERE student_id = ? AND content LIKE '%@amara%'", (sid,)).fetchone()["c"]
    reports = db.execute("SELECT COUNT(*) AS c FROM community_reports r JOIN community_posts p ON p.id = r.post_id WHERE p.student_id = ?", (sid,)).fetchone()["c"]

    ch_rows = db.execute(
        "SELECT room, COUNT(*) AS c FROM community_posts WHERE student_id = ? AND is_hidden = 0 GROUP BY room ORDER BY c DESC",
        (sid,),
    ).fetchall()
    top = ch_rows[0]["c"] if ch_rows else 1
    channels = [{"label": _room_label(c["room"]), "count": c["c"], "pct": int(c["c"] / top * 100)} for c in ch_rows]

    act_rows = db.execute("SELECT * FROM community_posts WHERE student_id = ? ORDER BY id DESC LIMIT 40", (sid,)).fetchall()
    activity = [{
        "id": a["id"], "is_comment": a["parent_id"] is not None, "room_label": _room_label(a["room"]),
        "ago": _ago(a["created_at"]), "content": a["content"], "is_hidden": bool(a["is_hidden"]),
    } for a in act_rows]

    m = {
        "id": row["id"], "name": _name(row), "initials": _initials(_name(row)), "email": row["email"],
        "user_type": row["user_type"] or "aspiring", "is_banned": bool(row["is_banned"]),
        "has_avatar": bool(row["avatar_path"]), "location": row["location"], "destination": row["destination"],
        "created": _ago(row["created_at"]), "last_seen": _ago(row["last_seen_at"] or row["created_at"]),
    }
    stats = {"posts": posts, "comments": comments, "votes": votes, "amara": amara, "reports": reports}
    return render_template("admin_member.html", m=m, stats=stats, channels=channels, activity=activity)


@admin_bp.route("/admin/members/<int:sid>/freeze", methods=["POST"])
@requires_admin_auth
def freeze_member(sid):
    db = get_db()
    row = db.execute("SELECT is_banned FROM students WHERE id = ?", (sid,)).fetchone()
    if row:
        db.execute("UPDATE students SET is_banned = ? WHERE id = ?", (0 if row["is_banned"] else 1, sid))
        db.commit()
    return redirect(request.referrer or url_for("admin.admin_member", sid=sid))


@admin_bp.route("/admin/members/<int:sid>/delete", methods=["POST"])
@requires_admin_auth
def delete_member(sid):
    db = get_db()
    row = db.execute("SELECT avatar_path FROM students WHERE id = ?", (sid,)).fetchone()
    if not row:
        return redirect(url_for("admin.admin_members"))

    # Remove all their content and associations.
    post_ids = [p["id"] for p in db.execute("SELECT id FROM community_posts WHERE student_id = ?", (sid,)).fetchall()]
    for pid in post_ids:
        db.execute("DELETE FROM community_votes WHERE post_id = ?", (pid,))
        db.execute("UPDATE community_reports SET resolved_at = ?, resolved_action = 'account-deleted' WHERE post_id = ? AND resolved_at IS NULL", (_now(), pid))
    db.execute("DELETE FROM community_posts WHERE student_id = ?", (sid,))
    db.execute("DELETE FROM community_votes WHERE student_id = ?", (sid,))
    db.execute("DELETE FROM room_members WHERE student_id = ?", (sid,))
    db.execute("DELETE FROM direct_messages WHERE sender_id = ? OR recipient_id = ?", (sid, sid))
    db.execute("DELETE FROM student_profiles WHERE student_id = ?", (sid,))
    db.execute("DELETE FROM community_reports WHERE reported_by = ?", (sid,))
    db.execute("DELETE FROM students WHERE id = ?", (sid,))
    db.commit()

    if row["avatar_path"]:
        try:
            os.remove(os.path.join(UPLOAD_DIR, row["avatar_path"]))
        except OSError:
            pass
    return redirect(url_for("admin.admin_members"))


@admin_bp.route("/admin/posts/<int:pid>/delete", methods=["POST"])
@requires_admin_auth
def delete_post(pid):
    db = get_db()
    _delete_post_cascade(db, pid)
    db.commit()
    if request.is_json:
        return jsonify({"ok": True})
    return redirect(request.form.get("next") or request.referrer or url_for("admin.admin_community"))


# ---------------------------------------------------------------------------
# Leads
# ---------------------------------------------------------------------------
@admin_bp.route("/admin/leads")
@requires_admin_auth
def admin_leads():
    db = get_db()
    rows = db.execute("SELECT * FROM leads ORDER BY id DESC").fetchall()
    return render_template(
        "admin_leads.html",
        rows=rows,
        google_form_configured=bool(GOOGLE_FORM_ACTION_URL),
        hubspot_configured=bool(HUBSPOT_ACCESS_TOKEN),
    )


# ---------------------------------------------------------------------------
# Human handoff inbox -- students Amara flagged (or a counsellor flagged
# manually) as needing a human. Landing here never pauses Amara by itself;
# she keeps answering normally until a counsellor actually opens a
# conversation and clicks "Take over" below, so no one's ever left waiting
# on a human who hasn't looked at the queue yet.
# ---------------------------------------------------------------------------
@admin_bp.route("/admin/inbox")
@requires_admin_auth
def admin_inbox():
    db = get_db()
    rows = db.execute(
        """
        SELECT q.id AS queue_id, q.student_id, q.reason, q.status, q.created_at, q.resolved_by,
               s.display_name, s.email,
               (SELECT content FROM chat_messages WHERE student_id = s.id ORDER BY id DESC LIMIT 1) AS last_message,
               (SELECT created_at FROM chat_messages WHERE student_id = s.id ORDER BY id DESC LIMIT 1) AS last_message_at
        FROM human_handoff_queue q
        JOIN students s ON s.id = q.student_id
        WHERE q.status IN ('open', 'assigned')
        ORDER BY (q.status = 'assigned'), q.created_at DESC
        """
    ).fetchall()
    conversations = []
    for r in rows:
        name = r["display_name"] or (r["email"].split("@")[0] if r["email"] else "Member")
        conversations.append({
            "queue_id": r["queue_id"], "student_id": r["student_id"], "name": name,
            "initials": _initials(name), "reason": r["reason"], "status": r["status"],
            "resolved_by": r["resolved_by"],
            "last_message": (r["last_message"] or "")[:140], "ago": _ago(r["last_message_at"] or r["created_at"]),
        })
    return render_template("admin_inbox.html", conversations=conversations)


@admin_bp.route("/admin/inbox/<int:sid>")
@requires_admin_auth
def admin_inbox_chat(sid):
    db = get_db()
    student = db.execute("SELECT * FROM students WHERE id = ?", (sid,)).fetchone()
    if not student:
        abort(404)
    messages = db.execute(
        "SELECT id, role, content, created_at FROM chat_messages WHERE student_id = ? ORDER BY id ASC",
        (sid,),
    ).fetchall()
    queue_entry = db.execute(
        "SELECT * FROM human_handoff_queue WHERE student_id = ? AND status IN ('open','assigned') "
        "ORDER BY id DESC LIMIT 1",
        (sid,),
    ).fetchone()
    last_id = messages[-1]["id"] if messages else 0
    return render_template(
        "admin_chat.html", student=student, name=_name(student), messages=messages,
        queue_entry=queue_entry, last_id=last_id,
    )


@admin_bp.route("/admin/inbox/<int:sid>/poll")
@requires_admin_auth
def admin_inbox_poll(sid):
    since = request.args.get("since", type=int, default=0)
    db = get_db()
    rows = db.execute(
        "SELECT id, role, content FROM chat_messages WHERE student_id = ? AND id > ? ORDER BY id ASC",
        (sid, since),
    ).fetchall()
    return jsonify({"ok": True, "messages": [{"id": r["id"], "role": r["role"], "content": r["content"]} for r in rows]})


@admin_bp.route("/admin/inbox/<int:sid>/takeover", methods=["POST"])
@requires_admin_auth
def admin_inbox_takeover(sid):
    db = get_db()
    counsellor = (request.authorization.username if request.authorization else "counsellor")
    db.execute("UPDATE students SET chat_mode = 'human' WHERE id = ?", (sid,))
    db.execute(
        "UPDATE human_handoff_queue SET status = 'assigned', resolved_by = ? "
        "WHERE student_id = ? AND status = 'open'",
        (counsellor, sid),
    )
    db.execute(
        "INSERT INTO chat_messages (student_id, role, content, created_at) VALUES (?, 'system', ?, ?)",
        (sid, "🟢 A TGM counsellor has joined the chat.", _now()),
    )
    db.commit()

    student = db.execute("SELECT phone FROM students WHERE id = ?", (sid,)).fetchone()
    if student and student["phone"]:
        try:
            send_text_message(student["phone"], "🟢 A TGM counsellor has joined the chat.")
        except WhatsAppSendError as exc:
            print(f"WhatsApp: takeover notice send failed for student {sid}: {exc}")
    return jsonify({"ok": True})


@admin_bp.route("/admin/inbox/<int:sid>/reply", methods=["POST"])
@requires_admin_auth
def admin_inbox_reply(sid):
    payload = request.get_json(silent=True) or {}
    content = (payload.get("content") or "").strip()
    if not content:
        return jsonify({"ok": False, "error": "Message cannot be empty."}), 400
    db = get_db()
    cur = db.execute(
        "INSERT INTO chat_messages (student_id, role, content, created_at) VALUES (?, 'counsellor', ?, ?)",
        (sid, content, _now()),
    )
    db.commit()

    # A web student picks this up via polling; a WhatsApp student only ever
    # sees it if we actively push it back out over the Cloud API.
    student = db.execute("SELECT phone FROM students WHERE id = ?", (sid,)).fetchone()
    if student and student["phone"]:
        try:
            send_text_message(student["phone"], content)
        except WhatsAppSendError as exc:
            print(f"WhatsApp: counsellor reply send failed for student {sid}: {exc}")

    return jsonify({"ok": True, "id": cur.lastrowid})


@admin_bp.route("/admin/inbox/<int:sid>/handback", methods=["POST"])
@requires_admin_auth
def admin_inbox_handback(sid):
    db = get_db()
    db.execute("UPDATE students SET chat_mode = 'ai' WHERE id = ?", (sid,))
    db.execute(
        "UPDATE human_handoff_queue SET status = 'resolved', resolved_at = ? "
        "WHERE student_id = ? AND status IN ('open','assigned')",
        (_now(), sid),
    )
    db.execute(
        "INSERT INTO chat_messages (student_id, role, content, created_at) VALUES (?, 'system', ?, ?)",
        (sid, "↩️ Back with Amara — feel free to keep asking questions.", _now()),
    )
    db.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Moderation
# ---------------------------------------------------------------------------
@admin_bp.route("/admin/community")
@requires_admin_auth
def admin_community():
    db = get_db()
    reports = db.execute(
        """
        SELECT r.id AS report_id, r.reason, r.created_at AS reported_at,
               p.id AS post_id, p.room, p.author_label, p.student_id, p.content, p.is_hidden
        FROM community_reports r
        JOIN community_posts p ON p.id = r.post_id
        WHERE r.resolved_at IS NULL
        ORDER BY r.id DESC
        """
    ).fetchall()
    return render_template("admin_community.html", reports=reports)


@admin_bp.route("/admin/community/posts/<int:post_id>/hide", methods=["POST"])
@requires_admin_auth
def hide_post(post_id):
    db = get_db()
    db.execute("UPDATE community_posts SET is_hidden = 1 WHERE id = ?", (post_id,))
    db.execute(
        "UPDATE community_reports SET resolved_at = ?, resolved_action = 'hidden' WHERE post_id = ? AND resolved_at IS NULL",
        (_now(), post_id),
    )
    db.commit()
    if request.is_json:
        return jsonify({"ok": True})
    return redirect(request.referrer or url_for("admin.admin_community"))


@admin_bp.route("/admin/community/posts/<int:post_id>/dismiss-reports", methods=["POST"])
@requires_admin_auth
def dismiss_reports(post_id):
    db = get_db()
    db.execute(
        "UPDATE community_reports SET resolved_at = ?, resolved_action = 'dismissed' WHERE post_id = ? AND resolved_at IS NULL",
        (_now(), post_id),
    )
    db.commit()
    if request.is_json:
        return jsonify({"ok": True})
    return redirect(request.referrer or url_for("admin.admin_community"))


# ---------------------------------------------------------------------------
# Counselors -- separate from the shared /admin login itself: each counselor
# gets their own account (extensions.counselor_login_required) so they only
# ever see conversations students sent to them specifically (blueprints/
# counselor_portal.py). Provisioning stays admin-only, no self-signup.
# ---------------------------------------------------------------------------
@admin_bp.route("/admin/counselors", methods=["GET", "POST"])
@requires_admin_auth
def admin_counselors():
    db = get_db()
    error = None
    created_password = None

    if request.method == "POST":
        full_name = (request.form.get("full_name") or "").strip()[:80]
        email = (request.form.get("email") or "").strip().lower()[:120]
        headline = (request.form.get("headline") or "").strip()[:160]

        if len(full_name) < 2:
            error = "Please enter the counselor's name."
        elif "@" not in email or "." not in email.split("@")[-1]:
            error = "Please enter a valid email address."
        elif db.execute("SELECT id FROM counselors WHERE email = ?", (email,)).fetchone():
            error = "A counselor with that email already exists."
        else:
            # Generated rather than asked for -- an admin creating an
            # account on someone else's behalf shouldn't be the one setting
            # (and therefore knowing) their password; shown once here so it
            # can be handed to the counselor to change after first login.
            created_password = secrets.token_urlsafe(9)
            db.execute(
                """
                INSERT INTO counselors (full_name, email, password_hash, headline, is_active, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (full_name, email, generate_password_hash(created_password), headline, _now()),
            )
            db.commit()

    counselors = db.execute("SELECT * FROM counselors ORDER BY created_at DESC").fetchall()
    return render_template(
        "admin_counselors.html", counselors=counselors, error=error, created_password=created_password,
    )


@admin_bp.route("/admin/counselors/<int:counselor_id>/toggle", methods=["POST"])
@requires_admin_auth
def toggle_counselor(counselor_id):
    db = get_db()
    row = db.execute("SELECT is_active FROM counselors WHERE id = ?", (counselor_id,)).fetchone()
    if row:
        db.execute("UPDATE counselors SET is_active = ? WHERE id = ?", (0 if row["is_active"] else 1, counselor_id))
        db.commit()
    return redirect(url_for("admin.admin_counselors"))
