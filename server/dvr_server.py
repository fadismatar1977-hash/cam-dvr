import cv2
import threading
import time
import os
import json
import datetime
import numpy as np
import shutil
import smtplib
import urllib.request as _ur
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from flask import Flask, Response, jsonify, request, render_template, send_file
from config import CAMERAS, SERVER, AUTH, TELEGRAM, EMAIL
from ai_enhancer import AIEnhancer, AIMotionDetector

app = Flask(__name__, template_folder="templates")
app.secret_key = os.urandom(16).hex()
streams = {}
recordings = {}
_start_time = time.time()


class AIState:
    ai_enhance = SERVER.get("ai_enhance", True)
    ai_super_res = SERVER.get("ai_super_res", False)
    ai_motion = SERVER.get("ai_motion", True)


def config_data():
    return {
        "cameras": CAMERAS,
        "record_on_motion": SERVER["recording_mode"] != "off",
        "recording_mode": SERVER.get("recording_mode", "motion"),
        "schedule_start": SERVER.get("schedule_start", 0),
        "schedule_end": SERVER.get("schedule_end", 24),
        "motion_sensitivity": SERVER["motion_sensitivity"],
        "max_days": SERVER["max_days"],
        "jpeg_quality": SERVER.get("jpeg_quality", 75),
        "ai_enhance": AIState.ai_enhance,
        "ai_motion": AIState.ai_motion,
        "ai_quality": SERVER.get("ai_quality", 2),
        "process_width": SERVER.get("process_width", 480),
        "frame_skip": SERVER.get("frame_skip", 2),
        "telegram_enabled": TELEGRAM.get("enabled", False),
        "telegram_bot_token": TELEGRAM.get("bot_token", ""),
        "telegram_chat_id": TELEGRAM.get("chat_id", ""),
        "email_enabled": EMAIL.get("enabled", False),
        "email_smtp_server": EMAIL.get("smtp_server", ""),
        "email_smtp_port": EMAIL.get("smtp_port", 587),
        "email_from": EMAIL.get("from_addr", ""),
        "email_to": EMAIL.get("to_addr", ""),
        "username": AUTH.get("username", "admin"),
    }


def send_telegram(message, image_path=None):
    if not TELEGRAM.get("enabled") or not TELEGRAM.get("bot_token") or not TELEGRAM.get("chat_id"):
        return
    try:
        token = TELEGRAM["bot_token"]
        chat_id = TELEGRAM["chat_id"]
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as f:
                data = f.read()
            boundary = "----boundary123"
            body = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="caption"\r\n\r\n{message}\r\n'
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="photo"; filename="snap.jpg"\r\n'
                f"Content-Type: image/jpeg\r\n\r\n"
            ).encode() + data + f"\r\n--{boundary}--\r\n".encode()
            req = _ur.Request(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )
        else:
            data = _ur.parse.urlencode({"chat_id": chat_id, "text": message}).encode()
            req = _ur.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
        _ur.urlopen(req, timeout=10)
    except Exception:
        pass


