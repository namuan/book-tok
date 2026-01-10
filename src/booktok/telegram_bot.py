"""Telegram bot interface with command handlers."""

import logging
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from booktok.models import User
from booktok.repository import DatabaseConnectionManager, UserRepository


logger = logging.getLogger(__name__)


WELCOME_MESSAGE = """📚 *Welcome to BookTok!*

I'm your personal reading companion that delivers bite-sized learning snippets from your books.

Here's how I work:
1. Upload a PDF or EPUB book
2. I'll extract it into digestible snippets
3. Receive daily snippets at your preferred time

Use /help to see all available commands.

Let's start reading! 📖"""


HELP_MESSAGE = """📖 *BookTok Commands*

*Getting Started:*
/start - Start the bot and create your profile
/help - Show this help message

*Book Management:*
(Coming soon - upload books to get started)

*Snippet Delivery:*
/next - Get the next snippet immediately

*Schedule:*
(Coming soon - set your delivery schedule)

*Progress:*
(Coming soon - view your reading progress)

Need help? Just send me a message!"""


class TelegramBotInterface:
    """Interface for handling Telegram bot commands and interactions."""

    def __init__(
        self,
        token: str,
        db_manager: DatabaseConnectionManager,
    ) -> None:
        """Initialize the Telegram bot interface.

        Args:
            token: Telegram bot API token.
            db_manager: Database connection manager.
        """
        self.token = token
        self.db_manager = db_manager
        self.user_repo = UserRepository(db_manager)
        self.application: Optional[Application] = None  # type: ignore[type-arg]

    def build_application(self) -> Application:  # type: ignore[type-arg]
        """Build and configure the Telegram application.

        Returns:
            Configured Telegram Application instance.
        """
        self.application = Application.builder().token(self.token).build()
        self._register_handlers()
        return self.application

    def _register_handlers(self) -> None:
        """Register all command handlers with the application."""
        if self.application is None:
            raise RuntimeError("Application not built. Call build_application() first.")

        self.application.add_handler(CommandHandler("start", self._handle_start))
        self.application.add_handler(CommandHandler("help", self._handle_help))

    async def _handle_start(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle the /start command.

        Creates a user profile if it doesn't exist and sends a welcome message.

        Args:
            update: Telegram update object.
            context: Callback context.
        """
        if update.effective_user is None or update.message is None:
            return

        telegram_user = update.effective_user
        telegram_id = telegram_user.id

        existing_user = self.user_repo.get_by_telegram_id(telegram_id)

        if existing_user is None:
            user = User(
                telegram_id=telegram_id,
                username=telegram_user.username,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
            )
            self.user_repo.create(user)
            logger.info(f"Created new user with telegram_id={telegram_id}")
        else:
            existing_user.username = telegram_user.username
            existing_user.first_name = telegram_user.first_name
            existing_user.last_name = telegram_user.last_name
            self.user_repo.update(existing_user)
            logger.info(f"Updated existing user with telegram_id={telegram_id}")

        await update.message.reply_text(
            WELCOME_MESSAGE,
            parse_mode="Markdown",
        )

    async def _handle_help(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle the /help command.

        Sends a message with all available commands.

        Args:
            update: Telegram update object.
            context: Callback context.
        """
        if update.message is None:
            return

        await update.message.reply_text(
            HELP_MESSAGE,
            parse_mode="Markdown",
        )

    async def run_polling(self) -> None:
        """Start the bot in polling mode."""
        if self.application is None:
            self.build_application()

        if self.application is not None:
            logger.info("Starting bot polling...")
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()  # type: ignore[union-attr]

    def get_user_repo(self) -> UserRepository:
        """Get the user repository.

        Returns:
            UserRepository instance.
        """
        return self.user_repo
