"""Telegram bot interface with command handlers."""

import logging
from datetime import datetime
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from booktok.delivery_scheduler import DeliveryScheduler
from booktok.models import User, UserProgress
from booktok.repository import (
    BookRepository,
    DatabaseConnectionManager,
    DeliveryScheduleRepository,
    SnippetRepository,
    UserProgressRepository,
    UserRepository,
)
from booktok.snippet_formatter import SnippetFormatter


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
/pause - Pause automatic snippet deliveries
/resume - Resume automatic snippet deliveries

*Schedule:*
(Coming soon - set your delivery schedule)

*Progress:*
(Coming soon - view your reading progress)

Need help? Just send me a message!"""


UNRECOGNIZED_COMMAND_MESSAGE = """❓ *Unrecognized Command*

I didn't understand that command.

*Available commands:*
/start - Start the bot and create your profile
/help - Show all available commands
/next - Get the next snippet immediately
/pause - Pause automatic deliveries
/resume - Resume automatic deliveries

*Did you mean one of these?*
• If you wanted to start: use /start
• If you need help: use /help
• To get the next snippet: use /next
• To pause deliveries: use /pause
• To resume deliveries: use /resume

Tip: Commands always start with a forward slash (/)"""


VALID_COMMANDS = ["start", "help", "next", "pause", "resume"]


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
        self.book_repo = BookRepository(db_manager)
        self.snippet_repo = SnippetRepository(db_manager)
        self.progress_repo = UserProgressRepository(db_manager)
        self.schedule_repo = DeliveryScheduleRepository(db_manager)
        self.scheduler = DeliveryScheduler(db_manager)
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
        self.application.add_handler(CommandHandler("next", self._handle_next))
        self.application.add_handler(CommandHandler("pause", self._handle_pause))
        self.application.add_handler(CommandHandler("resume", self._handle_resume))

        self.application.add_handler(
            MessageHandler(
                filters.COMMAND & ~filters.Regex(r"^/(start|help|next|pause|resume)"),
                self._handle_unrecognized_command,
            )
        )

        self.application.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self._handle_text_message,
            )
        )

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

    async def _handle_next(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle the /next command.

        Delivers the next sequential snippet from the user's active book.

        Args:
            update: Telegram update object.
            context: Callback context.
        """
        if update.effective_user is None or update.message is None:
            return

        telegram_id = update.effective_user.id
        user = self.user_repo.get_by_telegram_id(telegram_id)

        if user is None:
            await update.message.reply_text(
                "Please use /start first to create your profile.",
            )
            return

        if user.id is None:
            await update.message.reply_text(
                "An error occurred. Please try /start again.",
            )
            return

        progress_list = self.progress_repo.list_by_user(user.id)
        active_progress = None
        for progress in progress_list:
            if not progress.is_completed:
                active_progress = progress
                break

        if active_progress is None:
            await update.message.reply_text(
                "📚 You don't have any active books.\n\n"
                "Upload a PDF or EPUB to get started!",
            )
            return

        book = self.book_repo.get_by_id(active_progress.book_id)
        if book is None:
            await update.message.reply_text(
                "An error occurred finding your book. Please try again.",
            )
            return

        total_snippets = self.snippet_repo.count_by_book(book.id or 0)
        next_position = active_progress.current_position

        snippet = self.snippet_repo.get_by_book_and_position(
            active_progress.book_id, next_position
        )

        if snippet is None:
            await update.message.reply_text(
                f"📚 *{book.title}*\n\n"
                "No more snippets available. You've reached the end!",
                parse_mode="Markdown",
            )
            return

        formatter = SnippetFormatter(book, total_snippets=total_snippets)
        formatted = formatter.format_snippet(snippet, active_progress)

        for message in formatted.messages:
            await update.message.reply_text(
                message.text,
                parse_mode="Markdown",
            )

        active_progress.current_position = next_position + 1

        if active_progress.current_position >= total_snippets:
            active_progress.is_completed = True
            active_progress.completed_at = datetime.utcnow()
            await update.message.reply_text(
                f"🎉 *Congratulations!*\n\n"
                f"You've completed *{book.title}*!\n\n"
                f"📚 Total snippets read: {total_snippets}\n\n"
                f"Great job on finishing this book! 🏆",
                parse_mode="Markdown",
            )

        self.progress_repo.update(active_progress)

        if active_progress.current_position >= total_snippets:
            logger.info(
                f"User {telegram_id} completed book '{book.title}' "
                f"after delivering snippet {next_position + 1}/{total_snippets}"
            )
        else:
            logger.info(
                f"Delivered snippet {next_position + 1}/{total_snippets} "
                f"from book '{book.title}' to user {telegram_id}"
            )

    async def _handle_pause(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle the /pause command.

        Pauses automatic snippet deliveries for the user.

        Args:
            update: Telegram update object.
            context: Callback context.
        """
        if update.effective_user is None or update.message is None:
            return

        telegram_id = update.effective_user.id
        user = self.user_repo.get_by_telegram_id(telegram_id)

        if user is None:
            await update.message.reply_text(
                "Please use /start first to create your profile.",
            )
            return

        if user.id is None:
            await update.message.reply_text(
                "An error occurred. Please try /start again.",
            )
            return

        paused_count = self.scheduler.pause_all_schedules(user.id)

        if paused_count == 0:
            schedules = self.schedule_repo.list_by_user(user.id)
            if not schedules:
                await update.message.reply_text(
                    "⏸️ *No Schedules to Pause*\n\n"
                    "You don't have any delivery schedules set up yet.\n"
                    "Upload a book and set a schedule to get started!",
                    parse_mode="Markdown",
                )
            else:
                await update.message.reply_text(
                    "⏸️ *Already Paused*\n\n"
                    "All your delivery schedules are already paused.\n"
                    "Use /resume to restart automatic deliveries.",
                    parse_mode="Markdown",
                )
        else:
            await update.message.reply_text(
                f"⏸️ *Deliveries Paused*\n\n"
                f"Paused {paused_count} delivery schedule(s).\n\n"
                "You can still use /next to get snippets manually.\n"
                "Use /resume to restart automatic deliveries.",
                parse_mode="Markdown",
            )
            logger.info(f"User {telegram_id} paused {paused_count} schedules")

    async def _handle_resume(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle the /resume command.

        Resumes automatic snippet deliveries for the user.

        Args:
            update: Telegram update object.
            context: Callback context.
        """
        if update.effective_user is None or update.message is None:
            return

        telegram_id = update.effective_user.id
        user = self.user_repo.get_by_telegram_id(telegram_id)

        if user is None:
            await update.message.reply_text(
                "Please use /start first to create your profile.",
            )
            return

        if user.id is None:
            await update.message.reply_text(
                "An error occurred. Please try /start again.",
            )
            return

        resumed_count = self.scheduler.resume_all_schedules(user.id)

        if resumed_count == 0:
            schedules = self.schedule_repo.list_by_user(user.id)
            if not schedules:
                await update.message.reply_text(
                    "▶️ *No Schedules to Resume*\n\n"
                    "You don't have any delivery schedules set up yet.\n"
                    "Upload a book and set a schedule to get started!",
                    parse_mode="Markdown",
                )
            else:
                await update.message.reply_text(
                    "▶️ *Already Active*\n\n"
                    "All your delivery schedules are already active.\n"
                    "Use /pause to stop automatic deliveries.",
                    parse_mode="Markdown",
                )
        else:
            await update.message.reply_text(
                f"▶️ *Deliveries Resumed*\n\n"
                f"Resumed {resumed_count} delivery schedule(s).\n\n"
                "You will start receiving snippets at your scheduled times.\n"
                "Use /pause to stop automatic deliveries.",
                parse_mode="Markdown",
            )
            logger.info(f"User {telegram_id} resumed {resumed_count} schedules")

    async def _handle_unrecognized_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle unrecognized commands.

        Sends a helpful error message with list of valid commands.

        Args:
            update: Telegram update object.
            context: Callback context.
        """
        if update.message is None:
            return

        text = update.message.text or ""
        logger.info(f"Unrecognized command received: {text}")

        response = self._get_suggestion_message(text)
        await update.message.reply_text(
            response,
            parse_mode="Markdown",
        )

    async def _handle_text_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle plain text messages (not commands).

        Provides helpful guidance for users who send plain text.

        Args:
            update: Telegram update object.
            context: Callback context.
        """
        if update.message is None:
            return

        text = update.message.text or ""
        logger.info(f"Plain text message received: {text[:50]}...")

        response = """I can only respond to commands right now.

Try /help to see the list of available commands!"""
        await update.message.reply_text(response)

    def _get_suggestion_message(self, user_input: str) -> str:
        """Generate a helpful suggestion message based on user input.

        Args:
            user_input: The unrecognized command or text.

        Returns:
            A formatted message with suggestions.
        """
        user_input_lower = user_input.lower().strip()

        common_mistakes = {
            "begin": "/start",
            "starts": "/start",
            "starting": "/start",
            "hi": "/start",
            "hello": "/start",
            "hey": "/start",
            "helps": "/help",
            "helping": "/help",
            "?": "/help",
            "commands": "/help",
            "menu": "/help",
            "nexts": "/next",
            "continue": "/next",
            "more": "/next",
            "read": "/next",
            "snippet": "/next",
            "stop": "/pause",
            "paused": "/pause",
            "halt": "/pause",
            "unpause": "/resume",
            "restart": "/resume",
            "resumed": "/resume",
        }

        for key, suggestion in common_mistakes.items():
            if key in user_input_lower:
                return f"""❓ *Did you mean {suggestion}?*

Your message: `{user_input}`

Try using *{suggestion}* instead.

Use /help to see all available commands."""

        return UNRECOGNIZED_COMMAND_MESSAGE

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

    def start_book(self, user_id: int, book_id: int) -> UserProgress:
        """Initialize progress for a user on a book.

        Args:
            user_id: Database ID of the user.
            book_id: Database ID of the book.

        Returns:
            UserProgress record for the user's progress on the book.
        """
        return self.progress_repo.initialize_progress(user_id, book_id)
