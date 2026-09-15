"""Server-side client for Meta's WhatsApp Cloud API (Graph API): sending
messages out, and verifying/parsing the inbound webhook.

Requires WHATSAPP_PHONE_NUMBER_ID / WHATSAPP_ACCESS_TOKEN (for sending) and
WHATSAPP_APP_SECRET / WHATSAPP_VERIFY_TOKEN (for the inbound webhook) in
.env. Sending falls back to printing to the console when not configured, so
local development isn't blocked on setting this up (same pattern as
services/emailer.py).
"""
import hashlib
import hmac
import os

import requests

GRAPH_API_VERSION = "v20.0"
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "").strip()
WHATSAPP_ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN", "").strip()
WHATSAPP_APP_SECRET = os.environ.get("WHATSAPP_APP_SECRET", "").strip()
WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "").strip()

_GRAPH_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages"


class WhatsAppSendError(Exception):
    pass


def is_configured():
    return bool(WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_ACCESS_TOKEN)


def send_text_message(to_wa_id, text):
    """to_wa_id: the recipient's WhatsApp ID (phone number, no leading '+'),
    exactly as Meta sent it in the inbound webhook's `messages[].from`.
    Returns True if actually sent, False if it fell back to console
    logging (not configured yet). Raises WhatsAppSendError on a real
    send failure once the Cloud API *is* configured."""
    if not is_configured():
        print(
            "\n"
            "==================================================================\n"
            "  WhatsApp Cloud API is not configured (WHATSAPP_PHONE_NUMBER_ID /\n"
            "  WHATSAPP_ACCESS_TOKEN missing from .env) -- printing instead of\n"
            "  sending, for local testing only:\n"
            f"    to: {to_wa_id}\n"
            f"    text: {text}\n"
            "==================================================================\n"
        )
        return False

    try:
        resp = requests.post(
            _GRAPH_URL,
            headers={"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"},
            json={
                "messaging_product": "whatsapp",
                "to": to_wa_id,
                "type": "text",
                "text": {"body": text},
            },
            timeout=15,
        )
        if resp.status_code >= 300:
            raise WhatsAppSendError(f"WhatsApp send failed ({resp.status_code}): {resp.text[:300]}")
        return True
    except requests.RequestException as exc:
        raise WhatsAppSendError(f"Could not reach the WhatsApp Cloud API: {exc}") from exc


def mark_read(wamid):
    """Best-effort read receipt -- never raises, since a missed read receipt
    shouldn't block or fail the actual conversation."""
    if not is_configured():
        return
    try:
        requests.post(
            _GRAPH_URL,
            headers={"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"},
            json={"messaging_product": "whatsapp", "status": "read", "message_id": wamid},
            timeout=10,
        )
    except requests.RequestException:
        pass


def verify_signature(raw_body, signature_header):
    """signature_header: the raw 'X-Hub-Signature-256' header value, e.g.
    'sha256=abcdef...'. Returns False (never raises) if WHATSAPP_APP_SECRET
    isn't configured, so an unconfigured dev setup fails closed -- the
    webhook route treats an unverified request as untrusted either way."""
    if not WHATSAPP_APP_SECRET or not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(WHATSAPP_APP_SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    got = signature_header.split("=", 1)[1]
    return hmac.compare_digest(expected, got)


def extract_messages(payload):
    """payload: the parsed JSON body of an inbound webhook POST. Returns a
    list of {"wamid", "wa_id", "profile_name", "text"} for every plain-text
    message in the payload -- non-text messages (image/audio/location/etc)
    and delivery-status callbacks are skipped for this first version."""
    out = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            contacts = {c.get("wa_id"): c.get("profile", {}).get("name") for c in value.get("contacts", [])}
            for msg in value.get("messages", []):
                if msg.get("type") != "text":
                    continue
                wa_id = msg.get("from")
                out.append({
                    "wamid": msg.get("id"),
                    "wa_id": wa_id,
                    "profile_name": contacts.get(wa_id),
                    "text": (msg.get("text") or {}).get("body", ""),
                })
    return out
