import datetime
import hashlib
import secrets

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import get_db
from services.emailer import EmailSendError, send_otp_email

auth_bp = Blueprint("auth", __name__)

RESET_TTL_MINUTES = 15  # matches the "valid for 15 minutes" text baked into the EmailJS OTP template
MAX_VERIFY_ATTEMPTS = 5
MIN_PASSWORD_LEN = 8


def _hash_code(code):
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _safe_next(raw):
    """Only allow same-site relative paths as a post-auth redirect target."""
    if raw and raw.startswith("/") and not raw.startswith("//"):
        return raw
    return None


@auth_bp.route("/join", methods=["GET", "POST"])
def join():
    next_url = _safe_next(request.values.get("next")) or url_for("social.dashboard")

    if session.get("student_id"):
        return redirect(next_url)

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()[:40]
        email = (request.form.get("email") or "").strip().lower()[:120]
        password = request.form.get("password") or ""

        # Require a first and last name -- not a single nickname -- so
        # display names read as real people across the community.
        name_parts = [p for p in name.split() if len(p) > 1]
        if len(name_parts) < 2:
            return render_template(
                "join.html", next_url=next_url, name=name, email=email,
                error="Please enter your full name (first and last).",
            )
        if "@" not in email or "." not in email.split("@")[-1]:
            return render_template(
                "join.html", next_url=next_url, name=name, email=email,
                error="Please enter a valid email address.",
            )
        if len(password) < MIN_PASSWORD_LEN:
            return render_template(
                "join.html", next_url=next_url, name=name, email=email,
                error=f"Password must be at least {MIN_PASSWORD_LEN} characters.",
            )

        db = get_db()
        existing = db.execute("SELECT id FROM students WHERE email = ?", (email,)).fetchone()
        if existing is not None:
            return render_template(
                "join.html", next_url=next_url, name=name, email=email,
                error="That email already has an account -- log in instead.",
            )

        now = datetime.datetime.utcnow().isoformat()
        cur = db.execute(
            "INSERT INTO students (email, password_hash, display_name, created_at, last_seen_at) VALUES (?, ?, ?, ?, ?)",
            (email, generate_password_hash(password), name, now, now),
        )
        db.commit()

        session["student_id"] = cur.lastrowid
        session.permanent = True
        return redirect(next_url)

    return render_template("join.html", next_url=next_url, error=None, name="", email="")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    next_url = _safe_next(request.values.get("next")) or "/chat"

    if session.get("student_id"):
        return redirect(next_url)

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        db = get_db()
        row = db.execute("SELECT id, password_hash FROM students WHERE email = ?", (email,)).fetchone()

        if row is not None and not row["password_hash"]:
            # A pre-password-auth account (created via /join before this was
            # added, or via the ROI calculator's frictionless lead capture,
            # which never collects one) -- there's nothing to check against,
            # so send them to set one the same way a forgotten password gets
            # reset, rather than a confusing "incorrect password".
            return render_template(
                "login.html", email=email, next_url=next_url,
                error="This account doesn't have a password yet -- use \"Forgot password\" below to set one.",
            )

        if row is None or not check_password_hash(row["password_hash"], password):
            return render_template("login.html", email=email, next_url=next_url, error="Incorrect email or password.")

        db.execute(
            "UPDATE students SET last_seen_at = ? WHERE id = ?",
            (datetime.datetime.utcnow().isoformat(), row["id"]),
        )
        db.commit()
        session["student_id"] = row["id"]
        session.permanent = True
        return redirect(next_url)

    email = (request.args.get("email") or "").strip()
    return render_template("login.html", email=email, next_url=next_url, error=None)


@auth_bp.route("/forgot-password")
def forgot_password():
    next_url = _safe_next(request.args.get("next")) or "/chat"
    email = (request.args.get("email") or "").strip()
    return render_template("forgot_password.html", email=email, next_url=next_url)


@auth_bp.route("/api/auth/request-password-reset", methods=["POST"])
def request_password_reset():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "A valid email address is required."}), 400

    db = get_db()
    student = db.execute("SELECT id FROM students WHERE email = ?", (email,)).fetchone()
    if student is None:
        return jsonify({"ok": False, "error": "We don't recognise that email — sign up instead."}), 404

    code = f"{secrets.randbelow(900000) + 100000}"
    now = datetime.datetime.utcnow()
    expires_at = (now + datetime.timedelta(minutes=RESET_TTL_MINUTES)).isoformat()

    db.execute(
        "INSERT INTO otp_codes (email, code_hash, purpose, expires_at, created_at) VALUES (?, ?, 'reset', ?, ?)",
        (email, _hash_code(code), expires_at, now.isoformat()),
    )
    db.commit()

    try:
        # Reuses the same OTP template/plumbing as the old login flow --
        # a reset code is the same "prove you own this email" mechanic, just
        # for a different purpose ('reset' vs 'login' in otp_codes.purpose).
        send_otp_email(email, code, expires_at)
    except EmailSendError as exc:
        return jsonify({"ok": False, "error": f"Could not send the reset code: {exc}"}), 502

    return jsonify({"ok": True})


@auth_bp.route("/api/auth/reset-password", methods=["POST"])
def reset_password():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    code = (payload.get("code") or "").strip()
    new_password = payload.get("new_password") or ""
    next_url = _safe_next(payload.get("next")) or "/chat"

    if not email or not code:
        return jsonify({"ok": False, "error": "Email and code are required."}), 400
    if len(new_password) < MIN_PASSWORD_LEN:
        return jsonify({"ok": False, "error": f"Password must be at least {MIN_PASSWORD_LEN} characters."}), 400

    db = get_db()
    row = db.execute(
        """
        SELECT id, code_hash, expires_at, consumed_at, attempts
        FROM otp_codes
        WHERE email = ? AND purpose = 'reset'
        ORDER BY id DESC LIMIT 1
        """,
        (email,),
    ).fetchone()

    if row is None or row["consumed_at"] is not None:
        return jsonify({"ok": False, "error": "No active reset code — request a new one."}), 400
    if row["attempts"] >= MAX_VERIFY_ATTEMPTS:
        return jsonify({"ok": False, "error": "Too many attempts — request a new code."}), 429
    if datetime.datetime.utcnow().isoformat() > row["expires_at"]:
        return jsonify({"ok": False, "error": "That code has expired — request a new one."}), 400
    if _hash_code(code) != row["code_hash"]:
        db.execute("UPDATE otp_codes SET attempts = attempts + 1 WHERE id = ?", (row["id"],))
        db.commit()
        return jsonify({"ok": False, "error": "Incorrect code."}), 400

    student = db.execute("SELECT id FROM students WHERE email = ?", (email,)).fetchone()
    if student is None:
        return jsonify({"ok": False, "error": "We don't recognise that email."}), 404

    now = datetime.datetime.utcnow().isoformat()
    db.execute("UPDATE otp_codes SET consumed_at = ? WHERE id = ?", (now, row["id"]))
    db.execute(
        "UPDATE students SET password_hash = ?, last_seen_at = ? WHERE id = ?",
        (generate_password_hash(new_password), now, student["id"]),
    )
    db.commit()

    session["student_id"] = student["id"]
    session.permanent = True
    return jsonify({"ok": True, "redirect": next_url})


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("roi.home"))
