import os
import re
import secrets
import sqlite3
from functools import wraps

from flask import Response, g, redirect, request, session, url_for

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "leads.db")

# If DATABASE_URL is set (Railway/Render/etc Postgres addon), use Postgres via
# the compatibility layer below; otherwise fall back to the local SQLite file
# so the app still runs with zero setup in dev.
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

# ---------------------------------------------------------------------------
# Admin auth (HTTP Basic) for /admin/leads and /admin/community. Set
# ADMIN_USERNAME/ADMIN_PASSWORD in .env for a stable login. If ADMIN_PASSWORD is
# left unset, a random one is generated once and cached in data/.admin_password
# (not regenerated on every reload/restart) -- so the page is never reachable
# with a silent default credential.
# ---------------------------------------------------------------------------
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
if not ADMIN_PASSWORD:
    password_cache_path = os.path.join(DATA_DIR, ".admin_password")
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(password_cache_path):
        ADMIN_PASSWORD = open(password_cache_path, "r", encoding="utf-8").read().strip()
    else:
        ADMIN_PASSWORD = secrets.token_urlsafe(9)
        with open(password_cache_path, "w", encoding="utf-8") as f:
            f.write(ADMIN_PASSWORD)
        print(
            "\n"
            "==================================================================\n"
            "  No ADMIN_PASSWORD set in .env -- generated one and cached it in\n"
            "  data/.admin_password:\n"
            f"    username: {ADMIN_USERNAME}\n"
            f"    password: {ADMIN_PASSWORD}\n"
            "  It stays the same across restarts. Set ADMIN_USERNAME/ADMIN_PASSWORD\n"
            "  in .env instead if you want to choose your own.\n"
            "==================================================================\n"
        )


def check_admin_auth(username, password):
    return secrets.compare_digest(username, ADMIN_USERNAME) and secrets.compare_digest(
        password, ADMIN_PASSWORD
    )


