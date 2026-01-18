#!/usr/bin/env python3
"""Simplified monitor script for GitHub Actions - improved version."""

import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime

# Add src directory to path
sys.path.insert(0, '/home/runner/work/chatbot-kb-monitor/chatbot-kb-monitor/src')

async def main() -> int:
    """Run monitoring with config from environment variables."""

    # Get credentials from environment
    username = os.environ.get("KB_USERNAME", "")
    password = os.environ.get("KB_PASSWORD", "")
    webhook_url = os.environ.get("LARK_WEBHOOK_URL", "")
    app_id = os.environ.get("LARK_APP_ID", "")
    app_secret = os.environ.get("LARK_APP_SECRET", "")
    
    # Get direct_kb_url if available
    direct_kb_url = os.environ.get("DIRECT_KB_URL", "")

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
    print(f"Direct KB URL: {direct_kb_url if direct_kb_url else 'Using step-by-step navigation'}")
    print("=" * 60)

    # Import here (after path is set)
    try:
        from playwright.async_api import async_playwright

        print("Launching browser...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            # Use direct_kb_url if available
            target_url = direct_kb_url or "https://admin.gbase.ai"
            
            print(f"Navigating to: {target_url}")
            await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)

            # Login if needed
            if "admin.gbase.ai" in target_url and "admin.gbase.ai" not in page.url():
                print("Logging in...")
                await page.fill("input[name='username']", username)
                await page.fill("input[name='password']", password)
                await page.click("button[type='submit']")
                try:
                    await page.wait_for_url("**/datasets/**", timeout=15000)
                except:
                    await asyncio.sleep(10)

            # Navigate to KB file page if not already there
            if "data-source/file" not in page.url and not direct_kb_url:
                print("Navigating to KB file page...")
                kb_url = "https://admin.gbase.ai/assist/b50d5b21-262a-4802-a8c4-512af224c72f/datasets/b30daf1b-46c6-4113-af5d-ee68215490d4/data-source/file"
                await page.goto(kb_url, wait_until="domcontentloaded", timeout=60000)

            # Wait for table to be visible
            print("Waiting for table to load...")
            await asyncio.sleep(5)

            # Try multiple possible selectors
            table_selectors = [
                'tbody tr',      # table body rows
                '.list-item',    # alternative: list items
                '[role="row"]'     # alternative: elements with row role
            ]
            
            rows = None
            for selector in table_selectors:
                print(f"Trying selector: {selector}")
                try:
                    rows = await page.query_selector_all(selector)
                    if len(rows) > 0:
                        print(f"✓ Found {len(rows)} items using '{selector}'")
                        break
                except Exception as e:
                    print(f"  Selector '{selector}' failed: {e}")
                    continue

            if not rows or len(rows) == 0:
                print("ERROR: No table found on page")
                # Debug: save page source
                debug_path = "screenshots/debug_page.html"
                os.makedirs("screenshots", exist_ok=True)
                await page.screenshot(path=debug_path)
                print(f"Debug: Page source saved to {debug_path}")
                return 1

            total_items = len(rows)
            print(f"Found {total_items} items")

            # Scan for failures
            print("Scanning for failures...")
            failed_count = 0
            failed_items = []

            for i, row in enumerate(rows[:20]):  # Scan up to 20 items
                try:
                    text = await row.inner_text()
                    
                    # Check for failure indicators
                    failure_indicators = ["失敗", "エラー", "error", "failed"]
                    is_failed = any(indicator in text for indicator in failure_indicators)
                    
                    if is_failed:
                        failed_count += 1
                        failed_items.append(text[:50] + "..." if len(text) > 50 else text)
                        print(f"  Failed: {text[:30]}...")

                except Exception as e:
                    print(f"Error scanning row {i}: {e}")
                    continue

            print(f"SCAN COMPLETE: {total_items} items, {failed_count} failures")

            # Take full page screenshot
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"screenshots/status_{timestamp}.png"
            os.makedirs("screenshots", exist_ok=True)
            
            await page.screenshot(path=screenshot_path, full_page=True)
            print(f"Screenshot saved: {screenshot_path}")

            # Upload screenshot to Lark
            image_key = None
            if app_id and app_secret:
                image_key = await upload_image_to_lark_async(
                    screenshot_path, app_id, app_secret
                )

            # Send notification
            import requests

            card = {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {"tag": "plain_text", "content": f"📊 KB Monitor Report"},
                        "template_color": "green" if failed_count == 0 else "red"
                    },
                    "elements": [
                        {
                            "tag": "div",
                            "text": {
                                "tag": "lark_md",
                                "content": f"**Time**: {datetime.now().strftime('%Y-%m-%d %H:%M')} (Asia/Tokyo)\n\n**Summary**:\n- Total Items: {total_items}\n- Failed Items: {failed_count}"
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
                    "alt": {"tag": "plain_text", "content": "Screenshot"}
                })
                # Add separator
                card["card"]["elements"].append({"tag": "hr"})
                # Add timestamp
                card["card"]["elements"].append({
                    "tag": "div",
                    "text": {
                        "tag": "plain_text",
                        "content": f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} (Asia/Tokyo)"
                    }
                })
                # Add newline before closing
                card["card"]["elements"].append({
                    "tag": "div",
                    "text": {
                        "tag": "plain_text",
                        "content": f"\n\n---\n*Powered by GitHub Actions*"
                    }
                })

            response = requests.post(webhook_url, json=card, timeout=10)
            print(f"Notification sent: {response.status_code}")

            await browser.close()

            print("=" * 60)
            print("MONITOR COMPLETED SUCCESSFULLY!")
            print("=" * 60)

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


async def upload_image_to_lark_async(image_path: str, app_id: str, app_secret: str) -> str:
    """
    Upload image to Lark IM API - async version.
    
    Returns: image_key or None
    """
    try:
        import lark_oapi
        from lark_oapi.im.v1.model.create_image_request import CreateImageRequest
        from lark_oapi.im.v1.model.create_image_request_body import CreateImageRequestBody
        from lark_oapi.api.im.v1.model.get_token_response import GetTokenResponse
        from lark_oapi.api.im.v1.resource.image import Image as ImImage
        import lark_oapi

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

    except Exception as e:
        print(f"Image upload error: {e}")
        import traceback
        traceback.print_exc()
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


async def get_lark_access_token(app_id: str, app_secret: str) -> str:
    """Get Lark access token."""
    # Try async first, fallback to sync
    token = await get_lark_access_token_async(app_id, app_secret)
    if not token:
        print("Falling back to sync token request...")
        token = get_lark_access_token_sync(app_id, app_secret)
    return token


def get_lark_access_token_sync(app_id: str, app_secret: str) -> str:
    """Get Lark access token - synchronous version."""
    try:
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

    except Exception as e:
        print(f"Token error: {e}")
        return None


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
