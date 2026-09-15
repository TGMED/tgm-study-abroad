"""Inbound/outbound bridge between Meta's WhatsApp Cloud API and the same
Amara logic the web chat uses (services/prompts.py, services/gemini.py).

WhatsApp is deliberately kept to as few messages as possible -- Meta bills
per message, the web chat doesn't. A sender's very first WhatsApp message
gets a real Amara reply (saved to their chat history, so the web chat isn't
empty when they arrive) plus a one-time login link into it; that reply is
the only thing ever sent back over WhatsApp -- everything after is just a
short reminder pointing back at the same link, not a second AI turn (see
_handle_message). Meta's own per-message fee for that first exchange is the
one WhatsApp cost this doesn't (and can't) eliminate.

A WhatsApp sender has no email, so they get their own students row keyed by
`phone` (their WhatsApp ID) instead of going through /join or the ROI
calculator -- see _get_or_create_student. Everything else (chat_messages,
chat_mode, human_handoff_queue, the admin inbox) is the same machinery the
web chat already uses; a counsellor can take over a WhatsApp conversation
from /admin/inbox exactly like a web one (see admin.admin_inbox_reply for
the half of that round-trip that pushes the reply back out over WhatsApp).
"""
import datetime

from flask import Blueprint, current_app, jsonify, redirect, request, session, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from extensions import get_db
from blueprints.chat import _flag_for_human, _load_history, _load_profile, _save_message
from services.gemini import GeminiError, call_gemini
from services.prompts import build_chat_system_prompt, strip_needs_human_marker
from services.whatsapp import (
    WHATSAPP_VERIFY_TOKEN,
    WhatsAppSendError,
    extract_messages,
    mark_read,
    send_text_message,
    verify_signature,
)

whatsapp_bp = Blueprint("whatsapp", __name__)

_LINK_SALT = "wa-continue"
_LINK_MAX_AGE = 60 * 60  # 1 hour -- generous for someone to actually tap it, short
                         # enough that a leaked/old link isn't useful for long. Not
                         # single-use: this logs into the WhatsApp sender's own
                         # account (their own phone's conversation), not a payment
                         # or account-recovery flow, so a low-stakes time-boxed
                         # token is enough rather than needing single-use tracking.


def _wa_continue_link(student_id):
    token = URLSafeTimedSerializer(current_app.secret_key, salt=_LINK_SALT).dumps({"student_id": student_id})
    return url_for("whatsapp.wa_continue", token=token, _external=True)


@whatsapp_bp.route("/wa/<token>")
def wa_continue(token):
    try:
        data = URLSafeTimedSerializer(current_app.secret_key, salt=_LINK_SALT).loads(token, max_age=_LINK_MAX_AGE)
    except (BadSignature, SignatureExpired):
        # Expired/invalid isn't a dead end -- messaging WhatsApp again (see
        # _handle_message's reminder branch) immediately hands back a fresh
        # link, so there's no need for a dedicated error page here.
        return redirect(url_for("roi.home"))
    db = get_db()
    row = db.execute("SELECT id FROM students WHERE id = ?", (data.get("student_id"),)).fetchone()
    if not row:
        return redirect(url_for("roi.home"))
    session["student_id"] = row["id"]
    session.permanent = True
    return redirect(url_for("chat.chat_page"))


def _get_or_create_student(db, wa_id, profile_name):
    row = db.execute("SELECT id FROM students WHERE phone = ?", (wa_id,)).fetchone()
    if row:
        return row["id"]
    now = datetime.datetime.utcnow().isoformat()
    # No email exists for a WhatsApp-only sender -- a clearly-synthetic
    # placeholder satisfies the students.email NOT NULL UNIQUE constraint
    # without claiming to be a real, reachable address (mirrors the old
    # guest-account pattern, but legitimate here since there's no web form
    # for this person to type a real email into).
    placeholder_email = f"wa-{wa_id}@whatsapp.local"
    cur = db.execute(
        """
        INSERT INTO students (email, phone, display_name, created_at, last_seen_at, onboarded)
        VALUES (?, ?, ?, ?, ?, 1)
        """,
        (placeholder_email, wa_id, profile_name or wa_id, now, now),
    )
    db.commit()
    return cur.lastrowid


