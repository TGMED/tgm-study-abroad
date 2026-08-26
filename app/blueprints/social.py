"""Social layer: onboarding, member profiles (study/work history + avatar),
direct messaging, people/destination search, the communities index, room
membership, and the (coming-soon) referral section.

Two audiences share one experience here: people already abroad and people
planning to go. Everything is name/guest-friendly (no email required) and
degrades gracefully.
"""
import datetime
import json
import os

from flask import (
    Blueprint,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)

from extensions import get_db, login_required
from services.prompts import COMMUNITY_ROOMS, COMMUNITY_ROOM_META

social_bp = Blueprint("social", __name__)

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "uploads")
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_AVATAR_BYTES = 5 * 1024 * 1024


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now():
    return datetime.datetime.utcnow().isoformat()


def _load_json(raw):
    try:
        val = json.loads(raw) if raw else []
        return val if isinstance(val, list) else []
    except (ValueError, TypeError):
        return []


def current_student(db=None):
    sid = session.get("student_id")
    if not sid:
        return None
    db = db or get_db()
    return db.execute("SELECT * FROM students WHERE id = ?", (sid,)).fetchone()


def profile_dict(row):
    if not row:
        return None
    name = row["display_name"] or (row["email"].split("@")[0] if row["email"] else "Member")
    initials = "".join(w[0] for w in name.split()[:2]).upper() or "M"
    keys = row.keys()

    def g(k, default=None):
        return row[k] if k in keys else default

    return {
        "id": row["id"],
        "name": name,
        "initials": initials,
        "user_type": g("user_type") or "aspiring",
        "location": g("location") or "",
        "destination": g("destination") or "",
        "headline": g("headline") or "",
        "bio": g("bio") or "",
        "has_avatar": bool(g("avatar_path")),
        "study_history": _load_json(g("study_history")),
        "work_history": _load_json(g("work_history")),
        "onboarded": bool(g("onboarded")),
    }


def _rooms():
    return [
        {"key": k, **COMMUNITY_ROOM_META.get(k, {"label": k.title(), "code": k[:2].upper(), "blurb": ""})}
        for k in COMMUNITY_ROOMS
    ]


# Inject shared template context (current user + nav data) into every page.
@social_bp.app_context_processor
def _inject():
    me = None
    if session.get("student_id"):
        me = profile_dict(current_student())
    return {"me": me, "nav_rooms": _rooms()}


# Gate: signed-in but not-yet-onboarded users get routed to onboarding.
@social_bp.before_request
def _require_onboarding():
    exempt = {"social.onboarding", "social.avatar", "static"}
    if request.endpoint in exempt:
        return None
    if not session.get("student_id"):
        return None  # login_required on the view handles anon users
    row = current_student()
    if row and not (row["onboarded"] if "onboarded" in row.keys() else 0):
        return redirect(url_for("social.onboarding"))
    return None


# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------
@social_bp.route("/onboarding", methods=["GET", "POST"])
@login_required
def onboarding():
    db = get_db()
    row = current_student(db)
    if row is None:
        session.clear()
        return redirect(url_for("auth.join"))

    if row["onboarded"] if "onboarded" in row.keys() else 0:
        return redirect(url_for("social.communities"))

    if request.method == "POST":
        user_type = request.form.get("user_type")
        if user_type not in ("abroad", "aspiring"):
            user_type = "aspiring"
        location = (request.form.get("location") or "").strip()[:80]
        destination = (request.form.get("destination") or "").strip()[:80]
        headline = (request.form.get("headline") or "").strip()[:120]

        avatar_path = _save_avatar(row["id"], request.files.get("avatar"))
        error = None
        if not avatar_path:
            error = "Please add a profile picture — it helps members connect with you."
        if error:
            return render_template(
                "onboarding.html", error=error, form=request.form, rooms=_rooms()
            )

        db.execute(
            """UPDATE students SET user_type = ?, location = ?, destination = ?,
               headline = ?, avatar_path = ?, onboarded = 1 WHERE id = ?""",
            (user_type, location, destination, headline, avatar_path, row["id"]),
        )
        # Auto-join the community that matches their destination, if any.
        for rm in _rooms():
            if rm["label"].lower() in destination.lower() or rm["key"] in destination.lower():
                db.execute(
                    "INSERT OR IGNORE INTO room_members (student_id, room, joined_at) VALUES (?, ?, ?)",
                    (row["id"], rm["key"], _now()),
                )
                break
        db.commit()
        return redirect(url_for("social.dashboard"))

    return render_template("onboarding.html", error=None, form={}, rooms=_rooms())


