import datetime

from flask import Blueprint, jsonify, render_template, request

from extensions import get_db, requires_admin_auth
from blueprints.roi import GOOGLE_FORM_ACTION_URL, HUBSPOT_ACCESS_TOKEN

admin_bp = Blueprint("admin", __name__)


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


@admin_bp.route("/admin/community")
@requires_admin_auth
def admin_community():
    db = get_db()
    reports = db.execute(
        """
        SELECT r.id AS report_id, r.reason, r.created_at AS reported_at,
               p.id AS post_id, p.room, p.author_label, p.content, p.is_hidden, p.created_at AS post_created_at
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
    now = datetime.datetime.utcnow().isoformat()
    db.execute("UPDATE community_posts SET is_hidden = 1 WHERE id = ?", (post_id,))
    db.execute(
        "UPDATE community_reports SET resolved_at = ?, resolved_action = 'hidden' WHERE post_id = ? AND resolved_at IS NULL",
        (now, post_id),
    )
    db.commit()
    if request.is_json:
        return jsonify({"ok": True})
    from flask import redirect, url_for

    return redirect(url_for("admin.admin_community"))


@admin_bp.route("/admin/community/posts/<int:post_id>/dismiss-reports", methods=["POST"])
@requires_admin_auth
def dismiss_reports(post_id):
    db = get_db()
    now = datetime.datetime.utcnow().isoformat()
    db.execute(
        "UPDATE community_reports SET resolved_at = ?, resolved_action = 'dismissed' WHERE post_id = ? AND resolved_at IS NULL",
        (now, post_id),
    )
    db.commit()
    if request.is_json:
        return jsonify({"ok": True})
    from flask import redirect, url_for

    return redirect(url_for("admin.admin_community"))
