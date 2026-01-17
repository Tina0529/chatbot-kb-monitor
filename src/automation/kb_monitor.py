"""Knowledge base monitoring - core orchestration logic."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from .browser_controller import BrowserController, NavigationResult
from .retry_handler import RetryHandler, RetryResult
from utils import get_logger, AppConfig


@dataclass
class FailedItem:
    """Represents a failed KB item."""
    file_name: str
    status_text: str
    error_message: Optional[str] = None
    screenshot_path: Optional[str] = None


@dataclass
class MonitorResult:
    """Result of a monitoring run."""
    success: bool
    timestamp: datetime
    total_items: int = 0
    failed_items: List[FailedItem] = field(default_factory=list)
    screenshots_taken: List[str] = field(default_factory=list)
    retries_triggered: int = 0
    error: Optional[str] = None
    execution_time: float = 0.0

    @property
    def has_failures(self) -> bool:
        """Check if any failures were detected."""
        return len(self.failed_items) > 0


class KBMonitor:
    """
    Monitors knowledge base file processing status.

    Orchestrates browser automation to:
    1. Login to admin panel
    2. Navigate to KB files page
    3. Scan for failed status items
    4. Capture screenshots of errors
    5. Trigger retry for failed items
    """

    def __init__(self, config: AppConfig, browser_controller: BrowserController):
        """
        Initialize KB monitor.

        Args:
            config: Application configuration
            browser_controller: Browser automation controller
        """
        self.config = config
        self.browser = browser_controller
        self.retry_handler = RetryHandler(config)
        self.logger = get_logger("kb_monitor")

    async def check_status(
        self,
        username: str,
        password: str
    ) -> MonitorResult:
        """
        Run complete monitoring workflow.

        Args:
            username: Admin panel username
            password: Admin panel password

        Returns:
            MonitorResult with scan results
        """
        start_time = datetime.now()
        result = MonitorResult(success=False, timestamp=start_time)

        try:
            # Step 1: Login
            self.logger.info("Step 1: Logging in to admin panel")
            login_result = await self.browser.login(
                username=username,
                password=password,
                base_url=self.config.monitoring.base_url
            )

            if not login_result.success:
                result.error = f"Login failed: {login_result.message}"
                self.logger.error(result.error)
                return result

            # Step 2: Navigate to KB files page
            self.logger.info("Step 2: Navigating to KB files page")

            # Use direct URL if available, otherwise use step-by-step navigation
            if self.config.monitoring.direct_kb_url:
                self.logger.info("Using direct KB URL")
                nav_result = await self.browser.navigate_to_url(self.config.monitoring.direct_kb_url)
            else:
                self.logger.info("Using step-by-step navigation")
                nav_result = await self.browser.navigate_to_kb(
                    kb_name=self.config.monitoring.kb_name,
                    related_kb_text=self.config.monitoring.navigation.related_kb,
                    file_docs_text=self.config.monitoring.navigation.file_documents
                )

            if not nav_result.success:
                result.error = f"Navigation failed: {nav_result.message}"
                self.logger.error(result.error)
                return result

            # Step 3: Scan for failures
            self.logger.info("Step 3: Scanning for failed items")
            failed_items = await self._scan_failures()
            result.failed_items = failed_items
            result.total_items = await self._count_total_items()

            self.logger.info(f"Found {len(failed_items)} failed items out of {result.total_items} total")

            # Step 4: Always take full page screenshot first
            self.logger.info("Step 4: Taking status page screenshot")
            full_screenshot = await self._take_status_screenshot()
            if full_screenshot:
                result.screenshots_taken.append(full_screenshot)

            if failed_items:
                # Step 5: Capture failure details (hover and screenshot)
                self.logger.info("Step 5: Capturing failure details with tooltips")
                await self._capture_failure_details(failed_items)
                result.screenshots_taken.extend([
                    item.screenshot_path for item in failed_items
                    if item.screenshot_path
                ])

                # Step 6: Trigger retries
                self.logger.info("Step 6: Triggering retries for failed items")
                retry_count = await self._trigger_retries(failed_items)
                result.retries_triggered = retry_count
            else:
                self.logger.info("No failures detected - monitoring complete")

            result.success = True

        except Exception as e:
            result.error = f"Monitoring failed: {str(e)}"
            self.logger.error(result.error, exc_info=True)
            result.success = False

        finally:
            # Calculate execution time
            result.execution_time = (datetime.now() - start_time).total_seconds()

        return result

    async def _scan_failures(self) -> List[FailedItem]:
        """
        Scan the page for failed status items.

        Returns:
            List of FailedItem objects
        """
        failed_items = []

        try:
            # More reliable approach: check each table row for failure indicators
            rows = await self.browser.page.locator('tbody tr').all()
            self.logger.debug(f"Scanning {len(rows)} rows for failures")

            for row_index, row in enumerate(rows):
                try:
                    # Get the full text content of this row
                    row_text = await row.inner_text()

                    # Check if any failure indicator is in this row
                    has_failure = False
                    matched_indicator = None

                    for indicator in self.config.monitoring.failure_indicators:
                        if indicator in row_text:
                            has_failure = True
                            matched_indicator = indicator
                            break

                    if has_failure:
                        # Extract file name (usually first column or text)
                        file_name = await self._extract_file_name_from_row(row, row_text)

                        self.logger.debug(f"Row {row_index} has failure: {file_name}")

                        failed_items.append(FailedItem(
                            file_name=file_name or f"Row_{row_index}",
                            status_text=matched_indicator,
                            error_message=None,
                            screenshot_path=None
                        ))

                except Exception as e:
                    self.logger.debug(f"Error scanning row {row_index}: {e}")
                    continue

            # Log results
            if failed_items:
                self.logger.warning(f"Found {len(failed_items)} failed items")
                for item in failed_items:
                    self.logger.warning(f"  - {item.file_name}: {item.status_text}")
            else:
                self.logger.debug("No failures found in any rows")

        except Exception as e:
            self.logger.error(f"Error scanning for failures: {e}")

        return failed_items

    async def _extract_file_name_from_row(self, row, row_text: str) -> Optional[str]:
        """
        Extract file name from a table row.

        Args:
            row: Playwright Locator for the row element
            row_text: Text content of the row

        Returns:
            Extracted file name or None
        """
        if not row_text:
            return None

        # Try to get the first cell (td) which usually contains the file name
        try:
            first_cell = row.locator('td').first
            if await first_cell.count() > 0:
                cell_text = await first_cell.inner_text()
                if cell_text and cell_text.strip():
                    return cell_text.strip()
        except:
            pass

        # Parse the row text - file name is usually the first meaningful text
        lines = row_text.split('\n')
        for line in lines:
            line = line.strip()
            # Skip empty lines and known column headers
            if line and line not in ['リソース', 'タイトル', 'タイプ', 'サイズ', 'ステータス', 'モデル', 'トークン数', '最終更新日', 'アクション']:
                # This is likely the file name
                # Clean up common artifacts
                file_name = line.split('\t')[0].strip()
                if len(file_name) > 3:  # Minimum reasonable file name length
                    return file_name

        # Fallback: return first non-empty word
        words = row_text.strip().split()
        if words:
            first_word = words[0]
            # Clean up any trailing artifacts
            for char in ['\t', '\n', '	']:
                first_word = first_word.split(char)[0]
            return first_word

        return None

    def _extract_file_name(self, row_text: str) -> Optional[str]:
        """
        Extract file name from row text.

        Args:
            row_text: Text content of a table row

        Returns:
            Extracted file name or None
        """
        if not row_text:
            return None

        # Split by common delimiters
        parts = row_text.split('\t')
        if len(parts) > 1:
            return parts[0].strip()

        parts = row_text.split('|')
        if len(parts) > 1:
            return parts[0].strip()

        # Return first meaningful word
        words = row_text.strip().split()
        if words:
            return words[0]

        return None

    async def _count_total_items(self) -> int:
        """
        Count total number of items on the page.

        Returns:
            Total item count (excluding table headers)
        """
        try:
            # Try to find table data rows (exclude header)
            # tbody tr excludes the table header row
            rows = await self.browser.page.locator('tbody tr').all()

            # Fallback to regular tr if tbody doesn't exist
            if len(rows) == 0:
                all_rows = await self.browser.page.locator('tr').all()
                # Assume first row is header, subtract 1
                if len(all_rows) > 0:
                    return len(all_rows) - 1
                return 0

            return len(rows)
        except:
            # Fallback: return count of failed items as minimum
            return 0

    async def _capture_failure_details(self, failed_items: List[FailedItem]) -> None:
        """
        Capture screenshots and error messages for each failed item.
        Hovers over failed status to reveal error tooltips.

        Args:
            failed_items: List of failed items to document
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        for i, item in enumerate(failed_items):
            try:
                self.logger.info(f"Capturing details for failure {i+1}/{len(failed_items)}: {item.file_name}")

                # Find all table rows
                rows = await self.browser.page.locator('tbody tr').all()

                # Find the row containing this failed item
                target_row = None
                for row in rows:
                    row_text = await row.inner_text()
                    # Check if this row contains the file name and failure indicator
                    if item.file_name in row_text and item.status_text in row_text:
                        target_row = row
                        break

                if not target_row:
                    self.logger.warning(f"Could not find row for: {item.file_name}")
                    # Fallback: just take a screenshot without hover
                    screenshot_path = self._get_screenshot_path(f"error_{i+1}_{timestamp}")
                    await self.browser.take_screenshot(screenshot_path)
                    item.screenshot_path = screenshot_path
                    continue

                # Find the status cell in this row (look for cell with failure indicator)
                status_cell = None
                cells = await target_row.locator('td').all()

                for cell in cells:
                    cell_text = await cell.inner_text()
                    if item.status_text in cell_text:
                        status_cell = cell
                        break

                if status_cell:
                    # Hover over the status cell to reveal tooltip
                    self.logger.debug(f"Hovering over status cell for: {item.file_name}")
                    await status_cell.hover()

                    # Wait for tooltip to appear
                    await asyncio.sleep(1)

                    # Try to capture tooltip text
                    tooltip_text = await self._get_tooltip_text()
                    if tooltip_text:
                        item.error_message = tooltip_text
                        self.logger.info(f"Error message: {tooltip_text[:100]}...")

                    # Take screenshot with tooltip visible
                    screenshot_path = self._get_screenshot_path(f"error_{i+1}_{timestamp}")
                    await self.browser.take_screenshot(screenshot_path)
                    item.screenshot_path = screenshot_path
                    self.logger.debug(f"Screenshot saved: {screenshot_path}")
                else:
                    self.logger.warning(f"Could not find status cell for: {item.file_name}")
                    # Fallback screenshot
                    screenshot_path = self._get_screenshot_path(f"error_{i+1}_{timestamp}")
                    await self.browser.take_screenshot(screenshot_path)
                    item.screenshot_path = screenshot_path

            except Exception as e:
                self.logger.warning(f"Failed to capture details for {item.file_name}: {e}")

    async def _get_tooltip_text(self) -> Optional[str]:
        """
        Try to get tooltip text from the page.

        Returns:
            Tooltip text or None
        """
        try:
            # Common tooltip selectors
            selectors = [
                '[role="tooltip"]',
                '.tooltip',
                '.error-tooltip',
                '[data-tooltip]',
            ]

            for selector in selectors:
                try:
                    tooltip = self.browser.page.locator(selector).first
                    if await tooltip.is_visible():
                        text = await tooltip.inner_text()
                        if text:
                            return text
                except:
                    continue

            return None
        except:
            return None

    async def _take_status_screenshot(self) -> Optional[str]:
        """
        Take a screenshot of the full status page.

        Returns:
            Path to screenshot or None
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = self._get_screenshot_path(f"status_{timestamp}")

        return await self.browser.take_screenshot(
            screenshot_path,
            full_page=True
        )

    def _get_screenshot_path(self, filename: str) -> str:
        """
        Get full path for a screenshot file.

        Args:
            filename: Base filename

        Returns:
            Full path to screenshot file
        """
        base_dir = Path(__file__).parent.parent.parent
        screenshot_dir = base_dir / self.config.screenshots.directory
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        extension = self.config.screenshots.format
        return str(screenshot_dir / f"{self.config.screenshots.prefix}{filename}.{extension}")

    async def _trigger_retries(self, failed_items: List[FailedItem]) -> int:
        """
        Trigger retry for all failed items.

        Args:
            failed_items: List of items to retry

        Returns:
            Number of retries triggered
        """
        retries_triggered = 0

        try:
            # Look for "Retry All" or similar button
            retry_texts = ["再試行", "リトライ", "Retry", "再実行"]

            for retry_text in retry_texts:
                if await self.browser.click_button_with_text(retry_text):
                    self.logger.info(f"Clicked '{retry_text}' button")
                    retries_triggered = len(failed_items)

                    # Wait for action to complete
                    await asyncio.sleep(2)

                    # Take confirmation screenshot
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    confirm_screenshot = self._get_screenshot_path(f"retry_confirm_{timestamp}")
                    await self.browser.take_screenshot(confirm_screenshot)

                    return retries_triggered

            # If no bulk retry button, try individual retries
            self.logger.info("No bulk retry button found, trying individual retries")
            for item in failed_items:
                try:
                    # Try to find retry button near the failed item
                    if await self.browser.click_button_with_text(item.status_text):
                        retries_triggered += 1
                        await asyncio.sleep(0.5)
                except:
                    continue

        except Exception as e:
            self.logger.error(f"Error triggering retries: {e}")

        return retries_triggered

    async def close(self) -> None:
        """Close the browser and cleanup."""
        await self.browser.close()
