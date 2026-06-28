#!/bin/bash
# WatermarkWipe 啟動腳本

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Activate venv
source venv/bin/activate

# Create dirs
mkdir -p uploads outputs

echo "🚀 WatermarkWipe 正在啟動..."
echo "   網址：http://localhost:5000"
echo "   測試帳號：demo@example.com / demo123"
echo "   管理員：admin@watermarkwipe.com / admin123"
echo ""

python app.py