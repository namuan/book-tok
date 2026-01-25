"""Background summary pre-processing module."""

import asyncio
import logging
from typing import Optional

from booktok.ai_summarizer import AISummarizer
from booktok.config import OpenRouterConfig
from booktok.models import SnippetSummary
from booktok.repository import (
    BookRepository,
    DatabaseConnectionManager,
    SnippetRepository,
    SnippetSummaryRepository,
)

logger = logging.getLogger(__name__)


class SummaryPreprocessor:
    """Handles background pre-processing of book summaries."""

    def __init__(
        self,
        db_manager: DatabaseConnectionManager,
        ai_summarizer: AISummarizer,
        summary_page_count: int,
    ) -> None:
        """Initialize the summary preprocessor.

        Args:
            db_manager: Database connection manager.
            ai_summarizer: AI summarizer instance.
            summary_page_count: Number of snippets per summary.
        """
        self.db_manager = db_manager
        self.ai_summarizer = ai_summarizer
        self.summary_page_count = summary_page_count

        self.book_repo = BookRepository(db_manager)
        self.snippet_repo = SnippetRepository(db_manager)
        self.summary_repo = SnippetSummaryRepository(db_manager)

    async def preprocess_book(self, book_id: int) -> int:
        """Pre-process all summaries for a book.

        Args:
            book_id: Database ID of the book.

        Returns:
            Number of summaries generated.
        """
        book = self.book_repo.get_by_id(book_id)
        if book is None:
            logger.warning(f"Book {book_id} not found")
            return 0

        total_snippets = self.snippet_repo.count_by_book(book_id)
        if total_snippets == 0:
            logger.info(f"Book {book_id} has no snippets, skipping")
            return 0

        logger.info(
            f"Starting summary pre-processing for book '{book.title}' "
            f"({total_snippets} snippets, {self.summary_page_count} per summary)"
        )

        summaries_generated = 0
        position = 0

        while position < total_snippets:
            start_pos = position
            end_pos = min(position + self.summary_page_count - 1, total_snippets - 1)

            # Check if summary already exists
            existing = self.summary_repo.get_by_position(book_id, start_pos, end_pos)
            if existing is not None:
                logger.debug(
                    f"Summary already exists for book {book_id} positions {start_pos}-{end_pos}"
                )
                position += self.summary_page_count
                continue

            # Generate the summary
            try:
                summary_content = await self._generate_summary(
                    book_id, start_pos, end_pos
                )

                if summary_content:
                    # Save to database
                    summary = SnippetSummary(
                        book_id=book_id,
                        start_position=start_pos,
                        end_position=end_pos,
                        summary_content=summary_content,
                    )
                    self.summary_repo.create(summary)
                    summaries_generated += 1
                    logger.info(
                        f"Generated summary {summaries_generated} for book '{book.title}' "
                        f"positions {start_pos}-{end_pos}"
                    )
                else:
                    logger.warning(
                        f"Failed to generate summary for book {book_id} "
                        f"positions {start_pos}-{end_pos}"
                    )
            except Exception as e:
                logger.error(
                    f"Error generating summary for book {book_id} "
                    f"positions {start_pos}-{end_pos}: {e}",
                    exc_info=True,
                )

            position += self.summary_page_count

        logger.info(
            f"Completed pre-processing for book '{book.title}': "
            f"{summaries_generated} summaries generated"
        )
        return summaries_generated

    async def _generate_summary(
        self, book_id: int, start_pos: int, end_pos: int
    ) -> Optional[str]:
        """Generate a summary for a range of snippets.

        Args:
            book_id: Database ID of the book.
            start_pos: Starting position.
            end_pos: Ending position.

        Returns:
            Generated summary content, or None on failure.
        """
        # Fetch the snippets
        snippets = self.snippet_repo.get_range_by_book(book_id, start_pos, end_pos)

        if not snippets:
            return None

        # Get previous snippet for context
        previous_snippet = None
        if start_pos > 0:
            prev_obj = self.snippet_repo.get_by_book_and_position(
                book_id, start_pos - 1
            )
            if prev_obj:
                previous_snippet = prev_obj.content

        # Generate summary
        try:
            summary = await self.ai_summarizer.summarize_snippets(
                [s.content for s in snippets], previous_snippet
            )
            return summary
        except Exception as e:
            logger.error(f"Error calling AI summarizer: {e}", exc_info=True)
            return None

    def get_missing_summary_positions(self, book_id: int) -> list[tuple[int, int]]:
        """Get list of position ranges that need summaries.

        Args:
            book_id: Database ID of the book.

        Returns:
            List of (start_position, end_position) tuples.
        """
        total_snippets = self.snippet_repo.count_by_book(book_id)
        if total_snippets == 0:
            return []

        existing_summaries = self.summary_repo.list_by_book(book_id)
        existing_ranges = {
            (s.start_position, s.end_position) for s in existing_summaries
        }

        missing_ranges = []
        position = 0

        while position < total_snippets:
            start_pos = position
            end_pos = min(position + self.summary_page_count - 1, total_snippets - 1)

            if (start_pos, end_pos) not in existing_ranges:
                missing_ranges.append((start_pos, end_pos))

            position += self.summary_page_count

        return missing_ranges


