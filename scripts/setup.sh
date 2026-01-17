#!/bin/bash
# Chatbot KB Monitor - Setup Script
# This script sets up the virtual environment and installs dependencies

set -e  # Exit on error

echo "=========================================="
echo "Chatbot KB Monitor - Setup"
echo "=========================================="
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "Project directory: $PROJECT_DIR"
echo ""

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found. Please install Python 3.10 or later."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo "Found Python $PYTHON_VERSION"
echo ""

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "Virtual environment created."
else
    echo "Virtual environment already exists."
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo ""
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo ""
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Install Playwright browsers
echo ""
echo "Installing Playwright browser (Chromium)..."
playwright install chromium

# Create config/secrets.yaml if it doesn't exist
if [ ! -f "config/secrets.yaml" ]; then
    echo ""
    echo "Creating secrets.yaml from template..."
    cp config/secrets.example.yaml config/secrets.yaml
    echo "✓ Created config/secrets.yaml"
    echo ""
    echo "⚠️  IMPORTANT: Edit config/secrets.yaml and add your credentials:"
    echo "   - username"
    echo "   - password"
    echo "   - lark.webhook_url"
    echo ""
    echo "Example: nano config/secrets.yaml"
else
    echo ""
    echo "config/secrets.yaml already exists."
fi

# Set secure permissions on secrets file
if [ -f "config/secrets.yaml" ]; then
    chmod 600 config/secrets.yaml
    echo "✓ Set secure permissions (600) on config/secrets.yaml"
fi

echo ""
echo "=========================================="
echo "Setup complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Edit config/secrets.yaml with your credentials"
echo "  2. Run manually to test: ./scripts/run_monitor.sh"
echo "  3. If working, install launchd agent:"
echo "     ./scripts/install_launchd.sh"
echo ""
