"""Configuration management for the BookTok application."""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)


@dataclass
class DatabaseConfig:
    """Database configuration settings."""

    path: str = "booktok.db"
    max_retries: int = 3
    timeout: float = 30.0


@dataclass
class TelegramConfig:
    """Telegram bot configuration settings."""

    token: str = ""
    polling: bool = True


@dataclass
class SchedulerConfig:
    """Delivery scheduler configuration settings."""

    check_interval_seconds: int = 60
    max_retries: int = 5
    initial_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 30.0


@dataclass
class LoggingConfig:
    """Logging configuration settings."""

    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file: Optional[str] = None


@dataclass
class AppConfig:
    """Main application configuration."""

    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """Load configuration from environment variables and optional config file.

    Args:
        config_path: Optional path to config file (not yet implemented).

    Returns:
        AppConfig with all settings loaded.
    """
    config = AppConfig()

    database_path = os.environ.get("BOOKTOK_DB_PATH")
    if database_path:
        config.database.path = database_path

    db_retries = os.environ.get("BOOKTOK_DB_MAX_RETRIES")
    if db_retries:
        try:
            config.database.max_retries = int(db_retries)
        except ValueError:
            logger.warning(f"Invalid BOOKTOK_DB_MAX_RETRIES value: {db_retries}")

    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if telegram_token:
        config.telegram.token = telegram_token
    else:
        logger.warning("TELEGRAM_BOT_TOKEN not set - bot will not be able to run")

    polling = os.environ.get("TELEGRAM_POLLING")
    if polling:
        config.telegram.polling = polling.lower() in ("true", "1", "yes")

    check_interval = os.environ.get("BOOKTOK_CHECK_INTERVAL")
    if check_interval:
        try:
            config.scheduler.check_interval_seconds = int(check_interval)
        except ValueError:
            logger.warning(f"Invalid BOOKTOK_CHECK_INTERVAL value: {check_interval}")

    log_level = os.environ.get("BOOKTOK_LOG_LEVEL")
    if log_level:
        config.logging.level = log_level.upper()

    log_file = os.environ.get("BOOKTOK_LOG_FILE")
    if log_file:
        config.logging.file = log_file

    return config


def setup_logging(config: LoggingConfig) -> None:
    """Configure logging based on the provided configuration.

    Args:
        config: Logging configuration settings.
    """
    log_level = getattr(logging, config.level, logging.INFO)

    handlers: list[logging.Handler] = []

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(config.format))
    handlers.append(console_handler)

    if config.file:
        try:
            file_handler = logging.FileHandler(config.file)
            file_handler.setLevel(log_level)
            file_handler.setFormatter(logging.Formatter(config.format))
            handlers.append(file_handler)
        except Exception as e:
            logger.error(f"Failed to create log file {config.file}: {e}")

    logging.basicConfig(
        level=log_level,
        format=config.format,
        handlers=handlers,
    )

    logger.info(f"Logging configured with level: {config.level}")


def validate_config(config: AppConfig) -> bool:
    """Validate that the configuration is complete and valid.

    Args:
        config: Application configuration to validate.

    Returns:
        True if configuration is valid.
    """
    if not config.telegram.token:
        logger.error("TELEGRAM_BOT_TOKEN is required")
        return False

    if config.database.max_retries < 1:
        logger.error("Database max_retries must be at least 1")
        return False

    if config.scheduler.check_interval_seconds < 1:
        logger.error("Scheduler check interval must be at least 1 second")
        return False

    valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if config.logging.level not in valid_log_levels:
        logger.error(f"Invalid log level: {config.logging.level}")
        return False

    return True
