"""Browser automation controller using Playwright."""

import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime

try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Locator, TimeoutError as PlaywrightTimeout
except ImportError:
    # Fallback for compatibility
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Locator


from utils import get_logger, AppConfig


@dataclass
class NavigationResult:
    """Result of a navigation operation."""
    success: bool
    message: str
    screenshot_path: Optional[str] = None
    error: Optional[str] = None


@dataclass
class LoginResult:
    """Result of a login operation."""
    success: bool
    message: str
    error: Optional[str] = None


class BrowserController:
    """
    Controls browser automation for KB monitoring.

    Uses Playwright for reliable browser automation with support for
    modern web applications.
    """

    # Common selectors (generic, may need adjustment for specific site)
    SELECTORS = {
        'username_input': 'input[type="email"], input[name="username"], input[name="email"], input#email',
        'password_input': 'input[type="password"], input[name="password"], input#password',
        'login_button': 'button[type="submit"], button:has-text("ログイン"), button:has-text("Login")',
        'link_by_text': 'text={text}',
    }

    def __init__(self, config: AppConfig):
        """
        Initialize browser controller.

        Args:
            config: Application configuration
        """
        self.config = config
        self.logger = get_logger("browser_controller")

        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def start(self) -> bool:
        """
        Launch browser and create context.

        Returns:
            True if browser started successfully
        """
        try:
            self._playwright = await async_playwright().start()

            # Launch browser
            self._browser = await self._playwright.chromium.launch(
                headless=self.config.browser.headless,
                slow_mo=self.config.browser.slow_mo,
            )

            # Create context with options
            self._context = await self._browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                locale='ja-JP',
                timezone_id='Asia/Tokyo',
            )

            # Set default timeout
            self._context.set_default_timeout(self.config.browser.timeout)

            # Create new page
            self._page = await self._context.new_page()

            self.logger.info(f"Browser started (headless={self.config.browser.headless})")
            return True

        except Exception as e:
            self.logger.error(f"Failed to start browser: {e}")
            return False

    async def close(self) -> None:
        """Close browser and cleanup resources."""
        try:
            if self._page:
                await self._page.close()
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()

            self.logger.info("Browser closed")

        except Exception as e:
            self.logger.warning(f"Error during browser cleanup: {e}")

    async def navigate(self, url: str) -> NavigationResult:
        """
        Navigate to a URL.

        Args:
            url: Target URL

        Returns:
            NavigationResult with success status
        """
        try:
            self.logger.info(f"Navigating to: {url}")
            await self._page.goto(url, wait_until="networkidle")
            return NavigationResult(
                success=True,
                message=f"Successfully navigated to {url}"
            )

        except Exception as e:
            self.logger.error(f"Navigation failed: {e}")
            return NavigationResult(
                success=False,
                message=f"Navigation to {url} failed",
                error=str(e)
            )

    async def login(self, username: str, password: str, base_url: str) -> LoginResult:
        """
        Login to admin panel.

        Args:
            username: Login username/email
            password: Login password
            base_url: Base URL of admin panel

        Returns:
            LoginResult with success status
        """
        try:
            # Navigate to login page
            result = await self.navigate(base_url)
            if not result.success:
                return LoginResult(
                    success=False,
                    message="Failed to reach login page",
                    error=result.error
                )

            # Wait for page to load
            await self._page.wait_for_load_state("networkidle")

            # Try to find username input using multiple selectors
            username_selectors = self.SELECTORS['username_input'].split(', ')
            username_input = None

            for selector in username_selectors:
                try:
                    username_input = self._page.locator(selector).first
                    if await username_input.is_visible():
                        break
                except:
                    continue

            if not username_input or not await username_input.is_visible():
                return LoginResult(
                    success=False,
                    message="Could not find username input field"
                )

            # Fill username
            await username_input.fill(username)
            self.logger.debug("Username filled")

            # Find and fill password
            password_selectors = self.SELECTORS['password_input'].split(', ')
            password_input = None

            for selector in password_selectors:
                try:
                    password_input = self._page.locator(selector).first
                    if await password_input.is_visible():
                        break
                except:
                    continue

            if not password_input or not await password_input.is_visible():
                return LoginResult(
                    success=False,
                    message="Could not find password input field"
                )

            await password_input.fill(password)
            self.logger.debug("Password filled")

            # Find and click login button
            button_selectors = self.SELECTORS['login_button'].split(', ')
            login_button = None

            for selector in button_selectors:
                try:
                    login_button = self._page.locator(selector).first
                    if await login_button.is_visible():
                        break
                except:
                    continue

            if not login_button or not await login_button.is_visible():
                return LoginResult(
                    success=False,
                    message="Could not find login button"
                )

            # Click and wait for navigation
            async with self._page.expect_navigation(wait_until="networkidle", timeout=15000):
                await login_button.click()

            # Check if login was successful
            current_url = self._page.url
            if "login" in current_url.lower():
                return LoginResult(
                    success=False,
                    message="Login appears to have failed (still on login page)",
                    error="Authentication failed"
                )

            self.logger.info(f"Login successful, current URL: {current_url}")
            return LoginResult(
                success=True,
                message="Login successful"
            )

        except Exception as e:
            self.logger.error(f"Login failed: {e}")
            return LoginResult(
                success=False,
                message="Login failed with exception",
                error=str(e)
            )

    async def navigate_to_kb(self, kb_name: str, related_kb_text: str, file_docs_text: str) -> NavigationResult:
        """
        Navigate to knowledge base files page.

        Uses text-based navigation for robustness.

        Args:
            kb_name: Name of the knowledge base
            related_kb_text: Text for "Related KB" link
            file_docs_text: Text for "Files and Documents" link

        Returns:
            NavigationResult with success status
        """
        try:
            # Click "関連ナレッジベース" (Related Knowledge Base)
            self.logger.info(f"Looking for '{related_kb_text}' link")
            related_link = self._page.get_by_text(related_kb_text).first

            if not await related_link.is_visible():
                # Try alternative approach
                related_link = self._page.locator(f"*[role='link']:has-text('{related_kb_text}')").first

            await related_link.click()
            await self._page.wait_for_load_state("networkidle")
            self.logger.debug(f"Clicked '{related_kb_text}'")

            # Click KB name
            self.logger.info(f"Looking for '{kb_name}' link")
            kb_link = self._page.get_by_text(kb_name).first

            if not await kb_link.is_visible():
                kb_link = self._page.locator(f"*[role='link']:has-text('{kb_name}')").first

            await kb_link.click()
            await self._page.wait_for_load_state("networkidle")
            self.logger.debug(f"Clicked '{kb_name}'")

            # Click "ファイルとドキュメント" (Files and Documents)
            self.logger.info(f"Looking for '{file_docs_text}' link")
            docs_link = self._page.get_by_text(file_docs_text).first

            if not await docs_link.is_visible():
                docs_link = self._page.locator(f"*[role='link']:has-text('{file_docs_text}')").first

            await docs_link.click()
            await self._page.wait_for_load_state("networkidle")
            self.logger.debug(f"Clicked '{file_docs_text}'")

            return NavigationResult(
                success=True,
                message="Successfully navigated to KB files page"
            )

        except Exception as e:
            self.logger.error(f"Navigation to KB failed: {e}")
            return NavigationResult(
                success=False,
                message="Failed to navigate to KB files page",
                error=str(e)
            )

    async def navigate_to_url(self, url: str) -> NavigationResult:
        """
        Navigate directly to a specific URL.

        Useful for direct access to KB page after login.

        Args:
            url: Direct URL to navigate to

        Returns:
            NavigationResult with success status
        """
        try:
            self.logger.info(f"Navigating directly to: {url}")
            await self._page.goto(url, wait_until="networkidle")

            # Wait a bit for any dynamic content to load
            await self._page.wait_for_timeout(2000)

            self.logger.info(f"Successfully navigated to: {self._page.url}")
            return NavigationResult(
                success=True,
                message=f"Successfully navigated to {url}"
            )

        except Exception as e:
            self.logger.error(f"Direct navigation failed: {e}")
            return NavigationResult(
                success=False,
                message=f"Failed to navigate to {url}",
                error=str(e)
            )

    async def take_screenshot(self, path: str, full_page: bool = True) -> Optional[str]:
        """
        Take a screenshot of the current page.

        Args:
            path: File path to save screenshot
            full_page: Capture full scrolling page

        Returns:
            Path to saved screenshot, or None if failed
        """
        try:
            screenshot_path = Path(path)
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)

            await self._page.screenshot(
                path=str(screenshot_path),
                full_page=full_page
            )

            self.logger.debug(f"Screenshot saved: {screenshot_path}")
            return str(screenshot_path)

        except Exception as e:
            self.logger.error(f"Screenshot failed: {e}")
            return None

    async def hover_element(self, text: str, timeout: int = 5000) -> bool:
        """
        Hover over an element containing specific text.

        Useful for revealing tooltips or error messages.

        Args:
            text: Text to search for in element
            timeout: Milliseconds to wait

        Returns:
            True if hover was successful
        """
        try:
            element = self._page.get_by_text(text).first
            await element.hover(timeout=timeout)
            self.logger.debug(f"Hovered over element containing: '{text}'")
            return True

        except Exception as e:
            self.logger.warning(f"Hover failed for '{text}': {e}")
            return False

    async def find_elements_with_text(self, text_patterns: List[str]) -> List[Locator]:
        """
        Find all elements containing any of the given text patterns.

        Args:
            text_patterns: List of text patterns to search for

        Returns:
            List of matching element locators
        """
        found_elements = []

        for pattern in text_patterns:
            try:
                elements = self._page.get_by_text(pattern).all()
                if elements:
                    found_elements.extend(elements)
            except:
                continue

        self.logger.debug(f"Found {len(found_elements)} elements matching patterns")
        return found_elements

    async def click_button_with_text(self, text: str) -> bool:
        """
        Click a button containing specific text.

        Args:
            text: Text to search for in button

        Returns:
            True if click was successful
        """
        try:
            button = self._page.get_by_role("button", name=text).first
            if await button.is_visible():
                await button.click()
                await self._page.wait_for_load_state("networkidle")
                self.logger.debug(f"Clicked button: '{text}'")
                return True
            return False

        except Exception as e:
            self.logger.warning(f"Failed to click button '{text}': {e}")
            return False

    async def get_page_text(self) -> str:
        """
        Get all visible text from the current page.

        Returns:
            Page text content
        """
        try:
            return await self._page.inner_text("body")
        except Exception as e:
            self.logger.error(f"Failed to get page text: {e}")
            return ""

    async def wait_for_selector(self, selector: str, timeout: Optional[int] = None) -> bool:
        """
        Wait for a selector to appear on the page.

        Args:
            selector: CSS selector to wait for
            timeout: Milliseconds to wait (default from config)

        Returns:
            True if selector appeared
        """
        try:
            timeout = timeout or self.config.browser.timeout
            await self._page.wait_for_selector(selector, timeout=timeout)
            return True
        except:
            return False

    @property
    def page(self) -> Optional[Page]:
        """Get the current page instance."""
        return self._page

    @property
    def is_active(self) -> bool:
        """Check if browser is currently active."""
        return self._page is not None and not self._page.is_closed()
