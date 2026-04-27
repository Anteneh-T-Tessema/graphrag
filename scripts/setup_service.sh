#!/bin/bash
# ─── GraphRAG Background Service Installer ────────────────────────────────────
# This script sets up GraphRAG as a background service on macOS or Linux.
# It ensures the server starts on boot/login and runs "forever" in the background.

PROJECT_DIR=$(pwd)
VENV_DIR="$PROJECT_DIR/venv"
OS_TYPE=$(uname)

echo "🚀 Setting up GraphRAG Background Service..."
echo "📍 Project Directory: $PROJECT_DIR"

# 1. Create the run script
cat <<EOF > "$PROJECT_DIR/run_background.sh"
#!/bin/bash
cd "$PROJECT_DIR"
exec "$VENV_DIR/bin/uvicorn" server:app --host 0.0.0.0 --port 8000
EOF
chmod +x "$PROJECT_DIR/run_background.sh"

# 2. Setup based on OS
if [ "$OS_TYPE" == "Darwin" ]; then
    # macOS - Use LaunchAgents
    SERVICE_FILE="com.graphrag.server.plist"
    PLIST_PATH="$HOME/Library/LaunchAgents/$SERVICE_FILE"

    echo "🍎 Detected macOS. Creating LaunchAgent..."
    
    cat <<EOF > "$SERVICE_FILE"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.graphrag.server</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PROJECT_DIR/run_background.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR</string>
    <key>StandardOutPath</key>
    <string>$PROJECT_DIR/output/logs/background_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$PROJECT_DIR/output/logs/background_stderr.log</string>
</dict>
</plist>
EOF
    
    mkdir -p "$PROJECT_DIR/output/logs"
    cp "$SERVICE_FILE" "$PLIST_PATH"
    launchctl unload "$PLIST_PATH" 2>/dev/null
    launchctl load "$PLIST_PATH"
    
    echo "✅ LaunchAgent installed to $PLIST_PATH"
    echo "⚡ Service started. Access the UI at http://localhost:8000"

elif [ "$OS_TYPE" == "Linux" ]; then
    # Linux - Use Systemd (User mode)
    SERVICE_NAME="graphrag.service"
    SYSTEMD_DIR="$HOME/.config/systemd/user"
    mkdir -p "$SYSTEMD_DIR"
    
    echo "🐧 Detected Linux. Creating Systemd service..."
    
    cat <<EOF > "$SYSTEMD_DIR/$SERVICE_NAME"
[Unit]
Description=GraphRAG Background Intelligence Server
After=network.target

[Service]
Type=simple
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/run_background.sh
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF
    
    systemctl --user daemon-reload
    systemctl --user enable "$SERVICE_NAME"
    systemctl --user restart "$SERVICE_NAME"
    
    echo "✅ Systemd service installed to $SYSTEMD_DIR/$SERVICE_NAME"
    echo "⚡ Service started. Access the UI at http://localhost:8000"
    echo "💡 Note: To keep it running after logout, run: loginctl enable-linger \$USER"

else
    echo "❌ Unsupported OS type: $OS_TYPE"
    exit 1
fi
