#!/usr/bin/env python3
"""
Playwright 调试工具 - 帮助找到正确的页面选择器
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
    print("Playwright 调试工具")
    print("=" * 60)
    print()

    async with async_playwright() as p:
        # 启动浏览器（非 headless 模式，可以看到操作）
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=1000  # 慢速执行，方便观察
        )

        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            locale='ja-JP',
        )

        page = await context.new_page()
        page.set_default_timeout(30000)

        try:
            # Step 1: 导航到登录页
            print(f"[1] 导航到: {BASE_URL}")
            await page.goto(BASE_URL, wait_until="networkidle")
            print("   ✓ 页面加载完成")
            print(f"   当前 URL: {page.url}")
            print()

            # 等待用户观察
            input("按 Enter 继续到登录...")

            # Step 2: 查找并填写登录表单
            print("[2] 查找登录字段...")

            # 尝试多种选择器
            username_selectors = [
                'input[type="email"]',
                'input[name="username"]',
                'input[name="email"]',
                'input#email',
                'input[placeholder*="mail" i]',
                'input[placeholder*="メール" i]',
            ]

            username_input = None
            for selector in username_selectors:
                try:
                    if await page.locator(selector).count() > 0:
                        username_input = page.locator(selector).first
                        print(f"   ✓ 找到用户名输入框: {selector}")
                        break
                except:
                    continue

            if not username_input:
                print("   ✗ 未找到用户名输入框，请手动登录")
                input("登录完成后按 Enter...")
            else:
                await username_input.fill(USERNAME)
                print(f"   ✓ 已填写用户名")

                password_selectors = [
                    'input[type="password"]',
                    'input[name="password"]',
                ]

                password_input = None
                for selector in password_selectors:
                    try:
                        if await page.locator(selector).count() > 0:
                            password_input = page.locator(selector).first
                            print(f"   ✓ 找到密码输入框: {selector}")
                            break
                    except:
                        continue

                if password_input:
                    await password_input.fill(PASSWORD)
                    print(f"   ✓ 已填写密码")

                    # 查找登录按钮
                    login_button = page.get_by_role("button", name="ログイン")
                    if await login_button.count() == 0:
                        login_button = page.get_by_role("button", name="Login")
                    if await login_button.count() == 0:
                        login_button = page.locator('button[type="submit"]')

                    await login_button.first.click()
                    print("   ✓ 已点击登录按钮")

                    await page.wait_for_load_state("networkidle")
                    print(f"   ✓ 登录完成")
                    print(f"   当前 URL: {page.url}")

            print()
            input("按 Enter 继续分析页面...")

            # Step 3: 分析页面并查找所有链接和按钮
            print("[3] 分析页面元素...")
            print()

            # 获取所有链接
            print("=== 所有包含 'ナレッジ' 或 '知识' 的链接 ===")
            links = await page.locator('a:has-text("ナレッジ"), a:has-text("知識"), a:has-text("知識")').all()
            for i, link in enumerate(links):
                try:
                    text = await link.inner_text()
                    href = await link.get_attribute('href')
                    print(f"  [{i}] {text.strip()}")
                    print(f"      href: {href}")
                except:
                    pass

            print()
            print("=== 所有包含 'ニュウマン' 的链接 ===")
            links = await page.locator('a:has-text("ニュウマン")').all()
            for i, link in enumerate(links):
                try:
                    text = await link.inner_text()
                    href = await link.get_attribute('href')
                    print(f"  [{i}] {text.strip()}")
                    print(f"      href: {href}")
                except:
                    pass

            print()
            print("=== 所有按钮 ===")
            buttons = await page.locator('button').all()
            for i, btn in enumerate(buttons[:20]):  # 只显示前20个
                try:
                    text = await btn.inner_text()
                    if text.strip():
                        print(f"  [{i}] {text.strip()}")
                except:
                    pass

            print()
            input("按 Enter 获取页面 HTML...")

            # Step 4: 输出页面 HTML 用于分析
            print("[4] 页面 HTML 结构（前 5000 字符）:")
            print("-" * 60)
            html = await page.inner_html("body")
            print(html[:5000])
            print("-" * 60)
            print()

            # 保存完整 HTML 到文件
            output_file = Path(__file__).parent.parent / "debug_page.html"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html)
            print(f"✓ 完整 HTML 已保存到: {output_file}")

            print()
            print("=" * 60)
            print("调试完成！浏览器将保持打开状态...")
            print("=" * 60)

            # 保持浏览器打开，等待用户手动操作
            input("按 Enter 关闭浏览器并退出...")

        except Exception as e:
            print(f"错误: {e}")
            import traceback
            traceback.print_exc()
            input("按 Enter 退出...")

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
