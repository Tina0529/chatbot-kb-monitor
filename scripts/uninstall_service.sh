#!/bin/bash
# Uninstall macOS launchd service for KB Monitor

set -e

LAUNCHD_PLIST="$HOME/Library/LaunchAgents/com.chatbot.kb.monitor.plist"

echo "============================================================"
echo "KB Monitor - Uninstalling macOS Launch Service"
echo "============================================================"

# Check if service is loaded
if launchctl list | grep -q "com.chatbot.kb.monitor"; then
    echo "Unloading service..."
    launchctl unload "$LAUNCHD_PLIST"
    echo "✓ Service unloaded"
else
    echo "Service not currently loaded"
fi

# Remove plist file
if [ -f "$LAUNCHD_PLIST" ]; then
    rm "$LAUNCHD_PLIST"
    echo "✓ Removed plist file"
fi

echo ""
echo "Service uninstalled successfully"
echo "============================================================"
