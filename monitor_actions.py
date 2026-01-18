#!/usr/bin/env python3
"""Simplified monitor script for GitHub Actions - with login support."""

import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime

# Add src directory to path
sys.path.insert(0, '/home/runner/work/chatbot-kb-monitor/chatbot_kb_monitor/src')

async def main() -> int:
    """Run monitoring with config from environment variables."""

    # Get credentials from environment
    username = os.environ.get("KB_USERNAME", "")
    password = os.environ.get("KB_PASSWORD", "")
    webhook_url = os.environ.get("LARK_WEBHOOK_URL", "")
    app_id = os.environ.get("LARK_APP_ID", "")
    app_secret = os.environ.get("LARK_APP_SECRET", "")
    direct_kb_url = os.environ.get("DIRECT_KB_URL", "")
    base_url = os.environ.get("BASE_URL", "https://admin.gbase.ai")

    # Validate required environment variables
    if not username or not password:
        print("ERROR: KB_USERNAME and KB_PASSWORD must be set")
        return 1

    if not webhook_url:
        print("ERROR: LARK_WEBHOOK_URL must be set")
        return 1

    print("=" * 60)
    print("Starting KB Monitor (GitHub Actions Version)")
    print("=" * 60)
    print(f"Username: {'***' + username[-4:]}")
    print(f"Webhook configured: {'YES' if webhook_url else 'NO'}")
    print(f"Lark App configured: {'YES' if app_id else 'NO'}")
    print(f"Direct KB URL: {direct_kb_url[:50]}..." if direct_kb_url else "Direct KB URL: Not set")
    print("=" * 60)

    # Import here (after path is set)
    try:
        from playwright.async_api import async_playwright

        print("Launching browser...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            # Step 1: Login
            print(f"[Step 1] Logging in to {base_url}")
            await page.goto(base_url, wait_until="load", timeout=60000)
            await asyncio.sleep(2)

            # Fill credentials
            print("  Filling credentials...")
            await page.fill('input[name="username"]', username)
            await page.fill('input[type="password"]', password)

            # Click login button (try multiple selectors)
            print("  Clicking login button...")
            login_clicked = False
            for selector in ['button[type="submit"]', 'button:has-text("ログイン")', '.login-button']:
                try:
                    if await page.locator(selector).count() > 0:
                        await page.locator(selector).first.click()
                        login_clicked = True
                        print(f"  ✓ Clicked login using: {selector}")
                        break
                except:
                    continue

            if not login_clicked:
                print("  ERROR: Could not find login button")
                return 1

            # Wait for navigation after login
            await asyncio.sleep(5)
            print(f"  Current URL after login: {page.url[:80]}")

            # Step 2: Navigate to KB page
            print(f"\n[Step 2] Navigating to KB page...")
            if not direct_kb_url:
                print("  ERROR: DIRECT_KB_URL must be set")
                return 1

            await page.goto(direct_kb_url, wait_until="load", timeout=60000)
            await asyncio.sleep(5)  # Wait for dynamic content
            print(f"  ✓ Current URL: {page.url[:80]}")

            # Step 3: Scan for KB files using multiple selectors
            print(f"\n[Step 3] Scanning for KB files...")

            selectors_to_try = [
                ('.mantine-Table-tbody tr', 'Mantine Table body rows'),
                ('[class*="mantine-Table-tbody"] tr', 'Mantine Table body (variant)'),
                ('tbody tr', 'Standard table body rows'),
                ('table tr', 'All table rows'),
                ('[role="row"]', 'ARIA rows'),
            ]

            total_items = 0
            failed_count = 0
            files_found = False

            for selector, description in selectors_to_try:
                try:
                    print(f"  Trying: {description} ({selector})")
                    rows = await page.locator(selector).all()

                    if len(rows) > 0:
                        print(f"  ✓ Found {len(rows)} items using '{selector}'")
                        files_found = True
                        total_items = len(rows)

                        # Scan for failures
                        failure_indicators = ["失敗", "エラー", "error", "failed"]

                        for i, row in enumerate(rows[:50]):  # Check first 50 items
                            try:
                                row_text = await row.inner_text()

                                # Check for failure indicators
                                for indicator in failure_indicators:
                                    if indicator in row_text:
                                        failed_count += 1
                                        # Extract file name (first cell usually)
                                        try:
                                            first_cell = row.locator('td').first
                                            if await first_cell.count() > 0:
                                                file_name = await first_cell.inner_text()
                                                print(f"    Failed: {file_name[:50]}...")
                                                break
                                        except:
                                            print(f"    Failed: {row_text[:50]}...")
                                            break
                                # Stop after finding first few failures for performance
                                if failed_count >= 5:
                                    print(f"    ... (and {failed_count} total failures)")
                                    break
                            except Exception as e:
                                continue

                        break  # Use first successful selector
                except Exception as e:
                    print(f"  Selector '{selector}' failed: {e}")
                    continue

            if not files_found or total_items == 0:
                print("\nERROR: No KB files found on page!")
                print("Possible reasons:")
                print("  1. DIRECT_KB_URL is incorrect")
                print("  2. Login failed or session expired")
                print("  3. Page structure has changed")

                # Send error notification
                import requests

                error_msg = f"""⚠️ KB Monitor Failed

**Time**: {datetime.now().strftime('%Y-%m-%d %H:%M')} (Asia/Tokyo)

**Error**: No KB files found on page

**URL**: {direct_kb_url[:80] if direct_kb_url else 'Not set'}...

**Please check**:
1. KB file path configuration (DIRECT_KB_URL)
2. Login credentials
3. Network connectivity

---
*This is an automated message*"""

                response = requests.post(webhook_url, json={"msg_type": "text", "content": {"text": error_msg}}, timeout=10)
                print(f"Error notification sent: {response.status_code}")
                return 1

            print(f"\n[Step 4] SCAN COMPLETE: {total_items} total items, {failed_count} failures")

            # Step 5: Take screenshot
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"screenshots/status_{timestamp}.png"
            os.makedirs("screenshots", exist_ok=True)

            await page.screenshot(path=screenshot_path, full_page=True)
            print(f"Screenshot saved: {screenshot_path}")

            # Step 6: Upload screenshot to Lark
            image_key = None
            if app_id and app_secret:
                image_key = await upload_image_to_lark_async(
                    screenshot_path, app_id, app_secret
                )

            # Step 7: Send notification
            import requests

            color = "green" if failed_count == 0 else "red"
            emoji = "✅" if failed_count == 0 else "⚠️"

            card = {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {"tag": "plain_text", "content": f"{emoji} KB Monitor Report"},
                        "template_color": color
                    },
                    "elements": [
                        {
                            "tag": "div",
                            "text": {
                                "tag": "lark_md",
                                "content": f"""**Time**: {datetime.now().strftime('%Y-%m-%d %H:%M')} (Asia/Tokyo)

**Summary**:
• Total Items: {total_items}
• Failed Items: {failed_count}
• Status: {"✅ All OK" if failed_count == 0 else "⚠️ Has Failures"}

**Screenshot**: {"See below" if image_key else "No screenshot available"}"""
                            }
                        }
                    ]
                }
            }

            # Add image element if available
            if image_key:
                card["card"]["elements"].append({
                    "tag": "img",
                    "img_key": image_key,
                    "alt": {"tag": "plain_text", "content": "KB Status Screenshot"}
                })

            response = requests.post(webhook_url, json=card, timeout=10)
            print(f"Notification sent: {response.status_code}")

            await browser.close()

            print("\n" + "=" * 60)
            print("MONITOR COMPLETED SUCCESSFULLY!")
            print("=" * 60)

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

        # Send error notification
        import requests

        error_msg = f"""⚠️ KB Monitor Error

**Time**: {datetime.now().strftime('%Y-%m-%d %H:%M')} (Asia/Tokyo)

**Error**: {str(e)}

---
*This is an automated message*"""

        response = requests.post(webhook_url, json={"msg_type": "text", "content": {"text": error_msg}}, timeout=10)
        print(f"Error notification sent: {response.status_code}")

        return 1

    return 0