class SummaryPreprocessorRunner:
    """Background task runner for summary pre-processing."""

    def __init__(
        self,
        db_manager: DatabaseConnectionManager,
        openrouter_config: OpenRouterConfig,
        check_interval_seconds: int = 300,
    ) -> None:
        """Initialize the preprocessor runner.

        Args:
            db_manager: Database connection manager.
            openrouter_config: OpenRouter configuration.
            check_interval_seconds: How often to check for books needing processing.
        """
        self.db_manager = db_manager
        self.openrouter_config = openrouter_config
        self.check_interval = check_interval_seconds

        self.book_repo = BookRepository(db_manager)
        self.snippet_repo = SnippetRepository(db_manager)
        self.summary_repo = SnippetSummaryRepository(db_manager)

        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        self._preprocessor: Optional[SummaryPreprocessor] = None

    async def start(self) -> None:
        """Start the background pre-processing task."""
        if self._running:
            logger.warning("Summary preprocessor runner already running")
            return

        # Initialize AI summarizer and preprocessor
        ai_summarizer = AISummarizer(self.openrouter_config)
        self._preprocessor = SummaryPreprocessor(
            self.db_manager,
            ai_summarizer,
            self.openrouter_config.summary_page_count,
        )

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            f"Started summary preprocessor runner (check interval: {self.check_interval}s)"
        )

    async def stop(self) -> None:
        """Stop the background pre-processing task."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Stopped summary preprocessor runner")

    def is_running(self) -> bool:
        """Check if the preprocessor runner is active.

        Returns:
            True if running, False otherwise.
        """
        return self._running

    async def _run_loop(self) -> None:
        """Main loop that periodically checks for books needing processing."""
        while self._running:
            try:
                await self._process_books()
            except Exception as e:
                logger.error(f"Error in preprocessor loop: {e}", exc_info=True)

            # Wait before next check
            try:
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break

    async def _process_books(self) -> None:
        """Process all books that need summary pre-processing."""
        if self._preprocessor is None:
            logger.error("Preprocessor not initialized")
            return

        # Get all completed books
        conn = self.db_manager.get_connection()
        cursor = conn.execute(
            "SELECT id FROM books WHERE status = 'completed' ORDER BY id ASC"
        )
        book_ids = [row["id"] for row in cursor.fetchall()]

        if not book_ids:
            logger.debug("No completed books found for pre-processing")
            return

        logger.debug(f"Checking {len(book_ids)} books for summary pre-processing")

        for book_id in book_ids:
            if not self._running:
                break

            # Check if book needs processing
            missing = self._preprocessor.get_missing_summary_positions(book_id)
            if missing:
                logger.info(
                    f"Book {book_id} needs {len(missing)} summaries, starting pre-processing"
                )
                try:
                    await self._preprocessor.preprocess_book(book_id)
                except Exception as e:
                    logger.error(
                        f"Error pre-processing book {book_id}: {e}", exc_info=True
                    )
