"""Sends transactional email via EmailJS's REST API (server-side): OTP login
codes, community reply notifications, and the weekly activity digest.

Requires EMAILJS_SERVICE_ID / EMAILJS_PUBLIC_KEY / EMAILJS_PRIVATE_KEY, plus
one template ID per email kind (EMAILJS_OTP_TEMPLATE_ID /
EMAILJS_REPLY_TEMPLATE_ID / EMAILJS_DIGEST_TEMPLATE_ID) in .env. The Private
Key is a *different* credential from the public key already used client-side
in Desktop/Counselor/app.js -- it must be generated fresh in the EmailJS
dashboard (Account > API Keys), with "Allow API calls from non-browser
applications" enabled.

Until a given template ID is configured, that email kind falls back to
printing to the console so local development/testing isn't blocked on
setting up EmailJS.
"""
import datetime
import os

import requests

EMAILJS_SERVICE_ID = os.environ.get("EMAILJS_SERVICE_ID", "").strip()
EMAILJS_OTP_TEMPLATE_ID = os.environ.get("EMAILJS_OTP_TEMPLATE_ID", "").strip()
EMAILJS_REPLY_TEMPLATE_ID = os.environ.get("EMAILJS_REPLY_TEMPLATE_ID", "").strip()
EMAILJS_DIGEST_TEMPLATE_ID = os.environ.get("EMAILJS_DIGEST_TEMPLATE_ID", "").strip()
EMAILJS_PUBLIC_KEY = os.environ.get("EMAILJS_PUBLIC_KEY", "").strip()
EMAILJS_PRIVATE_KEY = os.environ.get("EMAILJS_PRIVATE_KEY", "").strip()
EMAILJS_SEND_URL = "https://api.emailjs.com/api/v1.0/email/send"


class EmailSendError(Exception):
    pass


def _send(template_id, to_email, template_params, console_label):
    """Returns True if actually emailed, False if it fell back to console
    logging (not configured yet). Raises EmailSendError on a real send
    failure once EmailJS *is* configured, so the caller can decide how to
    handle it (surface "try again" for a blocking send like OTP, or just log
    and move on to the next recipient for a batch send like the digest)."""
    if not (EMAILJS_SERVICE_ID and template_id and EMAILJS_PUBLIC_KEY and EMAILJS_PRIVATE_KEY):
        print(
            "\n"
            "==================================================================\n"
            f"  EmailJS is not configured for {console_label} (EMAILJS_SERVICE_ID /\n"
            "  the template ID / EMAILJS_PUBLIC_KEY / EMAILJS_PRIVATE_KEY missing\n"
            "  from .env) -- printing instead of emailing, for local testing only:\n"
            f"    to: {to_email}\n"
            f"    params: {template_params}\n"
            "==================================================================\n"
        )
        return False

    try:
        resp = requests.post(
            EMAILJS_SEND_URL,
            json={
                "service_id": EMAILJS_SERVICE_ID,
                "template_id": template_id,
                "user_id": EMAILJS_PUBLIC_KEY,
                "accessToken": EMAILJS_PRIVATE_KEY,
                # Every template's own "To Email" field must be set to
                # {{email}} -- EmailJS resolves the actual recipient from
                # that field, not from a separate API parameter.
                "template_params": dict(template_params, email=to_email),
            },
            timeout=10,
        )
        if resp.status_code >= 300:
            raise EmailSendError(f"EmailJS send failed ({resp.status_code}): {resp.text[:300]}")
        return True
    except requests.RequestException as exc:
        raise EmailSendError(f"Could not reach EmailJS: {exc}") from exc


def send_otp_email(email, code, expires_at):
    """expires_at: ISO timestamp (UTC) the code stops working -- formatted
    here into the {{time}} the OTP template displays alongside {{passcode}}."""
    expires_dt = datetime.datetime.fromisoformat(expires_at)
    time_display = expires_dt.strftime("%I:%M %p UTC")
    return _send(EMAILJS_OTP_TEMPLATE_ID, email, {"passcode": code, "time": time_display}, "OTP login codes")


def send_reply_notification_email(email, params):
    """params: to_name, replier_name, room_label, post_excerpt, reply_excerpt, post_url."""
    return _send(EMAILJS_REPLY_TEMPLATE_ID, email, params, "reply notifications")


def send_digest_email(email, params):
    """params: to_name, week_range, highlights_text, community_url."""
    return _send(EMAILJS_DIGEST_TEMPLATE_ID, email, params, "the weekly digest")
