import cv2
import threading
import time
import os
import json
import datetime
import numpy as np
from flask import Flask, Response, jsonify, request, render_template, send_file
from config import CAMERAS, SERVER, AUTH
from ai_enhancer import AIEnhancer, AIMotionDetector

app = Flask(__name__, template_folder="templates")
app.secret_key = os.urandom(16).hex()
streams = {}
recordings = {}


class AIState:
    ai_enhance = SERVER.get("ai_enhance", True)
    ai_super_res = SERVER.get("ai_super_res", False)
    ai_motion = SERVER.get("ai_motion", True)


def config_data():
    return {
        "cameras": CAMERAS,
        "record_on_motion": SERVER["record_on_motion"],
        "motion_sensitivity": SERVER["motion_sensitivity"],
        "max_days": SERVER["max_days"],
        "jpeg_quality": SERVER.get("jpeg_quality", 75),
        "ai_enhance": AIState.ai_enhance,
        "ai_motion": AIState.ai_motion,
        "ai_quality": SERVER.get("ai_quality", 2),
        "process_width": SERVER.get("process_width", 480),
        "frame_skip": SERVER.get("frame_skip", 2),
        "username": AUTH.get("username", "admin"),
    }


class CameraStream:
    def __init__(self, cam_id, name, url):
        self.id = cam_id
        self.name = name
        self.url = url
        self.cap = None
        self.frame = None
        self.raw_frame = None
        self.running = False
        self.online = False
        self.thread = None
        self.lock = threading.Lock()
        self.last_motion = 0
        self.recording = False
        self.record_writer = None
        self.enhancer = AIEnhancer(config=SERVER)
        self.motion_detector = AIMotionDetector(sensitivity=SERVER["motion_sensitivity"])
        self.fps_counter = 0
        self.last_fps_time = time.time()
        self.current_fps = 0

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        if self.cap:
            self.cap.release()

    def _loop(self):
        import urllib.request as _ur
        t = 0
        while self.running:
            try:
                if self.url.startswith("http://") or self.url.startswith("https://"):
                    try:
                        resp = _ur.urlopen(self.url, timeout=5)
                        raw_bytes = b""
                        while self.running:
                            chunk = resp.read(4096)
                            if not chunk:
                                break
                            raw_bytes += chunk
                            start = raw_bytes.find(b"\xff\xd8")
                            end = raw_bytes.find(b"\xff\xd9")
                            if start != -1 and end != -1 and end > start:
                                jpeg_data = raw_bytes[start:end+2]
                                raw_bytes = raw_bytes[end+2:]
                                raw = cv2.imdecode(np.frombuffer(jpeg_data, np.uint8), cv2.IMREAD_COLOR)
                                if raw is not None:
                                    self.online = True
                                    processed = raw.copy()
                                    if AIState.ai_enhance:
                                        processed = self.enhancer.enhance(processed)
                                    with self.lock:
                                        self.raw_frame = raw
                                        self.frame = processed
                                    self.fps_counter += 1
                                    now = time.time()
                                    if now - self.last_fps_time >= 1:
                                        self.current_fps = self.fps_counter
                                        self.fps_counter = 0
                                        self.last_fps_time = now
                                time.sleep(0.03)
                    except Exception:
                        self.online = False
                        resp = None
                        time.sleep(2)
                    continue

                if self.cap is None or not self.cap.isOpened():
                    self.cap = cv2.VideoCapture(self.url)
                    if not self.cap.isOpened():
                        self.online = False
                        time.sleep(2)
                        continue

                ret, raw = self.cap.read()
                if not ret:
                    self.cap.release()
                    self.cap = None
                    self.online = False
                    time.sleep(1)
                    continue

                self.online = True
                processed = raw.copy()

                if AIState.ai_enhance:
                    processed = self.enhancer.enhance(processed)

                motion = False
                if AIState.ai_motion and SERVER["record_on_motion"]:
                    motion, _, processed = self.motion_detector.detect(processed)

                with self.lock:
                    self.raw_frame = raw
                    self.frame = processed

                if SERVER["record_on_motion"]:
                    if motion:
                        self.last_motion = time.time()
                        if not self.recording:
                            self._start_recording(raw)
                    if self.recording and (time.time() - self.last_motion > 5):
                        self._stop_recording()

                if self.recording and self.record_writer:
                    self.record_writer.write(raw)

                self.fps_counter += 1
                now = time.time()
                if now - self.last_fps_time >= 1:
                    self.current_fps = self.fps_counter
                    self.fps_counter = 0
                    self.last_fps_time = now

            except Exception:
                self.online = False
                time.sleep(1)

    def _start_recording(self, frame):
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(SERVER["record_path"], str(self.id))
        os.makedirs(path, exist_ok=True)
        filename = os.path.join(path, f"{ts}.mp4")
        h, w = frame.shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self.record_writer = cv2.VideoWriter(filename, fourcc, 20.0, (w, h))
        self.recording = True
        self._record_file = filename

        if self.id not in recordings:
            recordings[self.id] = []
        recordings[self.id].append({
            "file": filename,
            "start": ts,
            "camera": self.name,
        })

    def _stop_recording(self):
        if self.record_writer:
            self.record_writer.release()
        self.recording = False
        self.record_writer = None

    def write_record_frame(self, frame):
        if self.record_writer and self.recording:
            self.record_writer.write(frame)

    def get_frame_jpeg(self, enhance=True):
        with self.lock:
            if self.frame is None:
                return None
            frame = self.frame if enhance else self.raw_frame
            if frame is None:
                return None
            quality = SERVER.get("jpeg_quality", 75)
            ret, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
            if ret:
                return jpeg.tobytes()
        return None

    def get_frame(self):
        with self.lock:
            return self.frame.copy() if self.frame is not None else None


