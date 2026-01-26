#!/usr/bin/env python3
"""Debug version - analyze page structure in GitHub Actions."""

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
    direct_kb_url = os.environ.get("DIRECT_KB_URL", "")
    base_url = os.environ.get("BASE_URL", "https://admin.gbase.ai")

    print("=" * 60)
    print("KB Monitor - DEBUG MODE")
    print("=" * 60)

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            # Step 1: Login
            print(f"[Step 1] Logging in to {base_url}")
            await page.goto(base_url, wait_until="load", timeout=60000)
            await asyncio.sleep(2)

            await page.fill('input[name="username"]', username)
            await page.fill('input[type="password"]', password)

            for selector in ['button[type="submit"]', 'button:has-text("ログイン")']:
                try:
                    if await page.locator(selector).count() > 0:
                        await page.locator(selector).first.click()
                        print(f"  ✓ Login clicked")
                        break
                except:
                    continue

            # Wait for Auth0 redirect - may take longer than expected
            print("  Waiting for login to complete (checking for redirect)...")
            max_wait_time = 30  # seconds
            check_interval = 2
            elapsed = 0
            login_success = False

            initial_url = page.url
            print(f"  Initial URL after clicking login: {page.url[:80]}")

            while elapsed < max_wait_time:
                await asyncio.sleep(check_interval)
                elapsed += check_interval

                current_url = page.url
                print(f"  [{elapsed}s] Current URL: {current_url[:80]}")

                # Check if we're no longer on login page
                if "/login" not in current_url and "auth0.com" not in current_url:
                    print(f"  ✓ Login completed! Redirected to: {current_url[:80]}")
                    login_success = True
                    break

                # If URL changed from initial, we're making progress
                if current_url != initial_url:
                    print(f"  ... URL changed, redirect in progress ...")
                    initial_url = current_url

            # If still on login/Auth0 page, try navigating to base URL directly
            if not login_success or "/login" in page.url or "auth0.com" in page.url:
                print("  ⚠ Login redirect may not have completed, trying direct navigation...")
                await page.goto(base_url, wait_until="load", timeout=60000)
                await asyncio.sleep(5)
                print(f"  After direct nav: {page.url[:80]}")

            # Step 2: Navigate to KB page
            print(f"\n[Step 2] Navigating to KB page...")
            await page.goto(direct_kb_url, wait_until="load", timeout=60000)

            # Wait longer for dynamic content
            print("  Waiting 10 seconds for dynamic content...")
            await asyncio.sleep(10)

            print(f"  ✓ Current URL: {page.url}")
            print(f"  Page title: {await page.title()}")

            # Step 3: Analyze page structure
            print(f"\n[Step 3] Analyzing page structure...")

            # Save page HTML for analysis
            html_dir = Path("debug_output")
            html_dir.mkdir(exist_ok=True)
            html_file = html_dir / f"page_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            html_file.write_text(await page.content(), encoding='utf-8')
            print(f"  ✓ Page HTML saved: {html_file}")

            # Check for common patterns
            print(f"\n[Step 4] Checking for various elements...")

            # Test 1: Check if page has any tables
            table_count = await page.locator('table').count()
            print(f"  Tables found: {table_count}")

            # Test 2: Check for tbody
            tbody_count = await page.locator('tbody').count()
            print(f"  tbody elements: {tbody_count}")

            # Test 3: Check for tr (table rows)
            tr_count = await page.locator('tr').count()
            print(f"  tr elements: {tr_count}")

            # Test 4: Check for ARIA rows
            aria_row_count = await page.locator('[role="row"]').count()
            print(f"  [role='row'] elements: {aria_row_count}")

            # Test 5: Check for common list patterns
            print(f"\n[Step 5] Checking for list patterns...")

            list_patterns = [
                ('ul li', 'Unordered list items'),
                ('ol li', 'Ordered list items'),
                ('div[class*="list"]', 'Divs with "list" in class'),
                ('div[class*="file"]', 'Divs with "file" in class'),
                ('div[class*="row"]', 'Divs with "row" in class'),
                ('[data-testid]', 'Elements with data-testid'),
                ('[data-row-key]', 'Elements with row key (Ant Design)'),
            ]

            for selector, description in list_patterns:
                count = await page.locator(selector).count()
                if count > 0:
                    print(f"  ✓ {description}: {count}")
                    # Show first 3 items
                    for i in range(min(3, count)):
                        try:
                            text = await page.locator(selector).nth(i).inner_text()
                            preview = text.strip()[:80].replace('\n', ' ')
                            print(f"    [{i}] {preview}...")
                        except:
                            pass

            # Test 6: Look for status text in page
            print(f"\n[Step 6] Searching for failure indicators in page...")

            failure_indicators = ["失敗", "エラー", "error", "failed", "成功", "完了"]

            for indicator in failure_indicators:
                try:
                    elements = await page.get_by_text(indicator).all()
                    if elements:
                        print(f"  ✓ '{indicator}': found {len(elements)} times")
                        # Show context around first occurrence
                        if len(elements) > 0:
                            try:
                                parent_text = await elements[0].evaluate("el => el.closest('div, td, li, tr')?.textContent")
                                if parent_text:
                                    preview = parent_text.strip()[:100].replace('\n', ' ')
                                    print(f"    Context: {preview}...")
                            except:
                                pass
                except:
                    pass

            # Test 7: Try scrolling to trigger lazy loading
            print(f"\n[Step 7] Trying to scroll page...")

            # Scroll to bottom
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(3)

            # Check again for rows
            tr_after_scroll = await page.locator('tr').count()
            print(f"  tr elements after scroll: {tr_after_scroll}")

            # Test 8: Look for any data grids
            print(f"\n[Step 8] Checking for data grid libraries...")

            grid_patterns = [
                ('.ag-root', 'AG Grid'),
                ('.react-grid', 'React Grid'),
                ('.ant-table', 'Ant Design Table'),
                ('.MuiTable-root', 'Material-UI Table'),
                ('[class*="DataGrid"]', 'MUI DataGrid'),
                ('[class*="table"]', 'Generic table class'),
            ]

            for selector, description in grid_patterns:
                count = await page.locator(selector).count()
                if count > 0:
                    print(f"  ✓ {description}: {count}")

            # Take screenshot
            screenshot_path = f"screenshots/debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            os.makedirs("screenshots", exist_ok=True)
            await page.screenshot(path=screenshot_path, full_page=True)
            print(f"\n  ✓ Screenshot saved: {screenshot_path}")

            await browser.close()

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
