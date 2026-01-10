"""Delivery scheduler for managing user book snippet delivery schedules."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from booktok.models import DeliverySchedule, Frequency
from booktok.repository import (
    BookRepository,
    DatabaseConnectionManager,
    DeliveryScheduleRepository,
    SnippetRepository,
    UserProgressRepository,
    UserRepository,
)


logger = logging.getLogger(__name__)


class SchedulerError(Exception):
    """Base exception for scheduler errors."""


class InvalidTimezoneError(SchedulerError):
    """Raised when an invalid timezone is provided."""


class InvalidScheduleError(SchedulerError):
    """Raised when schedule parameters are invalid."""


class UserNotFoundError(SchedulerError):
    """Raised when user is not found."""


class BookNotFoundError(SchedulerError):
    """Raised when book is not found."""


@dataclass
class ScheduleInfo:
    """Information about a user's delivery schedule for display."""

    schedule: DeliverySchedule
    book_title: str
    book_author: Optional[str]
    user_timezone: str
    local_delivery_time: str
    next_delivery_local: Optional[str]
    is_active: bool

    def format_for_display(self) -> str:
        """Format the schedule information for user display.

        Returns:
            Formatted string for Telegram message.
        """
        status = "🟢 Active" if self.is_active else "⏸️ Paused"
        frequency_display = {
            Frequency.DAILY: "Daily",
            Frequency.TWICE_DAILY: "Twice daily",
            Frequency.WEEKLY: "Weekly",
        }.get(self.schedule.frequency, "Unknown")

        lines = [
            f"📚 *{self.book_title}*",
        ]
        if self.book_author:
            lines.append(f"✍️ {self.book_author}")
        lines.extend(
            [
                "",
                f"⏰ *Delivery Time:* {self.local_delivery_time}",
                f"📅 *Frequency:* {frequency_display}",
                f"🌍 *Timezone:* {self.user_timezone}",
                f"📊 *Status:* {status}",
            ]
        )
        if self.next_delivery_local:
            lines.append(f"⏭️ *Next delivery:* {self.next_delivery_local}")

        return "\n".join(lines)


