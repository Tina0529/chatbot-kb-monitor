#!/usr/bin/env python3
"""测试 Lark 图片上传功能"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import load_config, load_secrets, setup_logger
from notifications import create_notifier


def test_image_upload():
    """测试图片上传"""
    config = load_config()
    secrets = load_secrets()
    logger = setup_logger("test_upload", config)

    logger.info("=" * 60)
    logger.info("Testing Lark Image Upload")
    logger.info("=" * 60)

    # Create notifier
    notifier = create_notifier(config, secrets)

    # Find a screenshot to test with
    screenshot_dir = Path(__file__).parent.parent / "screenshots"
    screenshots = list(screenshot_dir.glob("kb_monitor_*.png"))

    if not screenshots:
        logger.error(f"No screenshots found in {screenshot_dir}")
        return

    test_image = screenshots[-1]  # Use most recent
    logger.info(f"Testing with: {test_image}")
    logger.info(f"File size: {test_image.stat().st_size} bytes")

    # Test getting access token
    logger.info("\n[1] Testing access token...")
    token = notifier._get_access_token()
    if token:
        logger.info(f"✓ Token obtained: {token[:20]}...")
    else:
        logger.error("✗ Failed to get token")
        return

    # Test image upload
    logger.info("\n[2] Testing image upload...")
    image_key = notifier.upload_image(str(test_image))

    if image_key:
        logger.info(f"✓ Upload successful!")
        logger.info(f"  Image key: {image_key}")
    else:
        logger.error("✗ Upload failed")

    logger.info("\n" + "=" * 60)
    logger.info("Test complete")
    logger.info("=" * 60)


if __name__ == "__main__":
    test_image_upload()
