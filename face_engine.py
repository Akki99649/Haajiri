"""Face detection + recognition.

Two interchangeable back-ends:

* ``sface``  - OpenCV YuNet detector + SFace embeddings (accurate; needs two ONNX files in models/).
* ``lbph``   - Haar/LBP cascade + LBPH recogniser (works out of the box with opencv-contrib).

The engine picks ``sface`` automatically when the ONNX files exist, otherwise ``lbph``.
"""
import glob
import os
import threading
import time

import cv2
import numpy as np

import config

YUNET_PATH = os.path.join(config.MODELS_DIR, "face_detection_yunet_2023mar.onnx")
SFACE_PATH = os.path.join(config.MODELS_DIR, "face_recognition_sface_2021dec.onnx")
LBPH_PATH = os.path.join(config.DATA_DIR, "lbph_model.yml")
GALLERY_PATH = os.path.join(config.DATA_DIR, "sface_gallery.npz")
MAX_WIDTH = 960


def _load_cascade():
    """Return the first face cascade that OpenCV can actually load, or None."""
    candidates = []
    try:
        candidates.append(os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))
    except Exception:
        pass
    candidates.append(os.path.join(config.MODELS_DIR, "lbpcascade_frontalface_opencv.xml"))
    for path in candidates:
        if os.path.exists(path):
            cascade = cv2.CascadeClassifier(path)
            if not cascade.empty():
                return cascade
    return None


def draw_faces(frame, faces, names):
    """Draw boxes + labels. `faces` come from FaceEngine.recognize()."""
    for f in faces:
        x, y, w, h = f["box"]
        sid = f.get("student_id")
        known = sid is not None and sid in names
        color = (80, 200, 120) if known else (70, 70, 230)
        label = "%s  %d%%" % (names[sid], f["confidence"]) if known else "Unknown"
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        cv2.rectangle(frame, (x, max(0, y - th - 10)), (x + tw + 10, y), color, -1)
        cv2.putText(frame, label, (x + 5, max(th, y - 6)), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (255, 255, 255), 1, cv2.LINE_AA)
    return frame


