#!/bin/bash
# DVR - تنصيب كامل على Linux Mint

set -e

echo "=============================="
echo "  تنصيب AI DVR على لينكس"
echo "=============================="

# 1. تحديث النظام
echo "[1/5] تحديث النظام..."
sudo apt update
sudo apt upgrade -y

# 2. نصب المشتغل
echo "[2/5] نصب المشتغل (Python + OpenCV)..."
sudo apt install -y python3 python3-pip python3-opencv python3-numpy python3-flask git

# 3. تحميل المشروع
echo "[3/5] تحميل DVR..."
cd ~
if [ -d "cam-dvr" ]; then
    cd cam-dvr && git pull
else
    git clone https://github.com/fadismatar1977-hash/cam-dvr.git
    cd cam-dvr
fi

# 4. إعدادات للجهاز الضعيف
echo "[4/5] إعدادات للجهاز الضعيف..."
cat > server/config.py << 'PYEOF'
import os

CAMERAS = [
    {"name": "الكاميرا 1", "url": "rtsp://192.168.1.100:554/stream1", "enabled": True},
    {"name": "الكاميرا 2", "url": "rtsp://192.168.1.101:554/stream1", "enabled": True},
]

SERVER = {
    "host": "0.0.0.0",
    "port": 5000,
    "record_path": os.path.join(os.path.dirname(__file__), "recordings"),
    "motion_sensitivity": 5000,
    "recording_mode": "motion",
    "max_days": 7,
    "ai_enhance": True,
    "ai_motion": True,
    "ai_quality": 1,
    "process_width": 360,
    "frame_skip": 3,
    "jpeg_quality": 70,
}

TELEGRAM = {"enabled": False, "bot_token": "", "chat_id": ""}
EMAIL = {"enabled": False, "smtp_server": "", "smtp_port": 587, "from_addr": "", "to_addr": "", "password": ""}
AUTH = {"username": "admin", "password": "admin123"}
PYEOF

# 5. تشغيل تلقائي
echo "[5/5] تفعيل التشغيل التلقائي..."
SERVICE_PATH="/etc/systemd/system/camdvr.service"
sudo bash -c "cat > $SERVICE_PATH" << EOF
[Unit]
Description=AI DVR Server
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$HOME/cam-dvr/server
ExecStart=/usr/bin/python3 $HOME/cam-dvr/server/dvr_server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable camdvr
sudo systemctl start camdvr

# 6. جدار النار
echo "[6/6] فتح منفذ 5000..."
sudo ufw allow 5000/tcp 2>/dev/null || true

echo ""
echo "=============================="
echo "  ✅ اكتمل التنصيب!"
echo "=============================="
echo ""
IP=$(hostname -I | awk '{print $1}')
echo "  افتح المتصفح على:"
echo "  http://$IP:5000"
echo ""
echo "  اسم المستخدم: admin"
echo "  كلمة السر:    admin123"
echo ""
echo "  أوامر مفيدة:"
echo "  - إيقاف:    sudo systemctl stop camdvr"
echo "  - تشغيل:    sudo systemctl start camdvr"
echo "  - سجلات:    sudo journalctl -u camdvr -f"
echo "  - تحديث:    cd ~/cam-dvr && git pull"
echo ""
