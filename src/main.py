"""Main entry point for the BookTok application."""

import asyncio
import logging
import signal
import sys
from typing import Optional


from booktok.config import AppConfig, load_config, setup_logging, validate_config
from booktok.database import (
    close_database,
    DatabaseConnectionError,
)
from booktok.delivery_scheduler import AutomatedDeliveryRunner
from booktok.repository import DatabaseConnectionManager
from booktok.summary_preprocessor import SummaryPreprocessorRunner
from booktok.telegram_bot import TelegramBotInterface


logger = logging.getLogger(__name__)


class BookTokApplication:
    """Main application class for BookTok."""

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        """Initialize the application.

        Args:
            config: Optional pre-loaded configuration. If None, loads from environment.
        """
        self.config = config or load_config()
        self.db_manager: Optional[DatabaseConnectionManager] = None
        self.bot_interface: Optional[TelegramBotInterface] = None
        self.delivery_runner: Optional[AutomatedDeliveryRunner] = None
        self.preprocessor_runner: Optional[SummaryPreprocessorRunner] = None
        self._running = False

    def initialize(self) -> None:
        """Initialize all application components.

        Raises:
            DatabaseConnectionError: If database connection fails.
            ValueError: If configuration is invalid.
        """
        logger.info("Initializing BookTok application...")

        if not validate_config(self.config):
            raise ValueError("Invalid configuration")

        setup_logging(self.config.logging)

        try:
            self.db_manager = DatabaseConnectionManager(self.config.database.path)
            self.db_manager.initialize()
            logger.info("Database initialized successfully")
        except DatabaseConnectionError as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

        self.bot_interface = TelegramBotInterface(
            token=self.config.telegram.token,
            db_manager=self.db_manager,
            config=self.config,
        )
        logger.info("Telegram bot interface initialized")

        async def send_message(telegram_id: int, message: str) -> None:
            """Send message via Telegram - for automated delivery runner."""
            if self.bot_interface.application is None:  # type: ignore[union-attr]
                raise RuntimeError("Bot application not initialized")
            await self.bot_interface.application.bot.send_message(  # type: ignore[union-attr]
                chat_id=telegram_id,
                text=message,
                parse_mode="Markdown",
            )

        self.delivery_runner = AutomatedDeliveryRunner(
            db_manager=self.db_manager,
            send_message_func=send_message,  # type: ignore[arg-type]
            check_interval_seconds=self.config.scheduler.check_interval_seconds,
        )
        logger.info("Delivery runner initialized")

        # Initialize summary preprocessor if OpenRouter is configured
        if self.config.openrouter.api_key:
            self.preprocessor_runner = SummaryPreprocessorRunner(
                db_manager=self.db_manager,
                openrouter_config=self.config.openrouter,
                check_interval_seconds=300,  # Check every 5 minutes
            )
            logger.info("Summary preprocessor runner initialized")
        else:
            logger.info("Summary preprocessor disabled (no OpenRouter API key)")

        logger.info("BookTok application initialized successfully")

    async def start(self) -> None:
        """Start the application and all components."""
        if self.db_manager is None:
            self.initialize()

        self._running = True
        logger.info("Starting BookTok application...")

        try:
            self.bot_interface.build_application()  # type: ignore[union-attr]
            logger.info("Telegram bot application built")

            await self.bot_interface.run_polling()  # type: ignore[union-attr]
            logger.info("Telegram bot started polling")

            await self.delivery_runner.start()  # type: ignore[union-attr]
            logger.info("Delivery runner started")

            if self.preprocessor_runner:
                await self.preprocessor_runner.start()
                logger.info("Summary preprocessor runner started")

            logger.info("BookTok application is running")

            while self._running:
                await asyncio.sleep(1.0)

        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
            raise

    async def stop(self) -> None:
        """Stop the application and cleanup resources."""
        logger.info("Stopping BookTok application...")
        self._running = False

        if self.preprocessor_runner:
            await self.preprocessor_runner.stop()
            logger.info("Summary preprocessor runner stopped")

        if self.delivery_runner:
            await self.delivery_runner.stop()
            logger.info("Delivery runner stopped")

        if self.bot_interface and self.bot_interface.application:
            await self.bot_interface.application.stop()
            logger.info("Telegram bot stopped")

        if self.db_manager:
            close_database(self.db_manager.get_connection())
            logger.info("Database connection closed")

        logger.info("BookTok application stopped")


async def run_application() -> None:
    """Run the BookTok application with proper startup and shutdown."""
    app = BookTokApplication()

    loop = asyncio.get_event_loop()

    def signal_handler() -> None:
        logger.info("Received shutdown signal")
        asyncio.create_task(app.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    try:
        await app.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if app._running:
            await app.stop()


def main() -> None:
    """Main entry point."""
    try:
        asyncio.run(run_application())
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
