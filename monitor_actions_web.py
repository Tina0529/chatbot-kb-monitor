#!/usr/bin/env python3
"""Website Connector monitor for GitHub Actions.

Monitors the Website Connector data source page (data-source/web-connector).
Checks each row's Last Refresh block to ensure all sources are fully Learned
(Learning/Waiting/Failed/Unavailable counts are all 0, Status = Completed).

Unlike the file-based monitor (monitor_actions.py), this one:
  * Scans a different page URL (DIRECT_WEB_URL)
  * Uses positive-state detection (all-learned) instead of negative-keyword
    detection (失敗/エラー)
  * Does NOT trigger any retry — issues are reported and require manual
    investigation, since web-fetch failures are usually source-side problems
"""

import asyncio
import os
import re
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta


# Status labels we expect in the "Last Refresh" cell
STATUS_LABELS = ["Learned", "Learning", "Waiting", "Failed", "Unavailable"]


def parse_status_counts(text: str) -> dict:
    """Extract {Learned: N, Learning: N, ...} from a Last Refresh cell text.

    The cell typically renders as:
        Learned: 12
        Learning: 0
        Waiting: 0
        Failed: 0
        Unavailable: 0
    Some locales use a full-width colon (：).
    """
    counts = {}
    for label in STATUS_LABELS:
        m = re.search(rf"{label}\s*[：:]\s*(\d+)", text)
        counts[label] = int(m.group(1)) if m else None
    return counts


def is_row_healthy(status_text: str, counts: dict) -> bool:
    """A row is healthy when Status == Completed AND no outstanding work.

    Outstanding work = Learning/Waiting/Failed/Unavailable any > 0.
    Learned is allowed to be any value (including 0 — some sources may
    legitimately have no content, but we still surface them via the report).
    """
    if "completed" not in (status_text or "").lower():
        return False
    for label in ["Learning", "Waiting", "Failed", "Unavailable"]:
        v = counts.get(label)
        if v is None:
            # Couldn't parse — treat as anomaly so it surfaces
            return False
        if v > 0:
            return False
    return True


