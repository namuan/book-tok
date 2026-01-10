"""Delivery scheduler for managing user book snippet delivery schedules."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from booktok.models import DeliverySchedule, Frequency, User
from booktok.repository import (
    DatabaseConnectionManager,
    DeliveryScheduleRepository,
    UserRepository,
)


logger = logging.getLogger(__name__)


class SchedulerError(Exception):
    """Base exception for scheduler errors."""
    pass


class InvalidTimezoneError(SchedulerError):
    """Raised when an invalid timezone is provided."""
    pass


class InvalidScheduleError(SchedulerError):
    """Raised when schedule parameters are invalid."""
    pass


class UserNotFoundError(SchedulerError):
    """Raised when user is not found."""
    pass


class BookNotFoundError(SchedulerError):
    """Raised when book is not found."""
    pass


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
        lines.extend([
            f"",
            f"⏰ *Delivery Time:* {self.local_delivery_time}",
            f"📅 *Frequency:* {frequency_display}",
            f"🌍 *Timezone:* {self.user_timezone}",
            f"📊 *Status:* {status}",
        ])
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
            local_next = schedule.next_delivery_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
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
