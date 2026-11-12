"""Download the two OpenCV Zoo models that give much better accuracy than the built-in LBPH engine.

    python download_models.py

After the download, restart the app: it switches to the SFace engine automatically.
Then re-save each student's face photos (or press "Retrain" in Face setup) so embeddings are rebuilt.
"""
import os
import urllib.request

BASE = "https://github.com/opencv/opencv_zoo/raw/main/models"
FILES = {
    "face_detection_yunet_2023mar.onnx": BASE + "/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "face_recognition_sface_2021dec.onnx": BASE + "/face_recognition_sface/face_recognition_sface_2021dec.onnx",
}
MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")


def main():
    os.makedirs(MODELS_DIR, exist_ok=True)
    for name, url in FILES.items():
        dest = os.path.join(MODELS_DIR, name)
        if os.path.exists(dest) and os.path.getsize(dest) > 100_000:
            print("already have", name)
            continue
        print("downloading", name, "...")
        urllib.request.urlretrieve(url, dest)
        print("  saved %.1f MB" % (os.path.getsize(dest) / 1e6))
    print("Done. Restart the app to use the SFace engine.")


if __name__ == "__main__":
    main()