async def upload_image_to_lark_async(image_path: str, app_id: str, app_secret: str) -> str:
    """Upload image to Lark IM API - async version."""
    import lark_oapi
    from lark_oapi.im.v1.model.create_image_request import CreateImageRequest
    from lark_oapi.im.v1.model.create_image_request_body import CreateImageRequestBody

    # Get access token
    token = await get_lark_access_token_async(app_id, app_secret)
    if not token:
        print("Failed to get access token")
        return None

    # Read image
    image_file = Path(image_path)
    if not image_file.exists():
        print(f"Image not found: {image_path}")
        return None

    image_content = image_file.read_bytes()

    # Build request
    request = CreateImageRequest.builder().request_body(
        CreateImageRequestBody.builder()
            .image_type("message")
            .image(image_content=image_content)
            .build()
    ).build()

    # Upload
    client = lark_oapi.Client.builder().app_id(app_id).app_secret(app_secret).build()
    response = await client.im.v1.image.create(request)

    if response.code != 0:
        print(f"Upload error: code={response.code}, msg={response.msg}")
        return None

    if response.data and hasattr(response.data, 'image_key'):
        print(f"✓ Image uploaded: {response.data.image_key}")
        return response.data.image_key

    return None


async def get_lark_access_token_async(app_id: str, app_secret: str) -> str:
    """Get Lark access token - async version."""
    import requests

    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    payload = {
        "app_id": app_id,
        "app_secret": app_secret
    }

    response = requests.post(url, json=payload, timeout=10)
    response.raise_for_status()
    result = response.json()

    if result.get("code") != 0:
        return None

    return result.get("tenant_access_token")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