def send_email(subject, body, image_path=None):
    if not EMAIL.get("enabled"):
        return
    try:
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = EMAIL["from_addr"]
        msg["To"] = EMAIL["to_addr"]
        msg.attach(MIMEText(body, "plain"))
        if image_path and os.path.exists(image_path):
            with open(image_path, "rb") as f:
                img = MIMEImage(f.read())
                img.add_header("Content-Disposition", "attachment", filename="snapshot.jpg")
                msg.attach(img)
        server = smtplib.SMTP(EMAIL["smtp_server"], EMAIL["smtp_port"])
        server.starttls()
        server.login(EMAIL["from_addr"], EMAIL["password"])
        server.send_message(msg)
        server.quit()
    except Exception:
        pass


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
        self._last_notify = 0

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

    def _should_record(self, motion_detected=False):
        mode = SERVER.get("recording_mode", "motion")
        if mode == "off":
            return False
        if mode == "continuous":
            return True
        hour = datetime.datetime.now().hour
        s = SERVER.get("schedule_start", 0)
        e = SERVER.get("schedule_end", 24)
        in_schedule = s <= hour < e
        if mode == "schedule":
            return in_schedule
        if mode == "motion":
            return motion_detected
        return False

    def _loop(self):
        resp = None
        t = 0
        while self.running:
            try:
                if self.url.startswith("http://") or self.url.startswith("https://"):
                    try:
                        if resp is None:
                            resp = _ur.urlopen(self.url, timeout=5)
                        raw_bytes = b""
                        while self.running:
                            chunk = resp.read(4096)
                            if not chunk:
                                resp.close()
                                resp = _ur.urlopen(self.url, timeout=5)
                                continue
                            raw_bytes += chunk
                            start = raw_bytes.find(b"\xff\xd8")
                            end = raw_bytes.find(b"\xff\xd9")
                            if start != -1 and end != -1 and end > start:
                                jpeg_data = raw_bytes[start:end+2]
                                raw_bytes = raw_bytes[end+2:]
                                raw = cv2.imdecode(np.frombuffer(jpeg_data, np.uint8), cv2.IMREAD_COLOR)
                                if raw is not None:
                                    self._process_frame(raw)
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

                self._process_frame(raw)

            except Exception:
                self.online = False
                time.sleep(1)

    def _process_frame(self, raw):
        self.online = True
        processed = raw.copy()
        motion = False

        if AIState.ai_enhance:
            processed = self.enhancer.enhance(processed)

        if AIState.ai_motion:
            motion, _, processed = self.motion_detector.detect(processed)

        with self.lock:
            self.raw_frame = raw
            self.frame = processed

        should_rec = self._should_record(motion)
        now = time.time()

        if should_rec:
            if not self.recording:
                self._start_recording(raw)
            self.last_motion = now
        else:
            if self.recording:
                self._stop_recording()

        if self.recording and self.record_writer:
            self.record_writer.write(raw)

        if motion and now - self._last_notify > 30:
            self._last_notify = now
            notify = threading.Thread(target=self._send_alerts, daemon=True)
            notify.start()

        self.fps_counter += 1
        if now - self.last_fps_time >= 1:
            self.current_fps = self.fps_counter
            self.fps_counter = 0
            self.last_fps_time = now

    def _send_alerts(self):
        snap = self._save_snapshot()
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = f"🚨 حركة في {self.name}\n🕐 {ts}"
        if snap:
            threading.Thread(target=send_telegram, args=(msg, snap), daemon=True).start()
            threading.Thread(target=send_email, args=(f"حركة - {self.name}", msg, snap), daemon=True).start()
        else:
            threading.Thread(target=send_telegram, args=(msg,), daemon=True).start()

    def _save_snapshot(self):
        with self.lock:
            f = self.raw_frame
            if f is None:
                return None
            ret, jpeg = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ret:
                return None
        path = os.path.join(SERVER["record_path"], "snapshots")
        os.makedirs(path, exist_ok=True)
        fname = os.path.join(path, f"snap_{self.id}_{int(time.time())}.jpg")
        with open(fname, "wb") as f:
            f.write(jpeg.tobytes())
        return fname

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
    if request.method == "POST":
        u = request.form.get("username")
        p = request.form.get("password")
        ok = u == AUTH.get("username", "admin") and p == AUTH.get("password", "admin")
        resp = app.make_response(("ok" if ok else "خطأ", 200 if ok else 401))
        if ok:
            resp.set_cookie("auth", "1")
        return resp
    authed = request.cookies.get("auth") == "1"
    if not authed:
        u = request.args.get("username")
        p = request.args.get("password")
        if u == AUTH.get("username", "admin") and p == AUTH.get("password", "admin"):
            authed = True
    resp = app.make_response(render_template("index.html"))
    if authed and not request.cookies.get("auth"):
        resp.set_cookie("auth", "1")
    return resp


