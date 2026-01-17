#!/usr/bin/env python3
"""Chatbot Knowledge Base Monitor - Main entry point.

This script monitors the chatbot knowledge base for failed file processing,
captures screenshots, triggers retries, and sends notifications.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent))

from utils import load_config, load_secrets, setup_logger, ensure_directories, get_logger
from automation import BrowserController, KBMonitor
from notifications import create_notifier


async def main() -> int:
    """
    Main async entry point.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    # Load configuration
    try:
        config = load_config()
        secrets = load_secrets()
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        print("\nPlease ensure config/config.yaml exists.", file=sys.stderr)
        print("For GitHub Actions: Set environment variables (KB_USERNAME, KB_PASSWORD, LARK_WEBHOOK_URL, etc.)", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    # Setup logging
    logger = setup_logger("kb_monitor", config)
    logger.info("=" * 60)
    logger.info("Chatbot KB Monitor starting")
    logger.info("=" * 60)

    # Ensure directories exist
    ensure_directories(config)

    # Get credentials
    username = secrets.credentials.get("username")
    password = secrets.credentials.get("password")

    if not username or not password:
        logger.error("Username or password not found in secrets.yaml")
        return 1

    # Initialize components
    browser_controller: Optional[BrowserController] = None
    notifier = create_notifier(config, secrets)

    try:
        # Initialize browser controller
        logger.info("Initializing browser controller")
        browser_controller = BrowserController(config)

        # Start browser
        if not await browser_controller.start():
            logger.error("Failed to start browser")
            if notifier:
                notifier.send_error_alert("Failed to start browser")
            return 1

        # Run monitoring
        logger.info("Starting KB status check")
        monitor = KBMonitor(config, browser_controller)

        result = await monitor.check_status(
            username=username,
            password=password
        )

        # Log results
        if result.success:
            logger.info(f"Monitoring completed successfully")
            logger.info(f"Total items: {result.total_items}")
            logger.info(f"Failed items: {len(result.failed_items)}")
            logger.info(f"Retries triggered: {result.retries_triggered}")
            logger.info(f"Screenshots: {len(result.screenshots_taken)}")
        else:
            logger.error(f"Monitoring failed: {result.error}")

        # Send notification
        if notifier:
            logger.info("Sending Lark notification")
            notification_sent = notifier.send_summary(result, secrets)

            if notification_sent:
                logger.info("Notification sent successfully")
            else:
                logger.warning("Failed to send notification")

        # Return success if monitoring completed (even with failures)
        # Return failure only if there was a system error
        return 0 if result.success else 1

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 130  # Standard exit code for SIGINT

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)

        # Send error alert
        if notifier:
            notifier.send_error_alert(str(e), {
                "timestamp": datetime.now().isoformat(),
                "script": "main.py"
            })

        return 1

    finally:
        # Cleanup
        logger.info("Cleaning up")
        if browser_controller:
            await browser_controller.close()

        logger.info("Session complete")
        logger.info("=" * 60)


def run_sync() -> int:
    """
    Synchronous entry point for shell scripts.

    Returns:
        Exit code
    """
    try:
        return asyncio.run(main())
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(run_sync())