class FaceEngine:
    def __init__(self):
        self.lock = threading.RLock()
        self.backend = "lbph"
        self.cascade = None
        self.detector = None
        self.recognizer = None
        self.lbph = None
        self.gallery = {}  # student_id -> (n,128) float32, L2-normalised (sface only)
        self.error = None
        self._setup()
        self.load()

    # ------------------------------------------------------------------ setup
    def _setup(self):
        if os.path.exists(YUNET_PATH) and os.path.exists(SFACE_PATH) and hasattr(cv2, "FaceDetectorYN"):
            try:
                make_det = getattr(cv2.FaceDetectorYN, "create", None) or cv2.FaceDetectorYN_create
                make_rec = getattr(cv2.FaceRecognizerSF, "create", None) or cv2.FaceRecognizerSF_create
                self.detector = make_det(YUNET_PATH, "", (320, 320), 0.8, 0.3, 5000)
                self.recognizer = make_rec(SFACE_PATH, "")
                self.backend = "sface"
                return
            except Exception as exc:  # fall back to LBPH
                self.error = "SFace failed to load (%s); using LBPH" % exc
        self.cascade = _load_cascade()
        if self.cascade is None:
            self.error = ("No face detector could be loaded. Run `python download_models.py` (recommended) "
                          "or install opencv-contrib-python 4.x from requirements.txt.")
        elif not hasattr(cv2, "face"):
            self.error = "cv2.face is missing: install opencv-contrib-python (not opencv-python)."

    def load(self):
        with self.lock:
            if self.backend == "lbph":
                if os.path.exists(LBPH_PATH) and hasattr(cv2, "face"):
                    rec = cv2.face.LBPHFaceRecognizer_create()
                    rec.read(LBPH_PATH)
                    self.lbph = rec
            elif os.path.exists(GALLERY_PATH):
                data = np.load(GALLERY_PATH)
                self.gallery = {int(k): data[k] for k in data.files}

    # -------------------------------------------------------------- detection
    @staticmethod
    def _prep(frame):
        h, w = frame.shape[:2]
        if w > MAX_WIDTH:
            scale = MAX_WIDTH / float(w)
            return cv2.resize(frame, (MAX_WIDTH, int(h * scale))), scale
        return frame, 1.0

    def _detect(self, small):
        """Return [(box(x,y,w,h), row_or_None)] in `small` coordinates."""
        if self.backend == "sface":
            self.detector.setInputSize((small.shape[1], small.shape[0]))
            _, faces = self.detector.detect(small)
            out = []
            if faces is not None:
                for row in faces:
                    x, y, w, h = [int(v) for v in row[:4]]
                    out.append(((max(0, x), max(0, y), w, h), row))
            return out
        if self.cascade is None:
            return []
        gray = cv2.equalizeHist(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY))
        rects = self.cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        return [((int(x), int(y), int(w), int(h)), None) for (x, y, w, h) in rects]

    def _lbph_crop(self, small, box):
        x, y, w, h = box
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        face = gray[y:y + h, x:x + w]
        if face.size == 0:
            return None
        return cv2.equalizeHist(cv2.resize(face, (100, 100)))

    def _embed(self, small, row):
        aligned = self.recognizer.alignCrop(small, row)
        feat = self.recognizer.feature(aligned).astype(np.float32).reshape(-1)
        return feat / (np.linalg.norm(feat) + 1e-9)

    # ------------------------------------------------------------ recognition
    def recognize(self, frame):
        """Detect and identify every face. confidence is a 0-100 match percentage."""
        small, scale = self._prep(frame)
        results = []
        with self.lock:
            for box, row in self._detect(small):
                sid, conf = self._identify(small, box, row)
                x, y, w, h = [int(v / scale) for v in box]
                results.append({"box": (x, y, w, h), "student_id": sid, "confidence": conf})
        return results

    def _identify(self, small, box, row):
        if self.backend == "lbph":
            if self.lbph is None:
                return None, 0.0
            crop = self._lbph_crop(small, box)
            if crop is None:
                return None, 0.0
            label, dist = self.lbph.predict(crop)
            pct = max(0.0, min(100.0, 100.0 * (1.0 - dist / (2.0 * config.LBPH_THRESHOLD))))  # 50% = threshold
            return (int(label), pct) if dist <= config.LBPH_THRESHOLD else (None, pct)
        if not self.gallery:
            return None, 0.0
        feat = self._embed(small, row)
        best_id, best = None, -1.0
        for sid, mat in self.gallery.items():
            score = float(np.max(mat @ feat))
            if score > best:
                best_id, best = sid, score
        pct = max(0.0, min(100.0, best * 100.0))
        return (best_id, pct) if best >= config.SFACE_THRESHOLD else (None, pct)

    # ------------------------------------------------------------- enrolment
    def add_face_image(self, student_id, img):
        """Save a photo for a student if it contains a face. Returns True/False."""
        small, _ = self._prep(img)
        with self.lock:
            faces = self._detect(small)
        if not faces:
            return False
        folder = os.path.join(config.FACES_DIR, str(student_id))
        os.makedirs(folder, exist_ok=True)
        name = "%d_%03d.jpg" % (int(time.time() * 1000), len(os.listdir(folder)) + 1)
        cv2.imwrite(os.path.join(folder, name), small)
        return True

    def sample_count(self, student_id):
        return len(glob.glob(os.path.join(config.FACES_DIR, str(student_id), "*.jpg")))

    def clear_samples(self, student_id):
        for path in glob.glob(os.path.join(config.FACES_DIR, str(student_id), "*.jpg")):
            os.remove(path)

    def train(self):
        """(Re)build the recogniser from every saved photo."""
        with self.lock:
            if self.backend == "lbph":
                crops, labels = [], []
                for folder in sorted(glob.glob(os.path.join(config.FACES_DIR, "*"))):
                    if not os.path.basename(folder).isdigit():
                        continue
                    sid = int(os.path.basename(folder))
                    for path in sorted(glob.glob(os.path.join(folder, "*.jpg"))):
                        img = cv2.imread(path)
                        if img is None:
                            continue
                        faces = self._detect(img)
                        if not faces:
                            continue
                        box, _ = max(faces, key=lambda f: f[0][2] * f[0][3])
                        crop = self._lbph_crop(img, box)
                        if crop is None:
                            continue
                        crops += [crop, cv2.flip(crop, 1)]
                        labels += [sid, sid]
                if not crops or not hasattr(cv2, "face"):
                    self.lbph = None
                    if os.path.exists(LBPH_PATH):
                        os.remove(LBPH_PATH)
                else:
                    rec = cv2.face.LBPHFaceRecognizer_create(radius=1, neighbors=8, grid_x=8, grid_y=8)
                    rec.train(crops, np.array(labels, dtype=np.int32))
                    rec.write(LBPH_PATH)
                    self.lbph = rec
            else:
                gallery = {}
                for folder in sorted(glob.glob(os.path.join(config.FACES_DIR, "*"))):
                    if not os.path.basename(folder).isdigit():
                        continue
                    sid = int(os.path.basename(folder))
                    feats = []
                    for path in sorted(glob.glob(os.path.join(folder, "*.jpg"))):
                        img = cv2.imread(path)
                        faces = self._detect(img) if img is not None else []
                        if not faces:
                            continue
                        _, row = max(faces, key=lambda f: f[0][2] * f[0][3])
                        feats.append(self._embed(img, row))
                    if feats:
                        gallery[sid] = np.vstack(feats)
                self.gallery = gallery
                if gallery:
                    np.savez(GALLERY_PATH, **{str(k): v for k, v in gallery.items()})
                elif os.path.exists(GALLERY_PATH):
                    os.remove(GALLERY_PATH)
        return self.status()

    def trained_students(self):
        if self.backend == "lbph":
            if self.lbph is None:
                return 0
            try:
                return len(set(int(v) for v in self.lbph.getLabels().reshape(-1)))
            except Exception:
                return 0
        return len(self.gallery)

    def status(self):
        names = {"lbph": "LBPH (built-in)", "sface": "SFace (deep learning)"}
        return {
            "backend": self.backend,
            "backend_label": names[self.backend],
            "trained_students": self.trained_students(),
            "error": self.error,
        }


engine = FaceEngine()