class DeliveryScheduler:
    """Manages delivery schedules for book snippets."""

    def __init__(self, db_manager: DatabaseConnectionManager) -> None:
        """Initialize the delivery scheduler.

        Args:
            db_manager: Database connection manager.
        """
        self.db_manager = db_manager
        self.schedule_repo = DeliveryScheduleRepository(db_manager)
        self.user_repo = UserRepository(db_manager)

    def set_schedule(
        self,
        user_id: int,
        book_id: int,
        delivery_time: str,
        frequency: Frequency = Frequency.DAILY,
        timezone: Optional[str] = None,
    ) -> DeliverySchedule:
        """Set or update a delivery schedule for a user's book.

        Args:
            user_id: Database ID of the user.
            book_id: Database ID of the book.
            delivery_time: Preferred delivery time in HH:MM format.
            frequency: Delivery frequency (daily, twice_daily, weekly).
            timezone: User's timezone (e.g., "America/New_York"). If None, uses user's stored timezone.

        Returns:
            Created or updated DeliverySchedule.

        Raises:
            UserNotFoundError: If user is not found.
            InvalidTimezoneError: If timezone is invalid.
            InvalidScheduleError: If schedule parameters are invalid.
        """
        user = self.user_repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"User with ID {user_id} not found")

        if timezone is not None:
            self._validate_timezone(timezone)
            if user.timezone != timezone:
                user.timezone = timezone
                self.user_repo.update(user)
                logger.info(f"Updated timezone for user {user_id} to {timezone}")

        effective_timezone = timezone or user.timezone
        next_delivery = self._calculate_next_delivery(
            delivery_time, frequency, effective_timezone
        )

        existing_schedule = self.schedule_repo.get_by_user_and_book(user_id, book_id)

        if existing_schedule is not None:
            existing_schedule.delivery_time = delivery_time
            existing_schedule.frequency = frequency
            existing_schedule.next_delivery_at = next_delivery
            existing_schedule.is_paused = False
            self.schedule_repo.update(existing_schedule)
            logger.info(
                f"Updated schedule for user {user_id}, book {book_id}: "
                f"{delivery_time} {frequency.value}"
            )
            return existing_schedule

        schedule = DeliverySchedule(
            user_id=user_id,
            book_id=book_id,
            delivery_time=delivery_time,
            frequency=frequency,
            is_paused=False,
            next_delivery_at=next_delivery,
        )
        created_schedule = self.schedule_repo.create(schedule)
        logger.info(
            f"Created schedule for user {user_id}, book {book_id}: "
            f"{delivery_time} {frequency.value}"
        )
        return created_schedule

    def get_schedule(
        self,
        user_id: int,
        book_id: int,
    ) -> Optional[DeliverySchedule]:
        """Get the delivery schedule for a specific user and book.

        Args:
            user_id: Database ID of the user.
            book_id: Database ID of the book.

        Returns:
            DeliverySchedule if found, None otherwise.
        """
        return self.schedule_repo.get_by_user_and_book(user_id, book_id)

    def get_user_schedules(self, user_id: int) -> list[DeliverySchedule]:
        """Get all delivery schedules for a user.

        Args:
            user_id: Database ID of the user.

        Returns:
            List of DeliverySchedule objects.
        """
        return self.schedule_repo.list_by_user(user_id)

    def get_schedule_info(
        self,
        user_id: int,
        book_id: int,
        book_title: str,
        book_author: Optional[str] = None,
    ) -> Optional[ScheduleInfo]:
        """Get formatted schedule information for display.

        Args:
            user_id: Database ID of the user.
            book_id: Database ID of the book.
            book_title: Title of the book.
            book_author: Author of the book (optional).

        Returns:
            ScheduleInfo for display, or None if no schedule exists.
        """
        schedule = self.schedule_repo.get_by_user_and_book(user_id, book_id)
        if schedule is None:
            return None

        user = self.user_repo.get_by_id(user_id)
        if user is None:
            return None

        try:
            tz = ZoneInfo(user.timezone)
        except Exception:
            tz = ZoneInfo("UTC")

        local_delivery_time = schedule.delivery_time

        next_delivery_local: Optional[str] = None
        if schedule.next_delivery_at:
            local_next = schedule.next_delivery_at.replace(
                tzinfo=ZoneInfo("UTC")
            ).astimezone(tz)
            next_delivery_local = local_next.strftime("%Y-%m-%d %H:%M")

        return ScheduleInfo(
            schedule=schedule,
            book_title=book_title,
            book_author=book_author,
            user_timezone=user.timezone,
            local_delivery_time=local_delivery_time,
            next_delivery_local=next_delivery_local,
            is_active=not schedule.is_paused,
        )

    def update_user_timezone(self, user_id: int, timezone: str) -> None:
        """Update the timezone preference for a user.

        Args:
            user_id: Database ID of the user.
            timezone: IANA timezone name (e.g., "America/New_York").

        Raises:
            UserNotFoundError: If user is not found.
            InvalidTimezoneError: If timezone is invalid.
        """
        user = self.user_repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"User with ID {user_id} not found")

        self._validate_timezone(timezone)

        user.timezone = timezone
        self.user_repo.update(user)
        logger.info(f"Updated timezone for user {user_id} to {timezone}")

        for schedule in self.schedule_repo.list_by_user(user_id):
            new_next_delivery = self._calculate_next_delivery(
                schedule.delivery_time,
                schedule.frequency,
                timezone,
            )
            schedule.next_delivery_at = new_next_delivery
            self.schedule_repo.update(schedule)

    def get_user_timezone(self, user_id: int) -> str:
        """Get the timezone for a user.

        Args:
            user_id: Database ID of the user.

        Returns:
            Timezone string (defaults to "UTC" if user not found).
        """
        user = self.user_repo.get_by_id(user_id)
        if user is None:
            return "UTC"
        return user.timezone

    def format_schedules_for_display(
        self,
        user_id: int,
        book_info: dict[int, tuple[str, Optional[str]]],
    ) -> str:
        """Format all schedules for a user for display.

        Args:
            user_id: Database ID of the user.
            book_info: Mapping of book_id to (title, author) tuples.

        Returns:
            Formatted string for Telegram message.
        """
        schedules = self.get_user_schedules(user_id)

        if not schedules:
            return "📭 *No delivery schedules set*\n\nUpload a book and set a schedule to get started!"

        user = self.user_repo.get_by_id(user_id)
        user_tz = user.timezone if user else "UTC"

        lines = [
            "📅 *Your Delivery Schedules*",
            f"🌍 Timezone: {user_tz}",
            "",
        ]

        for i, schedule in enumerate(schedules, 1):
            book_title, book_author = book_info.get(
                schedule.book_id,
                ("Unknown Book", None),
            )

            status_emoji = "🟢" if not schedule.is_paused else "⏸️"
            freq_short = {
                Frequency.DAILY: "Daily",
                Frequency.TWICE_DAILY: "2x/day",
                Frequency.WEEKLY: "Weekly",
            }.get(schedule.frequency, "?")

            lines.append(f"{i}. {status_emoji} *{book_title}*")
            lines.append(f"   ⏰ {schedule.delivery_time} ({freq_short})")
            if schedule.next_delivery_at:
                try:
                    tz = ZoneInfo(user_tz)
                    local_next = schedule.next_delivery_at.replace(
                        tzinfo=ZoneInfo("UTC")
                    ).astimezone(tz)
                    lines.append(f"   ⏭️ Next: {local_next.strftime('%b %d, %H:%M')}")
                except Exception:
                    pass
            lines.append("")

        return "\n".join(lines)

    def pause_schedule(self, user_id: int, book_id: int) -> bool:
        """Pause automatic deliveries for a specific schedule.

        Args:
            user_id: Database ID of the user.
            book_id: Database ID of the book.

        Returns:
            True if schedule was paused, False if no schedule exists.
        """
        schedule = self.schedule_repo.get_by_user_and_book(user_id, book_id)
        if schedule is None:
            return False

        if schedule.is_paused:
            logger.info(f"Schedule for user {user_id}, book {book_id} already paused")
            return True

        schedule.is_paused = True
        self.schedule_repo.update(schedule)
        logger.info(f"Paused schedule for user {user_id}, book {book_id}")
        return True

    def resume_schedule(self, user_id: int, book_id: int) -> bool:
        """Resume automatic deliveries for a specific schedule.

        Args:
            user_id: Database ID of the user.
            book_id: Database ID of the book.

        Returns:
            True if schedule was resumed, False if no schedule exists.
        """
        schedule = self.schedule_repo.get_by_user_and_book(user_id, book_id)
        if schedule is None:
            return False

        if not schedule.is_paused:
            logger.info(f"Schedule for user {user_id}, book {book_id} already active")
            return True

        user = self.user_repo.get_by_id(user_id)
        user_tz = user.timezone if user else "UTC"

        schedule.is_paused = False
        schedule.next_delivery_at = self._calculate_next_delivery(
            schedule.delivery_time,
            schedule.frequency,
            user_tz,
        )
        self.schedule_repo.update(schedule)
        logger.info(f"Resumed schedule for user {user_id}, book {book_id}")
        return True

    def pause_all_schedules(self, user_id: int) -> int:
        """Pause all delivery schedules for a user.

        Args:
            user_id: Database ID of the user.

        Returns:
            Number of schedules that were paused.
        """
        schedules = self.schedule_repo.list_by_user(user_id)
        paused_count = 0

        for schedule in schedules:
            if not schedule.is_paused:
                schedule.is_paused = True
                self.schedule_repo.update(schedule)
                paused_count += 1

        logger.info(f"Paused {paused_count} schedules for user {user_id}")
        return paused_count

    def resume_all_schedules(self, user_id: int) -> int:
        """Resume all delivery schedules for a user.

        Args:
            user_id: Database ID of the user.

        Returns:
            Number of schedules that were resumed.
        """
        user = self.user_repo.get_by_id(user_id)
        user_tz = user.timezone if user else "UTC"

        schedules = self.schedule_repo.list_by_user(user_id)
        resumed_count = 0

        for schedule in schedules:
            if schedule.is_paused:
                schedule.is_paused = False
                schedule.next_delivery_at = self._calculate_next_delivery(
                    schedule.delivery_time,
                    schedule.frequency,
                    user_tz,
                )
                self.schedule_repo.update(schedule)
                resumed_count += 1

        logger.info(f"Resumed {resumed_count} schedules for user {user_id}")
        return resumed_count

    def _validate_timezone(self, timezone: str) -> None:
        """Validate that a timezone string is valid.

        Args:
            timezone: IANA timezone name.

        Raises:
            InvalidTimezoneError: If timezone is invalid.
        """
        try:
            ZoneInfo(timezone)
        except Exception as e:
            raise InvalidTimezoneError(f"Invalid timezone: {timezone}") from e

    def _calculate_next_delivery(
        self,
        delivery_time: str,
        frequency: Frequency,
        timezone: str,
    ) -> datetime:
        """Calculate the next delivery datetime in UTC.

        Args:
            delivery_time: Delivery time in HH:MM format.
            frequency: Delivery frequency.
            timezone: User's timezone.

        Returns:
            Next delivery datetime in UTC.
        """
        try:
            tz = ZoneInfo(timezone)
        except Exception:
            tz = ZoneInfo("UTC")

        now_utc = datetime.now(ZoneInfo("UTC"))
        now_local = now_utc.astimezone(tz)

        hour, minute = map(int, delivery_time.split(":"))

        next_local = now_local.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )

        if next_local <= now_local:
            if frequency == Frequency.DAILY or frequency == Frequency.TWICE_DAILY:
                next_local += timedelta(days=1)
            elif frequency == Frequency.WEEKLY:
                next_local += timedelta(weeks=1)

        return next_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


