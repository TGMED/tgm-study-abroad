"""Counselor login/logout. No self-signup -- accounts are created by an
admin (see blueprints/admin.py's counselor management), matching how real
staff access is provisioned rather than opened up publicly. Session key is
'counselor_id', kept entirely separate from a student's 'student_id' --
see extensions.counselor_login_required.
"""
import datetime

from flask import Blueprint, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from extensions import get_db

counselor_auth_bp = Blueprint("counselor_auth", __name__)


def _safe_next(raw):
    if raw and raw.startswith("/") and not raw.startswith("//"):
        return raw
    return None


@counselor_auth_bp.route("/counselor/login", methods=["GET", "POST"])
def counselor_login():
    next_url = _safe_next(request.values.get("next")) or url_for("counselor_portal.dashboard")

    if session.get("counselor_id"):
        return redirect(next_url)

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        db = get_db()
        row = db.execute("SELECT id, password_hash, is_active FROM counselors WHERE email = ?", (email,)).fetchone()

        if row is None or not check_password_hash(row["password_hash"], password):
            return render_template("counselor_login.html", email=email, next_url=next_url, error="Incorrect email or password.")
        if not row["is_active"]:
            return render_template("counselor_login.html", email=email, next_url=next_url, error="This account has been deactivated.")

        session["counselor_id"] = row["id"]
        session.permanent = True
        return redirect(next_url)

    return render_template("counselor_login.html", email="", next_url=next_url, error=None)


@counselor_auth_bp.route("/counselor/logout")
def counselor_logout():
    session.pop("counselor_id", None)
    return redirect(url_for("counselor_auth.counselor_login"))