async def main() -> int:
    """Run web-connector monitoring with config from environment."""

    username = os.environ.get("KB_USERNAME", "")
    password = os.environ.get("KB_PASSWORD", "")
    webhook_url = os.environ.get("LARK_WEBHOOK_URL", "")
    app_id = os.environ.get("LARK_APP_ID", "")
    app_secret = os.environ.get("LARK_APP_SECRET", "")
    direct_url = os.environ.get("DIRECT_WEB_URL", "")
    base_url = os.environ.get("BASE_URL", "https://admin.gbase.ai")

    if not username or not password:
        print("ERROR: KB_USERNAME and KB_PASSWORD must be set")
        return 1
    if not webhook_url:
        print("ERROR: LARK_WEBHOOK_URL must be set")
        return 1
    if not direct_url:
        print("ERROR: DIRECT_WEB_URL must be set (web-connector page URL)")
        return 1

    print("=" * 60)
    print("Starting Website Connector Monitor")
    print("=" * 60)
    print(f"Username: {'***' + username[-4:]}")
    print(f"Webhook configured: {'YES' if webhook_url else 'NO'}")
    print(f"Lark App configured: {'YES' if app_id else 'NO'}")
    print(f"Direct URL: {direct_url[:80]}...")

    runner_utc = datetime.now(timezone.utc)
    runner_jp = runner_utc.astimezone(timezone(timedelta(hours=9)))
    print(f"Runner UTC time: {runner_utc.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Runner JP time:  {runner_jp.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    def get_japan_time() -> datetime:
        return datetime.now(timezone(timedelta(hours=9)))

    try:
        from playwright.async_api import async_playwright
        import requests

        print("Launching browser...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            # Step 1: Login (same flow as monitor_actions.py)
            print(f"[Step 1] Logging in to {base_url}")
            await page.goto(base_url, wait_until="load", timeout=60000)
            await asyncio.sleep(3)

            # Diagnostic: snapshot the login page before attempting fill
            os.makedirs("screenshots", exist_ok=True)
            try:
                pre_login_path = "screenshots/00_pre_login.png"
                await page.screenshot(path=pre_login_path, full_page=True)
                print(f"  [diag] Login page URL: {page.url}")
                print(f"  [diag] Login page title: {await page.title()}")
                print(f"  [diag] Pre-login screenshot: {pre_login_path}")

                # Show which input-like elements exist on the page
                inputs_info = await page.evaluate("""
                    () => Array.from(document.querySelectorAll('input')).map(el => ({
                        name: el.name, type: el.type, id: el.id,
                        placeholder: el.placeholder, autocomplete: el.autocomplete
                    }))
                """)
                print(f"  [diag] Inputs on page: {inputs_info}")
            except Exception as e:
                print(f"  [diag] Could not capture diagnostics: {e}")

            # Reusable login routine so we can retry if the session bounces back
            # to the auth page (the most common cause of the misleading
            # "No rows found" failure — the session simply wasn't authenticated).
            async def fill_and_submit_login() -> bool:
                print("  Filling credentials...")
                # Login page renders: <input id="account" type="text"
                # autocomplete="username"> + <input id="password" type="password">.
                # Put the known-good selectors FIRST — the previous order tried
                # name="username"/type=email/id=username first, each missing and
                # burning a 10s timeout (~30s wasted) before reaching the real one.
                username_selectors = [
                    'input[autocomplete="username"]',
                    'input#account',
                    'input[name="username"]',
                    'input[type="email"]',
                    'input[type="text"]',
                ]
                username_filled = False
                for sel in username_selectors:
                    try:
                        await page.wait_for_selector(sel, timeout=8000, state="visible")
                        await page.fill(sel, username)
                        print(f"  ✓ Filled username using: {sel}")
                        username_filled = True
                        break
                    except Exception as e:
                        print(f"  ✗ Selector '{sel}' didn't work: {str(e)[:80]}")
                        continue
                if not username_filled:
                    err_screenshot = "screenshots/01_no_username_field.png"
                    await page.screenshot(path=err_screenshot, full_page=True)
                    raise RuntimeError(f"Could not find username input field. See {err_screenshot}")

                for sel in ['input[type="password"]', 'input[name="password"]',
                            'input[autocomplete="current-password"]']:
                    try:
                        await page.fill(sel, password)
                        print(f"  ✓ Filled password using: {sel}")
                        break
                    except Exception:
                        continue

                print("  Clicking login button...")
                for selector in ['button[type="submit"]', 'button:has-text("ログイン")', '.login-button']:
                    try:
                        if await page.locator(selector).count() > 0:
                            await page.locator(selector).first.click()
                            print(f"  ✓ Clicked login using: {selector}")
                            return True
                    except Exception:
                        continue
                return False

            async def wait_for_login(max_wait_time: int = 45) -> bool:
                """Poll until we leave the /login (and Auth0) pages."""
                elapsed = 0
                while elapsed < max_wait_time:
                    await asyncio.sleep(2)
                    elapsed += 2
                    current_url = page.url
                    if "/login" not in current_url and "auth0.com" not in current_url:
                        print(f"  ✓ Login completed: {current_url[:80]}")
                        return True
                print(f"  ⚠ Still on login page after {max_wait_time}s: {page.url[:80]}")
                return False

            if not await fill_and_submit_login():
                print("  ERROR: Could not find login button")
                return 1
            print("  Waiting for login to complete...")
            await wait_for_login()

            # Step 2: Navigate to web-connector page and verify authentication.
            async def goto_web_connector() -> str:
                print(f"\n[Step 2] Navigating to web-connector page...")
                await page.goto(direct_url, wait_until="load", timeout=60000)
                # The SPA may redirect an unauthenticated session back to /login,
                # and renders the table asynchronously — give it a moment.
                await asyncio.sleep(5)
                print(f"  ✓ Current URL: {page.url[:80]}")
                return page.url

            current_url = await goto_web_connector()
            # If we got bounced back to the auth page, the session isn't
            # authenticated. Retry the login once before giving up.
            if "/login" in current_url or "/auth" in current_url:
                print("  ⚠ Bounced to auth page — session not authenticated. Retrying login once...")
                await page.goto(base_url, wait_until="load", timeout=60000)
                await asyncio.sleep(3)
                if await fill_and_submit_login():
                    await wait_for_login()
                    current_url = await goto_web_connector()

            if "/login" in current_url or "/auth" in current_url:
                err = "Login failed — still redirected to the auth page"
                print(f"\nERROR: {err}")
                try:
                    await page.screenshot(path="screenshots/02_login_failed.png", full_page=True)
                except Exception:
                    pass
                error_msg = (
                    f"⚠️ Website Monitor Failed\n\n"
                    f"**Time**: {get_japan_time().strftime('%Y-%m-%d %H:%M')} (Asia/Tokyo)\n\n"
                    f"**Error**: {err}\n\n"
                    f"**URL**: {current_url[:80]}\n\n"
                    f"**Please check**:\n"
                    f"1. KB_USERNAME / KB_PASSWORD secrets\n"
                    f"2. admin.gbase.ai login latency / availability\n\n"
                    f"---\n*This is an automated message*"
                )
                requests.post(webhook_url, json={"msg_type": "text", "content": {"text": error_msg}}, timeout=10)
                return 1

            # Step 3: Scan rows. The table is rendered client-side after an async
            # data fetch, so POLL for rows instead of reading the DOM once —
            # locator().all() does not wait, so a single read races the render.
            print(f"\n[Step 3] Scanning website connector rows...")
            selectors_to_try = [
                ('.mantine-Table-tbody tr', 'Mantine Table body rows'),
                ('[class*="mantine-Table-tbody"] tr', 'Mantine Table body (variant)'),
                ('tbody tr', 'Standard table body rows'),
                ('table tr', 'All table rows'),
                ('[role="row"]', 'ARIA rows'),
            ]

            rows = []
            used_selector = None
            scan_deadline = 45  # seconds to wait for the table to render
            waited = 0
            while waited < scan_deadline and not rows:
                for selector, description in selectors_to_try:
                    try:
                        candidate = await page.locator(selector).all()
                        if len(candidate) > 0:
                            rows = candidate
                            used_selector = selector
                            print(f"  ✓ Found {len(rows)} rows using '{selector}' (after {waited}s)")
                            break
                    except Exception as e:
                        print(f"  Selector '{selector}' failed: {e}")
                        continue
                if rows:
                    break
                await asyncio.sleep(3)
                waited += 3

            if not rows:
                err = "No rows found on web-connector page"
                print(f"\nERROR: {err}")
                try:
                    await page.screenshot(path="screenshots/03_no_rows.png", full_page=True)
                except Exception:
                    pass
                error_msg = (
                    f"⚠️ Website Monitor Failed\n\n"
                    f"**Time**: {get_japan_time().strftime('%Y-%m-%d %H:%M')} (Asia/Tokyo)\n\n"
                    f"**Error**: {err} (waited {scan_deadline}s for table render)\n\n"
                    f"**URL**: {page.url[:80]}\n\n"
                    f"**Please check**:\n"
                    f"1. DIRECT_WEB_URL secret is correct\n"
                    f"2. Login credentials\n"
                    f"3. Page structure may have changed\n\n"
                    f"---\n*This is an automated message*"
                )
                requests.post(webhook_url, json={"msg_type": "text", "content": {"text": error_msg}}, timeout=10)
                return 1

            # Parse each row
            row_results = []
            for i, row in enumerate(rows):
                try:
                    cells = await row.locator('td').all()
                    if len(cells) < 5:
                        # Header row or unexpected layout
                        continue

                    name = (await cells[0].inner_text()).strip()
                    status_text = (await cells[3].inner_text()).strip() if len(cells) > 3 else ""
                    last_refresh_text = (await cells[4].inner_text()).strip() if len(cells) > 4 else ""

                    counts = parse_status_counts(last_refresh_text)
                    healthy = is_row_healthy(status_text, counts)

                    row_results.append({
                        "name": name or f"Row_{i}",
                        "status": status_text,
                        "counts": counts,
                        "healthy": healthy,
                    })

                    icon = "✅" if healthy else "⚠️"
                    counts_summary = ", ".join(
                        f"{k}={v}" for k, v in counts.items() if v is not None
                    )
                    print(f"  {icon} {name}: status='{status_text}' {counts_summary}")
                except Exception as e:
                    print(f"  Row {i} parse error: {e}")
                    continue

            total = len(row_results)
            unhealthy = [r for r in row_results if not r["healthy"]]
            print(f"\n[Step 4] SCAN COMPLETE: {total} rows, {len(unhealthy)} issue(s)")

            # Step 5: Screenshot
            timestamp = get_japan_time().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"screenshots/web_status_{timestamp}.png"
            os.makedirs("screenshots", exist_ok=True)
            await page.screenshot(path=screenshot_path, full_page=True)
            print(f"Screenshot saved: {screenshot_path}")

            # Step 6: Optional image upload
            image_key = None
            if app_id and app_secret:
                try:
                    image_key = await upload_image_to_lark_sdk(screenshot_path, app_id, app_secret)
                except Exception as e:
                    print(f"  ⚠ Image upload failed (continuing without image): {e}")

            # Step 7: Build notification
            color = "green" if len(unhealthy) == 0 else "red"
            emoji = "✅" if len(unhealthy) == 0 else "⚠️"
            status_text_summary = "All Learned" if len(unhealthy) == 0 else f"{len(unhealthy)} issue(s)"

            summary_lines = [
                f"**Time**: {get_japan_time().strftime('%Y-%m-%d %H:%M')} (Asia/Tokyo)",
                "",
                "**Summary**:",
                f"• Total Sources: {total}",
                f"• Status: {emoji} {status_text_summary}",
            ]

            # Per-row breakdown (max 15 to avoid huge cards)
            detail_lines = []
            for r in row_results[:15]:
                icon = "✅" if r["healthy"] else "⚠️"
                counts = r["counts"]
                # Compact status: show non-zero non-Learned counts as red flags
                flags = []
                for label in ["Learning", "Waiting", "Failed", "Unavailable"]:
                    v = counts.get(label)
                    if v is not None and v > 0:
                        flags.append(f"{label}={v}")
                learned = counts.get("Learned")
                learned_str = f"Learned {learned}" if learned is not None else "Learned ?"
                flag_str = f", {', '.join(flags)}" if flags else ""
                detail_lines.append(f"{icon} **{r['name']}** — {r['status']}, {learned_str}{flag_str}")

            if len(row_results) > 15:
                detail_lines.append(f"\n... and {len(row_results) - 15} more")

            card = {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {"tag": "plain_text", "content": f"{emoji} Website Connector Monitor"},
                        "template_color": color,
                    },
                    "elements": [
                        {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(summary_lines)}},
                    ],
                },
            }

            if detail_lines:
                card["card"]["elements"].append({"tag": "hr"})
                card["card"]["elements"].append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": "**Per-source Status**:\n" + "\n".join(detail_lines)},
                })

            if image_key:
                card["card"]["elements"].append({
                    "tag": "img",
                    "img_key": image_key,
                    "alt": {"tag": "plain_text", "content": "Website Connector Screenshot"},
                })

            response = requests.post(webhook_url, json=card, timeout=10)
            print(f"Notification sent: {response.status_code}")

            await browser.close()

            print("\n" + "=" * 60)
            print("WEBSITE MONITOR COMPLETED SUCCESSFULLY!")
            print("=" * 60)

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

        try:
            import requests
            error_msg = (
                f"⚠️ Website Monitor Error\n\n"
                f"**Time**: {get_japan_time().strftime('%Y-%m-%d %H:%M')} (Asia/Tokyo)\n\n"
                f"**Error**: {str(e)}\n\n"
                f"---\n*This is an automated message*"
            )
            requests.post(webhook_url, json={"msg_type": "text", "content": {"text": error_msg}}, timeout=10)
        except Exception:
            pass

        return 1

    return 0


