import datetime
import hashlib
import secrets

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from extensions import get_db
from services.emailer import EmailSendError, send_otp_email

auth_bp = Blueprint("auth", __name__)

OTP_TTL_MINUTES = 10
MAX_VERIFY_ATTEMPTS = 5


def _hash_code(code):
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


@auth_bp.route("/login")
def login():
    email = (request.args.get("email") or "").strip()
    next_url = request.args.get("next") or "/chat"
    return render_template("login.html", email=email, next_url=next_url)


def _safe_next(raw):
    """Only allow same-site relative paths as a post-join redirect target."""
    if raw and raw.startswith("/") and not raw.startswith("//"):
        return raw
    return None


@auth_bp.route("/join", methods=["GET", "POST"])
def join():
    next_url = _safe_next(request.values.get("next")) or url_for("social.dashboard")

    # Already signed in? Skip the name step.
    if session.get("student_id"):
        return redirect(next_url)

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()[:40]
        if len(name) < 2:
            return render_template(
                "join.html", next_url=next_url, error="Please enter your name (at least 2 characters)."
            )

        db = get_db()
        # Guests get a synthetic, unique email so the existing schema
        # (email NOT NULL UNIQUE) is satisfied without collecting one.
        now = datetime.datetime.utcnow().isoformat()
        guest_email = f"guest-{secrets.token_hex(8)}@guest.local"
        cur = db.execute(
            "INSERT INTO students (email, display_name, created_at, last_seen_at) VALUES (?, ?, ?, ?)",
            (guest_email, name, now, now),
        )
        db.commit()

        session["student_id"] = cur.lastrowid
        session.permanent = True
        return redirect(next_url)

    return render_template("join.html", next_url=next_url, error=None)


@auth_bp.route("/api/auth/request-otp", methods=["POST"])
def request_otp():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip()
    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "A valid email address is required."}), 400

    db = get_db()
    student = db.execute("SELECT id FROM students WHERE email = ?", (email,)).fetchone()
    if student is None:
        return jsonify({"ok": False, "error": "We don't recognise that email yet — complete the ROI calculator first."}), 404

    code = f"{secrets.randbelow(900000) + 100000}"
    now = datetime.datetime.utcnow()
    expires_at = (now + datetime.timedelta(minutes=OTP_TTL_MINUTES)).isoformat()

    db.execute(
        "INSERT INTO otp_codes (email, code_hash, purpose, expires_at, created_at) VALUES (?, ?, 'login', ?, ?)",
        (email, _hash_code(code), expires_at, now.isoformat()),
    )
    db.commit()

    try:
        send_otp_email(email, code)
    except EmailSendError as exc:
        return jsonify({"ok": False, "error": f"Could not send the login code: {exc}"}), 502

    return jsonify({"ok": True})


@auth_bp.route("/api/auth/verify-otp", methods=["POST"])
def verify_otp():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip()
    code = (payload.get("code") or "").strip()
    next_url = payload.get("next") or "/chat"
    if not email or not code:
        return jsonify({"ok": False, "error": "Email and code are required."}), 400

    db = get_db()
    row = db.execute(
        """
        SELECT id, code_hash, expires_at, consumed_at, attempts
        FROM otp_codes
        WHERE email = ? AND purpose = 'login'
        ORDER BY id DESC LIMIT 1
        """,
        (email,),
    ).fetchone()

    if row is None or row["consumed_at"] is not None:
        return jsonify({"ok": False, "error": "No active login code — request a new one."}), 400

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
        return jsonify({"ok": False, "error": "We don't recognise that email yet."}), 404

    db.execute(
        "UPDATE otp_codes SET consumed_at = ? WHERE id = ?",
        (datetime.datetime.utcnow().isoformat(), row["id"]),
    )
    db.execute(
        "UPDATE students SET last_seen_at = ? WHERE id = ?",
        (datetime.datetime.utcnow().isoformat(), student["id"]),
    )
    db.commit()

    session["student_id"] = student["id"]
    session.permanent = True

    return jsonify({"ok": True, "redirect": next_url})


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("roi.home"))
