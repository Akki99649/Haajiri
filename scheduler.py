"""Background reminders: tells teachers and students a few minutes before every period."""
import threading
from datetime import datetime

import config
import db

DEFAULT_SLOTS = [
    (1, "09:00", "09:55", "Period 1", 0),
    (2, "09:55", "10:50", "Period 2", 0),
    (3, "10:50", "11:05", "Short break", 1),
    (4, "11:05", "12:00", "Period 3", 0),
    (5, "12:00", "12:55", "Period 4", 0),
    (6, "12:55", "13:40", "Lunch", 1),
    (7, "13:40", "14:35", "Period 5", 0),
    (8, "14:35", "15:30", "Period 6", 0),
]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def reminder_minutes():
    try:
        return int(db.get_setting("reminder_minutes", config.REMINDER_MINUTES))
    except (TypeError, ValueError):
        return config.REMINDER_MINUTES


def ensure_slots(section):
    """Suggest the standard college day for a section that has no period timings yet."""
    if db.query("SELECT 1 FROM period_slots WHERE section=? LIMIT 1", (section,), one=True):
        return
    reset_slots(section)


def reset_slots(section):
    with db.transaction() as conn:
        conn.execute("DELETE FROM period_slots WHERE section=?", (section,))
        for no, start, end, label, is_break in DEFAULT_SLOTS:
            conn.execute("INSERT INTO period_slots(section,period_no,start_time,end_time,label,is_break) "
                         "VALUES(?,?,?,?,?,?)", (section, no, start, end, label, is_break))


def suggest_timetable(section):
    """Fill empty teaching periods Monday-Saturday by rotating through the section's subjects."""
    ensure_slots(section)
    subjects = db.query("SELECT id FROM subjects WHERE section=? ORDER BY id", (section,))
    slots = db.query("SELECT period_no FROM period_slots WHERE section=? AND is_break=0 ORDER BY period_no", (section,))
    if not subjects:
        return 0
    filled, n = 0, 0
    with db.transaction() as conn:
        for day in range(6):
            for slot in slots:
                n += 1
                exists = conn.execute("SELECT subject_id FROM timetable WHERE section=? AND day=? AND period_no=?",
                                      (section, day, slot["period_no"])).fetchone()
                if exists and exists["subject_id"]:
                    continue
                sid = subjects[(n * 5 // 4 + day) % len(subjects)]["id"] if len(subjects) > 1 else subjects[0]["id"]
                conn.execute("INSERT INTO timetable(section,day,period_no,subject_id) VALUES(?,?,?,?) "
                             "ON CONFLICT(section,day,period_no) DO UPDATE SET subject_id=excluded.subject_id",
                             (section, day, slot["period_no"], sid))
                filled += 1
    return filled


def _parse(hhmm):
    h, m = hhmm.split(":")
    return int(h), int(m)


def tick(now=None):
    """Send the 'class starts soon' notifications that are due. Safe to call repeatedly."""
    now = now or datetime.now()
    if now.weekday() > 5:
        return 0
    window = reminder_minutes()
    rows = db.query(
        "SELECT t.section, t.period_no, t.room, s.id AS subject_id, s.name AS subject_name, s.teacher_id, "
        "p.start_time FROM timetable t JOIN subjects s ON s.id=t.subject_id "
        "JOIN period_slots p ON p.section=t.section AND p.period_no=t.period_no "
        "WHERE t.day=? AND p.is_break=0", (now.weekday(),))
    sent = 0
    today = now.strftime("%Y-%m-%d")
    for r in rows:
        h, m = _parse(r["start_time"])
        mins = (now.replace(hour=h, minute=m, second=0, microsecond=0) - now).total_seconds() / 60.0
        if not 0 <= mins <= window:
            continue
        room = " in %s" % r["room"] if r["room"] else ""
        key = "remind:%s:%s:%s" % (today, r["section"], r["period_no"])
        db.notify(r["teacher_id"], "reminder", "%s starts at %s" % (r["subject_name"], r["start_time"]),
                  "Section %s%s. Open Take attendance when the class begins." % (r["section"], room),
                  "%s:t%d" % (key, r["teacher_id"]))
        for st in db.query("SELECT id FROM users WHERE role='student' AND section=?", (r["section"],)):
            db.notify(st["id"], "reminder", "Next: %s at %s" % (r["subject_name"], r["start_time"]),
                      "Starts in about %d min%s. Be in class so the camera can mark you present."
                      % (max(1, round(mins)), room), "%s:s%d" % (key, st["id"]))
            sent += 1
    return sent


_started = False


def start():
    global _started
    if _started:
        return
    _started = True

    def loop():
        stop = threading.Event()
        while not stop.wait(30):
            try:
                tick()
            except Exception as exc:
                print("[scheduler]", exc)

    threading.Thread(target=loop, daemon=True, name="reminders").start()