@whatsapp_bp.route("/webhook/whatsapp", methods=["GET"])
def verify():
    """Meta's one-time webhook verification handshake."""
    if (
        request.args.get("hub.mode") == "subscribe"
        and WHATSAPP_VERIFY_TOKEN
        and request.args.get("hub.verify_token") == WHATSAPP_VERIFY_TOKEN
    ):
        return request.args.get("hub.challenge", ""), 200
    return "Forbidden", 403


@whatsapp_bp.route("/webhook/whatsapp", methods=["POST"])
def incoming():
    if not verify_signature(request.get_data(), request.headers.get("X-Hub-Signature-256", "")):
        return jsonify({"ok": False}), 403

    payload = request.get_json(silent=True) or {}
    db = get_db()

    for msg in extract_messages(payload):
        if not msg["wamid"] or not msg["wa_id"] or not msg["text"].strip():
            continue
        # Meta retries a webhook delivery it didn't get a fast/clean 200 for
        # -- e.g. if a slow Gemini call below is still running when Meta's
        # own timeout fires. Skip anything already processed instead of
        # replying twice; the original attempt keeps running regardless of
        # whether Meta gave up waiting on this particular HTTP response.
        seen = db.execute("SELECT 1 FROM whatsapp_events WHERE wamid = ?", (msg["wamid"],)).fetchone()
        if seen:
            continue
        db.execute(
            "INSERT INTO whatsapp_events (wamid, created_at) VALUES (?, ?)",
            (msg["wamid"], datetime.datetime.utcnow().isoformat()),
        )
        db.commit()

        mark_read(msg["wamid"])
        student_id = _get_or_create_student(db, msg["wa_id"], msg["profile_name"])
        _handle_message(db, student_id, msg["wa_id"], msg["text"])

    return jsonify({"ok": True})


def _handle_message(db, student_id, wa_id, text):
    student = db.execute("SELECT chat_mode FROM students WHERE id = ?", (student_id,)).fetchone()
    chat_mode = student["chat_mode"] if student else "ai"
    is_first_message = db.execute(
        "SELECT 1 FROM chat_messages WHERE student_id = ?", (student_id,)
    ).fetchone() is None

    _save_message(db, student_id, "user", text)

    if chat_mode == "human":
        # A counsellor already has this conversation (from the admin inbox,
        # possibly taken over after being flagged from the web) -- they see
        # this message there and reply from there; admin.admin_inbox_reply
        # pushes it back out over WhatsApp. Amara stays silent either way.
        return

    link = _wa_continue_link(student_id)

    if not is_first_message:
        # They're still messaging WhatsApp instead of continuing on the
        # link already sent -- resend it rather than running another full
        # AI turn (and paying for another Meta message) here.
        try:
            send_text_message(wa_id, f"Let's continue our conversation here so I can help you properly: {link}")
        except WhatsAppSendError as exc:
            print(f"WhatsApp: link reminder send failed for student {student_id}: {exc}")
        return

    # First-ever message from this number: let Amara actually answer it, so
    # the web chat has a real reply waiting rather than being empty when
    # they arrive -- but that answer is only ever saved to their history,
    # never sent back over WhatsApp. WhatsApp only ever gets the link.
    profile = _load_profile(db, student_id)
    history = _load_history(db, student_id)
    # Gemini's API only accepts role "user"/"model" -- see chat.api_chat for
    # the same mapping applied to the web chat's history.
    gemini_history = [
        {"role": "model" if h["role"] in ("model", "counsellor") else "user", "content": h["content"]}
        for h in history if h["role"] != "system"
    ]

    system_prompt = build_chat_system_prompt(profile, opening=False)
    try:
        reply = call_gemini(system_prompt, gemini_history, timeout=45)
        reply, needs_human = strip_needs_human_marker(reply)
        _save_message(db, student_id, "model", reply)
        if needs_human:
            _flag_for_human(db, student_id)
    except GeminiError as exc:
        # The greeting/link below still goes out either way -- worst case
        # they land on a web chat with just their own message waiting and
        # can type again there, rather than being stuck on WhatsApp.
        print(f"WhatsApp: Gemini call failed for student {student_id}: {exc}")

    try:
        send_text_message(
            wa_id,
            "Hi, I'm Amara from TGM Education 👋 I've got your message and I'm ready to help — "
            f"let's continue here: {link}",
        )
    except WhatsAppSendError as exc:
        print(f"WhatsApp: greeting send failed for student {student_id}: {exc}")
