"""Lark notification sender using webhook with image upload support."""

import json
import base64
import mimetypes
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
import urllib.parse

import requests

from utils import get_logger, AppConfig, SecretsConfig

# Import Lark SDK for image upload
try:
    from lark_oapi.api.im.v1.model.create_image_request import CreateImageRequest
    from lark_oapi.api.im.v1.model.create_image_request_body import CreateImageRequestBody
    LARK_SDK_AVAILABLE = True
except ImportError:
    LARK_SDK_AVAILABLE = False
    import warnings
    warnings.warn("lark-oapi not installed, image upload will use fallback method")


class LarkNotifier:
    """
    Sends notifications to Lark via webhook.

    Supports Lark cards with rich formatting and image attachments.
    """

    # Lark API endpoints
    LARK_BASE_URL = "https://open.larksuite.com/open-apis"
    FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(self, webhook_url: str, config: AppConfig, app_id: Optional[str] = None, app_secret: Optional[str] = None):
        """
        Initialize Lark notifier.

        Args:
            webhook_url: Lark webhook URL
            config: Application configuration
            app_id: Lark app ID for image upload (optional)
            app_secret: Lark app secret for image upload (optional)
        """
        self.webhook_url = webhook_url
        self.config = config
        self.app_id = app_id
        self.app_secret = app_secret
        self.logger = get_logger("kb_monitor")

        # Determine which API to use based on webhook URL
        if "open.larksuite.com" in webhook_url:
            self.base_url = self.LARK_BASE_URL
        else:
            self.base_url = self.FEISHU_BASE_URL

        # Cache for access token (valid for 2 hours)
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[float] = None

    def _get_access_token(self) -> Optional[str]:
        """
        Get tenant access token for API calls.

        Returns:
            Access token or None if not configured
        """
        if not self.app_id or not self.app_secret:
            self.logger.warning("Lark app credentials not configured, cannot upload images")
            return None

        # Check if cached token is still valid
        if self._access_token and self._token_expiry:
            import time
            if time.time() < self._token_expiry:
                return self._access_token

        # Request new token
        try:
            url = f"{self.base_url}/auth/v3/tenant_access_token/internal"
            payload = {
                "app_id": self.app_id,
                "app_secret": self.app_secret
            }

            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()

            if result.get("code") != 0:
                self.logger.error(f"Failed to get access token: {result.get('msg')}")
                return None

            token = result.get("tenant_access_token")
            expire = result.get("expire", 7200) - 300  # Refresh 5 minutes before expiry

            import time
            self._access_token = token
            self._token_expiry = time.time() + expire

            self.logger.debug("Successfully obtained access token")
            return token

        except Exception as e:
            self.logger.error(f"Error getting access token: {e}")
            return None

    def upload_image(self, image_path: str) -> Optional[str]:
        """
        Upload an image to Lark using the official Lark SDK (lark-oapi).

        Uses the IM v1 image API specifically for message cards.

        Args:
            image_path: Path to image file

        Returns:
            Image key for use in cards, or None if upload failed
        """
        # Check if lark-oapi is available
        if not LARK_SDK_AVAILABLE:
            self.logger.error("lark-oapi SDK not installed. Run: pip install lark-oapi")
            return None

        token = self._get_access_token()
        if not token:
            return None

        try:
            image_file = Path(image_path)
            if not image_file.exists():
                self.logger.error(f"Image file not found: {image_path}")
                return None

            # Use the official Lark Python SDK (lark-oapi)
            # Reference: https://open.larksuite.com/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/image/create
            import lark_oapi

            self.logger.info(f"Using Lark SDK to upload {image_file.name}")

            # Create image upload request - note: image parameter must be a file-like object (IO)
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
                    .app_id(self.app_id or "")
                    .app_secret(self.app_secret or "")
                    .build()
                )

                # Call the API
                self.logger.info("Calling Lark IM v1 image/create API...")
                response = client.im.v1.image.create(request)

            # Handle response
            if response.code != 0:
                self.logger.error(f"Lark API error: code={response.code}, msg={response.msg}")
                return None

            if not response.data or not hasattr(response.data, 'image_key'):
                self.logger.error("No image_key in response")
                return None

            image_key = response.data.image_key
            self.logger.info(f"✓ Upload successful: {image_key}")
            return image_key

        except ImportError:
            self.logger.error("lark-oapi SDK not installed")
            return None

        except Exception as e:
            self.logger.error(f"Upload error: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())
            return None

    def send_summary(self, result: Any, secrets: Optional[SecretsConfig] = None) -> bool:
        """
        Send monitoring summary notification with image upload.
        Always uploads screenshots if available.

        Args:
            result: MonitorResult object with monitoring results
            secrets: Secrets configuration (for app credentials)

        Returns:
            True if notification sent successfully
        """
        try:
            # Upload screenshots if available (always upload, even without failures)
            image_keys = []
            if result.screenshots_taken:
                self.logger.info(f"Uploading {len(result.screenshots_taken)} screenshots...")

                # Upload up to 4 images (1 full page + 3 error screenshots)
                for screenshot_path in result.screenshots_taken[:4]:
                    image_key = self.upload_image(screenshot_path)
                    if image_key:
                        image_keys.append(image_key)
                    else:
                        self.logger.warning(f"Failed to upload: {screenshot_path}")

            # Build message card with images
            card = self._build_message_card(result, image_keys)
            return self._send_webhook(card)

        except Exception as e:
            self.logger.error(f"Failed to send notification: {e}")
            return False

    def _build_message_card(self, result: Any, image_keys: List[str] = None) -> Dict[str, Any]:
        """
        Build Lark card message.

        Args:
            result: MonitorResult object
            image_keys: List of uploaded image keys

        Returns:
            Lark card dictionary
        """
        # Determine card color based on status
        if result.has_failures:
            # Red theme for failures
            template_color = "red"
            status_emoji = "🔴"
            status_text = "Failures Detected"
        else:
            # Green theme for success
            template_color = "green"
            status_emoji = "✅"
            status_text = "No Failures"

        # Build summary
        summary_lines = [
            f"{status_emoji} **Status:** {status_text}",
            f"📊 **Total Items:** {result.total_items}",
            f"❌ **Failed:** {len(result.failed_items)}",
        ]

        if result.retries_triggered > 0:
            summary_lines.append(f"🔄 **Retries Triggered:** {result.retries_triggered}")

        summary_lines.append(f"⏱️ **Execution Time:** {result.execution_time:.1f}s")

        # Build card elements
        elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "\n".join(summary_lines)
                }
            }
        ]

        if result.failed_items:
            # Add separator
            elements.append({"tag": "hr"})

            # Add failed items details
            for i, item in enumerate(result.failed_items[:10], 1):  # Max 10 items
                item_text = f"**{i}.** {item.file_name}\n   Status: {item.status_text}"
                if item.error_message:
                    item_text += f"\n   Error: {item.error_message[:100]}..."

                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": item_text
                    }
                })

            if len(result.failed_items) > 10:
                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"\n... and {len(result.failed_items) - 10} more"
                    }
                })

        # Add images if available
        if image_keys:
            elements.append({"tag": "hr"})
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"📸 **Screenshots:**"
                }
            })

            for image_key in image_keys:
                elements.append({
                    "tag": "img",
                    "img_key": image_key,
                    "alt": {
                        "tag": "plain_text",
                        "content": "Screenshot"
                    }
                })
        elif result.screenshots_taken:
            # Image upload failed, mention file paths
            elements.append({"tag": "hr"})
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"📸 **Screenshots:** {len(result.screenshots_taken)} (saved locally)"
                }
            })

        # Add timestamp
        tz = self.config.lark.message_timezone
        timestamp = result.timestamp.strftime(f"%Y-%m-%d %H:%M:%S ({tz})")
        elements.append({"tag": "hr"})
        elements.append({
            "tag": "div",
            "text": {
                "tag": "plain_text",
                "content": f"Report generated: {timestamp}"
            }
        })

        # Build complete card
        card = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"KB Monitor Report - {status_emoji}"
                    },
                    "template_color": template_color
                },
                "elements": elements
            }
        }

        return card

    def _send_webhook(self, card: Dict[str, Any]) -> bool:
        """
        Send card to Lark webhook.

        Args:
            card: Lark card dictionary

        Returns:
            True if sent successfully
        """
        try:
            response = requests.post(
                self.webhook_url,
                json=card,
                timeout=self.config.lark.timeout
            )

            response.raise_for_status()

            result = response.json()
            if result.get("code") != 0:
                self.logger.error(f"Lark API error: {result.get('msg')}")
                return False

            self.logger.info("Notification sent successfully")
            return True

        except requests.RequestException as e:
            self.logger.error(f"Webhook request failed: {e}")
            return False

    def send_simple_message(self, message: str) -> bool:
        """
        Send a simple text message.

        Args:
            message: Text message to send

        Returns:
            True if sent successfully
        """
        card = {
            "msg_type": "text",
            "content": {
                "text": message
            }
        }

        return self._send_webhook(card)

    def send_error_alert(self, error: str, context: Optional[Dict] = None) -> bool:
        """
        Send an error alert notification.

        Args:
            error: Error message
            context: Optional context information

        Returns:
            True if sent successfully
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        content_lines = [
            f"🚨 **KB Monitor Error Alert**",
            f"",
            f"**Time:** {timestamp}",
            f"**Error:** {error}",
        ]

        if context:
            content_lines.append(f"**Context:**")
            for key, value in context.items():
                content_lines.append(f"  - {key}: {value}")

        card = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": "🚨 Error Alert"
                    },
                    "template_color": "red"
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": "\n".join(content_lines)
                        }
                    }
                ]
            }
        }

        return self._send_webhook(card)


def create_notifier(config: AppConfig, secrets: SecretsConfig) -> Optional['LarkNotifier']:
    """
    Create Lark notifier from configuration.

    Args:
        config: Application configuration
        secrets: Secrets configuration

    Returns:
        LarkNotifier instance or None if disabled
    """
    if not config.lark.enabled:
        return None

    webhook_url = secrets.lark.get("webhook_url")
    if not webhook_url:
        raise ValueError("Lark webhook URL not found in secrets.yaml")

    app_id = secrets.lark.get("app_id")
    app_secret = secrets.lark.get("app_secret")

    return LarkNotifier(
        webhook_url=webhook_url,
        config=config,
        app_id=app_id,
        app_secret=app_secret
    )
