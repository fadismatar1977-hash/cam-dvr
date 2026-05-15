import os

CAMERAS = [
    {"name": "الكاميرا 1 - المدخل", "url": "http://localhost:8090/1", "enabled": True},
    {"name": "الكاميرا 2 - الحديقة", "url": "http://localhost:8090/2", "enabled": True},
    {"name": "الكاميرا 3 - المستودع", "url": "http://localhost:8090/3", "enabled": True},
    {"name": "الكاميرا 4 - المواقف", "url": "http://localhost:8090/4", "enabled": True},
]

SERVER = {
    "host": "0.0.0.0",
    "port": 5000,
    "record_path": os.path.join(os.path.dirname(__file__), "recordings"),
    "motion_sensitivity": 5000,
    "recording_mode": "motion",
    "schedule_start": 0,
    "schedule_end": 24,
    "max_days": 7,
    "ai_enhance": True,
    "ai_super_res": False,
    "ai_motion": True,
    "ai_quality": 2,
    "process_width": 480,
    "frame_skip": 2,
    "jpeg_quality": 75,
}

TELEGRAM = {
    "enabled": False,
    "bot_token": "",
    "chat_id": "",
}

EMAIL = {
    "enabled": False,
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "from_addr": "",
    "to_addr": "",
    "password": "",
}

AUTH = {
    "username": "admin",
    "password": "admin123",
}
