#!/bin/bash
# U-Gift Bot ishga tushirish

cd ~/mybot
source venv/bin/activate

echo "🚀 U-Gift ishga tushmoqda..."

# Flask server background da
python3 app.py &
FLASK_PID=$!
echo "✅ Flask server ishga tushdi (PID: $FLASK_PID)"

# Bot
python3 bot.py
