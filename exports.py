"""Excel reports for teachers (openpyxl)."""
import os
import re

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import config
import db

INK = "101435"
BLUE = "4338FF"
FILL_PRESENT = PatternFill("solid", fgColor="D5F3EA")
FILL_LATE = PatternFill("solid", fgColor="FFF0CC")
FILL_ABSENT = PatternFill("solid", fgColor="FADADF")
FILL_HEAD = PatternFill("solid", fgColor=INK)
FILL_SOFT = PatternFill("solid", fgColor="EEF0FF")
THIN = Side(style="thin", color="D8D6EA")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
STATUS_FILL = {"present": FILL_PRESENT, "late": FILL_LATE, "absent": FILL_ABSENT}
PERIOD_TEXT = lambda label, n: label or ("Period %s" % n if n else "-")


def _slug(text):
    return re.sub(r"[^A-Za-z0-9]+", "-", str(text)).strip("-") or "x"


def _header_row(ws, row, values):
    for col, text in enumerate(values, 1):
        c = ws.cell(row=row, column=col, value=text)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = FILL_HEAD
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = BOX


def _widths(ws, widths):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def build_session_xlsx(session_id):
    """One sheet for one class: who was present, absent or late. Returns the file path."""
    s = db.query(
        "SELECT se.*, su.name AS subject_name, su.code, t.name AS teacher_name, "
        "p.start_time, p.end_time, p.label AS period_label FROM sessions se "
        "JOIN subjects su ON su.id=se.subject_id JOIN users t ON t.id=se.teacher_id "
        "LEFT JOIN period_slots p ON p.section=se.section AND p.period_no=se.period_no "
        "WHERE se.id=?", (session_id,), one=True)
    if s is None:
        raise ValueError("Session not found")
    rows = db.query(
        "SELECT u.roll_no, u.name, a.status, a.marked_at, a.confidence, a.method FROM attendance a "
        "JOIN users u ON u.id=a.student_id WHERE a.session_id=? ORDER BY u.roll_no, u.name", (session_id,))

    wb = Workbook()
    ws = wb.active
    ws.title = "Attendance"
    ws.sheet_view.showGridLines = False

    ws.merge_cells("A1:G1")
    ws["A1"] = "MVJ College of Engineering - Attendance Sheet"
    ws["A1"].font = Font(bold=True, size=15, color=INK)
    ws.row_dimensions[1].height = 26

    when = "%s - %s" % (s["start_time"], s["end_time"]) if s["start_time"] else "-"
    info = [("Subject", "%s (%s)" % (s["subject_name"], s["code"])), ("Section", s["section"]),
            ("Date", s["date"]), ("Period", "%s  (%s)" % (PERIOD_TEXT(s["period_label"], s["period_no"]), when)),
            ("Teacher", s["teacher_name"])]
    for i, (k, v) in enumerate(info, 3):
        ws.cell(row=i, column=1, value=k).font = Font(bold=True, color=BLUE)
        ws.cell(row=i, column=2, value=v)

    present = sum(1 for r in rows if r["status"] == "present")
    late = sum(1 for r in rows if r["status"] == "late")
    absent = sum(1 for r in rows if r["status"] == "absent")
    total = len(rows)
    pct = round(100.0 * (present + late) / total, 1) if total else 0
    stats = [("Total", total), ("Present", present), ("Late", late), ("Absent", absent), ("Attendance %", pct)]
    for i, (k, v) in enumerate(stats):
        a = ws.cell(row=3 + i, column=5, value=k)
        a.font = Font(bold=True, color=BLUE)
        b = ws.cell(row=3 + i, column=6, value=v)
        b.font = Font(bold=True)
        b.fill = FILL_SOFT

    start = 10
    _header_row(ws, start, ["S.No", "Roll No", "Student name", "Status", "Time marked", "Match %", "Marked by"])
    for i, r in enumerate(rows, 1):
        row = start + i
        vals = [i, r["roll_no"], r["name"], (r["status"] or "absent").title(),
                (r["marked_at"] or "")[11:19], r["confidence"] if r["confidence"] is not None else "",
                {"face": "Face recognition", "manual": "Teacher"}.get(r["method"], "-")]
        for col, v in enumerate(vals, 1):
            c = ws.cell(row=row, column=col, value=v)
            c.border = BOX
            c.alignment = Alignment(horizontal="left" if col == 3 else "center")
        ws.cell(row=row, column=4).fill = STATUS_FILL.get(r["status"], FILL_ABSENT)
    ws.freeze_panes = ws.cell(row=start + 1, column=1)
    _widths(ws, [11, 16, 30, 12, 14, 11, 20])

    name = "%s_%s_%s_P%s_s%d.xlsx" % (_slug(s["code"]), _slug(s["section"]), s["date"], s["period_no"] or 0, session_id)
    path = os.path.join(config.EXPORTS_DIR, name)
    wb.save(path)
    db.execute("UPDATE sessions SET export_path=? WHERE id=?", (path, session_id))
    return path


