#!/bin/bash
# تثبيت الـ DVR كخدمة (تشغيل تلقائي عند بداية الجهاز)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS - LaunchAgent
    PLIST="$HOME/Library/LaunchAgents/com.camdvr.server.plist"
    cat > "$PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.camdvr.server</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>${SCRIPT_DIR}/dvr_server.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${SCRIPT_DIR}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${SCRIPT_DIR}/dvr.log</string>
    <key>StandardErrorPath</key>
    <string>${SCRIPT_DIR}/dvr.log</string>
</dict>
</plist>
EOF
    launchctl load "$PLIST"
    echo "✅ تم تثبيت الخدمة على macOS"
    echo "   launchctl start com.camdvr.server"

elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux - systemd
    SERVICE="/etc/systemd/system/camdvr.service"
    sudo bash -c "cat > $SERVICE" << EOF
[Unit]
Description=AI DVR Server
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=${SCRIPT_DIR}
ExecStart=/usr/bin/python3 ${SCRIPT_DIR}/dvr_server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable camdvr
    sudo systemctl start camdvr
    echo "✅ تم تثبيت الخدمة على Linux"
    echo "   systemctl start camdvr"
else
    echo "⚠️  نظام غير معروف. شغّل السيرفر يدويًا:"
    echo "   python3 ${SCRIPT_DIR}/dvr_server.py"
fi
