import os

CAMERAS = [
    {
        "name": "الكاميرا 1",
        "url": "rtsp://192.168.1.100:554/stream1",
        "enabled": True,
    },
    {
        "name": "الكاميرا 2",
        "url": "rtsp://192.168.1.101:554/stream1",
        "enabled": True,
    },
]

SERVER = {
    "host": "0.0.0.0",
    "port": 5000,
    "record_path": os.path.join(os.path.dirname(__file__), "recordings"),
    "motion_sensitivity": 5000,
    "record_on_motion": True,
    "max_days": 7,
    "ai_enhance": True,
    "ai_super_res": False,
    "ai_motion": True,
    "jpeg_quality": 75,
}

AUTH = {
    "username": "admin",
    "password": "admin123",
}
