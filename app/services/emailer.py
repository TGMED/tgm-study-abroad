"""Sends OTP login codes via EmailJS's REST API (server-side).

Requires EMAILJS_SERVICE_ID / EMAILJS_OTP_TEMPLATE_ID / EMAILJS_PUBLIC_KEY /
EMAILJS_PRIVATE_KEY in .env. The Private Key is a *different* credential from
the public key already used client-side in Desktop/Counselor/app.js -- it must
be generated fresh in the EmailJS dashboard (Account > API Keys), with
"Allow API calls from non-browser applications" enabled, since generating the
OTP server-side (required -- SQLite has no client-writable RLS-equivalent) and
then emailing it via the public-key browser SDK would mean the browser has to
be handed the code first, which defeats the point of emailing it.

Until configured, falls back to printing the code to the console so local
development/testing isn't blocked on setting up EmailJS.
"""
import os

import requests

EMAILJS_SERVICE_ID = os.environ.get("EMAILJS_SERVICE_ID", "").strip()
EMAILJS_TEMPLATE_ID = os.environ.get("EMAILJS_OTP_TEMPLATE_ID", "").strip()
EMAILJS_PUBLIC_KEY = os.environ.get("EMAILJS_PUBLIC_KEY", "").strip()
EMAILJS_PRIVATE_KEY = os.environ.get("EMAILJS_PRIVATE_KEY", "").strip()
EMAILJS_SEND_URL = "https://api.emailjs.com/api/v1.0/email/send"


class EmailSendError(Exception):
    pass


def send_otp_email(email, code):
    """Returns True if actually emailed, False if it fell back to console
    logging (not configured yet). Raises EmailSendError on a real send failure
    once EmailJS *is* configured, so the caller can surface "try again"."""
    if not (EMAILJS_SERVICE_ID and EMAILJS_TEMPLATE_ID and EMAILJS_PUBLIC_KEY and EMAILJS_PRIVATE_KEY):
        print(
            "\n"
            "==================================================================\n"
            "  EmailJS is not configured (EMAILJS_SERVICE_ID / EMAILJS_OTP_TEMPLATE_ID /\n"
            "  EMAILJS_PUBLIC_KEY / EMAILJS_PRIVATE_KEY missing from .env) -- printing\n"
            "  the login code here instead of emailing it, for local testing only:\n"
            f"    {email} -> {code}\n"
            "==================================================================\n"
        )
        return False

    try:
        resp = requests.post(
            EMAILJS_SEND_URL,
            json={
                "service_id": EMAILJS_SERVICE_ID,
                "template_id": EMAILJS_TEMPLATE_ID,
                "user_id": EMAILJS_PUBLIC_KEY,
                "accessToken": EMAILJS_PRIVATE_KEY,
                "template_params": {"to_email": email, "otp_code": code},
            },
            timeout=10,
        )
        if resp.status_code >= 300:
            raise EmailSendError(f"EmailJS send failed ({resp.status_code}): {resp.text[:300]}")
        return True
    except requests.RequestException as exc:
        raise EmailSendError(f"Could not reach EmailJS: {exc}") from exc
