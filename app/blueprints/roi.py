import datetime
import time
from urllib.parse import quote

import requests
from flask import Blueprint, jsonify, render_template, request, session

from extensions import get_db

roi_bp = Blueprint("roi", __name__)

# ---------------------------------------------------------------------------
# FX (moved verbatim from the old monolithic app.py)
# ---------------------------------------------------------------------------
FX_ENDPOINT = "https://open.er-api.com/v6/latest/USD"
FX_TTL_SECONDS = 6 * 60 * 60  # refetch at most every 6 hours
FX_CURRENCIES = ("GBP", "CAD", "EUR", "PLN")

# Fallback rates used only if the live FX call has never succeeded (e.g. no
# network access). These are illustrative, not something to build a real
# quote on.
FX_FALLBACK = {"GBP": 2000, "CAD": 1050, "EUR": 1650, "PLN": 380}

_fx_cache = {"ts": 0, "data": None}


def fetch_live_fx():
    """Fetch NGN-per-unit rates for GBP/CAD/EUR/PLN from a free, keyless FX API.

    Cached in-memory for FX_TTL_SECONDS. Falls back to the last known-good
    result if the upstream call fails, and to FX_FALLBACK if there is no
    known-good result yet at all.
    """
    now = time.time()
    if _fx_cache["data"] and (now - _fx_cache["ts"] < FX_TTL_SECONDS):
        return _fx_cache["data"]

    try:
        resp = requests.get(FX_ENDPOINT, timeout=8)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("result") != "success":
            raise ValueError("unexpected FX API response")

        rates = payload["rates"]
        ngn_per_usd = rates["NGN"]
        ngn_rates = {}
        for code in FX_CURRENCIES:
            unit_rate = rates.get(code)
            if unit_rate:
                ngn_rates[code] = round(ngn_per_usd / unit_rate, 4)

        data = {
            "live": True,
            "asOf": payload.get("time_last_update_utc"),
            "rates": ngn_rates,
        }
        _fx_cache["ts"] = now
        _fx_cache["data"] = data
        return data
    except Exception as exc:  # noqa: BLE001 - any failure just falls back
        from flask import current_app

        current_app.logger.warning("Live FX fetch failed: %s", exc)
        if _fx_cache["data"]:
            return _fx_cache["data"]
        return {"live": False, "asOf": None, "rates": FX_FALLBACK}


# ---------------------------------------------------------------------------
# Google Form / HubSpot lead forwarding (moved verbatim)
# ---------------------------------------------------------------------------
import os  # noqa: E402

GOOGLE_FORM_ACTION_URL = os.environ.get("GOOGLE_FORM_ACTION_URL", "").strip()
GOOGLE_FORM_ENTRIES = {
    "email": os.environ.get("GOOGLE_FORM_ENTRY_EMAIL", "").strip(),
    "qualification": os.environ.get("GOOGLE_FORM_ENTRY_QUALIFICATION", "").strip(),
    "grade": os.environ.get("GOOGLE_FORM_ENTRY_GRADE", "").strip(),
    "profession": os.environ.get("GOOGLE_FORM_ENTRY_PROFESSION", "").strip(),
    "destination": os.environ.get("GOOGLE_FORM_ENTRY_DESTINATION", "").strip(),
    "city": os.environ.get("GOOGLE_FORM_ENTRY_CITY", "").strip(),
}

HUBSPOT_ACCESS_TOKEN = os.environ.get("HUBSPOT_ACCESS_TOKEN", "").strip()
HUBSPOT_API_BASE = "https://api.hubapi.com"


def forward_to_google_form(row):
    """Best-effort forward of a captured lead to a Google Form.

    Returns True if a forward was actually attempted and succeeded, False
    otherwise. Never raises — a broken/unconfigured Form must not block a
    lead from being saved locally.
    """
    if not GOOGLE_FORM_ACTION_URL:
        return False

    form_payload = {}
    for field, entry_id in GOOGLE_FORM_ENTRIES.items():
        if entry_id:
            form_payload[entry_id] = row.get(field, "")

    if not form_payload:
        return False

    try:
        resp = requests.post(GOOGLE_FORM_ACTION_URL, data=form_payload, timeout=6)
        return resp.status_code < 400
    except Exception:  # noqa: BLE001
        from flask import current_app

        current_app.logger.warning("Google Form forward failed", exc_info=True)
        return False