@dataclass
class DeliveryResult:
    """Result of a scheduled delivery attempt."""

    schedule_id: int
    user_id: int
    book_id: int
    success: bool
    message: str
    snippet_position: Optional[int] = None
    error: Optional[str] = None
    attempts: int = 1


SendMessageFunc = Callable[[int, str], "asyncio.Future[bool]"]


class AutomatedDeliveryRunner:
    """Handles automated scheduled delivery of book snippets."""

    MAX_RETRIES = 5
    INITIAL_BACKOFF_SECONDS = 1.0
    MAX_BACKOFF_SECONDS = 30.0
    BACKOFF_MULTIPLIER = 2.0

    def __init__(
        self,
        db_manager: DatabaseConnectionManager,
        send_message_func: SendMessageFunc,
        check_interval_seconds: int = 60,
    ) -> None:
        """Initialize the automated delivery runner.

        Args:
            db_manager: Database connection manager.
            send_message_func: Async function to send messages via Telegram.
                              Takes (telegram_id, message_text) and returns success bool.
            check_interval_seconds: How often to check for pending deliveries.
        """
        self.db_manager = db_manager
        self.send_message_func = send_message_func
        self.check_interval = check_interval_seconds

        self.schedule_repo = DeliveryScheduleRepository(db_manager)
        self.user_repo = UserRepository(db_manager)
        self.book_repo = BookRepository(db_manager)
        self.snippet_repo = SnippetRepository(db_manager)
        self.progress_repo = UserProgressRepository(db_manager)

        self._running = False
        self._task: Optional[asyncio.Task[None]] = None

    async def start(self) -> None:
        """Start the background delivery task."""
        if self._running:
            logger.warning("Delivery runner already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            f"Started automated delivery runner (check interval: {self.check_interval}s)"
        )

    async def stop(self) -> None:
        """Stop the background delivery task."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Stopped automated delivery runner")

    def is_running(self) -> bool:
        """Check if the delivery runner is active.

        Returns:
            True if running, False otherwise.
        """
        return self._running

    async def _send_message_with_retry(
        self,
        telegram_id: int,
        message: str,
    ) -> tuple[bool, int, str]:
        """Send a message with exponential backoff retries.

        Args:
            telegram_id: The Telegram user ID to send to.
            message: The message text to send.

        Returns:
            Tuple of (success, attempt_count, error_message).
            success is True if message was sent successfully.
            attempt_count is the number of attempts made.
            error_message is empty if successful, contains error info if failed.
        """
        last_error = ""
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                result = await self.send_message_func(telegram_id, message)
                if result:
                    logger.info(
                        f"Message sent to user {telegram_id} on attempt {attempt}"
                    )
                    return (True, attempt, "")
                else:
                    last_error = "send_message_func returned False"
            except asyncio.CancelledError:
                raise
            except Exception as e:
                last_error = str(e)

            if attempt < self.MAX_RETRIES:
                backoff_time = min(
                    self.INITIAL_BACKOFF_SECONDS
                    * (self.BACKOFF_MULTIPLIER ** (attempt - 1)),
                    self.MAX_BACKOFF_SECONDS,
                )
                logger.warning(
                    f"Attempt {attempt}/{self.MAX_RETRIES} failed for user {telegram_id}: {last_error}. "
                    f"Retrying in {backoff_time:.1f}s"
                )
                await asyncio.sleep(backoff_time)

        logger.error(
            f"All {self.MAX_RETRIES} attempts failed for user {telegram_id}: {last_error}"
        )
        return (False, self.MAX_RETRIES, last_error)

    async def _run_loop(self) -> None:
        """Main loop that periodically checks for pending deliveries."""
        while self._running:
            try:
                await self._process_pending_deliveries()
            except Exception as e:
                logger.error(f"Error in delivery loop: {e}", exc_info=True)

            await asyncio.sleep(self.check_interval)

    async def _process_pending_deliveries(self) -> list[DeliveryResult]:
        """Check for and process all pending deliveries.

        Returns:
            List of delivery results.
        """
        now_utc = datetime.now(ZoneInfo("UTC")).replace(tzinfo=None)
        pending_schedules = self.schedule_repo.list_pending_deliveries(now_utc)

        results: list[DeliveryResult] = []

        for schedule in pending_schedules:
            try:
                result = await self._deliver_snippet(schedule)
                results.append(result)

                if result.success:
                    self._update_schedule_after_delivery(schedule)
                    logger.info(
                        f"Delivered snippet {result.snippet_position} for schedule "
                        f"{schedule.id} to user {schedule.user_id}"
                    )
                else:
                    logger.warning(
                        f"Failed to deliver for schedule {schedule.id}: {result.error}"
                    )
            except Exception as e:
                logger.error(
                    f"Error processing schedule {schedule.id}: {e}",
                    exc_info=True,
                )
                results.append(
                    DeliveryResult(
                        schedule_id=schedule.id or 0,
                        user_id=schedule.user_id,
                        book_id=schedule.book_id,
                        success=False,
                        message="Internal error during delivery",
                        error=str(e),
                    )
                )

        return results

    async def _deliver_snippet(self, schedule: DeliverySchedule) -> DeliveryResult:
        """Deliver the next snippet for a scheduled delivery.

        Args:
            schedule: The delivery schedule to process.

        Returns:
            DeliveryResult with success/failure information.
        """
        from booktok.snippet_formatter import SnippetFormatter

        user = self.user_repo.get_by_id(schedule.user_id)
        if user is None:
            return DeliveryResult(
                schedule_id=schedule.id or 0,
                user_id=schedule.user_id,
                book_id=schedule.book_id,
                success=False,
                message="User not found",
                error="User not found in database",
            )

        book = self.book_repo.get_by_id(schedule.book_id)
        if book is None:
            return DeliveryResult(
                schedule_id=schedule.id or 0,
                user_id=schedule.user_id,
                book_id=schedule.book_id,
                success=False,
                message="Book not found",
                error="Book not found in database",
            )

        progress = self.progress_repo.get_by_user_and_book(
            schedule.user_id,
            schedule.book_id,
        )

        if progress is None:
            return DeliveryResult(
                schedule_id=schedule.id or 0,
                user_id=schedule.user_id,
                book_id=schedule.book_id,
                success=False,
                message="No progress record found",
                error="UserProgress not found for user/book",
            )

        if progress.is_completed:
            return DeliveryResult(
                schedule_id=schedule.id or 0,
                user_id=schedule.user_id,
                book_id=schedule.book_id,
                success=False,
                message="Book already completed",
                error="Book is marked as completed",
            )

        snippet = self.snippet_repo.get_by_book_and_position(
            schedule.book_id,
            progress.current_position,
        )

        if snippet is None:
            return DeliveryResult(
                schedule_id=schedule.id or 0,
                user_id=schedule.user_id,
                book_id=schedule.book_id,
                success=False,
                message="No more snippets available",
                error=f"Snippet at position {progress.current_position} not found",
            )

        total_snippets = self.snippet_repo.count_by_book(book.id or 0)
        formatter = SnippetFormatter(book, total_snippets=total_snippets)
        formatted = formatter.format_snippet(snippet, progress)

        all_sent = True
        total_attempts = 0
        for message in formatted.messages:
            success, attempts, error = await self._send_message_with_retry(
                user.telegram_id, message.text
            )
            total_attempts += attempts
            if not success:
                all_sent = False
                logger.error(
                    f"Failed to deliver message to user {user.telegram_id} "
                    f"after {attempts} attempts: {error}"
                )
                break

        if all_sent:
            progress.current_position += 1

            if progress.current_position >= total_snippets:
                progress.is_completed = True
                progress.completed_at = datetime.utcnow()

                congratulatory = (
                    f"🎉 *Congratulations!*\n\n"
                    f"You've completed *{book.title}*!\n\n"
                    f"📚 Total snippets read: {total_snippets}\n\n"
                    f"Great job on finishing this book! 🏆"
                )
                success, attempts, error = await self._send_message_with_retry(
                    user.telegram_id, congratulatory
                )
                if not success:
                    logger.error(
                        f"Failed to send completion message to user {user.telegram_id}: {error}"
                    )

            self.progress_repo.update(progress)

            return DeliveryResult(
                schedule_id=schedule.id or 0,
                user_id=schedule.user_id,
                book_id=schedule.book_id,
                success=True,
                message="Snippet delivered successfully",
                snippet_position=progress.current_position - 1,
                attempts=total_attempts,
            )
        else:
            return DeliveryResult(
                schedule_id=schedule.id or 0,
                user_id=schedule.user_id,
                book_id=schedule.book_id,
                success=False,
                message="Failed to send message via Telegram",
                error=f"Telegram message delivery failed after {total_attempts} attempts",
                attempts=total_attempts,
            )

    def _update_schedule_after_delivery(self, schedule: DeliverySchedule) -> None:
        """Update schedule after successful delivery.

        Args:
            schedule: The schedule that was delivered.
        """
        user = self.user_repo.get_by_id(schedule.user_id)
        user_tz = user.timezone if user else "UTC"

        now_utc = datetime.now(ZoneInfo("UTC")).replace(tzinfo=None)
        schedule.last_delivered_at = now_utc

        next_delivery = self._calculate_next_delivery_for_schedule(
            schedule.delivery_time,
            schedule.frequency,
            user_tz,
        )
        schedule.next_delivery_at = next_delivery

        self.schedule_repo.update(schedule)

    def _calculate_next_delivery_for_schedule(
        self,
        delivery_time: str,
        frequency: Frequency,
        timezone: str,
    ) -> datetime:
        """Calculate the next delivery datetime.

        Args:
            delivery_time: Delivery time in HH:MM format.
            frequency: Delivery frequency.
            timezone: User's timezone.

        Returns:
            Next delivery datetime in UTC.
        """
        try:
            tz = ZoneInfo(timezone)
        except Exception:
            tz = ZoneInfo("UTC")

        now_utc = datetime.now(ZoneInfo("UTC"))
        now_local = now_utc.astimezone(tz)

        hour, minute = map(int, delivery_time.split(":"))

        next_local = now_local.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )

        if frequency == Frequency.DAILY:
            next_local += timedelta(days=1)
        elif frequency == Frequency.TWICE_DAILY:
            next_local += timedelta(hours=12)
            if next_local <= now_local:
                next_local += timedelta(hours=12)
        elif frequency == Frequency.WEEKLY:
            next_local += timedelta(weeks=1)
        else:
            next_local += timedelta(days=1)

        return next_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    async def run_once(self) -> list[DeliveryResult]:
        """Run a single check for pending deliveries.

        Useful for testing or manual triggering.

        Returns:
            List of delivery results.
        """
        return await self._process_pending_deliveries()