async def upload_image_to_lark_sdk(image_path: str, app_id: str, app_secret: str):
    """Upload image to Lark using official SDK (mirrors monitor_actions.py)."""
    from lark_oapi.api.im.v1.model.create_image_request import CreateImageRequest
    from lark_oapi.api.im.v1.model.create_image_request_body import CreateImageRequestBody
    import lark_oapi

    image_file = Path(image_path)
    if not image_file.exists():
        print(f"Image not found: {image_path}")
        return None

    try:
        print(f"Uploading image using Lark SDK...")
        request = (
            CreateImageRequest.builder()
            .request_body(
                CreateImageRequestBody.builder()
                .image_type("message")
                .build()
            )
            .build()
        )
        with open(image_file, 'rb') as f:
            request.body.image = f
            client = (
                lark_oapi.Client.builder()
                .app_id(app_id)
                .app_secret(app_secret)
                .build()
            )
            response = client.im.v1.image.create(request)

        if response.code != 0:
            print(f"Lark API error: code={response.code}, msg={response.msg}")
            return None
        if not response.data or not hasattr(response.data, 'image_key'):
            print("No image_key in response")
            return None

        image_key = response.data.image_key
        print(f"✓ Image uploaded: {image_key}")
        return image_key
    except Exception as e:
        print(f"Upload error: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
