"""Live attendance sessions.

A Runner belongs to one attendance session. It receives frames either from a server-side
camera (USB / RTSP / HTTP stream, read in a background thread) or from the teacher's
browser camera (frames POSTed to the API), recognises faces and marks students present
once the same face has been seen CONFIRM_HITS times within CONFIRM_WINDOW_SEC seconds.
"""
import os
import threading
import time

import cv2

import config
import db
from face_engine import engine, draw_faces

# TCP is far more reliable than UDP for RTSP CCTV cameras.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

STREAM_WIDTH = 960
PROCESS_EVERY_SEC = 0.25


class Runner:
    def __init__(self, session_id, section, source):
        self.session_id = session_id
        self.section = section
        self.source = source            # "browser" or a camera source string
        self.lock = threading.Lock()
        self.names = {}                 # student_id -> name
        self.hits = {}                  # student_id -> [timestamps]
        self.present = set()
        self.latest_jpeg = None
        self.state = "live" if source == "browser" else "starting"
        self.message = ""
        self.stop_event = threading.Event()
        self.thread = None
        self._load_roster()

    # ------------------------------------------------------------------ roster
    def _load_roster(self):
        rows = db.query(
            "SELECT u.id, u.name, a.status FROM users u "
            "JOIN attendance a ON a.student_id=u.id AND a.session_id=? "
            "WHERE u.role='student'", (self.session_id,))
        for r in rows:
            self.names[r["id"]] = r["name"]
            if r["status"] in ("present", "late"):
                self.present.add(r["id"])

    def sync_manual(self, student_id, status):
        """Keep the in-memory state in step with a manual change by the teacher."""
        with self.lock:
            if status in ("present", "late"):
                self.present.add(student_id)
            else:
                self.present.discard(student_id)
                self.hits.pop(student_id, None)

    # -------------------------------------------------------------- processing
    def process(self, frame):
        faces = engine.recognize(frame)
        now = time.time()
        confirmed = []
        with self.lock:
            for f in faces:
                sid = f["student_id"]
                if sid is None or sid not in self.names:
                    continue
                stamps = [t for t in self.hits.get(sid, []) if now - t <= config.CONFIRM_WINDOW_SEC]
                if not stamps or now - stamps[-1] >= 0.4:      # count one hit per ~0.4 s
                    stamps.append(now)
                self.hits[sid] = stamps
                if len(stamps) >= config.CONFIRM_HITS and sid not in self.present:
                    self.present.add(sid)
                    confirmed.append((sid, f["confidence"]))
        for sid, conf in confirmed:
            self._mark_present(sid, conf)
        return faces

    def _mark_present(self, student_id, confidence):
        # A manual decision by the teacher is never overwritten by the camera.
        db.execute(
            "UPDATE attendance SET status='present', marked_at=?, confidence=?, method='face' "
            "WHERE session_id=? AND student_id=? AND status!='present' "
            "AND (method IS NULL OR method!='manual')",
            (db.now_str(), round(confidence, 1), self.session_id, student_id))

    def annotate(self, frame, faces):
        out = draw_faces(frame.copy(), faces, self.names)
        h, w = out.shape[:2]
        if w > STREAM_WIDTH:
            out = cv2.resize(out, (STREAM_WIDTH, int(h * STREAM_WIDTH / w)))
        ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return buf.tobytes() if ok else None

    # ------------------------------------------------------------ camera thread
    def start(self):
        if self.source == "browser" or (self.thread and self.thread.is_alive()):
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True, name="camera-%s" % self.session_id)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.state = "stopped"

    def _open(self):
        src = int(self.source) if str(self.source).strip().isdigit() else self.source
        return cv2.VideoCapture(src)

    def _loop(self):
        cap, last = None, 0.0
        while not self.stop_event.is_set():
            if cap is None or not cap.isOpened():
                cap = self._open()
                if not cap.isOpened():
                    self.state = "error"
                    self.message = "Cannot open the camera. Check the address, network and login."
                    cap.release()
                    cap = None
                    self.stop_event.wait(3)
                    continue
            ok, frame = cap.read()
            if not ok or frame is None:
                self.state = "error"
                self.message = "Lost the camera signal. Trying to reconnect."
                cap.release()
                cap = None
                self.stop_event.wait(1.5)
                continue
            self.state, self.message = "live", ""
            if time.time() - last < PROCESS_EVERY_SEC:
                continue                      # keep draining the buffer so the view stays current
            last = time.time()
            try:
                self.latest_jpeg = self.annotate(frame, self.process(frame))
            except Exception as exc:          # never let one bad frame kill the session
                self.message = "Recognition error: %s" % exc
        if cap is not None:
            cap.release()


_runners = {}
_runners_lock = threading.Lock()


def get_runner(session_row, create=True):
    """Return the Runner for a session, rebuilding it after a server restart."""
    sid = session_row["id"]
    with _runners_lock:
        runner = _runners.get(sid)
        if runner is None and create and session_row["status"] == "active":
            runner = Runner(sid, session_row["section"], session_row["camera_source"] or "browser")
            _runners[sid] = runner
            runner.start()
        return runner


def stop_runner(session_id):
    with _runners_lock:
        runner = _runners.pop(session_id, None)
    if runner:
        runner.stop()


def test_camera(source, timeout=8):
    """Try to open a camera and grab one frame. Returns (ok, message)."""
    result = {}

    def work():
        cap = None
        try:
            src = int(source) if str(source).strip().isdigit() else source
            cap = cv2.VideoCapture(src)
            if not cap.isOpened():
                result["msg"] = "Could not open the camera. Check the address and login."
                return
            ok, frame = cap.read()
            if ok and frame is not None:
                result["ok"] = True
                result["msg"] = "Connected. Frame size %dx%d." % (frame.shape[1], frame.shape[0])
            else:
                result["msg"] = "Opened the camera but received no picture."
        except Exception as exc:
            result["msg"] = "Camera error: %s" % exc
        finally:
            if cap is not None:
                cap.release()

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return False, "The camera did not answer within %d seconds." % timeout
    return bool(result.get("ok")), result.get("msg", "Unknown error.")
