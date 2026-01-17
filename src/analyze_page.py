#!/usr/bin/env python3
"""
分析页面结构 - 找到正确的文件列表选择器
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from playwright.async_api import async_playwright
from utils import load_config, load_secrets


async def main():
    # 加载配置
    config = load_config()
    secrets = load_secrets()

    async with async_playwright() as p:
        # 启动浏览器（可见模式）
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()

        # 登录
        print("[1] 登录中...")
        await page.goto("https://admin.gbase.ai")
        await page.wait_for_load_state("networkidle")

        await page.fill('input[name="username"]', secrets.credentials["username"])
        await page.fill('input[type="password"]', secrets.credentials["password"])
        await page.get_by_role("button", name="ログイン").or_(page.locator('button[type="submit"]')).first.click()
        await page.wait_for_load_state("networkidle")
        print("   ✓ 登录成功")

        # 导航到文件页面
        print(f"[2] 导航到文件页面...")
        target_url = config.monitoring.direct_kb_url
        await page.goto(target_url)
        await page.wait_for_load_state("networkidle")
        print(f"   ✓ 当前 URL: {page.url}")

        # 保存截图
        screenshot_dir = Path(__file__).parent.parent / "screenshots"
        screenshot_dir.mkdir(exist_ok=True)
        await page.screenshot(path=str(screenshot_dir / "analysis_page.png"), full_page=True)
        print(f"   ✓ 截图保存: screenshots/analysis_page.png")

        # 分析页面结构
        print("\n[3] 分析页面元素...")
        print("-" * 60)

        # 查找所有可能包含文件列表的元素
        selectors_to_test = [
            '[role="row"]',
            'tr',
            'tbody tr',
            'table tr',
            '.file-item',
            '.list-item',
            '[data-testid*="file" i]',
            '[data-testid*="row" i]',
        ]

        for selector in selectors_to_test:
            try:
                count = await page.locator(selector).count()
                if count > 0:
                    print(f"\n选择器: {selector}")
                    print(f"  找到 {count} 个元素")

                    # 显示前3个元素的文本内容
                    for i in range(min(3, count)):
                        try:
                            text = await page.locator(selector).nth(i).inner_text()
                            if text.strip():
                                preview = text.strip()[:80].replace('\n', ' ')
                                print(f"  [{i}] {preview}...")
                        except:
                            pass
            except Exception as e:
                pass

        # 查找状态相关的元素
        print("\n" + "-" * 60)
        print("[4] 查找状态指示器...")

        status_indicators = ["失敗", "エラー", "成功", "完了", "処理中", "error", "success", "failed"]

        for indicator in status_indicators:
            try:
                elements = await page.get_by_text(indicator).all()
                if elements:
                    print(f"\n'{indicator}': 找到 {len(elements)} 个")

                    # 显示包含该文字的父元素
                    for i, el in enumerate(elements[:3]):
                        try:
                            # 获取父元素的文本
                            parent_text = await el.evaluate("el => el.closest('tr, div, li')?.textContent")
                            if parent_text:
                                preview = parent_text.strip()[:100].replace('\n', ' ')
                                print(f"  [{i}] {preview}...")
                        except:
                            pass
            except:
                pass

        # 保存页面 HTML
        print("\n" + "-" * 60)
        print("[5] 保存页面 HTML...")
        html = await page.inner_html("body")
        html_file = Path(__file__).parent.parent / "debug_output" / "file_page.html"
        html_file.parent.mkdir(exist_ok=True)
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"   ✓ HTML 保存: {html_file}")

        # 查找所有表格
        print("\n" + "-" * 60)
        print("[6] 查找表格...")
        tables = await page.locator('table').all()
        print(f"找到 {len(tables)} 个表格")

        for i, table in enumerate(tables):
            try:
                rows = await table.locator('tr').all()
                print(f"  表格 {i}: {len(rows)} 行")

                # 显示表头
                if rows:
                    header = await rows[0].inner_text()
                    print(f"    表头: {header[:100]}...")
            except:
                pass

        print("\n" + "=" * 60)
        print("分析完成！浏览器将保持打开 30 秒...")
        print("=" * 60)

        await asyncio.sleep(30)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
