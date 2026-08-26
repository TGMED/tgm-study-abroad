import datetime
import os

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from extensions import get_db, requires_admin_auth
from blueprints.roi import GOOGLE_FORM_ACTION_URL, HUBSPOT_ACCESS_TOKEN
from services.prompts import COMMUNITY_ROOM_META

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
    try:
        n = get_db().execute(
            "SELECT COUNT(*) AS c FROM community_reports WHERE resolved_at IS NULL"
        ).fetchone()["c"]
    except Exception:
        n = 0
    return {"open_reports": n}


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
