"""Telegram bot interface with command handlers."""

import logging
from datetime import datetime
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, NetworkError, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bs4 import BeautifulSoup

from booktok.book_processor import BookProcessor
from booktok.book_scanner import BookScanner
from booktok.config import AppConfig
from booktok.delivery_scheduler import DeliveryScheduler
from booktok.models import Book, BookStatus, User, UserProgress
from booktok.snippet_generator import SnippetGenerator
from booktok.repository import (
    BookRepository,
    DatabaseConnectionManager,
    DeliveryScheduleRepository,
    SnippetRepository,
    UserProgressRepository,
    UserRepository,
)
from booktok.snippet_formatter import SnippetFormatter
from booktok.ai_summarizer import AISummarizer


logger = logging.getLogger(__name__)


def clean_html_for_telegram(text: str) -> str:
    """Clean and format HTML for Telegram message requirements.

    Converts unsupported block tags to newlines/bullets and strips
    unsupported inline tags while keeping content.
    """
    if not text:
        return ""

    soup = BeautifulSoup(text, "html.parser")

    # Define supported tags
    ALLOWED_TAGS = [
        "b",
        "strong",
        "i",
        "em",
        "u",
        "ins",
        "s",
        "strike",
        "del",
        "code",
        "pre",
    ]

    # Handle line breaks first
    for br in soup.find_all("br"):
        br.replace_with("\n")

    # Handle list items
    for li in soup.find_all("li"):
        # Add bullet point and newline
        new_content = f"• {li.get_text()} \n"
        li.replace_with(new_content)

    # Handle headings (make them bold and add newline)
    for tag_name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
        for tag in soup.find_all(tag_name):
            new_b = soup.new_tag("b")
            new_b.string = tag.get_text()
            tag.replace_with(new_b)
            new_b.insert_after("\n")

    # Handle paragraphs (add double newline for spacing)
    for p in soup.find_all("p"):
        p.insert_after("\n\n")
        p.unwrap()

    # Remove all other unsupported tags but keep content
    for tag in soup.find_all(True):
        if tag.name not in ALLOWED_TAGS:
            tag.unwrap()

    # Get text and clean up excessive whitespace
    cleaned_text = str(soup)

    # Fix multiple newlines (more than 2)
    import re

    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text)

    return cleaned_text.strip()


def sanitize_text_for_telegram(text: str) -> str:
    """Sanitize text to remove invalid Unicode characters for Telegram.

    Args:
        text: The text to sanitize.

    Returns:
        Sanitized text safe for Telegram messages.
    """
    # Remove surrogate pairs and other invalid Unicode
    return text.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")


WELCOME_MESSAGE = """📚 *Welcome to BookTok!*

I'm your personal reading companion that delivers bite-sized learning snippets from your books.

Here's how I work:
1. Browse available books with /books
2. Select a book to start reading
3. Get snippets with /next or receive them automatically

Use /help to see all available commands.

Let's start reading! 📖"""


HELP_MESSAGE = """📖 *BookTok Commands*

*Getting Started:*
/start - Start the bot and create your profile
/help - Show this help message

*Book Management:*
/books - Browse and select books to read

*Snippet Delivery:*
/next - Get the next snippet immediately
/pause - Pause automatic snippet deliveries
/resume - Resume automatic snippet deliveries

*Schedule:*
/schedule - Set up automatic snippet delivery times

*Progress:*
(Coming soon - view your reading progress)

Need help? Just send me a message!"""


UNRECOGNIZED_COMMAND_MESSAGE = """❓ *Unrecognized Command*

I didn't understand that command.

*Available commands:*
/start - Start the bot and create your profile
/help - Show all available commands
/books - List available books
/next - Get the next snippet immediately
/pause - Pause automatic deliveries
/resume - Resume automatic deliveries

*Did you mean one of these?*
• If you wanted to start: use /start
• If you need help: use /help
• To see available books: use /books
• To get the next snippet: use /next
• To pause deliveries: use /pause
• To resume deliveries: use /resume

Tip: Commands always start with a forward slash (/)"""


