#!/bin/bash
# Chatbot KB Monitor - Run Script
# This script runs the KB monitor manually

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Change to project directory
cd "$PROJECT_DIR"

# Activate virtual environment
if [ ! -d "venv" ]; then
    echo "Error: Virtual environment not found."
    echo "Please run ./scripts/setup.sh first."
    exit 1
fi

source venv/bin/activate

# Run the monitor
python src/main.py "$@"