def _hubspot_headers():
    return {
        "Authorization": f"Bearer {HUBSPOT_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }


def _upsert_hubspot_contact(email, properties):
    """Create-or-update a HubSpot contact matched by email. Returns the
    contact's HubSpot ID on success, None on any failure (including unknown
    custom property names, which HubSpot rejects for the whole request)."""
    from flask import current_app

    try:
        resp = requests.post(
            f"{HUBSPOT_API_BASE}/crm/v3/objects/contacts/batch/upsert",
            headers=_hubspot_headers(),
            json={"inputs": [{"idProperty": "email", "id": email, "properties": properties}]},
            timeout=8,
        )
        if resp.status_code >= 400:
            current_app.logger.warning("HubSpot contact upsert failed (%s): %s", resp.status_code, resp.text[:500])
            return None
        results = (resp.json() or {}).get("results") or []
        return results[0]["id"] if results else None
    except Exception as exc:  # noqa: BLE001
        current_app.logger.warning("HubSpot contact upsert error: %s", exc)
        return None


def _attach_hubspot_note(contact_id, row):
    """Attach a plain-text Note with the full lead detail to a contact. Works
    regardless of whether any custom properties exist in the HubSpot account,
    so counsellors always see the full picture even with zero HubSpot-side
    setup beyond the access token."""
    from flask import current_app

    note_body = "<br>".join([
        f"New {row.get('source') or 'Global Education ROI'} lead",
        f"Qualification: {row.get('qualification') or '—'} | Grade: {row.get('grade') or '—'}",
        f"Profession: {row.get('profession') or '—'} | City: {row.get('city') or '—'}",
        f"Destination: {row.get('destination') or '—'}",
        f"Salary: ₦{row.get('salary') or '—'}/mo | ROI Score: {row.get('score') if row.get('score') is not None else '—'}/100 | Ratio: {row.get('ratio') if row.get('ratio') is not None else '—'}x",
    ])
    try:
        resp = requests.post(
            f"{HUBSPOT_API_BASE}/engagements/v1/engagements",
            headers=_hubspot_headers(),
            json={
                "engagement": {"active": True, "type": "NOTE"},
                "associations": {"contactIds": [int(contact_id)]},
                "metadata": {"body": note_body},
            },
            timeout=8,
        )
        if resp.status_code >= 400:
            current_app.logger.warning("HubSpot note attach failed (%s): %s", resp.status_code, resp.text[:500])
    except Exception as exc:  # noqa: BLE001
        current_app.logger.warning("HubSpot note attach error: %s", exc)


def forward_to_hubspot(row):
    """Best-effort push of a captured lead into HubSpot CRM: upserts a
    Contact by email, then attaches a readable Note with the full detail.

    Never raises -- a broken or unconfigured HubSpot integration must not
    block a lead from being saved locally.
    """
    if not HUBSPOT_ACCESS_TOKEN:
        return False

    full_properties = {
        "email": row["email"],
        "tgm_qualification": row.get("qualification", ""),
        "tgm_grade": row.get("grade", ""),
        "tgm_profession": row.get("profession", ""),
        "tgm_destination": row.get("destination", ""),
        "tgm_city": row.get("city", ""),
        "tgm_salary_ngn": str(row.get("salary", "")),
        "tgm_roi_score": str(row.get("score", "")),
        "tgm_roi_ratio": str(row.get("ratio", "")),
        "tgm_lead_source": row.get("source", ""),
    }

    contact_id = _upsert_hubspot_contact(row["email"], full_properties)
    if contact_id is None:
        contact_id = _upsert_hubspot_contact(row["email"], {"email": row["email"]})

    if contact_id is None:
        return False

    _attach_hubspot_note(contact_id, row)
    return True


# ---------------------------------------------------------------------------
# Destination label -> short id, for the student_profiles/chat/community keys.
# The ROI calculator (static/js/main.js DATA.destinations) sends the human
# label (e.g. "United Kingdom") as `destination` in the /api/leads payload, to
# keep the existing `leads` table/admin view showing readable text -- this map
# is only used when deriving the *student's* profile/room, never applied back
# onto the `leads` row itself.
# ---------------------------------------------------------------------------
DESTINATION_LABEL_TO_ID = {
    "united kingdom": "uk",
    "canada": "canada",
    "germany": "germany",
    "poland": "poland",
    "ireland": "ireland",
}


def normalize_destination(label):
    return DESTINATION_LABEL_TO_ID.get((label or "").strip().lower())


def _upsert_student_and_profile(db, row, lead_id):
    """Upserts `students` (by email) and `student_profiles` (latest ROI
    snapshot). Returns (student_id, is_new_student)."""
    now = datetime.datetime.utcnow().isoformat()
    existing = db.execute("SELECT id FROM students WHERE email = ?", (row["email"],)).fetchone()
    is_new = existing is None

    if is_new:
        cur = db.execute(
            "INSERT INTO students (email, created_at, last_seen_at) VALUES (?, ?, ?)",
            (row["email"], now, now),
        )
        student_id = cur.lastrowid
    else:
        student_id = existing["id"]
        db.execute("UPDATE students SET last_seen_at = ? WHERE id = ?", (now, student_id))

    destination_id = normalize_destination(row.get("destination"))
    db.execute(
        """
        INSERT INTO student_profiles
            (student_id, lead_id, qualification, grade, profession, destination, city, salary, score, ratio, updated_at)
        VALUES
            (:student_id, :lead_id, :qualification, :grade, :profession, :destination, :city, :salary, :score, :ratio, :updated_at)
        ON CONFLICT(student_id) DO UPDATE SET
            lead_id=excluded.lead_id, qualification=excluded.qualification, grade=excluded.grade,
            profession=excluded.profession, destination=excluded.destination, city=excluded.city,
            salary=excluded.salary, score=excluded.score, ratio=excluded.ratio, updated_at=excluded.updated_at
        """,
        {
            "student_id": student_id,
            "lead_id": lead_id,
            "qualification": row.get("qualification"),
            "grade": row.get("grade"),
            "profession": row.get("profession"),
            "destination": destination_id,
            "city": row.get("city"),
            "salary": row.get("salary"),
            "score": row.get("score"),
            "ratio": row.get("ratio"),
            "updated_at": now,
        },
    )
    return student_id, is_new


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@roi_bp.route("/")
def home():
    return render_template("home.html")


@roi_bp.route("/calculator")
def index():
    return render_template("index.html")


@roi_bp.route("/api/fx")
def api_fx():
    return jsonify(fetch_live_fx())


@roi_bp.route("/api/leads", methods=["POST"])
def api_leads():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip()
    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "A valid email address is required."}), 400

    row = {
        "created_at": datetime.datetime.utcnow().isoformat(),
        "email": email,
        "qualification": (payload.get("qualification") or "")[:120],
        "grade": (payload.get("grade") or "")[:120],
        "profession": (payload.get("profession") or "")[:120],
        "destination": (payload.get("destination") or "")[:120],
        "city": (payload.get("city") or "")[:120],
        "salary": payload.get("salary") or 0,
        "score": payload.get("score"),
        "ratio": payload.get("ratio"),
        "source": (payload.get("source") or "Global Education ROI")[:120],
    }

    forwarded_google_form = forward_to_google_form(row)
    forwarded_hubspot = forward_to_hubspot(row)

    db = get_db()
    cur = db.execute(
        """
        INSERT INTO leads
            (created_at, email, qualification, grade, profession, destination, city,
             salary, score, ratio, source, forwarded_to_google_form, forwarded_to_hubspot)
        VALUES
            (:created_at, :email, :qualification, :grade, :profession, :destination, :city,
             :salary, :score, :ratio, :source, :forwarded_google_form, :forwarded_hubspot)
        """,
        dict(row, forwarded_google_form=int(forwarded_google_form), forwarded_hubspot=int(forwarded_hubspot)),
    )
    lead_id = cur.lastrowid

    student_id, is_new_student = _upsert_student_and_profile(db, row, lead_id)
    db.commit()

    if is_new_student:
        # First-time visitor: trust the email enough for a frictionless first
        # session (they just typed it into a form they're about to leave), and
        # send them straight into chat. See PLAN.md for the accepted tradeoff.
        session["student_id"] = student_id
        session.permanent = True
        redirect_to = "/chat"
    else:
        # Known email returning: don't silently log in from an unauthenticated
        # POST (anyone could type someone else's email otherwise) -- send them
        # through the OTP challenge instead.
        redirect_to = f"/login?email={quote(email)}&next=/chat"

    return jsonify({
        "ok": True,
        "id": lead_id,
        "student_new": is_new_student,
        "redirect": redirect_to,
        "forwarded_to_google_form": forwarded_google_form,
        "forwarded_to_hubspot": forwarded_hubspot,
    })
