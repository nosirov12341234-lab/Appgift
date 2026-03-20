#!/bin/bash
cd ~/mybot
source venv/bin/activate
echo "🚀 U-Gift ishga tushmoqda..."
python3 app.py &
sleep 2
python3 bot.py
