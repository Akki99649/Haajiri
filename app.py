"""Haajiri - face-recognition attendance. Flask backend.

Run:  python app.py      then open http://127.0.0.1:5000
"""
import base64
import re
import threading
import time
from datetime import datetime
from functools import wraps

import cv2
import numpy as np
from flask import (Flask, Response, abort, jsonify, redirect, render_template, request,
                   send_file, session)
from werkzeug.security import check_password_hash, generate_password_hash

import config
import db
import exports
import live
import scheduler
from face_engine import engine

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024
db.init_db()

HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_train_lock = threading.Lock()


# ---------------------------------------------------------------- helpers
def current_user():
    uid = session.get("uid")
    return db.query("SELECT * FROM users WHERE id=?", (uid,), one=True) if uid else None


def api(role=None):
    """Route decorator: requires a signed-in user (optionally of a given role); passes it as `me`."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            me = current_user()
            if me is None:
                return jsonify(error="Please sign in to continue."), 401
            if role and me["role"] != role:
                return jsonify(error="This action is not available for your account."), 403
            return fn(me, *args, **kwargs)
        return wrapper
    return deco


def err(message, code=400):
    return jsonify(error=message), code


def body():
    return request.get_json(force=True, silent=True) or {}


def user_dict(u):
    d = {"id": u["id"], "name": u["name"], "email": u["email"], "role": u["role"],
         "roll_no": u["roll_no"], "section": u["section"]}
    if u["role"] == "student":
        d["face_samples"] = engine.sample_count(u["id"])
    return d


def decode_image(data):
    if not data:
        return None
    if "," in data:
        data = data.split(",", 1)[1]
    try:
        arr = np.frombuffer(base64.b64decode(data), np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception:
        return None


def my_session(me, sid):
    row = db.query(
        "SELECT se.*, su.name AS subject_name, su.code AS subject_code FROM sessions se "
        "JOIN subjects su ON su.id=se.subject_id WHERE se.id=?", (sid,), one=True)
    if row is None or row["teacher_id"] != me["id"]:
        abort(404)
    return row


def counts(sid):
    r = db.query(
        "SELECT SUM(status='present') p, SUM(status='late') l, SUM(status='absent') a, COUNT(*) n "
        "FROM attendance WHERE session_id=?", (sid,), one=True)
    return {"present": r["p"] or 0, "late": r["l"] or 0, "absent": r["a"] or 0, "total": r["n"] or 0}


def retrain():
    with _train_lock:
        return engine.train()


# ------------------------------------------------------------------ pages
@app.get("/")
def home():
    me = current_user()
    if me:
        return redirect("/teacher" if me["role"] == "teacher" else "/student")
    return render_template("index.html")


@app.get("/teacher")
def teacher_page():
    me = current_user()
    if not me or me["role"] != "teacher":
        return redirect("/")
    return render_template("teacher.html", me=user_dict(me))


@app.get("/student")
def student_page():
    me = current_user()
    if not me or me["role"] != "student":
        return redirect("/")
    return render_template("student.html", me=user_dict(me))


# ------------------------------------------------------------------- auth
@app.post("/api/register")
def register():
    d = body()
    name = (d.get("name") or "").strip()
    email = (d.get("email") or "").strip().lower()
    password = d.get("password") or ""
    role = d.get("role")
    if role not in ("teacher", "student"):
        return err("Choose whether you are a teacher or a student.")
    if len(name) < 2:
        return err("Enter your full name.")
    if not EMAIL.match(email):
        return err("Enter a valid email address.")
    if len(password) < 6:
        return err("Use a password with at least 6 characters.")
    roll = section = None
    if role == "teacher":
        if (d.get("code") or "").strip() != config.TEACHER_REGISTER_CODE:
            return err("The teacher access code is not correct. Ask your department for it.")
    else:
        roll = (d.get("roll_no") or "").strip().upper()
        section = (d.get("section") or "").strip().upper()
        if not roll or not section:
            return err("Enter your roll number (USN) and section.")
        if db.query("SELECT 1 FROM users WHERE roll_no=?", (roll,), one=True):
            return err("That roll number is already registered.")
    if db.query("SELECT 1 FROM users WHERE email=?", (email,), one=True):
        return err("That email is already registered. Sign in instead.")
    uid = db.execute(
        "INSERT INTO users(name,email,password_hash,role,roll_no,section,created_at) VALUES(?,?,?,?,?,?,?)",
        (name, email, generate_password_hash(password), role, roll, section, db.now_str()))
    session["uid"] = uid
    if role == "student":
        db.notify(uid, "welcome", "Welcome to Haajiri",
                  "Add your face photos from the Face setup tab so the class camera can recognise you.")
    return jsonify(user=user_dict(db.query("SELECT * FROM users WHERE id=?", (uid,), one=True)))


@app.post("/api/login")
def login():
    d = body()
    ident = (d.get("email") or "").strip()
    u = db.query("SELECT * FROM users WHERE lower(email)=lower(?) OR upper(roll_no)=upper(?)", (ident, ident), one=True)
    if u is None or not check_password_hash(u["password_hash"], d.get("password") or ""):
        return err("Email, roll number or password is not correct.", 401)
    session["uid"] = u["id"]
    return jsonify(user=user_dict(u))


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/me")
@api()
def me_info(me):
    return jsonify(user=user_dict(me))


# --------------------------------------------------------- subjects, sections
@app.get("/api/sections")
@api()
def sections(me):
    rows = db.query("SELECT section FROM users WHERE section IS NOT NULL UNION SELECT section FROM subjects ORDER BY 1")
    return jsonify(sections=[r["section"] for r in rows])


@app.get("/api/subjects")
@api()
def list_subjects(me):
    section = (request.args.get("section") or "").strip().upper()
    if me["role"] == "teacher" and section:     # every subject of a section, for editing its timetable
        rows = db.query("SELECT su.*, u.name AS teacher_name FROM subjects su JOIN users u ON u.id=su.teacher_id "
                        "WHERE su.section=? ORDER BY su.name", (section,))
    elif me["role"] == "teacher":
        rows = db.query("SELECT su.*, u.name AS teacher_name FROM subjects su JOIN users u ON u.id=su.teacher_id "
                        "WHERE su.teacher_id=? ORDER BY su.section, su.name", (me["id"],))
    else:
        rows = db.query("SELECT su.*, u.name AS teacher_name FROM subjects su JOIN users u ON u.id=su.teacher_id "
                        "WHERE su.section=? ORDER BY su.name", (me["section"],))
    return jsonify(subjects=[dict(r) for r in rows])


@app.post("/api/subjects")
@api("teacher")
def add_subject(me):
    d = body()
    name = (d.get("name") or "").strip()
    code = (d.get("code") or "").strip().upper()
    sec = (d.get("section") or "").strip().upper()
    if not (name and code and sec):
        return err("Enter the subject name, subject code and section.")
    if db.query("SELECT 1 FROM subjects WHERE code=? AND section=?", (code, sec), one=True):
        return err("Section %s already has a subject with code %s." % (sec, code))
    sid = db.execute("INSERT INTO subjects(name,code,section,teacher_id) VALUES(?,?,?,?)", (name, code, sec, me["id"]))
    scheduler.ensure_slots(sec)
    return jsonify(id=sid)


@app.delete("/api/subjects/<int:sid>")
@api("teacher")
def delete_subject(me, sid):
    sub = db.query("SELECT * FROM subjects WHERE id=? AND teacher_id=?", (sid, me["id"]), one=True)
    if sub is None:
        return err("Subject not found.", 404)
    if db.query("SELECT 1 FROM sessions WHERE subject_id=? LIMIT 1", (sid,), one=True):
        return err("This subject already has attendance records, so it cannot be deleted.", 409)
    db.execute("DELETE FROM timetable WHERE subject_id=?", (sid,))
    db.execute("DELETE FROM subjects WHERE id=?", (sid,))
    return jsonify(ok=True)


# ----------------------------------------------------- students + face setup
@app.get("/api/students")
@api("teacher")
def list_students(me):
    sec = (request.args.get("section") or "").strip().upper()
    sql, args = "SELECT * FROM users WHERE role='student'", ()
    if sec:
        sql, args = sql + " AND section=?", (sec,)
    rows = db.query(sql + " ORDER BY section, roll_no", args)
    return jsonify(students=[{"id": r["id"], "name": r["name"], "roll_no": r["roll_no"], "section": r["section"],
                              "samples": engine.sample_count(r["id"])} for r in rows])


def _can_edit_faces(me, sid):
    return me["role"] == "teacher" or me["id"] == sid


@app.post("/api/students/<int:sid>/faces")
@api()
def upload_faces(me, sid):
    if not _can_edit_faces(me, sid):
        return err("You can only add photos for yourself.", 403)
    st = db.query("SELECT 1 FROM users WHERE id=? AND role='student'", (sid,), one=True)
    if st is None:
        return err("Student not found.", 404)
    images = body().get("images") or []
    saved = 0
    for data in images[:40]:
        img = decode_image(data)
        if img is not None and engine.add_face_image(sid, img):
            saved += 1
    status = retrain() if saved else engine.status()
    return jsonify(saved=saved, rejected=len(images) - saved, samples=engine.sample_count(sid), engine=status)


@app.delete("/api/students/<int:sid>/faces")
@api()
def clear_faces(me, sid):
    if not _can_edit_faces(me, sid):
        return err("You can only remove your own photos.", 403)
    engine.clear_samples(sid)
    return jsonify(engine=retrain(), samples=0)


@app.post("/api/train")
@api("teacher")
def train(me):
    return jsonify(engine=retrain())


@app.get("/api/engine")
@api()
def engine_status(me):
    return jsonify(engine=engine.status())


# -------------------------------------------------------------- timetable
def timetable_payload(section):
    scheduler.ensure_slots(section)
    slots = [dict(r) for r in db.query("SELECT * FROM period_slots WHERE section=? ORDER BY period_no", (section,))]
    cells = {}
    for r in db.query(
            "SELECT t.day, t.period_no, t.room, t.subject_id, su.name AS subject, su.code, u.name AS teacher "
            "FROM timetable t LEFT JOIN subjects su ON su.id=t.subject_id LEFT JOIN users u ON u.id=su.teacher_id "
            "WHERE t.section=?", (section,)):
        cells["%d-%d" % (r["day"], r["period_no"])] = dict(r)
    return {"section": section, "days": scheduler.DAYS, "slots": slots, "cells": cells}


@app.get("/api/timetable")
@api()
def get_timetable(me):
    section = (request.args.get("section") or me["section"] or "").strip().upper()
    if not section:
        return err("Choose a section.")
    return jsonify(timetable_payload(section))


@app.post("/api/timetable/suggest")
@api("teacher")
def suggest(me):
    d = body()
    section = (d.get("section") or "").strip().upper()
    if not section:
        return err("Choose a section.")
    if d.get("reset_times"):
        scheduler.reset_slots(section)
    filled = scheduler.suggest_timetable(section)
    return jsonify(filled=filled, **timetable_payload(section))


@app.put("/api/timetable/slots")
@api("teacher")
def save_slots(me):
    d = body()
    section = (d.get("section") or "").strip().upper()
    slots = d.get("slots") or []
    if not section or not slots:
        return err("Nothing to save.")
    cleaned = []
    for i, s in enumerate(slots, 1):
        start, end = (s.get("start_time") or "").strip(), (s.get("end_time") or "").strip()
        if not (HHMM.match(start) and HHMM.match(end)):
            return err("Row %d: enter times as HH:MM, for example 09:00." % i)
        if end <= start:
            return err("Row %d: the end time must be after the start time." % i)
        cleaned.append((int(s.get("period_no") or i), start, end, (s.get("label") or "").strip()[:30],
                        1 if s.get("is_break") else 0))
    ordered = sorted(cleaned, key=lambda c: c[0])
    for a, b in zip(ordered, ordered[1:]):
        if b[1] < a[2]:
            return err("Periods %d and %d overlap. Move the start of period %d to %s or later." % (a[0], b[0], b[0], a[2]))
    with db.transaction() as conn:
        conn.execute("DELETE FROM period_slots WHERE section=?", (section,))
        for no, start, end, label, brk in ordered:
            conn.execute("INSERT INTO period_slots(section,period_no,start_time,end_time,label,is_break) "
                         "VALUES(?,?,?,?,?,?)", (section, no, start, end, label or "Period %d" % no, brk))
    for st in db.query("SELECT id FROM users WHERE role='student' AND section=?", (section,)):
        db.notify(st["id"], "timetable", "Period timings changed",
                  "%s updated the period timings for section %s. Check the Timetable tab." % (me["name"], section))
    return jsonify(timetable_payload(section))


@app.put("/api/timetable/cell")
@api("teacher")
def save_cell(me):
    d = body()
    section = (d.get("section") or "").strip().upper()
    try:
        day, period = int(d.get("day")), int(d.get("period_no"))
    except (TypeError, ValueError):
        return err("Choose a day and a period.")
    subject_id = d.get("subject_id") or None
    if subject_id:
        sub = db.query("SELECT * FROM subjects WHERE id=? AND section=?", (subject_id, section), one=True)
        if sub is None:
            return err("That subject does not belong to section %s." % section)
    db.execute("INSERT INTO timetable(section,day,period_no,subject_id,room) VALUES(?,?,?,?,?) "
               "ON CONFLICT(section,day,period_no) DO UPDATE SET subject_id=excluded.subject_id, room=excluded.room",
               (section, day, period, subject_id, (d.get("room") or "").strip()[:20]))
    return jsonify(ok=True)


# ------------------------------------------------------ settings + camera
@app.get("/api/settings")
@api("teacher")
def get_settings(me):
    return jsonify(reminder_minutes=scheduler.reminder_minutes(),
                   camera_source=db.get_setting("camera_source", config.DEFAULT_CAMERA_SOURCE),
                   engine=engine.status())


@app.put("/api/settings")
@api("teacher")
def put_settings(me):
    d = body()
    if "reminder_minutes" in d:
        try:
            m = int(d["reminder_minutes"])
        except (TypeError, ValueError):
            return err("Enter the reminder time in minutes.")
        if not 1 <= m <= 60:
            return err("Reminder time must be between 1 and 60 minutes.")
        db.set_setting("reminder_minutes", str(m))
    if "camera_source" in d:
        db.set_setting("camera_source", str(d["camera_source"]).strip())
    return get_settings()


@app.post("/api/camera/test")
@api("teacher")
def camera_test(me):
    source = str(body().get("source") or "").strip()
    if not source:
        return err("Enter a camera address or number first.")
    ok, msg = live.test_camera(source)
    return jsonify(ok=ok, message=msg)


# --------------------------------------------------------------- sessions
@app.get("/api/today")
@api("teacher")
def today(me):
    day = datetime.now().weekday()
    rows = db.query(
        "SELECT t.section, t.period_no, t.room, su.id AS subject_id, su.name AS subject, su.code, "
        "p.label, p.start_time, p.end_time FROM timetable t JOIN subjects su ON su.id=t.subject_id "
        "JOIN period_slots p ON p.section=t.section AND p.period_no=t.period_no "
        "WHERE t.day=? AND su.teacher_id=? AND p.is_break=0 ORDER BY p.start_time", (day, me["id"]))
    today_s = db.today_str()
    out = []
    for r in rows:
        d = dict(r)
        s = db.query("SELECT id, status FROM sessions WHERE subject_id=? AND date=? AND period_no=? ORDER BY id DESC",
                     (r["subject_id"], today_s, r["period_no"]), one=True)
        d["session_id"], d["session_status"] = (s["id"], s["status"]) if s else (None, None)
        out.append(d)
    active = db.query(
        "SELECT se.id, se.section, su.name AS subject FROM sessions se JOIN subjects su ON su.id=se.subject_id "
        "WHERE se.teacher_id=? AND se.status='active'", (me["id"],))
    return jsonify(classes=out, active=[dict(a) for a in active], day=scheduler.DAYS[day] if day < 6 else "Sunday",
                   date=today_s)


@app.get("/api/sessions")
@api("teacher")
def list_sessions(me):
    rows = db.query(
        "SELECT se.id, se.section, se.date, se.period_no, se.status, se.started_at, su.name AS subject, su.code, p.label AS period_label, "
        "(SELECT COUNT(*) FROM attendance a WHERE a.session_id=se.id AND a.status IN ('present','late')) AS present, "
        "(SELECT COUNT(*) FROM attendance a WHERE a.session_id=se.id) AS total "
        "FROM sessions se JOIN subjects su ON su.id=se.subject_id "
        "LEFT JOIN period_slots p ON p.section=se.section AND p.period_no=se.period_no WHERE se.teacher_id=? "
        "ORDER BY se.id DESC LIMIT 100", (me["id"],))
    return jsonify(sessions=[dict(r) for r in rows])


@app.post("/api/sessions/start")
@api("teacher")
def start_session(me):
    d = body()
    sub = db.query("SELECT * FROM subjects WHERE id=? AND teacher_id=?", (d.get("subject_id"), me["id"]), one=True)
    if sub is None:
        return err("Choose one of your subjects.")
    period = d.get("period_no")
    today_s = db.today_str()
    existing = db.query("SELECT * FROM sessions WHERE subject_id=? AND date=? AND status='active'",
                        (sub["id"], today_s), one=True)
    if existing:
        live.get_runner(existing)
        return jsonify(id=existing["id"], resumed=True)
    mode = d.get("mode", "browser")
    source = "browser"
    if mode == "camera":
        source = str(d.get("camera_source") or db.get_setting("camera_source", config.DEFAULT_CAMERA_SOURCE)).strip()
    students = db.query("SELECT id FROM users WHERE role='student' AND section=?", (sub["section"],))
    if not students:
        return err("Section %s has no registered students yet." % sub["section"])
    sid = db.execute(
        "INSERT INTO sessions(subject_id,teacher_id,section,period_no,date,started_at,status,camera_source) "
        "VALUES(?,?,?,?,?,?,'active',?)",
        (sub["id"], me["id"], sub["section"], period, today_s, db.now_str(), source))
    with db.transaction() as conn:
        conn.executemany("INSERT INTO attendance(session_id,student_id,status) VALUES(?,?,'absent')",
                         [(sid, s["id"]) for s in students])
    live.get_runner(db.query("SELECT * FROM sessions WHERE id=?", (sid,), one=True))
    for s in students:
        db.notify(s["id"], "session", "Attendance is open for %s" % sub["name"],
                  "%s has started attendance. Face the class camera so you are marked present." % me["name"],
                  "open:%d:%d" % (sid, s["id"]))
    return jsonify(id=sid, resumed=False)


@app.get("/api/sessions/<int:sid>")
@api("teacher")
def session_detail(me, sid):
    s = my_session(me, sid)
    runner = live.get_runner(s, create=True)
    slot = db.query("SELECT label FROM period_slots WHERE section=? AND period_no=?", (s["section"], s["period_no"]), one=True)
    rows = db.query(
        "SELECT u.id, u.name, u.roll_no, a.status, a.marked_at, a.confidence, a.method FROM attendance a "
        "JOIN users u ON u.id=a.student_id WHERE a.session_id=? ORDER BY u.roll_no", (sid,))
    return jsonify(
        session=dict({k: s[k] for k in ("id", "section", "date", "period_no", "status", "started_at", "ended_at",
                                        "camera_source", "subject_name", "subject_code")},
                     period_label=slot["label"] if slot else None),
        roster=[dict(r, samples=engine.sample_count(r["id"])) for r in rows], counts=counts(sid),
        camera={"state": runner.state if runner else "stopped", "message": runner.message if runner else ""},
        engine=engine.status())


@app.post("/api/sessions/<int:sid>/frame")
@api("teacher")
def session_frame(me, sid):
    s = my_session(me, sid)
    if s["status"] != "active":
        return err("This class has already ended.", 409)
    runner = live.get_runner(s)
    img = decode_image(body().get("image"))
    if img is None:
        return err("The picture could not be read.")
    faces = runner.process(img)
    h, w = img.shape[:2]
    out = []
    for f in faces:
        sid_ = f["student_id"]
        known = sid_ is not None and sid_ in runner.names
        out.append({"box": f["box"], "known": known, "name": runner.names.get(sid_) if known else None,
                    "student_id": sid_ if known else None, "confidence": round(f["confidence"], 1)})
    return jsonify(faces=out, width=w, height=h, counts=counts(sid))


@app.get("/api/sessions/<int:sid>/stream")
@api("teacher")
def session_stream(me, sid):
    s = my_session(me, sid)
    runner = live.get_runner(s)
    if runner is None:
        abort(404)

    def gen():
        last = None
        while not runner.stop_event.is_set():
            jpg = runner.latest_jpeg
            if jpg is not None and jpg is not last:
                last = jpg
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
            time.sleep(0.12)

    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.post("/api/sessions/<int:sid>/mark")
@api("teacher")
def manual_mark(me, sid):
    s = my_session(me, sid)
    d = body()
    status = d.get("status")
    if status not in ("present", "late", "absent"):
        return err("Choose present, late or absent.")
    stu = d.get("student_id")
    if not db.query("SELECT 1 FROM attendance WHERE session_id=? AND student_id=?", (sid, stu), one=True):
        return err("That student is not in this class.", 404)
    db.execute("UPDATE attendance SET status=?, method='manual', marked_at=?, confidence=NULL "
               "WHERE session_id=? AND student_id=?", (status, db.now_str() if status != "absent" else None, sid, stu))
    runner = live.get_runner(s, create=False)
    if runner:
        runner.sync_manual(stu, status)
    return jsonify(counts=counts(sid))


@app.post("/api/sessions/<int:sid>/end")
@api("teacher")
def end_session(me, sid):
    s = my_session(me, sid)
    if s["status"] == "active":
        live.stop_runner(sid)
        db.execute("UPDATE sessions SET status='ended', ended_at=? WHERE id=?", (db.now_str(), sid))
        _notify_results(s)
    path = exports.build_session_xlsx(sid)
    return jsonify(ok=True, counts=counts(sid), export_url="/api/sessions/%d/export" % sid, filename=path.split("/")[-1])


def _notify_results(s):
    rows = db.query("SELECT student_id, status FROM attendance WHERE session_id=?", (s["id"],))
    for r in rows:
        stu = r["student_id"]
        if r["status"] == "absent":
            title, body_ = "Marked absent in %s" % s["subject_name"], "You were not seen in the %s class on %s." % (s["subject_name"], s["date"])
        elif r["status"] == "late":
            title, body_ = "Marked late in %s" % s["subject_name"], "Your attendance for %s on %s is recorded as late." % (s["subject_name"], s["date"])
        else:
            title, body_ = "Present in %s" % s["subject_name"], "Your attendance for %s on %s is recorded." % (s["subject_name"], s["date"])
        db.notify(stu, "result", title, body_, "result:%d:%d" % (s["id"], stu))
        pct = _percent(stu, s["subject_id"])
        if pct is not None and pct < 75:
            db.notify(stu, "warning", "Attendance is low in %s" % s["subject_name"],
                      "You are at %.0f%%. Most colleges need at least 75%% to sit exams." % pct,
                      "low:%d:%d" % (s["id"], stu))


def _percent(student_id, subject_id):
    r = db.query(
        "SELECT SUM(a.status IN ('present','late')) AS got, COUNT(*) AS n FROM attendance a "
        "JOIN sessions s ON s.id=a.session_id WHERE a.student_id=? AND s.subject_id=? AND s.status='ended'",
        (student_id, subject_id), one=True)
    return 100.0 * (r["got"] or 0) / r["n"] if r and r["n"] else None


@app.get("/api/sessions/<int:sid>/export")
@api("teacher")
def export_session(me, sid):
    my_session(me, sid)
    path = exports.build_session_xlsx(sid)
    return send_file(path, as_attachment=True, download_name=path.split("/")[-1])


@app.get("/api/subjects/<int:sid>/report")
@api("teacher")
def export_subject(me, sid):
    if db.query("SELECT 1 FROM subjects WHERE id=? AND teacher_id=?", (sid, me["id"]), one=True) is None:
        abort(404)
    path = exports.build_subject_xlsx(sid)
    return send_file(path, as_attachment=True, download_name=path.split("/")[-1])


# ---------------------------------------------------------------- students
@app.get("/api/student/overview")
@api("student")
def student_overview(me):
    subjects = []
    for su in db.query("SELECT su.*, u.name AS teacher_name FROM subjects su JOIN users u ON u.id=su.teacher_id "
                       "WHERE su.section=? ORDER BY su.name", (me["section"],)):
        r = db.query(
            "SELECT SUM(a.status IN ('present','late')) AS got, COUNT(*) AS n FROM attendance a "
            "JOIN sessions s ON s.id=a.session_id WHERE a.student_id=? AND s.subject_id=? AND s.status='ended'",
            (me["id"], su["id"]), one=True)
        n, got = r["n"] or 0, r["got"] or 0
        need = 0
        if n and got / n < 0.75:                       # classes still to attend in a row to reach 75%
            need = max(0, int(np.ceil((0.75 * n - got) / 0.25)))
        subjects.append({"id": su["id"], "name": su["name"], "code": su["code"], "teacher": su["teacher_name"],
                         "attended": got, "total": n, "percent": round(100.0 * got / n, 1) if n else None,
                         "need_more": need})
    recent = db.query(
        "SELECT su.name AS subject, s.date, s.period_no, ps.label AS period_label, a.status, a.marked_at FROM attendance a "
        "JOIN sessions s ON s.id=a.session_id JOIN subjects su ON su.id=s.subject_id "
        "LEFT JOIN period_slots ps ON ps.section=s.section AND ps.period_no=s.period_no "
        "WHERE a.student_id=? AND s.status='ended' ORDER BY s.id DESC LIMIT 12", (me["id"],))
    day = datetime.now().weekday()
    timeline = []
    if day < 6 and me["section"]:
        tt = timetable_payload(me["section"])
        for slot in tt["slots"]:
            cell = tt["cells"].get("%d-%d" % (day, slot["period_no"]))
            timeline.append({"period_no": slot["period_no"], "start": slot["start_time"], "end": slot["end_time"],
                             "label": slot["label"], "is_break": slot["is_break"],
                             "subject": cell["subject"] if cell and cell["subject_id"] else None,
                             "teacher": cell["teacher"] if cell and cell["subject_id"] else None,
                             "room": cell["room"] if cell else None})
    return jsonify(subjects=subjects, recent=[dict(r) for r in recent], today=timeline,
                   day=scheduler.DAYS[day] if day < 6 else "Sunday", now=datetime.now().strftime("%H:%M"),
                   face_samples=engine.sample_count(me["id"]))


# ----------------------------------------------------------- notifications
@app.get("/api/notifications")
@api()
def notifications(me):
    rows = db.query("SELECT id, kind, title, body, created_at, is_read FROM notifications WHERE user_id=? "
                    "ORDER BY id DESC LIMIT 50", (me["id"],))
    unread = db.query("SELECT COUNT(*) AS n FROM notifications WHERE user_id=? AND is_read=0", (me["id"],), one=True)["n"]
    return jsonify(notifications=[dict(r) for r in rows], unread=unread)


@app.post("/api/notifications/read")
@api()
def notifications_read(me):
    nid = body().get("id")
    if nid:
        db.execute("UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?", (nid, me["id"]))
    else:
        db.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (me["id"],))
    return jsonify(ok=True)


@app.errorhandler(404)
def not_found(_e):
    if request.path.startswith("/api/"):
        return jsonify(error="Not found."), 404
    return redirect("/")


if __name__ == "__main__":
    scheduler.start()
    print("Haajiri is running -> http://127.0.0.1:5000  (face engine: %s)" % engine.status()["backend_label"])
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
