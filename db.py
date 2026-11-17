"""SQLite helpers. A fresh connection is opened per call, so it is safe across threads."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('teacher','student')),
    roll_no TEXT,
    section TEXT,
    created_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_roll ON users(roll_no) WHERE roll_no IS NOT NULL;

CREATE TABLE IF NOT EXISTS subjects(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    code TEXT NOT NULL,
    section TEXT NOT NULL,
    teacher_id INTEGER NOT NULL REFERENCES users(id),
    UNIQUE(code, section)
);

CREATE TABLE IF NOT EXISTS period_slots(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section TEXT NOT NULL,
    period_no INTEGER NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    label TEXT,
    is_break INTEGER NOT NULL DEFAULT 0,
    UNIQUE(section, period_no)
);

CREATE TABLE IF NOT EXISTS timetable(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section TEXT NOT NULL,
    day INTEGER NOT NULL,
    period_no INTEGER NOT NULL,
    subject_id INTEGER REFERENCES subjects(id) ON DELETE CASCADE,
    room TEXT,
    UNIQUE(section, day, period_no)
);

CREATE TABLE IF NOT EXISTS settings(
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS sessions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL REFERENCES subjects(id),
    teacher_id INTEGER NOT NULL REFERENCES users(id),
    section TEXT NOT NULL,
    period_no INTEGER,
    date TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    export_path TEXT,
    camera_source TEXT
);

CREATE TABLE IF NOT EXISTS attendance(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'absent',
    marked_at TEXT,
    confidence REAL,
    method TEXT,
    UNIQUE(session_id, student_id)
);

CREATE TABLE IF NOT EXISTS notifications(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT,
    title TEXT NOT NULL,
    body TEXT,
    created_at TEXT,
    is_read INTEGER NOT NULL DEFAULT 0,
    dedupe_key TEXT UNIQUE
);
"""


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str():
    return datetime.now().strftime("%Y-%m-%d")


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = connect()
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def query(sql, args=(), one=False):
    conn = connect()
    try:
        rows = conn.execute(sql, args).fetchall()
    finally:
        conn.close()
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql, args=()):
    conn = connect()
    try:
        cur = conn.execute(sql, args)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


@contextmanager
def transaction():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_setting(key, default=None):
    row = query("SELECT value FROM settings WHERE key=?", (key,), one=True)
    return row["value"] if row else default


def set_setting(key, value):
    execute("INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def notify(user_id, kind, title, body="", dedupe_key=None):
    """Insert a notification; a repeated dedupe_key is silently ignored."""
    execute("INSERT OR IGNORE INTO notifications(user_id,kind,title,body,created_at,dedupe_key) "
            "VALUES(?,?,?,?,?,?)", (user_id, kind, title, body, now_str(), dedupe_key))