VALID_COMMANDS = ["start", "help", "books", "next", "pause", "resume", "schedule"]


class TelegramBotInterface:
    """Interface for handling Telegram bot commands and interactions."""

    def __init__(
        self,
        token: str,
        db_manager: DatabaseConnectionManager,
        config: AppConfig,
    ) -> None:
        """Initialize the Telegram bot interface.

        Args:
            token: Telegram bot API token.
            db_manager: Database connection manager.
            config: Application configuration.
        """
        self.token = token
        self.db_manager = db_manager
        self.config = config
        self.books_config = config.books
        self.book_scanner = BookScanner(config.books.directory)
        self.user_repo = UserRepository(db_manager)
        self.book_repo = BookRepository(db_manager)
        self.snippet_repo = SnippetRepository(db_manager)
        self.progress_repo = UserProgressRepository(db_manager)
        self.schedule_repo = DeliveryScheduleRepository(db_manager)
        self.scheduler = DeliveryScheduler(db_manager)
        self.application: Optional[Application] = None  # type: ignore[type-arg]

        self.ai_summarizer: Optional[AISummarizer] = None
        if config.openrouter.api_key:
            self.ai_summarizer = AISummarizer(config.openrouter)
            logger.info("AI Summarizer initialized with OpenRouter")

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
        self.application.add_handler(CommandHandler("books", self._handle_books))
        self.application.add_handler(CommandHandler("next", self._handle_next))
        self.application.add_handler(CommandHandler("pause", self._handle_pause))
        self.application.add_handler(CommandHandler("resume", self._handle_resume))
        self.application.add_handler(CommandHandler("schedule", self._handle_schedule))

        # Callback query handler for book selection
        self.application.add_handler(
            CallbackQueryHandler(self._handle_book_selection, pattern=r"^select_book:")
        )

        self.application.add_handler(
            MessageHandler(
                filters.COMMAND
                & ~filters.Regex(r"^/(start|help|books|next|pause|resume)"),
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

    async def _handle_books(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle the /books command.

        Lists all available books from the configured books directory.

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

        # Scan for available books
        books = self.book_scanner.scan()

        if not books:
            await update.message.reply_text(
                "📚 *No Books Available*\n\n"
                f"No books found in the configured directory.\n\n"
                f"Directory: `{self.books_config.directory}`\n\n"
                "Please contact the administrator to add books.",
                parse_mode="Markdown",
            )
            return

        # Build message with book list
        message_lines = ["📚 *Available Books*\n"]
        message_lines.append(f"Found {len(books)} book(s):\n")
        message_lines.append("Select a book to start reading:\n")

        # Create inline keyboard buttons for book selection
        keyboard = []
        for idx, book in enumerate(books, start=1):
            size_str = self.book_scanner.format_size(book.size_bytes)
            file_type = book.file_type.value.upper()
            message_lines.append(
                f"{idx}. *{book.display_name}*\n" f"   📊 {file_type} | {size_str}"
            )

            # Add button for this book
            button_text = f"{idx}. {book.display_name[:30]}"
            # Use index instead of filename to avoid callback_data 64 byte limit
            callback_data = f"select_book:{idx}"
            keyboard.append(
                [InlineKeyboardButton(button_text, callback_data=callback_data)]
            )

        message = "\n".join(message_lines)
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            message,
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )

        logger.info(f"User {telegram_id} listed {len(books)} available books")

    async def _handle_book_selection(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle book selection from inline keyboard.

        Processes the selected book, generates snippets, and starts user progress.

        Args:
            update: Telegram update object with callback query.
            context: Callback context.
        """
        query = update.callback_query
        if query is None or update.effective_user is None:
            return

        await query.answer()

        telegram_id = update.effective_user.id
        user = self.user_repo.get_by_telegram_id(telegram_id)

        if user is None or user.id is None:
            await query.edit_message_text(
                "Please use /start first to create your profile.",
            )
            return

        # Extract index from callback data
        callback_data = query.data or ""
        if not callback_data.startswith("select_book:"):
            await query.edit_message_text("Invalid selection. Please try again.")
            return

        try:
            # We communicate via index to keep callback_data short
            idx = int(callback_data.replace("select_book:", ""))
        except ValueError:
            await query.edit_message_text(
                "Invalid book selection format. Please try /books again."
            )
            return

        # Re-scan to resolve index to file
        books = self.book_scanner.scan()
        if idx < 1 or idx > len(books):
            await query.edit_message_text(
                "Book selection out of range. The book list may have changed.\n"
                "Please use /books to see the current list."
            )
            return

        book_file = books[idx - 1]

        # Show processing message
        await query.edit_message_text(
            f"\u231b *Processing Book*\n\n"
            f"Selected: *{book_file.display_name}*\n\n"
            "Processing the book and generating snippets...\n"
            "This may take a moment.",
            parse_mode="Markdown",
        )

        try:
            # Check if book already exists in database
            existing_book = self.book_repo.get_by_file_path(str(book_file.path))
            book = None
            should_process = False

            if existing_book is not None:
                if (
                    existing_book.status == BookStatus.COMPLETED
                    and existing_book.total_snippets > 0
                ):
                    # Book already processed and valid
                    book = existing_book
                    logger.info(
                        f"Book '{book.title}' already exists (ID: {book.id}), "
                        f"linking to user {telegram_id}"
                    )
                else:
                    # Book exists but is incomplete or failed, reprocess it
                    book = existing_book
                    should_process = True
                    logger.info(
                        f"Reprocessing existing book '{book.title}' (ID: {book.id}) "
                        f"Status: {book.status}, Snippets: {book.total_snippets}"
                    )
            else:
                # Create new book entry
                book = Book(
                    title=book_file.display_name,
                    file_path=str(book_file.path),
                    file_type=book_file.file_type,
                    status=BookStatus.PROCESSING,
                )
                book = self.book_repo.create(book)
                should_process = True
                logger.info(f"Created book entry: {book.title} (ID: {book.id})")

            if should_process:
                # Update status to processing
                if book.status != BookStatus.PROCESSING:
                    book.status = BookStatus.PROCESSING
                    self.book_repo.update(book)

                # Clear any existing snippets if we are reprocessing
                if existing_book:
                    deleted_count = self.snippet_repo.delete_by_book(book.id)  # type: ignore
                    logger.info(
                        f"Deleted {deleted_count} old snippets for book {book.id}"
                    )

                # Process the book
                processor = BookProcessor(book)
                result = processor.process_book_safely()

                if not result.success or result.text is None:
                    book.status = BookStatus.FAILED
                    self.book_repo.update(book)
                    await query.edit_message_text(
                        f"\u274c *Processing Failed*\n\n"
                        f"{result.get_user_message()}",
                        parse_mode="Markdown",
                    )
                    return

                # Generate snippets
                generator = SnippetGenerator(book)
                snippets = generator.generate_snippets(result.text)

                # Save snippets to database
                for snippet in snippets:
                    self.snippet_repo.create(snippet)

                # Update book status
                book.total_snippets = len(snippets)
                book.status = BookStatus.COMPLETED
                self.book_repo.update(book)

                logger.info(
                    f"Successfully processed book '{book.title}' "
                    f"with {len(snippets)} snippets"
                )

            # Check if user has active progress on a different book
            progress_list = self.progress_repo.list_by_user(user.id)
            for progress in progress_list:
                if not progress.is_completed and progress.book_id != book.id:
                    # Mark old book progress as inactive/paused
                    # For now, we just start fresh with the new book
                    logger.info(
                        f"User {telegram_id} switching from book {progress.book_id} "
                        f"to book {book.id}"
                    )

            # Initialize or reset user progress for this book
            existing_progress = self.progress_repo.get_by_user_and_book(
                user.id, book.id or 0
            )

            if existing_progress is not None:
                # Resume progress - update will refresh the updated_at timestamp
                # making this the active book
                self.progress_repo.update(existing_progress)
                progress = existing_progress
                logger.info(
                    f"Resumed progress for user {telegram_id} on book '{book.title}' at position {progress.current_position}"
                )
            else:
                # Create new progress
                progress = self.progress_repo.initialize_progress(user.id, book.id or 0)
                logger.info(
                    f"Initialized progress for user {telegram_id} on book '{book.title}'"
                )

            # Send success message
            title_safe = sanitize_text_for_telegram(book.title)
            await query.edit_message_text(
                f"\u2705 *Book Selected*\n\n"
                f"*{title_safe}*\n\n"
                f"📚 Total snippets: {book.total_snippets}\n"
                f"📍 Your position: {progress.current_position + 1}/{book.total_snippets}\n\n"
                "Use /next to start reading!",
                parse_mode="Markdown",
            )

        except Exception as e:
            logger.error(f"Error processing book selection: {e}", exc_info=True)
            await query.edit_message_text(
                "\u274c *Error*\n\n"
                "An error occurred while processing the book.\n"
                "Please try again later or contact support.",
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

        try:
            await self._handle_next_impl(update, context)
        except (NetworkError, TelegramError) as e:
            logger.error(f"Error delivering snippet: {e}", exc_info=True)
            if update.message:
                try:
                    await update.message.reply_text(
                        "⚠️ Sorry, something went wrong. Please try again.\n\n"
                        "Tap /next to continue reading."
                    )
                except Exception as retry_error:
                    logger.error(f"Failed to send error message: {retry_error}")
        except Exception as e:
            logger.error(f"Unexpected error in _handle_next: {e}", exc_info=True)
            if update.message:
                try:
                    await update.message.reply_text(
                        "⚠️ Sorry, something went wrong. Please try again.\n\n"
                        "Tap /next to continue reading."
                    )
                except Exception as retry_error:
                    logger.error(f"Failed to send error message: {retry_error}")

    async def _handle_next_impl(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Implementation of the /next command handler.

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

        if self.ai_summarizer:
            # AI Summarization Mode
            target_count = self.config.openrouter.summary_page_count
            snippets = self.snippet_repo.get_range_by_book(
                active_progress.book_id,
                next_position,
                next_position + target_count - 1,
            )

            if not snippets:
                title_safe = sanitize_text_for_telegram(book.title)
                await update.message.reply_text(
                    f"📚 *{title_safe}*\n\n"
                    "No more snippets available. You've reached the end!",
                    parse_mode="Markdown",
                )
                return

            # Fetch previous context if available
            previous_snippet = None
            if next_position > 0:
                prev_obj = self.snippet_repo.get_by_book_and_position(
                    active_progress.book_id, next_position - 1
                )
                if prev_obj:
                    previous_snippet = prev_obj.content

            start_page = snippets[0].position + 1
            end_page = snippets[-1].position + 1
            title_safe = sanitize_text_for_telegram(book.title)
            status_msg = f"🤖 *{title_safe}* Generating summary for pages {start_page}-{end_page}..."
            try:
                await update.message.reply_text(
                    status_msg,
                    parse_mode="Markdown",
                )
            except BadRequest as e:
                logger.warning(
                    f"Failed to send status with Markdown: {e}. Retrying without formatting."
                )
                await update.message.reply_text(
                    status_msg,
                    parse_mode=None,
                )

            summary = await self.ai_summarizer.summarize_snippets(
                [s.content for s in snippets], previous_snippet
            )

            # Clean and format the summary specifically for Telegram HTML
            formatted_summary = clean_html_for_telegram(summary)
            safe_summary = sanitize_text_for_telegram(formatted_summary)

            try:
                await update.message.reply_text(
                    safe_summary,
                    parse_mode="HTML",
                )
            except BadRequest as e:
                logger.warning(
                    f"Failed to send summary with HTML: {e}. Retrying with plain text."
                )
                # Fallback: Strip all tags for clean plain text
                plain_text = BeautifulSoup(summary, "html.parser").get_text()
                await update.message.reply_text(
                    sanitize_text_for_telegram(plain_text),
                    parse_mode=None,
                )

            # Advance logical position
            new_position = next_position + len(snippets)
            active_progress.current_position = new_position

            # Show progress
            progress_pct = (new_position / total_snippets) * 100
            await update.message.reply_text(
                f"📖 *Progress*: {new_position}/{total_snippets} ({progress_pct:.1f}%)\n\n"
                "Tap /next to continue reading.",
                parse_mode="Markdown",
            )

        else:
            # Standard Mode (Single Snippet)
            snippet = self.snippet_repo.get_by_book_and_position(
                active_progress.book_id, next_position
            )

            if snippet is None:
                title_safe = sanitize_text_for_telegram(book.title)
                await update.message.reply_text(
                    f"📚 *{title_safe}*\n\n"
                    "No more snippets available. You've reached the end!",
                    parse_mode="Markdown",
                )
                return

            formatter = SnippetFormatter(book, total_snippets=total_snippets)
            formatted = formatter.format_snippet(snippet, active_progress)

            for message in formatted.messages:
                try:
                    await update.message.reply_text(
                        message.text,
                        parse_mode="Markdown",
                    )
                except BadRequest as e:
                    logger.warning(
                        f"Failed to send snippet with Markdown: {e}. Retrying without formatting."
                    )
                    await update.message.reply_text(
                        message.text,
                        parse_mode=None,
                    )

            active_progress.current_position = next_position + 1

        if active_progress.current_position >= total_snippets:
            active_progress.is_completed = True
            active_progress.completed_at = datetime.utcnow()
            title_safe = sanitize_text_for_telegram(book.title)
            await update.message.reply_text(
                f"🎉 *Congratulations!*\n\n"
                f"You've completed *{title_safe}*!\n\n"
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

    async def _handle_schedule(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /schedule command to set up automatic snippet delivery.

        Args:
            update: Telegram update object.
            context: Callback context.
        """
        if update.message is None or update.message.from_user is None:
            return

        telegram_id = update.message.from_user.id
        user = self.user_repo.get_by_telegram_id(telegram_id)

        if user is None:
            await update.message.reply_text(
                "Please use /start first to create your profile.",
            )
            return

        # Check if user has selected a book
        progress_records = self.progress_repo.list_by_user(user.id)
        if not progress_records:
            await update.message.reply_text(
                "⚠️ *No Book Selected*\n\n"
                "You need to select a book first before setting up a schedule.\n\n"
                "Use /books to select a book!",
                parse_mode="Markdown",
            )
            return

        # Get the active book (most recent non-completed)
        active_progress = None
        for progress in progress_records:
            if not progress.is_completed:
                active_progress = progress
                break

        if active_progress is None:
            await update.message.reply_text(
                "⚠️ *No Active Book*\n\n"
                "You've completed all your books! Use /books to select a new one.",
                parse_mode="Markdown",
            )
            return

        book = self.book_repo.get_by_id(active_progress.book_id)
        if book is None:
            await update.message.reply_text(
                "Error: Book not found. Please select a book again using /books.",
            )
            return

        # Parse the schedule parameters from the command
        # Format: /schedule HH:MM [daily|twice_daily|weekly] [timezone]
        # Example: /schedule 09:00 daily America/New_York
        args = context.args or []

        if len(args) == 0:
            # Show current schedule if exists, otherwise show help
            existing_schedule = self.scheduler.get_schedule(user.id, book.id or 0)
            if existing_schedule:
                schedule_info = self.scheduler.get_schedule_info(
                    user.id,
                    book.id or 0,
                    book.title,
                    book.author,
                )
                if schedule_info:
                    await update.message.reply_text(
                        f"📅 *Current Schedule*\n\n{schedule_info.format_for_display()}",
                        parse_mode="Markdown",
                    )
                    return

            # Show usage help
            await update.message.reply_text(
                "⏰ *Set Delivery Schedule*\n\n"
                "*Usage:* `/schedule TIME [FREQUENCY] [TIMEZONE]`\n\n"
                "*Examples:*\n"
                "• `/schedule 09:00` - Daily at 9 AM (your local time)\n"
                "• `/schedule 14:30 daily` - Daily at 2:30 PM\n"
                "• `/schedule 08:00 twice_daily` - Every 12 hours starting at 8 AM\n"
                "• `/schedule 10:00 weekly` - Weekly at 10 AM\n"
                "• `/schedule 09:00 daily America/New_York` - With timezone\n\n"
                "*Frequency options:*\n"
                "• `daily` (default) - Once per day\n"
                "• `twice_daily` - Every 12 hours\n"
                "• `weekly` - Once per week\n\n"
                f"*Your timezone:* {user.timezone}\n\n"
                "💡 *Tip:* Just type the time to use default settings!",
                parse_mode="Markdown",
            )
            return

        # Parse time (required)
        time_str = args[0]
        if ":" not in time_str or len(time_str.split(":")) != 2:
            await update.message.reply_text(
                "❌ *Invalid Time Format*\n\n"
                "Please use HH:MM format (e.g., 09:00 or 14:30)\n\n"
                "Example: `/schedule 09:00`",
                parse_mode="Markdown",
            )
            return

        try:
            hour, minute = map(int, time_str.split(":"))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("Invalid time")
        except ValueError:
            await update.message.reply_text(
                "❌ *Invalid Time*\n\n"
                "Hours must be 0-23 and minutes must be 0-59.\n\n"
                "Example: `/schedule 09:00`",
                parse_mode="Markdown",
            )
            return

        # Parse frequency (optional, default: daily)
        from booktok.models import Frequency

        frequency = Frequency.DAILY
        if len(args) > 1:
            freq_str = args[1].lower()
            if freq_str in ["daily", "d"]:
                frequency = Frequency.DAILY
            elif freq_str in ["twice_daily", "twice", "2x"]:
                frequency = Frequency.TWICE_DAILY
            elif freq_str in ["weekly", "week", "w"]:
                frequency = Frequency.WEEKLY
            else:
                await update.message.reply_text(
                    "❌ *Invalid Frequency*\n\n"
                    "Valid options: `daily`, `twice_daily`, `weekly`\n\n"
                    "Example: `/schedule 09:00 daily`",
                    parse_mode="Markdown",
                )
                return

        # Parse timezone (optional)
        timezone = None
        if len(args) > 2:
            timezone = args[2]
            try:
                from zoneinfo import ZoneInfo

                ZoneInfo(timezone)  # Validate timezone
            except Exception:
                await update.message.reply_text(
                    f"❌ *Invalid Timezone*\n\n"
                    f"'{timezone}' is not a valid timezone.\n\n"
                    "Examples: `America/New_York`, `Europe/London`, `Asia/Tokyo`\n\n"
                    "See: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones",
                    parse_mode="Markdown",
                )
                return

        # Set the schedule
        try:
            self.scheduler.set_schedule(
                user_id=user.id,
                book_id=book.id or 0,
                delivery_time=time_str,
                frequency=frequency,
                timezone=timezone,
            )

            frequency_display = {
                Frequency.DAILY: "daily",
                Frequency.TWICE_DAILY: "every 12 hours",
                Frequency.WEEKLY: "weekly",
            }.get(frequency, "daily")

            effective_tz = timezone or user.timezone

            await update.message.reply_text(
                f"✅ *Schedule Set!*\n\n"
                f"📚 *Book:* {book.title}\n"
                f"⏰ *Time:* {time_str}\n"
                f"📅 *Frequency:* {frequency_display}\n"
                f"🌍 *Timezone:* {effective_tz}\n\n"
                f"You'll receive snippets automatically at your scheduled time.\n\n"
                f"Use /pause to temporarily stop deliveries or /resume to restart them.",
                parse_mode="Markdown",
            )
            logger.info(
                f"User {telegram_id} set schedule: {time_str} {frequency.value} for book {book.id}"
            )

        except Exception as e:
            logger.error(
                f"Error setting schedule for user {telegram_id}: {e}", exc_info=True
            )
            await update.message.reply_text(
                f"❌ *Error Setting Schedule*\n\n"
                f"An error occurred: {str(e)}\n\n"
                "Please try again or contact support.",
                parse_mode="Markdown",
            )

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
