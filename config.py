"""Central configuration for FaceAttend (AI face-recognition attendance)."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
FACES_DIR = os.path.join(DATA_DIR, "faces")
EXPORTS_DIR = os.path.join(DATA_DIR, "exports")
MODELS_DIR = os.path.join(BASE_DIR, "models")
DB_PATH = os.path.join(DATA_DIR, "attendance.db")

# Change these before any real use (set as environment variables).
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
TEACHER_REGISTER_CODE = os.environ.get("TEACHER_CODE", "MVJ2026")

# "0" = first webcam, or an RTSP URL such as rtsp://user:pass@192.168.1.64:554/Streaming/Channels/101
DEFAULT_CAMERA_SOURCE = os.environ.get("CAMERA_SOURCE", "0")

REMINDER_MINUTES = 5          # notify students/teacher this long before a period starts
CONFIRM_HITS = 3              # a face must be recognised this many times ...
CONFIRM_WINDOW_SEC = 10       # ... within this many seconds to be marked present
LBPH_THRESHOLD = 80.0         # LBPH distance: lower is a closer match
SFACE_THRESHOLD = 0.363       # SFace cosine similarity: higher is a closer match

for _d in (DATA_DIR, FACES_DIR, EXPORTS_DIR, MODELS_DIR):
    os.makedirs(_d, exist_ok=True)
