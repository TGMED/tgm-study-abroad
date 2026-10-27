import datetime
import os
import re
import secrets
import sqlite3
from functools import wraps
from urllib.parse import urlparse

from flask import g, redirect, request, session, url_for

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "leads.db")

# If DATABASE_URL is set (mysql://user:password@host:port/dbname), use MySQL
# via the compatibility layer below; otherwise fall back to the local SQLite
# file so the app still runs with zero setup in dev.
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

# ---------------------------------------------------------------------------
# Admin auth -- a proper session-backed login page (see blueprints/admin.py's
# admin_login/admin_logout), not the browser's native Basic Auth prompt. Set
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
        if not session.get("is_admin"):
            return redirect(url_for("admin.admin_login", next=request.path))
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


def counselor_login_required(view):
    """Separate session namespace from student auth (session['counselor_id'],
    never session['student_id']) -- a counselor and a student are distinct
    identities that happen to share a browser cookie jar, not the same
    account wearing different hats."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("counselor_id"):
            return redirect(url_for("counselor_auth.counselor_login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


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
# MySQL compatibility layer -- lets every blueprint keep using its
# sqlite3-style calls (`?`/`:name` placeholders, `db.execute(...).fetchall()`,
# `row["col"]`, `cur.lastrowid`) unchanged regardless of which backend is
# active, so DATABASE_URL is the only thing that switches behavior. PyMySQL
# (like sqlite3) sets cursor.lastrowid natively after an AUTO_INCREMENT
# INSERT, so unlike a Postgres version of this layer, nothing special is
# needed to fake that up -- it just falls out of PyMySQL's own cursor.
# ---------------------------------------------------------------------------
_NAMED_PARAM_RE = re.compile(r":(\w+)\b")
# SQLite's upsert-on-conflict shorthand, used verbatim in a couple of
# blueprints (see social.py) -- MySQL's equivalent statement-level modifier.
_INSERT_OR_IGNORE_RE = re.compile(r"(?i)^(\s*)INSERT OR IGNORE\b")
# Matches a whole single-quoted string literal (with '' as an escaped quote
# inside one), so placeholder substitution can skip over literal content --
# e.g. "LIKE '%?%'" has a literal ? that must survive untouched, not become
# a second (unbound) %s alongside the query's real placeholders.
_STRING_LITERAL_RE = re.compile(r"'(?:[^']|'')*'")


def _translate_placeholders(segment, params):
    if isinstance(params, dict):
        return _NAMED_PARAM_RE.sub(r"%(\1)s", segment)
    return segment.replace("?", "%s")


def _translate_sql(sql, params):
    sql = _INSERT_OR_IGNORE_RE.sub(r"\1INSERT IGNORE", sql)

    parts = []
    pos = 0
    for m in _STRING_LITERAL_RE.finditer(sql):
        parts.append(_translate_placeholders(sql[pos:m.start()], params))
        parts.append(m.group(0))  # leave the literal's contents untouched
        pos = m.end()
    parts.append(_translate_placeholders(sql[pos:], params))
    return "".join(parts)


def _parse_mysql_url(url):
    """mysql://user:password@host:port/dbname -> pymysql.connect() kwargs."""
    parsed = urlparse(url)
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 3306,
        "user": parsed.username,
        "password": parsed.password or "",
        "database": (parsed.path or "").lstrip("/"),
    }


class _MySQLCursor:
    def __init__(self, cur):
        self._cur = cur

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    @property
    def lastrowid(self):
        return self._cur.lastrowid


class _MySQLConnection:
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        cur = self._conn.cursor()
        cur.execute(_translate_sql(sql, params), params)
        return _MySQLCursor(cur)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


# ---------------------------------------------------------------------------
# DB connection (per-request, via Flask's `g`) -- SQLite or MySQL
# ---------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        if DATABASE_URL:
            import pymysql
            import pymysql.cursors

            g.db = _MySQLConnection(pymysql.connect(
                cursorclass=pymysql.cursors.DictCursor, **_parse_mysql_url(DATABASE_URL)
            ))
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
        _init_db_mysql()
    else:
        _init_db_sqlite()


# One-time seed for the `communities` table -- the rooms this app shipped
# with before admins could create/delete their own via /admin/communities.
# Only inserted when the table is empty, so an admin's own edits (including
# deleting one of these) are never clobbered on a later restart.
_DEFAULT_COMMUNITIES = [
    ("general", "General", "★", "Say hello & meet the whole Community, whatever your destination"),
    ("uk", "United Kingdom", "GB", "Students & pros across the UK"),
    ("canada", "Canada", "CA", "PGWP, PR routes & campus life"),
    ("ireland", "Ireland", "IE", "EU tech hub & English-taught study"),
    ("usa", "United States", "US", "F-1, OPT & the American route"),
    ("poland", "Poland", "PL", "Affordable tuition & the Schengen route"),
    ("germany", "Germany", "DE", "Tuition-free public unis & blocked-account visas"),
    ("australia", "Australia", "AU", "Post-study work visas & world-class unis"),
]


