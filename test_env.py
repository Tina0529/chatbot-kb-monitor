#!/usr/bin/env python3
"""Quick test to verify environment variables are loaded correctly."""

import os
import sys

print("=== Environment Variables Test ===")
print(f"KB_USERNAME: {'***' + os.environ.get('KB_USERNAME', 'NOT SET')[-4:] if os.environ.get('KB_USERNAME') else 'NOT SET'}")
print(f"KB_PASSWORD: {'***' + os.environ.get('KB_PASSWORD', 'NOT SET')[-4:] if os.environ.get('KB_PASSWORD') else 'NOT SET'}")
print(f"LARK_WEBHOOK_URL: {'***' + os.environ.get('LARK_WEBHOOK_URL', 'NOT SET')[-4:] if os.environ.get('LARK_WEBHOOK_URL') else 'NOT SET'}")
print(f"LARK_APP_ID: {os.environ.get('LARK_APP_ID', 'NOT SET')}")
print(f"LARK_APP_SECRET: {'***' + os.environ.get('LARK_APP_SECRET', 'NOT SET')[-4:] if os.environ.get('LARK_APP_SECRET') else 'NOT SET'}")

# Try to load secrets
sys.path.insert(0, '/home/runner/work/chatbot-kb-monitor/chatbot-kb-monitor/src')
try:
    from utils import load_secrets
    secrets = load_secrets()
    print("\n=== Secrets Loaded Successfully ===")
    print(f"Username: {secrets.credentials.get('username', 'MISSING')}")
    print(f"Lark webhook configured: {'YES' if secrets.lark.get('webhook_url') else 'NO'}")
except Exception as e:
    print(f"\nError loading secrets: {e}")
    sys.exit(1)
