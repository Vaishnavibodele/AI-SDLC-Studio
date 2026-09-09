#!/usr/bin/env bash
# ==============================================================================
# AI SDLC Studio - AWS EC2 Backend Automated Deployment Script
# Deploys all 4 agents (Requirement, Design, Development, Testing) on Port 8000
# ==============================================================================

set -e

echo "=========================================================="
echo "🚀 Deploying AI SDLC Studio Unified Backend to AWS EC2"
echo "=========================================================="

APP_DIR="/opt/ai-sdlc-studio/backend"
SERVICE_NAME="ai-sdlc-backend"

# 1. Update OS packages and install Python 3.10+ & build tools
echo "📦 Step 1: Installing system prerequisites..."
sudo apt-get update -y || sudo yum update -y
sudo apt-get install -y python3 python3-pip python3-venv git curl || sudo yum install -y python3 python3-pip git curl

# 2. Create app directory if not present
echo "📁 Step 2: Setting up application directory at ${APP_DIR}..."
sudo mkdir -p ${APP_DIR}
sudo chown -R $USER:$USER /opt/ai-sdlc-studio

# 3. Create or update virtual environment
echo "🐍 Step 3: Setting up Python virtual environment..."
cd ${APP_DIR}
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

# 4. Configure environment file
if [ ! -f ".env" ]; then
    echo "⚙️ Creating default .env file..."
    cat <<EOF > .env
STUDIO_API_KEY=default_secret_key_12345
CORS_ORIGINS=*
PORT=8000
HOST=0.0.0.0
EOF
fi

# 5. Setup Systemd Service
echo "🔧 Step 4: Installing systemd service '${SERVICE_NAME}'..."
sudo cp ${APP_DIR}/deploy/ai-sdlc-backend.service /etc/systemd/system/${SERVICE_NAME}.service || sudo cp ${APP_DIR}/../deploy/ai-sdlc-backend.service /etc/systemd/system/${SERVICE_NAME}.service 2>/dev/null || cat <<EOF | sudo tee /etc/systemd/system/${SERVICE_NAME}.service
[Unit]
Description=AI SDLC Studio Unified Backend (4 Agents on Port 8000)
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=${APP_DIR}
Environment="PATH=${APP_DIR}/.venv/bin"
EnvironmentFile=-${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}
sudo systemctl restart ${SERVICE_NAME}

echo "✅ Backend service status:"
sudo systemctl status ${SERVICE_NAME} --no-pager -l

echo ""
echo "=========================================================="
echo "🎉 AI SDLC Studio Backend is running on EC2 Port 8000!"
echo "API Health Check: http://localhost:8000/health"
echo "Interactive Docs: http://localhost:8000/docs"
echo "=========================================================="
