#!/bin/bash
# Install macOS launchd service for KB Monitor

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PLIST_FILE="$PROJECT_DIR/com.chatbot.kb.monitor.plist"
LAUNCHD_PLIST="$HOME/Library/LaunchAgents/com.chatbot.kb.monitor.plist"

echo "============================================================"
echo "KB Monitor - Installing macOS Launch Service"
echo "============================================================"

# Check if plist file exists
if [ ! -f "$PLIST_FILE" ]; then
    echo "Error: plist file not found at $PLIST_FILE"
    exit 1
fi

# Unload existing service if it exists
if launchctl list | grep -q "com.chatbot.kb.monitor"; then
    echo "Unloading existing service..."
    launchctl unload "$LAUNCHD_PLIST" 2>/dev/null || true
fi

# Copy plist file to LaunchAgents
echo "Copying plist file to $LAUNCHD_PLIST"
cp "$PLIST_FILE" "$LAUNCHD_PLIST"

# Set proper permissions
chmod 644 "$LAUNCHD_PLIST"

# Load the service
echo "Loading service..."
launchctl load "$LAUNCHD_PLIST"

# Verify service is loaded
if launchctl list | grep -q "com.chatbot.kb.monitor"; then
    echo "✓ Service installed successfully"
    echo ""
    echo "Service will run daily at 9:20 AM"
    echo ""
    echo "Commands:"
    echo "  Check status:  launchctl list | grep com.chatbot.kb.monitor"
    echo "  Start now:     launchctl start com.chatbot.kb.monitor"
    echo "  Stop:          launchctl stop com.chatbot.kb.monitor"
    echo "  Uninstall:     launchctl unload $LAUNCHD_PLIST"
else
    echo "✗ Failed to load service"
    exit 1
fi

echo "============================================================"
