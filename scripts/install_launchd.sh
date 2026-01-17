#!/bin/bash
# Chatbot KB Monitor - Launchd Installation Script
# This script helps install and manage the launchd agent

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PLIST_FILE="$PROJECT_DIR/launchd/com.chatbot.kbmonitor.plist"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST_TARGET="$LAUNCH_AGENTS_DIR/com.chatbot.kbmonitor.plist"

# Function to print usage
usage() {
    echo "Usage: $0 {install|uninstall|load|unload|status|help}"
    echo ""
    echo "Commands:"
    echo "  install    Copy plist to LaunchAgents and load it"
    echo "  uninstall  Unload and remove plist from LaunchAgents"
    echo "  load       Load the agent (must be installed first)"
    echo "  unload     Unload the agent"
    echo "  status     Show agent status"
    echo "  help       Show this help message"
    echo ""
    echo "Example:"
    echo "  $0 install   # Install and start the scheduled task"
}

# Function to check if agent is loaded
check_loaded() {
    if launchctl list | grep -q "com.chatbot.kbmonitor"; then
        return 0  # Loaded
    else
        return 1  # Not loaded
    fi
}

# Function to update plist with current path
update_plist_path() {
    local project_path="$1"

    echo "Updating plist with project path: $project_path"

    # Update the plist file with the correct path
    sed -i.bak "s|/Users/agent2025/Downloads/chatbot-kb-monitor|$project_path|g" "$PLIST_FILE"

    # Remove backup file
    rm -f "$PLIST_FILE.bak"
}

# Main script
case "${1:-}" in
    install)
        echo "=========================================="
        echo "Installing Chatbot KB Monitor Launchd Agent"
        echo "=========================================="
        echo ""

        # Get absolute path of project directory
        PROJECT_ABS="$(cd "$PROJECT_DIR" && pwd)"

        # Update plist with correct path
        update_plist_path "$PROJECT_ABS"

        # Create LaunchAgents directory if it doesn't exist
        mkdir -p "$LAUNCH_AGENTS_DIR"

        # Copy plist file
        echo "Copying plist to $PLIST_TARGET"
        cp "$PLIST_FILE" "$PLIST_TARGET"

        # Load the agent
        echo "Loading launchd agent..."
        launchctl load "$PLIST_TARGET"

        echo ""
        echo "✓ Agent installed and loaded successfully!"
        echo ""
        echo "The monitor will run every day at 9:20 AM."
        echo ""
        echo "To view logs:"
        echo "  tail -f $PROJECT_ABS/logs/launchd.log"
        echo ""
        echo "To run manually:"
        echo "  ./scripts/run_monitor.sh"
        echo ""
        echo "To uninstall:"
        echo "  $0 uninstall"
        ;;

    uninstall)
        echo "Uninstalling Chatbot KB Monitor Launchd Agent..."
        echo ""

        # Unload if loaded
        if check_loaded; then
            echo "Unloading agent..."
            launchctl unload "$PLIST_TARGET"
        fi

        # Remove plist file
        if [ -f "$PLIST_TARGET" ]; then
            echo "Removing $PLIST_TARGET"
            rm "$PLIST_TARGET"
        fi

        echo ""
        echo "✓ Agent uninstalled successfully!"
        ;;

    load)
        echo "Loading launchd agent..."
        launchctl load "$PLIST_TARGET"
        echo "✓ Agent loaded!"
        ;;
    unload)
        echo "Unloading launchd agent..."
        launchctl unload "$PLIST_TARGET"
        echo "✓ Agent unloaded!"
        ;;

    status)
        echo "=========================================="
        echo "Chatbot KB Monitor Status"
        echo "=========================================="
        echo ""

        if check_loaded; then
            echo "Status: ✓ Loaded (running)"
            echo ""
            echo "Scheduled jobs:"
            launchctl list | grep "com.chatbot.kbmonitor"
        else
            echo "Status: ✗ Not loaded"
            echo ""
            echo "To install and load:"
            echo "  $0 install"
        fi
        echo ""
        echo "Recent logs:"
        echo "----------------------------------------"
        if [ -f "$PROJECT_DIR/logs/monitor.log" ]; then
            tail -n 5 "$PROJECT_DIR/logs/monitor.log"
        else
            echo "No log file found yet."
        fi
        ;;

    help|--help|-h)
        usage
        ;;

    *)
        echo "Error: Unknown command '${1:-}'"
        echo ""
        usage
        exit 1
        ;;
esac
