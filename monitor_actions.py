#!/usr/bin/env python3
"""Simplified monitor script for GitHub Actions - with login support."""

import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

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

    # Helper function to get Japan time
    def get_japan_time() -> datetime:
        """Get current time in Japan timezone (UTC+9)."""
        japan_tz = timezone(timedelta(hours=9))
        return datetime.now(japan_tz)

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
            failed_rows = []  # Store failed rows with file names
            files_found = False
            used_selector = None

            for selector, description in selectors_to_try:
                try:
                    print(f"  Trying: {description} ({selector})")
                    rows = await page.locator(selector).all()

                    if len(rows) > 0:
                        print(f"  ✓ Found {len(rows)} items using '{selector}'")
                        files_found = True
                        total_items = len(rows)
                        used_selector = selector

                        # Scan for failures and store row elements
                        failure_indicators = ["失敗", "エラー", "error", "failed"]

                        for i, row in enumerate(rows):
                            try:
                                row_text = await row.inner_text()

                                # Check for failure indicators
                                is_failed = False
                                for indicator in failure_indicators:
                                    if indicator in row_text:
                                        is_failed = True
                                        break

                                if is_failed:
                                    # Extract file name (first cell usually)
                                    try:
                                        first_cell = row.locator('td').first
                                        if await first_cell.count() > 0:
                                            file_name = await first_cell.inner_text()
                                            file_name = file_name.strip()
                                            failed_rows.append({
                                                'row': row,
                                                'file_name': file_name,
                                                'index': i
                                            })
                                            print(f"    Failed: {file_name}")
                                    except:
                                        failed_rows.append({
                                            'row': row,
                                            'file_name': f'File #{i}',
                                            'index': i
                                        })
                                        print(f"    Failed: (unable to get name)")
                            except Exception as e:
                                continue

                        print(f"  Total: {total_items} items, {len(failed_rows)} failed")
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

**Time**: {get_japan_time().strftime('%Y-%m-%d %H:%M')} (Asia/Tokyo)

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

            print(f"\n[Step 4] SCAN COMPLETE: {total_items} total items, {len(failed_rows)} failed")

            # Step 4.5: Retry failed items (if any)
            retry_results = []
            if failed_rows:
                print(f"\n[Step 4.5] Retrying {len(failed_rows)} failed items...")
                retry_results = await retry_failed_items(page, failed_rows, used_selector)

            # Step 5: Take screenshot
            timestamp = get_japan_time().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"screenshots/status_{timestamp}.png"
            os.makedirs("screenshots", exist_ok=True)

            await page.screenshot(path=screenshot_path, full_page=True)
            print(f"Screenshot saved: {screenshot_path}")

            # Step 6: Upload screenshot to Lark (optional)
            image_key = None
            if app_id and app_secret:
                try:
                    image_key = await upload_image_to_lark_sdk(
                        screenshot_path, app_id, app_secret
                    )
                except Exception as e:
                    print(f"  ⚠ Image upload failed (continuing without image): {e}")
                    image_key = None

            # Step 7: Send notification
            import requests

            # Calculate final status
            initial_failed = len(failed_rows)
            successful_retries = sum(1 for r in retry_results if r['success'])
            still_failed = initial_failed - successful_retries

            color = "green" if still_failed == 0 else ("turquoise" if successful_retries > 0 else "red")
            emoji = "✅" if still_failed == 0 else ("🔄" if successful_retries > 0 else "⚠️")

            # Build notification content
            summary_lines = [
                f"**Time**: {get_japan_time().strftime('%Y-%m-%d %H:%M')} (Asia/Tokyo)",
                "",
                "**Summary**:",
                f"• Total Items: {total_items}",
                f"• Initially Failed: {initial_failed}",
            ]

            if retry_results:
                summary_lines.extend([
                    f"• Successfully Retried: {successful_retries}",
                    f"• Still Failed: {still_failed}",
                    f"• Status: {'✅ All OK' if still_failed == 0 else '🔄 Partially Recovered' if successful_retries > 0 else '⚠️ Has Failures'}",
                ])
            else:
                summary_lines.extend([
                    f"• Failed Items: {initial_failed}",
                    f"• Status: {'✅ All OK' if initial_failed == 0 else '⚠️ Has Failures'}",
                ])

            summary_lines.append(f"**Screenshot**: {'See below' if image_key else 'No screenshot available'}")

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
                                "content": "\n".join(summary_lines)
                            }
                        }
                    ]
                }
            }

            # Add retry details if any retries were performed
            if retry_results:
                retry_details = []
                for result in retry_results:
                    status_icon = "✅" if result['success'] else "❌"
                    retry_details.append(f"{status_icon} **{result['file_name']}**")
                    if result['attempts'] > 0:
                        retry_details.append(f"   Attempts: {result['attempts']}, Result: {result['final_status']}")

                if retry_details:
                    card["card"]["elements"].append({"tag": "hr"})
                    card["card"]["elements"].append({
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": "**Retry Details**:\n" + "\n".join(retry_details[:10])
                        }
                    })
                    if len(retry_details) > 10:
                        card["card"]["elements"].append({
                            "tag": "div",
                            "text": {
                                "tag": "lark_md",
                                "content": f"\n... and {len(retry_details) - 10} more"
                            }
                        })

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

**Time**: {get_japan_time().strftime('%Y-%m-%d %H:%M')} (Asia/Tokyo)

**Error**: {str(e)}