@app.route("/stream/<int:cam_id>")
def stream(cam_id):
    if request.cookies.get("auth") != "1":
        return "غير مصرح", 401
    def gen():
        while True:
            cam = streams.get(cam_id)
            if not cam:
                break
            jpeg = cam.get_frame_jpeg()
            if jpeg:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            time.sleep(0.05)
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/cameras")
def api_cameras():
    if request.cookies.get("auth") != "1":
        return "غير مصرح", 401
    return jsonify([
        {"id": sid, "name": s.name, "online": s.online, "fps": s.current_fps, "recording": s.recording}
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
    if request.cookies.get("auth") != "1":
        return "غير مصرح", 401
    cam = streams.get(cam_id)
    if not cam:
        return "غير موجودة", 404
    jpeg = cam.get_frame_jpeg()
    if not jpeg:
        return "لا يوجد", 503
    return Response(jpeg, mimetype="image/jpeg")


@app.route("/api/recordings")
def api_recordings():
    if request.cookies.get("auth") != "1":
        return "غير مصرح", 401
    all_recs = []
    for cid, recs in recordings.items():
        all_recs.extend(recs)
    all_recs.sort(key=lambda r: r["start"], reverse=True)
    return jsonify(all_recs)


@app.route("/api/status")
def api_status():
    if request.cookies.get("auth") != "1":
        return "غير مصرح", 401
    return jsonify({
        "cameras": len(streams),
        "online": sum(1 for s in streams.values() if s.online),
        "recording": sum(1 for s in streams.values() if s.recording),
        "ai_enhance": AIState.ai_enhance,
        "ai_super_res": AIState.ai_super_res,
        "ai_motion": AIState.ai_motion,
    })


@app.route("/api/system")
def api_system():
    if request.cookies.get("auth") != "1":
        return "غير مصرح", 401
    try:
        du = shutil.disk_usage(SERVER["record_path"])
        total_recs = sum(len(v) for v in recordings.values())
        total_size = 0
        for v in recordings.values():
            for r in v:
                try:
                    total_size += os.path.getsize(r["file"])
                except:
                    pass
        uptime = time.time() - _start_time
        return jsonify({
            "uptime": int(uptime),
            "uptime_str": f"{int(uptime//3600)}h {int((uptime%3600)//60)}m",
            "recordings_count": total_recs,
            "recordings_size": total_size,
            "recordings_size_str": f"{total_size/1024/1024:.1f} MB",
            "disk_free": du.free,
            "disk_free_str": f"{du.free/1024/1024/1024:.1f} GB",
            "disk_total": du.total,
            "disk_total_str": f"{du.total/1024/1024/1024:.1f} GB",
            "disk_used": du.used,
            "disk_used_str": f"{du.used/1024/1024/1024:.1f} GB",
            "disk_percent": round(du.used / du.total * 100, 1),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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

    for key in ("recording_mode", "motion_sensitivity", "max_days", "jpeg_quality",
                 "ai_quality", "process_width", "frame_skip", "schedule_start", "schedule_end"):
        if key in data:
            SERVER[key] = data[key]

    if "telegram_enabled" in data:
        TELEGRAM["enabled"] = bool(data["telegram_enabled"])
    if "telegram_bot_token" in data:
        TELEGRAM["bot_token"] = data["telegram_bot_token"]
    if "telegram_chat_id" in data:
        TELEGRAM["chat_id"] = data["telegram_chat_id"]

    if "email_enabled" in data:
        EMAIL["enabled"] = bool(data["email_enabled"])
    if "email_smtp_server" in data:
        EMAIL["smtp_server"] = data["email_smtp_server"]
    if "email_smtp_port" in data:
        EMAIL["smtp_port"] = int(data["email_smtp_port"])
    if "email_from" in data:
        EMAIL["from_addr"] = data["email_from"]
    if "email_to" in data:
        EMAIL["to_addr"] = data["email_to"]
    if "email_password" in data:
        EMAIL["password"] = data["email_password"]

    for s in streams.values():
        s.enhancer.quality = SERVER.get("ai_quality", 2)
        s.enhancer.process_width = SERVER.get("process_width", 480)
        s.enhancer.frame_skip = SERVER.get("frame_skip", 2)
        s.enhancer.enable_super_res = AIState.ai_super_res

    return jsonify({"ok": True, **config_data()})


@app.route("/api/config/export")
def api_config_export():
    if request.cookies.get("auth") != "1":
        return "غير مصرح", 401
    return jsonify({"cameras": CAMERAS, "server": {k: SERVER[k] for k in SERVER if k != "record_path"},
                     "auth": {k: AUTH[k] for k in AUTH}, "telegram": TELEGRAM, "email": EMAIL})


@app.route("/api/config/import", methods=["POST"])
def api_config_import():
    if request.cookies.get("auth") != "1":
        return jsonify({"error": "unauthorized"}), 401
    data = request.json
    if not data:
        return jsonify({"error": "no data"}), 400
    if "cameras" in data:
        CAMERAS.clear()
        CAMERAS.extend(data["cameras"])
    if "server" in data:
        for k, v in data["server"].items():
            if k in SERVER:
                SERVER[k] = v
    if "telegram" in data:
        for k, v in data["telegram"].items():
            TELEGRAM[k] = v
    if "email" in data:
        for k, v in data["email"].items():
            EMAIL[k] = v
    return jsonify({"ok": True})


@app.route("/api/ptz/<int:cam_id>/<command>")
def api_ptz(cam_id, command):
    if request.cookies.get("auth") != "1":
        return jsonify({"error": "unauthorized"}), 401
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
