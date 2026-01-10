"""Data models for the BookTok Telegram bot."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class BookStatus(Enum):
    """Status of book processing."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class FileType(Enum):
    """Supported book file types."""

    PDF = "pdf"
    EPUB = "epub"


class Frequency(Enum):
    """Delivery frequency options."""

    DAILY = "daily"
    TWICE_DAILY = "twice_daily"
    WEEKLY = "weekly"


class ValidationError(Exception):
    """Raised when model validation fails."""


@dataclass
class User:
    """Represents a Telegram user of the bot."""

    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    timezone: str = "UTC"
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def validate(self) -> None:
        """Validate the user data.

        Raises:
            ValidationError: If validation fails.
        """
        if not isinstance(self.telegram_id, int):
            raise ValidationError("telegram_id must be an integer")
        if self.telegram_id <= 0:
            raise ValidationError("telegram_id must be a positive integer")
        if self.username is not None and not isinstance(self.username, str):
            raise ValidationError("username must be a string or None")
        if self.first_name is not None and not isinstance(self.first_name, str):
            raise ValidationError("first_name must be a string or None")
        if self.last_name is not None and not isinstance(self.last_name, str):
            raise ValidationError("last_name must be a string or None")
        if not isinstance(self.timezone, str) or not self.timezone:
            raise ValidationError("timezone must be a non-empty string")

    def __post_init__(self) -> None:
        """Validate after initialization."""
        self.validate()


@dataclass
class Book:
    """Represents a book that has been uploaded for processing."""

    title: str
    file_path: str
    file_type: FileType
    author: Optional[str] = None
    status: BookStatus = BookStatus.PENDING
    total_snippets: int = 0
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def validate(self) -> None:
        """Validate the book data.

        Raises:
            ValidationError: If validation fails.
        """
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValidationError("title must be a non-empty string")
        if not isinstance(self.file_path, str) or not self.file_path.strip():
            raise ValidationError("file_path must be a non-empty string")
        if not isinstance(self.file_type, FileType):
            raise ValidationError("file_type must be a FileType enum")
        if self.author is not None and not isinstance(self.author, str):
            raise ValidationError("author must be a string or None")
        if not isinstance(self.status, BookStatus):
            raise ValidationError("status must be a BookStatus enum")
        if not isinstance(self.total_snippets, int) or self.total_snippets < 0:
            raise ValidationError("total_snippets must be a non-negative integer")

    def __post_init__(self) -> None:
        """Validate after initialization."""
        self.validate()


@dataclass
class Snippet:
    """Represents a learning snippet extracted from a book."""

    book_id: int
    position: int
    content: str
    id: Optional[int] = None
    created_at: Optional[datetime] = None

    def validate(self) -> None:
        """Validate the snippet data.

        Raises:
            ValidationError: If validation fails.
        """
        if not isinstance(self.book_id, int) or self.book_id <= 0:
            raise ValidationError("book_id must be a positive integer")
        if not isinstance(self.position, int) or self.position < 0:
            raise ValidationError("position must be a non-negative integer")
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValidationError("content must be a non-empty string")

    def __post_init__(self) -> None:
        """Validate after initialization."""
        self.validate()


@dataclass
class UserProgress:
    """Tracks a user's progress through a book."""

    user_id: int
    book_id: int
    current_position: int = 0
    is_completed: bool = False
    id: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def validate(self) -> None:
        """Validate the user progress data.

        Raises:
            ValidationError: If validation fails.
        """
        if not isinstance(self.user_id, int) or self.user_id <= 0:
            raise ValidationError("user_id must be a positive integer")
        if not isinstance(self.book_id, int) or self.book_id <= 0:
            raise ValidationError("book_id must be a positive integer")
        if not isinstance(self.current_position, int) or self.current_position < 0:
            raise ValidationError("current_position must be a non-negative integer")
        if not isinstance(self.is_completed, bool):
            raise ValidationError("is_completed must be a boolean")

    def __post_init__(self) -> None:
        """Validate after initialization."""
        self.validate()


@dataclass
class DeliverySchedule:
    """Represents a user's delivery schedule for a book."""

    user_id: int
    book_id: int
    delivery_time: str
    frequency: Frequency = Frequency.DAILY
    is_paused: bool = False
    id: Optional[int] = None
    last_delivered_at: Optional[datetime] = None
    next_delivery_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def validate(self) -> None:
        """Validate the delivery schedule data.

        Raises:
            ValidationError: If validation fails.
        """
        if not isinstance(self.user_id, int) or self.user_id <= 0:
            raise ValidationError("user_id must be a positive integer")
        if not isinstance(self.book_id, int) or self.book_id <= 0:
            raise ValidationError("book_id must be a positive integer")
        if not isinstance(self.delivery_time, str) or not self.delivery_time.strip():
            raise ValidationError("delivery_time must be a non-empty string")
        self._validate_time_format(self.delivery_time)
        if not isinstance(self.frequency, Frequency):
            raise ValidationError("frequency must be a Frequency enum")
        if not isinstance(self.is_paused, bool):
            raise ValidationError("is_paused must be a boolean")

    def _validate_time_format(self, time_str: str) -> None:
        """Validate that time is in HH:MM format.

        Args:
            time_str: Time string to validate.

        Raises:
            ValidationError: If time format is invalid.
        """
        parts = time_str.split(":")
        if len(parts) != 2:
            raise ValidationError("delivery_time must be in HH:MM format")
        try:
            hour = int(parts[0])
            minute = int(parts[1])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValidationError(
                    "delivery_time must have valid hour (0-23) and minute (0-59)"
                )
        except ValueError:
            raise ValidationError(
                "delivery_time must be in HH:MM format with numeric values"
            )

    def __post_init__(self) -> None:
        """Validate after initialization."""
        self.validate()
