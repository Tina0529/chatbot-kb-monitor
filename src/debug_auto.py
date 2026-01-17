#!/usr/bin/env python3
"""
Playwright 自动调试工具 - 自动登录并分析页面
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from playwright.async_api import async_playwright

# 凭据
USERNAME = "support@sparticle.com"
PASSWORD = "Sparticle2026"
BASE_URL = "https://admin.gbase.ai"


async def main():
    print("=" * 60)
    print("Playwright 自动调试工具")
    print("=" * 60)
    print()

    async with async_playwright() as p:
        # 启动浏览器（非 headless 模式）
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=500
        )

        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            locale='ja-JP',
        )

        page = await context.new_page()
        page.set_default_timeout(30000)

        output_dir = Path(__file__).parent.parent / "debug_output"
        output_dir.mkdir(exist_ok=True)

        try:
            # Step 1: 导航到登录页
            print(f"[1] 导航到: {BASE_URL}")
            await page.goto(BASE_URL, wait_until="networkidle")
            print(f"   当前 URL: {page.url}")

            # 截图登录页
            await page.screenshot(path=str(output_dir / "01_login_page.png"))
            print(f"   ✓ 截图已保存: debug_output/01_login_page.png")

            # Step 2: 自动登录
            print()
            print("[2] 尝试自动登录...")

            # 查找用户名输入框
            username_input = None
            for selector in ['input[type="email"]', 'input[name="username"]', 'input[name="email"]']:
                try:
                    if await page.locator(selector).count() > 0:
                        username_input = page.locator(selector).first
                        print(f"   ✓ 找到用户名输入: {selector}")
                        break
                except:
                    continue

            if username_input:
                await username_input.fill(USERNAME)

                # 查找密码输入框
                for selector in ['input[type="password"]', 'input[name="password"]']:
                    try:
                        if await page.locator(selector).count() > 0:
                            password_input = page.locator(selector).first
                            print(f"   ✓ 找到密码输入: {selector}")
                            await password_input.fill(PASSWORD)
                            break
                    except:
                        continue

                # 点击登录按钮
                await page.get_by_role("button", name="ログイン").or_(
                    page.get_by_role("button", name="Login")
                ).or_(
                    page.locator('button[type="submit"]')
                ).first.click()

                await page.wait_for_load_state("networkidle", timeout=15000)
                print(f"   ✓ 登录完成")
                print(f"   当前 URL: {page.url}")

                # 截图登录后页面
                await page.screenshot(path=str(output_dir / "02_after_login.png"), full_page=True)
                print(f"   ✓ 截图已保存: debug_output/02_after_login.png")

            # 等待一下让用户看到
            await asyncio.sleep(3)

            # Step 3: 分析页面元素
            print()
            print("[3] 分析页面元素...")

            # 获取所有链接文本
            all_links = await page.locator('a').all()
            print(f"\n   共找到 {len(all_links)} 个链接")

            # 查找包含特定文字的链接
            search_terms = ["ナレッジ", "知識", "Knowledge", "KB", "ニュウマン"]
            found_links = {}

            for term in search_terms:
                matching = await page.locator(f'a:has-text("{term}")').all()
                if matching:
                    found_links[term] = matching

            if found_links:
                print(f"\n   找到包含关键词的链接:")
                for term, links in found_links.items():
                    print(f"\n   关键词 '{term}':")
                    for link in links[:5]:
                        try:
                            text = await link.inner_text()
                            print(f"      - {text.strip()[:50]}")
                        except:
                            pass

            # 截图页面元素分析
            await page.screenshot(path=str(output_dir / "03_page_elements.png"))
            print(f"\n   ✓ 截图已保存: debug_output/03_page_elements.png")

            # Step 4: 保存页面 HTML
            html = await page.inner_html("body")
            html_file = output_dir / "page_source.html"
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html)
            print(f"\n   ✓ HTML 已保存: debug_output/page_source.html")

            # Step 5: 尝试点击导航
            print()
            print("[4] 尝试导航...")

            # 尝试找到 "関連ナレッジベース"
            nav_texts = ["関連ナレッジベース", "関連KB", "Related KB", "Knowledge Base"]

            for nav_text in nav_texts:
                try:
                    link = page.get_by_text(nav_text).first
                    if await link.is_visible():
                        print(f"   ✓ 找到链接: '{nav_text}'")
                        await link.click()
                        await page.wait_for_load_state("networkidle", timeout=10000)
                        print(f"   ✓ 已点击")
                        print(f"   当前 URL: {page.url}")

                        await page.screenshot(path=str(output_dir / "04_after_nav_click.png"), full_page=True)
                        print(f"   ✓ 截图已保存: debug_output/04_after_nav_click.png")

                        # 保存这个页面的 HTML
                        html2 = await page.inner_html("body")
                        with open(output_dir / "page_source_2.html", 'w', encoding='utf-8') as f:
                            f.write(html2)
                        print(f"   ✓ HTML 已保存: debug_output/page_source_2.html")

                        await asyncio.sleep(3)
                        break
                except Exception as e:
                    print(f"   ✗ '{nav_text}' 未找到: {e}")
                    continue

            print()
            print("=" * 60)
            print("调试完成！")
            print(f"所有输出文件保存在: {output_dir}")
            print("=" * 60)
            print()
            print("浏览器将保持打开 30 秒供你观察...")

            await asyncio.sleep(30)

        except Exception as e:
            print(f"\n错误: {e}")
            import traceback
            traceback.print_exc()

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