def _save_avatar(student_id, file_storage):
    if not file_storage or not file_storage.filename:
        return None
    ext = os.path.splitext(file_storage.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return None
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    fname = f"avatar_{student_id}{ext}"
    path = os.path.join(UPLOAD_DIR, fname)
    file_storage.save(path)
    if os.path.getsize(path) > MAX_AVATAR_BYTES:
        os.remove(path)
        return None
    return fname


@social_bp.route("/media/avatar/<int:user_id>")
def avatar(user_id):
    db = get_db()
    row = db.execute("SELECT avatar_path FROM students WHERE id = ?", (user_id,)).fetchone()
    if not row or not row["avatar_path"]:
        abort(404)
    return send_from_directory(UPLOAD_DIR, row["avatar_path"])


# ---------------------------------------------------------------------------
# Dashboard — the member's home / overview, everything linked out
# ---------------------------------------------------------------------------
def _ago(iso):
    try:
        t = datetime.datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return ""
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
    if d < 7:
        return f"{d}d ago"
    return t.strftime("%d %b")


def _inits(name):
    parts = [w for w in (name or "").split() if w]
    return ("".join(w[0] for w in parts[:2]).upper()) or "M"


@social_bp.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    sid = session["student_id"]
    me_row = current_student(db)
    prof = profile_dict(me_row)

    joined = db.execute(
        "SELECT room FROM room_members WHERE student_id = ? ORDER BY joined_at", (sid,)
    ).fetchall()
    joined_keys = [r["room"] for r in joined]
    joined_rooms = [
        {"key": k, **COMMUNITY_ROOM_META.get(k, {"label": k.title(), "code": k[:2].upper(), "blurb": ""})}
        for k in joined_keys
    ]

    my_posts = db.execute(
        "SELECT COUNT(*) AS c FROM community_posts WHERE student_id = ? AND is_hidden = 0", (sid,)
    ).fetchone()["c"]
    convo_count = db.execute(
        """SELECT COUNT(DISTINCT other_id) AS c FROM (
             SELECT CASE WHEN sender_id = ? THEN recipient_id ELSE sender_id END AS other_id
             FROM direct_messages WHERE sender_id = ? OR recipient_id = ?)""",
        (sid, sid, sid),
    ).fetchone()["c"]
    people_count = db.execute(
        "SELECT COUNT(*) AS c FROM students WHERE onboarded = 1 AND id != ?", (sid,)
    ).fetchone()["c"]
    stats = {"communities": len(joined_rooms), "posts": my_posts, "chats": convo_count, "people": people_count}

    # Questions waiting on you — recent question posts from other members.
    q_rows = db.execute(
        """SELECT p.id, p.room, p.content, p.student_id, p.created_at,
                  s.avatar_path AS av, s.user_type AS ut, s.location AS loc, s.destination AS dest, s.display_name AS dn
           FROM community_posts p LEFT JOIN students s ON s.id = p.student_id
           WHERE p.parent_id IS NULL AND p.is_hidden = 0 AND p.is_ai = 0
                 AND p.content LIKE '%?%' AND (p.student_id IS NULL OR p.student_id != ?)
           ORDER BY p.id DESC LIMIT 8""",
        (sid,),
    ).fetchall()
    questions = []
    for r in q_rows[:3]:
        name = r["dn"] or "Member"
        ctx = (f"moving to {r['dest']}" if (r["ut"] != "abroad" and r["dest"]) else
               (f"in {r['loc']}" if r["loc"] else "newcomer"))
        questions.append({
            "id": r["id"], "room": r["room"], "author": name, "initials": _inits(name),
            "author_id": r["student_id"], "has_avatar": bool(r["av"]), "context": ctx, "body": r["content"],
        })
    questions_total = len(q_rows)

    # Activity feed — recent posts across communities.
    f_rows = db.execute(
        """SELECT p.id, p.room, p.content, p.student_id, p.created_at, p.author_label,
                  s.avatar_path AS av, s.user_type AS ut,
                  (SELECT COUNT(*) FROM community_posts c WHERE c.parent_id = p.id AND c.is_hidden = 0) AS replies
           FROM community_posts p LEFT JOIN students s ON s.id = p.student_id
           WHERE p.parent_id IS NULL AND p.is_hidden = 0 AND p.is_ai = 0
           ORDER BY p.id DESC LIMIT 6""",
    ).fetchall()
    feed = [{
        "id": r["id"], "room": r["room"],
        "room_label": COMMUNITY_ROOM_META.get(r["room"], {}).get("label", r["room"].title()),
        "author": r["author_label"], "author_id": r["student_id"], "initials": _inits(r["author_label"]),
        "has_avatar": bool(r["av"]), "ago": _ago(r["created_at"]), "body": r["content"],
        "replies": r["replies"], "tag": "Arrived" if r["ut"] == "abroad" else "Asking",
    } for r in f_rows]

    # People to meet — prioritise members tied to my destination.
    dest = me_row["destination"] or ""
    sug_rows = db.execute(
        """SELECT * FROM students WHERE onboarded = 1 AND id != ?
           ORDER BY (CASE WHEN destination LIKE ? OR location LIKE ? THEN 0 ELSE 1 END), id DESC LIMIT 4""",
        (sid, f"%{dest}%", f"%{dest}%"),
    ).fetchall()
    suggestions = [profile_dict(r) for r in sug_rows]

    # Communities for you — rooms not yet joined.
    sug_comms = []
    for rm in _rooms():
        if rm["key"] in joined_keys:
            continue
        members = db.execute("SELECT COUNT(*) AS c FROM room_members WHERE room = ?", (rm["key"],)).fetchone()["c"]
        posts = db.execute("SELECT COUNT(*) AS c FROM community_posts WHERE room = ? AND is_hidden = 0", (rm["key"],)).fetchone()["c"]
        sug_comms.append({**rm, "members": members, "posts": posts})
    sug_comms = sug_comms[:3]

    # Two steps left — only the incomplete profile steps.
    steps = [
        {"label": "Add a profile photo", "done": bool(me_row["avatar_path"]), "href": url_for("social.settings")},
        {"label": "Write a headline", "done": bool(prof["headline"]), "href": url_for("social.settings")},
        {"label": "Add your study history", "done": bool(prof["study_history"]), "href": url_for("social.settings")},
        {"label": "Add your work history", "done": bool(prof["work_history"]), "href": url_for("social.settings")},
        {"label": "Join your first community", "done": len(joined_rooms) > 0, "href": url_for("social.communities")},
    ]
    remaining = [s for s in steps if not s["done"]]
    completeness = int((len(steps) - len(remaining)) / len(steps) * 100)

    return render_template(
        "dashboard.html", prof=prof, stats=stats, joined_rooms=joined_rooms,
        questions=questions, questions_total=questions_total, feed=feed,
        suggestions=suggestions, sug_comms=sug_comms,
        remaining=remaining[:3], completeness=completeness,
    )


# ---------------------------------------------------------------------------
# Communities index + membership
# ---------------------------------------------------------------------------
@social_bp.route("/community")
@login_required
def communities():
    db = get_db()
    sid = session["student_id"]
    joined = {r["room"] for r in db.execute(
        "SELECT room FROM room_members WHERE student_id = ?", (sid,)
    ).fetchall()}
    rooms = []
    for rm in _rooms():
        counts = db.execute(
            "SELECT COUNT(*) AS c FROM community_posts WHERE room = ? AND is_hidden = 0",
            (rm["key"],),
        ).fetchone()["c"]
        members = db.execute(
            "SELECT COUNT(*) AS c FROM room_members WHERE room = ?", (rm["key"],)
        ).fetchone()["c"]
        rooms.append({**rm, "joined": rm["key"] in joined, "posts": counts, "members": members})
    return render_template("communities.html", rooms=rooms)


@social_bp.route("/api/community/<room>/membership", methods=["POST"])
@login_required
def toggle_membership(room):
    if room not in COMMUNITY_ROOMS:
        abort(404)
    db = get_db()
    sid = session["student_id"]
    existing = db.execute(
        "SELECT 1 FROM room_members WHERE student_id = ? AND room = ?", (sid, room)
    ).fetchone()
    if existing:
        db.execute("DELETE FROM room_members WHERE student_id = ? AND room = ?", (sid, room))
        joined = False
    else:
        db.execute(
            "INSERT OR IGNORE INTO room_members (student_id, room, joined_at) VALUES (?, ?, ?)",
            (sid, room, _now()),
        )
        joined = True
    db.commit()
    return jsonify({"ok": True, "joined": joined})


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------
@social_bp.route("/me")
@login_required
def me():
    return redirect(url_for("social.profile", user_id=session["student_id"]))


@social_bp.route("/u/<int:user_id>")
@login_required
def profile(user_id):
    db = get_db()
    row = db.execute("SELECT * FROM students WHERE id = ?", (user_id,)).fetchone()
    if not row:
        abort(404)
    prof = profile_dict(row)
    joined = [
        COMMUNITY_ROOM_META.get(r["room"], {}).get("label", r["room"])
        for r in db.execute("SELECT room FROM room_members WHERE student_id = ?", (user_id,)).fetchall()
    ]
    return render_template(
        "profile.html", prof=prof, joined_rooms=joined, is_me=(user_id == session["student_id"])
    )


@social_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    db = get_db()
    row = current_student(db)

    if request.method == "POST":
        user_type = request.form.get("user_type")
        if user_type not in ("abroad", "aspiring"):
            user_type = row["user_type"] or "aspiring"
        location = (request.form.get("location") or "").strip()[:80]
        destination = (request.form.get("destination") or "").strip()[:80]
        headline = (request.form.get("headline") or "").strip()[:120]
        bio = (request.form.get("bio") or "").strip()[:600]
        display_name = (request.form.get("display_name") or "").strip()[:40] or row["display_name"]
        study = _parse_history(request.form, "study")
        work = _parse_history(request.form, "work")

        avatar_path = _save_avatar(row["id"], request.files.get("avatar")) or row["avatar_path"]

        db.execute(
            """UPDATE students SET display_name = ?, user_type = ?, location = ?, destination = ?,
               headline = ?, bio = ?, study_history = ?, work_history = ?, avatar_path = ? WHERE id = ?""",
            (display_name, user_type, location, destination, headline, bio,
             json.dumps(study), json.dumps(work), avatar_path, row["id"]),
        )
        db.commit()
        return redirect(url_for("social.profile", user_id=row["id"]))

    return render_template("settings.html", prof=profile_dict(row))


def _parse_history(form, prefix):
    """Rebuild a list of {title, org, years} rows from repeated form fields."""
    titles = form.getlist(f"{prefix}_title")
    orgs = form.getlist(f"{prefix}_org")
    years = form.getlist(f"{prefix}_years")
    out = []
    for i, title in enumerate(titles):
        title = (title or "").strip()[:120]
        org = (orgs[i] if i < len(orgs) else "").strip()[:120]
        yr = (years[i] if i < len(years) else "").strip()[:40]
        if title or org:
            out.append({"title": title, "org": org, "years": yr})
    return out


# ---------------------------------------------------------------------------
# Refer (coming soon)
# ---------------------------------------------------------------------------
@social_bp.route("/refer")
@login_required
def refer():
    return render_template("refer.html")
