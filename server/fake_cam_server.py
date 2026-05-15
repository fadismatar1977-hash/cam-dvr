import cv2
import numpy as np
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

w, h = 640, 360

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        t = 0
        while True:
            frame = np.zeros((h, w, 3), dtype=np.uint8)
            cx, cy = w // 2, h // 2
            cv2.rectangle(frame, (0, 0), (w, h), (20, 20, 30), -1)

            for i in range(6):
                x = int(cx + 180 * np.cos(t * 0.5 + i * np.pi / 3))
                y = int(cy + 120 * np.sin(t * 0.7 + i * np.pi / 3))
                color = (
                    int(128 + 127 * np.sin(t + i * 1.1)),
                    int(128 + 127 * np.sin(t + 2 + i * 1.3)),
                    int(128 + 127 * np.sin(t + 4 + i * 0.7)),
                )
                cv2.circle(frame, (x, y), 20 + int(8 * np.sin(t + i * 1.5)), color, -1)

            cam_id = self.path.strip("/")
            cam_label = f"الكاميرا {cam_id}" if cam_id else "TEST"
            cv2.rectangle(frame, (0, h - 28), (w, h), (0, 0, 0), -1)
            cv2.putText(frame, f"AI DVR | {cam_label} | {time.strftime('%H:%M:%S')}",
                        (10, h - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 212, 255), 1)

            ret, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ret:
                self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n")
            t += 0.1
            time.sleep(0.066)

print("Fake camera server on http://localhost:8090")
HTTPServer(("", 8090), Handler).serve_forever()
