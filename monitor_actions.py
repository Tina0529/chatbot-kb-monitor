#!/usr/bin/env python3
"""Simplified monitor script for GitHub Actions - reads all config from environment variables."""

import asyncio
import os
import sys
from datetime import datetime

# Add src directory to path
sys.path.insert(0, '/home/runner/work/chatbot-kb-monitor/chatbot-kb-monitor/src')

async def main():
    """Run monitoring with config from environment variables."""

    # Get credentials from environment
    username = os.environ.get("KB_USERNAME", "")
    password = os.environ.get("KB_PASSWORD", "")

    webhook_url = os.environ.get("LARK_WEBHOOK_URL", "")
    app_id = os.environ.get("LARK_APP_ID", "")
    app_secret = os.environ.get("LARK_APP_SECRET", "")

    # Validate required environment variables
    if not username or not password:
        print("ERROR: KB_USERNAME and KB_PASSWORD must be set as environment variables")
        return 1

    if not webhook_url:
        print("ERROR: LARK_WEBHOOK_URL must be set as environment variable")
        return 1

    print("=" * 60)
    print("Starting KB Monitor (GitHub Actions Version)")
    print("=" * 60)
    print(f"Username: {'***' + username[-4:]}")
    print(f"Webhook configured: {'YES' if webhook_url else 'NO'}")
    print(f"Lark App configured: {'YES' if app_id else 'NO'}")
    print("=" * 60)

    # Import here (after path is set)
    try:
        from playwright.async_api import async_playwright

        print("Launching browser...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            print("Navigating to KB page...")
            await page.goto("https://admin.gbase.ai")

            # Login
            print("Logging in...")
            await page.fill("input[name='username']", username)
            await page.fill("input[name='password']", password)
            await page.click("button[type='submit']")
            await asyncio.sleep(5)

            # Navigate to KB page
            kb_url = "https://admin.gbase.ai/assist/b50d5b21-262a-4802-a8c4-512af224c72f/datasets/b30daf1b-46c6-4113-af5d-ee68215490d4/data-source/file"
            await page.goto(kb_url)
            await asyncio.sleep(3)

            # Scan for failures
            print("Scanning for failures...")
            rows = await page.locator('tbody tr').all()
            failed_count = 0

            for i, row in enumerate(rows[:10]):
                text = await row.inner_text()
                if any(indicator in text.lower() for indicator in ["失敗", "エラー", "error", "failed"]):
                    failed_count += 1
                    print(f"  Failed item: {text[:50]}...")

            print(f"Scan complete: {len(rows)} items, {failed_count} failures")

            # Take screenshot
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"screenshots/status_{timestamp}.png"
            os.makedirs("screenshots", exist_ok=True)
            await page.screenshot(path=screenshot_path)
            print(f"Screenshot saved: {screenshot_path}")

            # Send notification
            import requests

            message = f"""
📊 **KB Monitor Report** (GitHub Actions)

**Time**: {datetime.now().strftime('%Y-%m-%d %H:%M')} (Asia/Tokyo)
**Run**: #{os.environ.get('GITHUB_RUN_NUMBER', 'N/A')}
**Source**: GitHub Actions

**Summary**:
- Total items: {len(rows)}
- Failed items: {failed_count}
- Screenshots: 1
- Screenshot: {screenshot_path}
"""

            response = requests.post(webhook_url, json={"msg_type": "text", "content": {"text": message.strip()}}, timeout=10)
            print(f"Notification sent: {response.status_code}")

            await browser.close()

            print("=" * 60)
            print("Monitor completed successfully!")
            print("=" * 60)

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