def build_subject_xlsx(subject_id):
    """Whole-semester view for one subject: every class as a column, with totals and a 75% check."""
    sub = db.query(
        "SELECT su.*, t.name AS teacher_name FROM subjects su JOIN users t ON t.id=su.teacher_id WHERE su.id=?",
        (subject_id,), one=True)
    if sub is None:
        raise ValueError("Subject not found")
    sessions = db.query(
        "SELECT se.id, se.date, se.period_no, p.label AS period_label FROM sessions se "
        "LEFT JOIN period_slots p ON p.section=se.section AND p.period_no=se.period_no "
        "WHERE se.subject_id=? AND se.status='ended' ORDER BY se.date, se.id",
        (subject_id,))
    students = db.query(
        "SELECT id, roll_no, name FROM users WHERE role='student' AND section=? ORDER BY roll_no", (sub["section"],))
    marks = {}
    for r in db.query(
            "SELECT a.session_id, a.student_id, a.status FROM attendance a "
            "JOIN sessions s ON s.id=a.session_id WHERE s.subject_id=?", (subject_id,)):
        marks[(r["session_id"], r["student_id"])] = r["status"]

    wb = Workbook()
    ws = wb.active
    ws.title = "Subject report"
    ws.sheet_view.showGridLines = False
    ws["A1"] = "%s (%s) - Section %s" % (sub["name"], sub["code"], sub["section"])
    ws["A1"].font = Font(bold=True, size=15, color=INK)
    ws["A2"] = "Teacher: %s   |   Classes held: %d" % (sub["teacher_name"], len(sessions))
    head = ["Roll No", "Student name"] + ["%s\n%s" % (s["date"][5:], (s["period_label"] or "").replace("Period ", "P") or "-") for s in sessions] \
           + ["Attended", "Classes", "Attendance %"]
    _header_row(ws, 4, head)
    ws.row_dimensions[4].height = 32
    for c in range(1, len(head) + 1):
        ws.cell(row=4, column=c).alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for i, st in enumerate(students, 5):
        ws.cell(row=i, column=1, value=st["roll_no"]).border = BOX
        ws.cell(row=i, column=2, value=st["name"]).border = BOX
        attended = 0
        for j, s in enumerate(sessions, 3):
            status = marks.get((s["id"], st["id"]), "absent")
            attended += status in ("present", "late")
            c = ws.cell(row=i, column=j, value={"present": "P", "late": "L"}.get(status, "A"))
            c.fill = STATUS_FILL.get(status, FILL_ABSENT)
            c.alignment = Alignment(horizontal="center")
            c.border = BOX
        base = 3 + len(sessions)
        ws.cell(row=i, column=base, value=attended).border = BOX
        ws.cell(row=i, column=base + 1, value=len(sessions)).border = BOX
        pct = round(100.0 * attended / len(sessions), 1) if sessions else 0
        pc = ws.cell(row=i, column=base + 2, value=pct)
        pc.border = BOX
        pc.font = Font(bold=True, color="B3261E" if sessions and pct < 75 else "0B7A5E")
        for col in (base, base + 1, base + 2):
            ws.cell(row=i, column=col).alignment = Alignment(horizontal="center")
    ws.freeze_panes = "C5"
    _widths(ws, [14, 28] + [8] * len(sessions) + [10, 9, 13])
    path = os.path.join(config.EXPORTS_DIR, "%s_%s_report.xlsx" % (_slug(sub["code"]), _slug(sub["section"])))
    wb.save(path)
    return path
