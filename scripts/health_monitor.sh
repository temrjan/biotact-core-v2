#!/bin/bash
# BIOTACT Health Monitor v1.0
# Runs via cron every 5 minutes

set -e

# Load environment
source /opt/biotact-core-v2/.env

# Config
API_URL="http://localhost:8000/api/v1/health"
ADMIN_CHAT_ID="8503214095"
LOG_FILE="/var/log/biotact_monitor.log"
STATE_FILE="/tmp/biotact_monitor_state"

# Send Telegram alert (using bot token from .env)
send_alert() {
    local message="$1"
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage"         -d chat_id="${ADMIN_CHAT_ID}"         -d text="${message}" > /dev/null 2>&1
}

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

# Track state to avoid repeated alerts
get_state() {
    cat "$STATE_FILE" 2>/dev/null || echo "ok"
}

set_state() {
    echo "$1" > "$STATE_FILE"
}

errors=""

# Check API
api_status=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$API_URL" 2>/dev/null || echo "000")
if [ "$api_status" != "200" ]; then
    errors+="API: HTTP $api_status\n"
fi

# Check containers
for container in biotact-api biotact-qdrant biotact-redis biotact-postgres; do
    status=$(docker inspect -f '{{.State.Status}}' $container 2>/dev/null || echo "not found")
    if [ "$status" != "running" ]; then
        errors+="Container $container: $status\n"
    fi
done

# Send alert if errors found and state was OK
if [ -n "$errors" ]; then
    log "ERRORS: $errors"
    if [ "$(get_state)" = "ok" ]; then
        send_alert "🚨 BIOTACT Alert!

$errors
Время: $(date '+%H:%M %d.%m.%Y')"
        set_state "error"
    fi
else
    # Recover notification
    if [ "$(get_state)" = "error" ]; then
        send_alert "✅ BIOTACT восстановлен!

Все сервисы работают.
Время: $(date '+%H:%M %d.%m.%Y')"
        log "RECOVERED"
    fi
    set_state "ok"
fi
