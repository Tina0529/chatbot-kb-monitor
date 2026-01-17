"""Configuration loader with validation using Pydantic."""

import os
from pathlib import Path
from typing import Optional, List, Any

try:
    from pydantic import BaseModel, Field, validator
except ImportError:
    # Fallback for older pydantic versions
    from pydantic.v1 import BaseModel, Field, validator

import yaml


class BrowserConfig(BaseModel):
    """Browser configuration."""
    headless: bool = True
    timeout: int = 30000
    slow_mo: int = 0
    screenshot: dict = Field(default_factory=lambda: {"enabled": True, "full_page": True})


class NavigationConfig(BaseModel):
    """Navigation configuration."""
    related_kb: str = "関連ナレッジベース"
    file_documents: str = "ファイルとドキュメント"


class RetryConfig(BaseModel):
    """Retry configuration."""
    max_attempts: int = 3
    backoff_base: int = 2
    initial_delay: int = 1


class MonitoringConfig(BaseModel):
    """Monitoring configuration."""
    base_url: str = "https://admin.gbase.ai"
    direct_kb_url: Optional[str] = None  # Direct URL to KB page (skip navigation)
    kb_name: str = "ニュウマン高輪教育用"
    navigation: NavigationConfig = Field(default_factory=NavigationConfig)
    failure_indicators: List[str] = Field(default_factory=lambda: ["失敗", "エラー", "error", "failed"])
    retry: RetryConfig = Field(default_factory=RetryConfig)


class LoggingConfig(BaseModel):
    """Logging configuration."""
    level: str = "INFO"
    file: str = "logs/monitor.log"
    max_bytes: int = 10485760
    backup_count: int = 5

    @validator('level')
    def validate_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'Invalid log level: {v}. Must be one of {valid_levels}')
        return v.upper()


class ScreenshotConfig(BaseModel):
    """Screenshot configuration."""
    directory: str = "screenshots"
    prefix: str = "kb_monitor_"
    format: str = "png"

    @validator('format')
    def validate_format(cls, v):
        valid_formats = ['png', 'jpeg', 'jpg']
        if v.lower() not in valid_formats:
            raise ValueError(f'Invalid screenshot format: {v}. Must be one of {valid_formats}')
        return v.lower()


class LarkConfig(BaseModel):
    """Lark notification configuration."""
    enabled: bool = True
    timeout: int = 10
    message_timezone: str = "Asia/Tokyo"


class AppConfig(BaseModel):
    """Main application configuration."""
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    screenshots: ScreenshotConfig = Field(default_factory=ScreenshotConfig)
    lark: LarkConfig = Field(default_factory=LarkConfig)


class SecretsConfig(BaseModel):
    """Secrets configuration."""
    credentials: dict = Field(default_factory=lambda: {"username": "", "password": ""})
    lark: dict = Field(default_factory=lambda: {"webhook_url": ""})


def load_yaml(file_path: Path) -> dict:
    """Load YAML file with error handling."""
    if not file_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        try:
            return yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {file_path}: {e}")


def find_config_file(filename: str, search_paths: List[Path]) -> Path:
    """Find configuration file in search paths."""
    for path in search_paths:
        full_path = path / filename
        if full_path.exists():
            return full_path
    raise FileNotFoundError(f"Could not find {filename} in search paths: {search_paths}")


def get_config_dir() -> Path:
    """Get the configuration directory path."""
    # Start from current file location
    current_dir = Path(__file__).parent.absolute()

    # Look for config directory
    config_dir = current_dir.parent.parent / "config"
    if config_dir.exists():
        return config_dir

    # Fallback to current directory
    return Path.cwd() / "config"


def load_config(config_file: str = "config.yaml") -> AppConfig:
    """
    Load and validate application configuration.

    Args:
        config_file: Name of the config file to load

    Returns:
        AppConfig: Validated configuration object

    Raises:
        FileNotFoundError: If config file is not found
        ValueError: If config is invalid
    """
    config_dir = get_config_dir()
    config_path = config_dir / config_file

    config_data = load_yaml(config_path)

    # Merge with environment variables if present
    config_data = _merge_env_vars(config_data)

    return AppConfig(**config_data)


def load_secrets() -> SecretsConfig:
    """
    Load and validate secrets configuration.

    Returns:
        SecretsConfig: Validated secrets object

    Raises:
        FileNotFoundError: If secrets.yaml is not found
        ValueError: If secrets are invalid
    """
    config_dir = get_config_dir()
    secrets_path = config_dir / "secrets.yaml"

    secrets_data = load_yaml(secrets_path)

    return SecretsConfig(**secrets_data)


def _merge_env_vars(config: dict) -> dict:
    """
    Merge environment variables into configuration.

    Environment variables should be prefixed with KB_MONITOR_
    and use double underscores for nested keys.

    Example:
        KB_MONITOR_BROWSER__HEADLESS=false
        KB_MONITOR_LOGGING__LEVEL=DEBUG
    """
    prefix = "KB_MONITOR_"

    for key, value in os.environ.items():
        if key.startswith(prefix):
            # Remove prefix and split by double underscore
            config_path = key[len(prefix):].lower().split('__')

            # Navigate to the correct nested location
            current = config
            for part in config_path[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]

            # Set the value, converting to appropriate type
            final_key = config_path[-1]
            current[final_key] = _convert_env_value(value)

    return config


def _convert_env_value(value: str) -> Any:
    """Convert environment variable string to appropriate type."""
    # Boolean
    if value.lower() in ('true', 'yes', '1'):
        return True
    if value.lower() in ('false', 'no', '0'):
        return False

    # Integer
    try:
        return int(value)
    except ValueError:
        pass

    # Float
    try:
        return float(value)
    except ValueError:
        pass

    # String (default)
    return value


def ensure_directories(config: AppConfig) -> None:
    """
    Ensure required directories exist.

    Args:
        config: Application configuration
    """
    base_dir = get_config_dir().parent

    # Create logs directory
    log_path = base_dir / config.logging.file
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Create screenshots directory
    screenshot_dir = base_dir / config.screenshots.directory
    screenshot_dir.mkdir(parents=True, exist_ok=True)