def init_cameras():
    for i, cfg in enumerate(CAMERAS):
        if not cfg["enabled"]:
            continue
        cam = CameraStream(i, cfg["name"], cfg["url"])
        streams[i] = cam
        cam.start()


@app.route("/", methods=["GET", "POST"])
def index():
    authed = request.cookies.get("auth") == "1"
    if request.method == "POST":
        if request.form.get("username") == AUTH.get("username", "admin") and \
           request.form.get("password") == AUTH.get("password", "admin"):
            authed = True

    resp = app.make_response(render_template("index.html", authed=authed))
    if authed and not request.cookies.get("auth"):
        resp.set_cookie("auth", "1")
    return resp


@app.route("/stream/<int:cam_id>")
def stream(cam_id):
    if request.cookies.get("auth") != "1":
        return "غير مصرح", 401

    def generate():
        while True:
            cam = streams.get(cam_id)
            if not cam:
                break
            jpeg = cam.get_frame_jpeg()
            if jpeg:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            time.sleep(0.05)

    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/cameras")
def api_cameras():
    return jsonify([
        {"id": sid, "name": s.name, "online": s.online, "fps": s.current_fps}
        for sid, s in streams.items()
    ])


@app.route("/api/ai/status")
def api_ai_status():
    return jsonify({
        "enhance": AIState.ai_enhance,
        "super_res": AIState.ai_super_res,
        "motion": AIState.ai_motion,
    })


@app.route("/api/ai/toggle/<feature>")
def api_ai_toggle(feature):
    if feature == "enhance":
        AIState.ai_enhance = not AIState.ai_enhance
    elif feature == "super_res":
        AIState.ai_super_res = not AIState.ai_super_res
        for s in streams.values():
            s.enhancer.enable_super_res = AIState.ai_super_res
            if AIState.ai_super_res:
                s.enhancer._download_models()
    elif feature == "motion":
        AIState.ai_motion = not AIState.ai_motion
    return api_ai_status()


@app.route("/api/snapshot/<int:cam_id>")
def api_snapshot(cam_id):
    cam = streams.get(cam_id)
    if not cam:
        return "غير موجودة", 404
    jpeg = cam.get_frame_jpeg()
    if not jpeg:
        return "لا يوجد", 503
    return Response(jpeg, mimetype="image/jpeg")


@app.route("/api/recordings")
def api_recordings():
    all_recs = []
    for cid, recs in recordings.items():
        all_recs.extend(recs)
    all_recs.sort(key=lambda r: r["start"], reverse=True)
    return jsonify(all_recs)


@app.route("/api/status")
def api_status():
    return jsonify({
        "cameras": len(streams),
        "online": sum(1 for s in streams.values() if s.online),
        "recording": sum(1 for s in streams.values() if s.recording),
        "ai_enhance": AIState.ai_enhance,
        "ai_super_res": AIState.ai_super_res,
        "ai_motion": AIState.ai_motion,
    })


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.cookies.get("auth") != "1":
        return jsonify({"error": "unauthorized"}), 401

    if request.method == "GET":
        return jsonify(config_data())

    data = request.json
    if not data:
        return jsonify({"error": "no data"}), 400

    if "password" in data and data["password"]:
        AUTH["password"] = data["password"]

    if "ai_enhance" in data:
        AIState.ai_enhance = bool(data["ai_enhance"])
    if "ai_motion" in data:
        AIState.ai_motion = bool(data["ai_motion"])

    for key in ("record_on_motion", "motion_sensitivity", "max_days", "jpeg_quality",
                 "ai_quality", "process_width", "frame_skip"):
        if key in data:
            SERVER[key] = data[key]

    for s in streams.values():
        s.enhancer.quality = SERVER.get("ai_quality", 2)
        s.enhancer.process_width = SERVER.get("process_width", 480)
        s.enhancer.frame_skip = SERVER.get("frame_skip", 2)
        s.enhancer.enable_super_res = AIState.ai_super_res

    return jsonify({"ok": True, **config_data()})


@app.route("/api/ptz/<int:cam_id>/<command>")
def api_ptz(cam_id, command):
    if request.cookies.get("auth") != "1":
        return jsonify({"error": "unauthorized"}), 401
    cam = streams.get(cam_id)
    if not cam:
        return jsonify({"error": "not found"}), 404
    return jsonify({"ok": True, "command": command, "camera": cam_id})


@app.route("/api/download/<path:filepath>")
def api_download(filepath):
    if request.cookies.get("auth") != "1":
        return "غير مصرح", 401
    if not os.path.exists(filepath):
        return "الملف غير موجود", 404
    return send_file(filepath, as_attachment=True)


def cleanup_old():
    while True:
        time.sleep(3600)
        now = time.time()
        max_age = SERVER["max_days"] * 86400
        for cid, recs in recordings.items():
            for r in recs[:]:
                try:
                    age = now - os.path.getmtime(r["file"])
                    if age > max_age:
                        os.remove(r["file"])
                        recs.remove(r)
                except:
                    pass


if __name__ == "__main__":
    os.makedirs(SERVER["record_path"], exist_ok=True)
    init_cameras()
    threading.Thread(target=cleanup_old, daemon=True).start()
    print(f"DVR Server running on http://{SERVER['host']}:{SERVER['port']}")
    app.run(host=SERVER["host"], port=SERVER["port"], debug=False, threaded=True)
