"""Fill the database with demo data so you can try every screen straight away.

    python seed_demo.py

Teacher login : rao@mvj.edu   / demo123
Student login : 1MJ23CS001    / demo123   (roll numbers 1MJ23CS001 ... 1MJ23CS012, section 5A)
Delete data/attendance.db to start again with an empty app.
"""
import random
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

import db
import exports
import scheduler

NAMES = ["Akash Kumar", "Meera Nair", "Ravi Shetty", "Ananya Rao", "Karthik Gowda", "Sneha Patil",
         "Imran Khan", "Divya Reddy", "Rohan Das", "Pooja Hegde", "Vikram Singh", "Lakshmi Iyer"]
SUBJECTS = [("Operating Systems", "CS501"), ("Database Management", "CS502"), ("Computer Networks", "CS503"),
            ("Software Engineering", "CS504"), ("Theory of Computation", "CS505"), ("Python Lab", "CS506")]


def main():
    db.init_db()
    if db.query("SELECT 1 FROM users LIMIT 1", one=True):
        print("The database already has users. Delete data/attendance.db first to reseed.")
        return
    pw = generate_password_hash("demo123")
    mk = lambda *a: db.execute("INSERT INTO users(name,email,password_hash,role,roll_no,section,created_at) VALUES(?,?,?,?,?,?,?)", a)
    rao = mk("Prof. Rao", "rao@mvj.edu", pw, "teacher", None, None, db.now_str())
    other = mk("Prof. Lakshmi", "lakshmi@mvj.edu", pw, "teacher", None, None, db.now_str())
    students = [mk(n, "%s@student.mvj.edu" % n.split()[0].lower(), pw, "student", "1MJ23CS%03d" % i, "5A", db.now_str())
                for i, n in enumerate(NAMES, 1)]
    subjects = []
    for i, (name, code) in enumerate(SUBJECTS):
        subjects.append(db.execute("INSERT INTO subjects(name,code,section,teacher_id) VALUES(?,?,?,?)",
                                   (name, code, "5A", rao if i < 3 else other)))
    scheduler.reset_slots("5A")
    scheduler.suggest_timetable("5A")

    random.seed(7)
    day = datetime.now() - timedelta(days=14)
    for k in range(12):                                   # past classes, so percentages look real
        day += timedelta(days=1)
        if day.weekday() == 6:
            continue
        sub = subjects[k % 3]
        sid = db.execute(
            "INSERT INTO sessions(subject_id,teacher_id,section,period_no,date,started_at,ended_at,status,camera_source) "
            "VALUES(?,?,?,?,?,?,?, 'ended','browser')",
            (sub, rao, "5A", 1 + k % 4, day.strftime("%Y-%m-%d"), day.strftime("%Y-%m-%d 09:00:00"), day.strftime("%Y-%m-%d 09:55:00")))
        for j, st in enumerate(students):
            keen = 0.95 if j % 4 else 0.6                  # every 4th student attends less
            status = "present" if random.random() < keen else ("late" if random.random() < 0.2 else "absent")
            db.execute("INSERT INTO attendance(session_id,student_id,status,marked_at,confidence,method) VALUES(?,?,?,?,?,?)",
                       (sid, st, status, day.strftime("%Y-%m-%d 09:05:00") if status != "absent" else None,
                        round(random.uniform(62, 96), 1) if status != "absent" else None, "face" if status != "absent" else None))
        exports.build_session_xlsx(sid)
    print("Demo data ready.\n  Teacher: rao@mvj.edu / demo123\n  Student: 1MJ23CS001 / demo123")


if __name__ == "__main__":
    main()
