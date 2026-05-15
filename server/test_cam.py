import cv2
import numpy as np
import sys
import time

w, h = 640, 360
fps = 15
frame_time = 1.0 / fps

def draw_test_pattern(frame, t):
    h, w = frame.shape[:2]
    cx, cy = w // 2, h // 2

    cv2.rectangle(frame, (0, 0), (w, h), (20, 20, 30), -1)

    for i in range(8):
        x = int(cx + 150 * np.cos(t * 0.5 + i * np.pi / 4))
        y = int(cy + 100 * np.sin(t * 0.7 + i * np.pi / 4))
        color = (
            int(128 + 127 * np.sin(t + i)),
            int(128 + 127 * np.sin(t + 2 + i * 1.3)),
            int(128 + 127 * np.sin(t + 4 + i * 0.7)),
        )
        cv2.circle(frame, (x, y), 15 + int(10 * np.sin(t + i)), color, -1)

    cv2.rectangle(frame, (0, h - 30), (w, h), (0, 0, 0), -1)
    cv2.putText(frame, f"AI DVR TEST | {time.strftime('%H:%M:%S')}", (10, h - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 212, 255), 1)

    cv2.putText(frame, "CAM 1", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 212, 255), 1)

    return frame

t = 0
while True:
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame = draw_test_pattern(frame, t)
    ret, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
    if ret:
        sys.stdout.buffer.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n")
        sys.stdout.buffer.flush()
    t += 0.1
    time.sleep(frame_time)
