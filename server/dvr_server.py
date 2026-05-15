import cv2
import threading
import time
import os
import json
import datetime
import numpy as np
from flask import Flask, Response, jsonify, request, render_template_string
from config import CAMERAS, SERVER, AUTH
from ai_enhancer import AIEnhancer, AIMotionDetector

app = Flask(__name__)
streams = {}
recordings = {}

HTML_PAGE = '''
<!DOCTYPE html>
<html dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI DVR - كاميرات</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:system-ui,sans-serif}
body{background:#0a0a1a;color:#fff;padding:20px}
h1{color:#00d2ff;margin-bottom:8px;font-size:22px}
.sub{color:#666;font-size:13px;margin-bottom:20px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:16px}
.cam-card{background:#16213e;border-radius:12px;overflow:hidden}
.cam-card .header{padding:12px 16px;display:flex;justify-content:space-between;align-items:center}
.cam-card .name{font-weight:600;font-size:14px}
.cam-card .badge{font-size:11px;padding:3px 10px;border-radius:20px}
.badge.on{background:#0a3a0a;color:#0f0}
.badge.off{background:#3a0a0a;color:#f44}
.cam-card img{width:100%;display:block;aspect-ratio:16/9;object-fit:cover;background:#000}
.cam-card .footer{padding:8px 16px;display:flex;justify-content:space-between;font-size:11px;color:#666}
.cam-card .ai-badge{background:linear-gradient(135deg, rgba(0,210,255,.15), rgba(124,58,237,.15));color:#00d2ff;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600}
.login{max-width:400px;margin:100px auto;background:#16213e;padding:30px;border-radius:16px}
.login h2{margin-bottom:16px}
.login input{width:100%;padding:12px;margin:8px 0;background:#0a0a1a;border:1px solid #333;border-radius:8px;color:#fff}
.login button{width:100%;padding:12px;background:#00d2ff;border:none;border-radius:8px;color:#000;font-weight:bold;cursor:pointer}
.ai-bar{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}
.ai-btn{padding:8px 16px;border-radius:20px;border:1px solid #333;background:transparent;color:#888;font-size:12px;cursor:pointer}
.ai-btn.on{background:rgba(0,210,255,.1);border-color:#00d2ff33;color:#00d2ff}
</style>
</head>
<body>
{% if not authed %}
<div class="login">
<h2>تسجيل الدخول</h2>
<form method="post">
<input name="username" placeholder="اسم المستخدم" required>
<input name="password" type="password" placeholder="كلمة السر" required>
<button type="submit">دخول</button>
</form>
</div>
{% else %}
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
<h1>📹 AI DVR</h1>
<span style="font-size:12px;color:#666">{{ cams|length }} كاميرات</span>
</div>
<div class="sub">🤖 AI Enhancement • Motion Detection • 24/7 Recording</div>
<div class="ai-bar">
<button class="ai-btn on" onclick="toggleAI('enhance')">✨ AI Enhance</button>
<button class="ai-btn on" onclick="toggleAI('motion')">🎯 AI Motion</button>
<button class="ai-btn" onclick="toggleAI('super_res')">🔍 Super Res</button>
</div>
<div class="grid">
{% for cam in cams %}
<div class="cam-card">
<div class="header">
<span class="name">{{ cam.name }}</span>
<span><span class="badge {{ 'on' if cam.on else 'off' }}">{{ '● مباشر' if cam.on else '● معطل' }}</span></span>
</div>
{% if cam.on %}
<img src="/stream/{{ cam.id }}" alt="{{ cam.name }}">
<div class="footer"><span>⚡ {{ cam.fps }} FPS</span><span class="ai-badge">✦ AI</span></div>
{% else %}
<div style="padding:60px;text-align:center;color:#666">⚠️ الكاميرا غير متصلة</div>
{% endif %}
</div>
{% endfor %}
</div>
<script>
function toggleAI(feature) {
  fetch('/api/ai/toggle/'+feature).then(r=>r.json()).then(d=>{
    document.querySelectorAll('.ai-btn').forEach(b=>b.classList.remove('on'));
    if(d.enhance) document.querySelectorAll('.ai-btn')[0].classList.add('on');
    if(d.motion) document.querySelectorAll('.ai-btn')[1].classList.add('on');
    if(d.super_res) document.querySelectorAll('.ai-btn')[2].classList.add('on');
  });
}
</script>
{% endif %}
</body>
</html>
'''


class AIState:
    ai_enhance = SERVER.get("ai_enhance", True)
    ai_super_res = SERVER.get("ai_super_res", False)
    ai_motion = SERVER.get("ai_motion", True)


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
        self.enhancer = AIEnhancer(enable_super_res=False)
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
        while self.running:
            try:
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


@app.route("/")
def index():
    authed = request.cookies.get("auth") == "1"
    if request.method == "POST":
        if request.form.get("username") == AUTH.get("username", "admin") and \
           request.form.get("password") == AUTH.get("password", "admin"):
            authed = True

    cams = [{"id": sid, "name": s.name, "on": s.online} for sid, s in streams.items()]
    resp = app.make_response(render_template_string(
        HTML_PAGE, authed=authed, cams=cams
    ))
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
    print(f"🚀 DVR Server running on http://{SERVER['host']}:{SERVER['port']}")
    app.run(host=SERVER["host"], port=SERVER["port"], debug=False, threaded=True)
