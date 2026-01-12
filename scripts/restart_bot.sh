#!/bin/bash
# Restart Telegram Bot Script
# Kills existing bot process and starts a new one

set -e

# Find and kill existing bot process
BOT_PID=$(pgrep -f "telegram_bot" 2>/dev/null || echo "")

if [ -n "$BOT_PID" ]; then
    echo "Stopping bot (PID: $BOT_PID)..."
    kill $BOT_PID 2>/dev/null || true
    sleep 2
fi

# Start new bot process
echo "Starting bot..."
cd /app
nohup python -m src.biotact.telegram_bot > /tmp/bot.log 2>&1 &

NEW_PID=$!
sleep 2

# Verify bot started
if ps -p $NEW_PID > /dev/null 2>&1; then
    echo "Bot started successfully (PID: $NEW_PID)"
    exit 0
else
    echo "Failed to start bot"
    exit 1
fi