def requires_admin_auth(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_admin_auth(auth.username, auth.password):
            return Response(
                "Authentication required.",
                401,
                {"WWW-Authenticate": 'Basic realm="Global Education ROI Admin"'},
            )
        return view(*args, **kwargs)

    return wrapped


# ---------------------------------------------------------------------------
# Student session auth (cookie-based, set after /api/leads or OTP verify).
# ---------------------------------------------------------------------------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("student_id"):
            return redirect(url_for("auth.join", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def current_student_id():
    return session.get("student_id")


# ---------------------------------------------------------------------------
# Flask secret key -- same "env var else generate-and-cache" pattern as
# ADMIN_PASSWORD above, so sessions survive a restart instead of invalidating
# every logged-in student each time the server reloads.
# ---------------------------------------------------------------------------
def get_or_create_secret_key():
    env_key = os.environ.get("FLASK_SECRET_KEY")
    if env_key:
        return env_key
    key_cache_path = os.path.join(DATA_DIR, ".flask_secret_key")
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(key_cache_path):
        return open(key_cache_path, "r", encoding="utf-8").read().strip()
    key = secrets.token_hex(32)
    with open(key_cache_path, "w", encoding="utf-8") as f:
        f.write(key)
    return key


# ---------------------------------------------------------------------------
# Postgres compatibility layer -- lets every blueprint keep using its
# sqlite3-style calls (`?`/`:name` placeholders, `db.execute(...).fetchall()`,
# `row["col"]`, `cur.lastrowid`) unchanged regardless of which backend is
# active, so DATABASE_URL is the only thing that switches behavior.
# ---------------------------------------------------------------------------
_NAMED_PARAM_RE = re.compile(r":(\w+)\b")


def _pg_translate(sql, params):
    if isinstance(params, dict):
        return _NAMED_PARAM_RE.sub(r"%(\1)s", sql)
    return sql.replace("?", "%s")


class _PGCursor:
    def __init__(self, cur):
        self._cur = cur
        self.lastrowid = None

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()


class _PGConnection:
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        from psycopg2.extras import RealDictCursor

        translated = _pg_translate(sql, params)
        # Every table this app pulls .lastrowid from has an `id` primary key;
        # student_profiles is the one INSERT that doesn't (its PK is
        # student_id) and it's always the ON CONFLICT upsert, so that's used
        # as the signal to skip an otherwise-invalid "RETURNING id". The
        # community_votes table is a composite-PK (post_id, student_id)
        # upsert too, same reasoning.
        wants_id = (
            translated.lstrip().upper().startswith("INSERT")
            and "RETURNING" not in translated.upper()
            and "ON CONFLICT" not in translated.upper()
        )
        if wants_id:
            translated += " RETURNING id"

        cur = self._conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(translated, params)
        wrapped = _PGCursor(cur)
        if wants_id:
            wrapped.lastrowid = cur.fetchone()["id"]
        return wrapped

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


# ---------------------------------------------------------------------------
# DB connection (per-request, via Flask's `g`) -- SQLite or Postgres
# ---------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        if DATABASE_URL:
            import psycopg2

            g.db = _PGConnection(psycopg2.connect(DATABASE_URL))
        else:
            os.makedirs(DATA_DIR, exist_ok=True)
            g.db = sqlite3.connect(DB_PATH)
            g.db.row_factory = sqlite3.Row
    return g.db


def close_db(app):
    @app.teardown_appcontext
    def _close_db(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()


def init_db():
    if DATABASE_URL:
        _init_db_postgres()
    else:
        _init_db_sqlite()


def _init_db_postgres():
    import psycopg2

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS leads (
            id SERIAL PRIMARY KEY,
            created_at TEXT NOT NULL,
            email TEXT NOT NULL,
            qualification TEXT,
            grade TEXT,
            profession TEXT,
            destination TEXT,
            city TEXT,
            salary REAL,
            score INTEGER,
            ratio REAL,
            source TEXT,
            forwarded_to_google_form INTEGER NOT NULL DEFAULT 0,
            forwarded_to_hubspot INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS students (
            id SERIAL PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            display_name TEXT,
            created_at TEXT NOT NULL,
            last_seen_at TEXT,
            is_banned INTEGER NOT NULL DEFAULT 0,
            user_type TEXT,
            avatar_path TEXT,
            location TEXT,
            destination TEXT,
            headline TEXT,
            bio TEXT,
            study_history TEXT,
            work_history TEXT,
            onboarded INTEGER NOT NULL DEFAULT 0,
            chat_mode TEXT NOT NULL DEFAULT 'ai'
        );

        CREATE TABLE IF NOT EXISTS student_profiles (
            student_id INTEGER PRIMARY KEY REFERENCES students(id),
            lead_id INTEGER REFERENCES leads(id),
            qualification TEXT,
            grade TEXT,
            profession TEXT,
            destination TEXT,
            city TEXT,
            salary REAL,
            score INTEGER,
            ratio REAL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS otp_codes (
            id SERIAL PRIMARY KEY,
            email TEXT NOT NULL,
            code_hash TEXT NOT NULL,
            purpose TEXT NOT NULL DEFAULT 'login',
            expires_at TEXT NOT NULL,
            consumed_at TEXT,
            created_at TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id SERIAL PRIMARY KEY,
            student_id INTEGER NOT NULL REFERENCES students(id),
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS community_posts (
            id SERIAL PRIMARY KEY,
            room TEXT NOT NULL,
            student_id INTEGER REFERENCES students(id),
            author_label TEXT NOT NULL,
            is_ai INTEGER NOT NULL DEFAULT 0,
            parent_id INTEGER REFERENCES community_posts(id),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_hidden INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS community_votes (
            post_id INTEGER NOT NULL REFERENCES community_posts(id),
            student_id INTEGER NOT NULL REFERENCES students(id),
            value INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (post_id, student_id)
        );

        CREATE TABLE IF NOT EXISTS room_members (
            student_id INTEGER NOT NULL REFERENCES students(id),
            room TEXT NOT NULL,
            joined_at TEXT NOT NULL,
            PRIMARY KEY (student_id, room)
        );

        CREATE TABLE IF NOT EXISTS direct_messages (
            id SERIAL PRIMARY KEY,
            sender_id INTEGER NOT NULL REFERENCES students(id),
            recipient_id INTEGER NOT NULL REFERENCES students(id),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            read_at TEXT,
            shared_post_id INTEGER REFERENCES community_posts(id)
        );

        CREATE TABLE IF NOT EXISTS community_reports (
            id SERIAL PRIMARY KEY,
            post_id INTEGER NOT NULL REFERENCES community_posts(id),
            reported_by INTEGER REFERENCES students(id),
            reason TEXT,
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            resolved_action TEXT
        );

        CREATE TABLE IF NOT EXISTS human_handoff_queue (
            id SERIAL PRIMARY KEY,
            student_id INTEGER NOT NULL REFERENCES students(id),
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            resolved_by TEXT
        );
        """
    )
    conn.commit()
    cur.close()
    conn.close()


def _init_db_sqlite():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            email TEXT NOT NULL,
            qualification TEXT,
            grade TEXT,
            profession TEXT,
            destination TEXT,
            city TEXT,
            salary REAL,
            score INTEGER,
            ratio REAL,
            source TEXT,
            forwarded_to_google_form INTEGER NOT NULL DEFAULT 0,
            forwarded_to_hubspot INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            display_name TEXT,
            created_at TEXT NOT NULL,
            last_seen_at TEXT,
            is_banned INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS student_profiles (
            student_id INTEGER PRIMARY KEY REFERENCES students(id),
            lead_id INTEGER REFERENCES leads(id),
            qualification TEXT,
            grade TEXT,
            profession TEXT,
            destination TEXT,
            city TEXT,
            salary REAL,
            score INTEGER,
            ratio REAL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS otp_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            code_hash TEXT NOT NULL,
            purpose TEXT NOT NULL DEFAULT 'login',
            expires_at TEXT NOT NULL,
            consumed_at TEXT,
            created_at TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL REFERENCES students(id),
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS community_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room TEXT NOT NULL,
            student_id INTEGER REFERENCES students(id),
            author_label TEXT NOT NULL,
            is_ai INTEGER NOT NULL DEFAULT 0,
            parent_id INTEGER REFERENCES community_posts(id),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_hidden INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS community_votes (
            post_id INTEGER NOT NULL REFERENCES community_posts(id),
            student_id INTEGER NOT NULL REFERENCES students(id),
            value INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (post_id, student_id)
        );

        CREATE TABLE IF NOT EXISTS room_members (
            student_id INTEGER NOT NULL REFERENCES students(id),
            room TEXT NOT NULL,
            joined_at TEXT NOT NULL,
            PRIMARY KEY (student_id, room)
        );

        CREATE TABLE IF NOT EXISTS direct_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL REFERENCES students(id),
            recipient_id INTEGER NOT NULL REFERENCES students(id),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            read_at TEXT,
            shared_post_id INTEGER REFERENCES community_posts(id)
        );

        CREATE TABLE IF NOT EXISTS community_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL REFERENCES community_posts(id),
            reported_by INTEGER REFERENCES students(id),
            reason TEXT,
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            resolved_action TEXT
        );

        CREATE TABLE IF NOT EXISTS human_handoff_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL REFERENCES students(id),
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            resolved_by TEXT
        );
        """
    )
    # Migrations for databases created before these columns existed.
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(leads)")}
    if "grade" not in existing_columns:
        conn.execute("ALTER TABLE leads ADD COLUMN grade TEXT")
    if "forwarded_to_hubspot" not in existing_columns:
        conn.execute("ALTER TABLE leads ADD COLUMN forwarded_to_hubspot INTEGER NOT NULL DEFAULT 0")

    # Social-profile columns on students (added incrementally).
    student_columns = {row[1] for row in conn.execute("PRAGMA table_info(students)")}
    student_migrations = {
        "user_type": "TEXT",          # 'abroad' | 'aspiring'
        "avatar_path": "TEXT",         # uploaded avatar filename
        "location": "TEXT",            # where they are now
        "destination": "TEXT",         # where they are / want to be abroad
        "headline": "TEXT",            # short tagline
        "bio": "TEXT",
        "study_history": "TEXT",       # JSON list
        "work_history": "TEXT",        # JSON list
        "onboarded": "INTEGER NOT NULL DEFAULT 0",
        "chat_mode": "TEXT NOT NULL DEFAULT 'ai'",  # 'ai' | 'human' -- who currently answers this student's 1:1 chat
    }
    for col, decl in student_migrations.items():
        if col not in student_columns:
            conn.execute(f"ALTER TABLE students ADD COLUMN {col} {decl}")

    dm_columns = {row[1] for row in conn.execute("PRAGMA table_info(direct_messages)")}
    if "shared_post_id" not in dm_columns:
        conn.execute("ALTER TABLE direct_messages ADD COLUMN shared_post_id INTEGER")
    conn.commit()
    conn.close()