def _mysql_table_columns(cur, table):
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = %s",
        (table,),
    )
    return {row[0] for row in cur.fetchall()}


def _init_db_mysql():
    import pymysql

    conn = pymysql.connect(**_parse_mysql_url(DATABASE_URL))
    cur = conn.cursor()
    # One statement per execute() -- unlike sqlite3's executescript()/psycopg2,
    # PyMySQL's cursor.execute() doesn't run a semicolon-separated batch.
    for statement in (
        """
        CREATE TABLE IF NOT EXISTS leads (
            id INT AUTO_INCREMENT PRIMARY KEY,
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
        )
        """,
        # email/phone are VARCHAR (not TEXT) because they're UNIQUE -- MySQL
        # requires a bounded length on any indexed/unique/key column, unlike
        # SQLite/Postgres which index TEXT columns directly. chat_mode is
        # VARCHAR for a different reason: MySQL only allows a DEFAULT on
        # TEXT/BLOB columns from 8.0.13 onward, so a short enum-like string
        # with a default is kept VARCHAR everywhere to not depend on that.
        """
        CREATE TABLE IF NOT EXISTS students (
            id INT AUTO_INCREMENT PRIMARY KEY,
            email VARCHAR(255) NOT NULL UNIQUE,
            phone VARCHAR(32) UNIQUE,
            password_hash TEXT,
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
            chat_mode VARCHAR(16) NOT NULL DEFAULT 'ai'
        )
        """,
        """
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
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS otp_codes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            email TEXT NOT NULL,
            code_hash TEXT NOT NULL,
            purpose VARCHAR(16) NOT NULL DEFAULT 'login',
            expires_at TEXT NOT NULL,
            consumed_at TEXT,
            created_at TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INT AUTO_INCREMENT PRIMARY KEY,
            student_id INTEGER NOT NULL REFERENCES students(id),
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
        # `key` is VARCHAR (not TEXT) because it's the PRIMARY KEY, and
        # backtick-quoted because KEY is a reserved word in MySQL -- every
        # query touching this column backtick-quotes it the same way (see
        # services/communities.py), which SQLite also accepts unchanged.
        """
        CREATE TABLE IF NOT EXISTS communities (
            `key` VARCHAR(32) PRIMARY KEY,
            label TEXT NOT NULL,
            code TEXT NOT NULL,
            blurb TEXT,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS community_posts (
            id INT AUTO_INCREMENT PRIMARY KEY,
            room TEXT NOT NULL,
            student_id INTEGER REFERENCES students(id),
            author_label TEXT NOT NULL,
            is_ai INTEGER NOT NULL DEFAULT 0,
            parent_id INTEGER REFERENCES community_posts(id),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_hidden INTEGER NOT NULL DEFAULT 0,
            image_path TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS community_votes (
            post_id INTEGER NOT NULL REFERENCES community_posts(id),
            student_id INTEGER NOT NULL REFERENCES students(id),
            value INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (post_id, student_id)
        )
        """,
        # room is VARCHAR here (unlike community_posts.room) because it's
        # part of this table's composite PRIMARY KEY.
        """
        CREATE TABLE IF NOT EXISTS room_members (
            student_id INTEGER NOT NULL REFERENCES students(id),
            room VARCHAR(32) NOT NULL,
            joined_at TEXT NOT NULL,
            PRIMARY KEY (student_id, room)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS direct_messages (
            id INT AUTO_INCREMENT PRIMARY KEY,
            sender_id INTEGER NOT NULL REFERENCES students(id),
            recipient_id INTEGER NOT NULL REFERENCES students(id),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            read_at TEXT,
            shared_post_id INTEGER REFERENCES community_posts(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS community_reports (
            id INT AUTO_INCREMENT PRIMARY KEY,
            post_id INTEGER NOT NULL REFERENCES community_posts(id),
            reported_by INTEGER REFERENCES students(id),
            reason TEXT,
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            resolved_action TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ai_post_queue (
            id INT AUTO_INCREMENT PRIMARY KEY,
            room VARCHAR(32) NOT NULL DEFAULT 'general',
            content TEXT NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            reviewed_at TEXT,
            posted_at TEXT,
            community_post_id INTEGER REFERENCES community_posts(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS human_handoff_queue (
            id INT AUTO_INCREMENT PRIMARY KEY,
            student_id INTEGER NOT NULL REFERENCES students(id),
            reason TEXT NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            resolved_by TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS whatsapp_events (
            wamid VARCHAR(128) PRIMARY KEY,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS counselors (
            id INT AUTO_INCREMENT PRIMARY KEY,
            full_name TEXT NOT NULL,
            email VARCHAR(255) NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            headline TEXT,
            avatar_path TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS counselor_conversations (
            id INT AUTO_INCREMENT PRIMARY KEY,
            student_id INTEGER NOT NULL REFERENCES students(id),
            counselor_id INTEGER NOT NULL REFERENCES counselors(id),
            created_at TEXT NOT NULL,
            last_message_at TEXT NOT NULL,
            UNIQUE(student_id, counselor_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS counselor_messages (
            id INT AUTO_INCREMENT PRIMARY KEY,
            conversation_id INTEGER NOT NULL REFERENCES counselor_conversations(id),
            sender_type TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
    ):
        cur.execute(statement)

    # password_hash/image_path were added after some deployments already had
    # these tables -- CREATE TABLE IF NOT EXISTS above is a no-op against
    # those, so add the columns explicitly for anything created before this.
    # Checked via information_schema rather than `ADD COLUMN IF NOT EXISTS`
    # since that clause only exists from MySQL 8.0.29 -- this works on any
    # MySQL/MariaDB version, same defensive approach _init_db_sqlite already
    # takes with PRAGMA table_info.
    student_columns = _mysql_table_columns(cur, "students")
    if "password_hash" not in student_columns:
        cur.execute("ALTER TABLE students ADD COLUMN password_hash TEXT")
    post_columns = _mysql_table_columns(cur, "community_posts")
    if "image_path" not in post_columns:
        cur.execute("ALTER TABLE community_posts ADD COLUMN image_path TEXT")

    cur.execute("SELECT COUNT(*) FROM communities")
    if cur.fetchone()[0] == 0:
        now_iso = datetime.datetime.utcnow().isoformat()
        for key, label, code, blurb in _DEFAULT_COMMUNITIES:
            cur.execute(
                "INSERT INTO communities (`key`, label, code, blurb, created_at) VALUES (%s, %s, %s, %s, %s)",
                (key, label, code, blurb, now_iso),
            )

    # #general was introduced after some students had already onboarded --
    # backfill them in, since every member is expected to land there.
    # INSERT IGNORE is MySQL's equivalent of SQLite's INSERT OR IGNORE; the
    # timestamp is computed in Python (matching every other created_at in
    # this app) rather than relying on MySQL's NOW(), which returns a
    # DATETIME, not the ISO-8601 string format the rest of the app uses.
    now_iso = datetime.datetime.utcnow().isoformat()
    cur.execute(
        "INSERT IGNORE INTO room_members (student_id, room, joined_at) SELECT id, 'general', %s FROM students WHERE onboarded = 1",
        (now_iso,),
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

        CREATE TABLE IF NOT EXISTS communities (
            `key` TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            code TEXT NOT NULL,
            blurb TEXT,
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
            is_hidden INTEGER NOT NULL DEFAULT 0,
            image_path TEXT
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

        CREATE TABLE IF NOT EXISTS ai_post_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room TEXT NOT NULL DEFAULT 'general',
            content TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            reviewed_at TEXT,
            posted_at TEXT,
            community_post_id INTEGER REFERENCES community_posts(id)
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

        CREATE TABLE IF NOT EXISTS whatsapp_events (
            wamid TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS counselors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            headline TEXT,
            avatar_path TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS counselor_conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL REFERENCES students(id),
            counselor_id INTEGER NOT NULL REFERENCES counselors(id),
            created_at TEXT NOT NULL,
            last_message_at TEXT NOT NULL,
            UNIQUE(student_id, counselor_id)
        );

        CREATE TABLE IF NOT EXISTS counselor_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL REFERENCES counselor_conversations(id),
            sender_type TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
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
        "phone": "TEXT",               # WhatsApp wa_id -- unique index added separately below (SQLite can't
                                        # add a UNIQUE column via ALTER TABLE)
        "password_hash": "TEXT",       # NULL for accounts created before password auth existed, or via the
                                        # WhatsApp flow, which never collects a password
    }
    for col, decl in student_migrations.items():
        if col not in student_columns:
            conn.execute(f"ALTER TABLE students ADD COLUMN {col} {decl}")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_students_phone ON students(phone) WHERE phone IS NOT NULL")

    dm_columns = {row[1] for row in conn.execute("PRAGMA table_info(direct_messages)")}
    if "shared_post_id" not in dm_columns:
        conn.execute("ALTER TABLE direct_messages ADD COLUMN shared_post_id INTEGER")

    post_columns = {row[1] for row in conn.execute("PRAGMA table_info(community_posts)")}
    if "image_path" not in post_columns:
        conn.execute("ALTER TABLE community_posts ADD COLUMN image_path TEXT")

    if conn.execute("SELECT COUNT(*) FROM communities").fetchone()[0] == 0:
        now_iso = datetime.datetime.utcnow().isoformat()
        conn.executemany(
            "INSERT INTO communities (`key`, label, code, blurb, created_at) VALUES (?, ?, ?, ?, ?)",
            [(key, label, code, blurb, now_iso) for key, label, code, blurb in _DEFAULT_COMMUNITIES],
        )

    # #general was introduced after some students had already onboarded --
    # backfill them in, since every member is expected to land there.
    conn.execute(
        """
        INSERT OR IGNORE INTO room_members (student_id, room, joined_at)
        SELECT id, 'general', datetime('now') FROM students WHERE onboarded = 1
        """
    )
    conn.commit()
    conn.close()
