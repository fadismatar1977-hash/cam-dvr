import cv2
import numpy as np
import time
import threading
from flask import Flask, Response

app = Flask(__name__)

frames = {}
for cam_id in [1, 2, 3, 4]:
    frames[cam_id] = None

def gen_frame(cam_id, w=480, h=320):
    t = 0
    while True:
        f = np.zeros((h, w, 3), dtype=np.uint8)
        cv2.rectangle(f, (0, 0), (w, h), (20, 20, 30), -1)

        if cam_id == 1:
            for i in range(6):
                x = int(w//2 + 120*np.cos(t*0.5 + i*np.pi/3))
                y = int(h//2 + 80*np.sin(t*0.7 + i*np.pi/3))
                c = (int(128+127*np.sin(t+i)), int(128+127*np.sin(t+2+i)), int(128+127*np.sin(t+4+i)))
                cv2.circle(f, (x, y), 15+int(6*np.sin(t+i)), c, -1)
        elif cam_id == 2:
            for i in range(3):
                x = int(250 + 150*np.sin(t*0.3 + i*2.1))
                y = int(100 + 80*np.cos(t*0.4 + i*1.3))
                cv2.rectangle(f, (x-30, y-15), (x+30, y+15), (0, 180+i*20, 255-i*30), -1)
        elif cam_id == 3:
            pts = np.array([[int(240+100*np.cos(t*0.2)), int(160+80*np.sin(t*0.3))],
                            [int(240+100*np.cos(t*0.2+2.1)), int(160+80*np.sin(t*0.3+1.5))],
                            [int(240+100*np.cos(t*0.2+4.2)), int(160+80*np.sin(t*0.3+3.0))]], np.int32)
            cv2.polylines(f, [pts], True, (100, 200, 255), 2)
            cv2.fillPoly(f, [pts], (60, 120, 200))
        else:
            cv2.circle(f, (w//2, h//2), 50+int(30*np.sin(t)), (0, 200, 200), -1)
            cv2.circle(f, (w//2, h//2), 30+int(20*np.sin(t*0.7)), (50, 100, 255), -1)

        cv2.rectangle(f, (0, h-22), (w, h), (0, 0, 0), -1)
        label = f"CAM {cam_id} | AI DVR | {time.strftime('%H:%M:%S')}"
        cv2.putText(f, label, (8, h-6), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 212, 255), 1)
        frames[cam_id] = f
        t += 0.1
        time.sleep(0.066)


for cam_id in [1, 2, 3, 4]:
    t = threading.Thread(target=gen_frame, args=(cam_id,), daemon=True)
    t.start()

@app.route("/<int:cam_id>")
def stream(cam_id):
    def gen():
        while True:
            f = frames.get(cam_id)
            if f is not None:
                r, j = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 65])
                if r:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + j.tobytes() + b"\r\n"
            time.sleep(0.066)
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

print("Fake cameras on http://localhost:8090/1 .. /4")
app.run(host="0.0.0.0", port=8090, debug=False, threaded=True)