---
*This is an automated message*"""

        response = requests.post(webhook_url, json={"msg_type": "text", "content": {"text": error_msg}}, timeout=10)
        print(f"Error notification sent: {response.status_code}")

        return 1

    return 0


async def upload_image_to_lark_sdk(image_path: str, app_id: str, app_secret: str) -> str:
    """Upload image to Lark using official SDK (same as local script)."""
    # Use correct import path
    from lark_oapi.api.im.v1.model.create_image_request import CreateImageRequest
    from lark_oapi.api.im.v1.model.create_image_request_body import CreateImageRequestBody
    import lark_oapi

    # Read image
    image_file = Path(image_path)
    if not image_file.exists():
        print(f"Image not found: {image_path}")
        return None

    try:
        print(f"Uploading image using Lark SDK...")

        # Create image upload request
        request = (
            CreateImageRequest.builder()
            .request_body(
                CreateImageRequestBody.builder()
                .image_type("message")  # for use in message cards
                .build()
            )
            .build()
        )

        # Open file and attach to request body
        with open(image_file, 'rb') as f:
            request.body.image = f

            # Get client using app credentials
            client = (
                lark_oapi.Client.builder()
                .app_id(app_id)
                .app_secret(app_secret)
                .build()
            )

            # Call the API
            response = client.im.v1.image.create(request)

        # Handle response
        if response.code != 0:
            print(f"Lark API error: code={response.code}, msg={response.msg}")
            return None

        if not response.data or not hasattr(response.data, 'image_key'):
            print("No image_key in response")
            return None

        image_key = response.data.image_key
        print(f"✓ Image uploaded: {image_key}")
        return image_key

    except ImportError as e:
        print(f"lark-oapi SDK import error: {e}")
        return None
    except Exception as e:
        print(f"Upload error: {e}")
        import traceback
        traceback.print_exc()
        return None


async def retry_failed_items(page, failed_rows: list, table_selector: str) -> list:
    """
    Retry failed items by clicking Action menu and selecting "重新学习".

    Args:
        page: Playwright page object
        failed_rows: List of dicts with 'row', 'file_name', 'index'
        table_selector: The selector that successfully found the table

    Returns:
        List of retry results with file_name, attempts, final_status
    """
    results = []
    failure_indicators = ["失敗", "エラー", "error", "failed"]
    MAX_RETRIES = 3

    for item in failed_rows:
        file_name = item['file_name']
        row_index = item['index']

        print(f"\n  Retrying: {file_name}")
        result = {
            'file_name': file_name,
            'attempts': 0,
            'final_status': 'still_failed',
            'success': False
        }

        for attempt in range(1, MAX_RETRIES + 1):
            result['attempts'] = attempt
            print(f"    Attempt {attempt}/{MAX_RETRIES}...", end=" ")

            try:
                # Re-find the row (page may have changed)
                rows = await page.locator(table_selector).all()
                if row_index >= len(rows):
                    print(f"SKIP (row no longer exists)")
                    result['final_status'] = 'row_disappeared'
                    break

                current_row = rows[row_index]

                # Click the three-dot menu (ActionIcon)
                # Try multiple selectors for the menu button
                menu_clicked = False
                menu_selectors = [
                    current_row.locator('.mantine-ActionIcon-icon'),
                    current_row.locator('[class*="ActionIcon"]'),
                    current_row.locator('button[aria-label*="more" i]'),
                    current_row.locator('button:has-text("…")'),
                    current_row.locator('button:last-child'),
                ]

                for menu_sel in menu_selectors:
                    try:
                        if await menu_sel.count() > 0:
                            await menu_sel.first.click()
                            menu_clicked = True
                            await asyncio.sleep(1)  # Wait for menu to appear
                            break
                    except:
                        continue

                if not menu_clicked:
                    print(f"FAIL (could not find menu button)")
                    result['final_status'] = 'menu_not_found'
                    break

                # Click "重新学习" (Retry learning) menu item
                # The menu item label class: mantine-Menu-itemLabel
                retry_clicked = False
                retry_selectors = [
                    page.locator('.mantine-Menu-itemLabel:has-text("重新学习")'),
                    page.locator('.mantine-Menu-itemLabel:has-text("再学習")'),
                    page.locator('[class*="Menu-item"]:has-text("重新学习")'),
                    page.locator('[class*="Menu-item"]:has-text("再学習")'),
                    page.get_by_text("重新学习"),
                    page.get_by_text("再学習"),
                ]

                for retry_sel in retry_selectors:
                    try:
                        if await retry_sel.count() > 0:
                            await retry_sel.first.click()
                            retry_clicked = True
                            await asyncio.sleep(3)  # Wait for processing
                            break
                    except:
                        continue

                if not retry_clicked:
                    print(f"FAIL (could not find retry option)")
                    # Click outside to close menu
                    await page.keyboard.press('Escape')
                    await asyncio.sleep(0.5)
                    result['final_status'] = 'retry_option_not_found'
                    break

                # Check if status changed
                await asyncio.sleep(2)  # Extra wait for status update
                rows_after = await page.locator(table_selector).all()
                if row_index < len(rows_after):
                    check_row = rows_after[row_index]
                    row_text = await check_row.inner_text()

                    # Check if still has failure indicators
                    still_failed = any(indicator in row_text for indicator in failure_indicators)

                    if not still_failed:
                        print(f"SUCCESS! ✓")
                        result['final_status'] = 'success'
                        result['success'] = True
                        break
                    else:
                        if attempt < MAX_RETRIES:
                            print(f"still failed...")
                        else:
                            print(f"FAIL (max retries reached)")
                            result['final_status'] = 'max_retries_reached'
                else:
                    print(f"FAIL (row disappeared)")
                    result['final_status'] = 'row_disappeared'
                    break

            except Exception as e:
                print(f"ERROR: {e}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(2)
                else:
                    result['final_status'] = f'error: {str(e)[:50]}'

        results.append(result)
        print(f"    Final: {result['final_status']}")

    return results


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
