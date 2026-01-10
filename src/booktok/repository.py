"""Database repositories implementing CRUD operations for all models."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional

from booktok.database import initialize_database, create_tables
from booktok.models import (
    Book,
    BookStatus,
    DeliverySchedule,
    FileType,
    Frequency,
    Snippet,
    User,
    UserProgress,
)


class DatabaseConnectionManager:
    """Manages SQLite database connections with context manager support."""

    def __init__(self, db_path: str | Path = "booktok.db") -> None:
        """Initialize the connection manager.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = Path(db_path)
        self._connection: Optional[sqlite3.Connection] = None

    def connect(self) -> sqlite3.Connection:
        """Establish a database connection.

        Returns:
            Active database connection.
        """
        if self._connection is None:
            self._connection = sqlite3.connect(self.db_path)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON")
        return self._connection

    def close(self) -> None:
        """Close the database connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def initialize(self) -> None:
        """Initialize the database schema."""
        conn = self.connect()
        create_tables(conn)

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for database transactions with automatic commit/rollback.

        Yields:
            Active database connection within a transaction.

        Raises:
            Exception: Re-raises any exception after rollback.
        """
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def get_connection(self) -> sqlite3.Connection:
        """Get the current connection, creating one if needed.

        Returns:
            Active database connection.
        """
        return self.connect()


class UserRepository:
    """Repository for User CRUD operations."""

    def __init__(self, db_manager: DatabaseConnectionManager) -> None:
        """Initialize the repository.

        Args:
            db_manager: Database connection manager.
        """
        self.db = db_manager

    def create(self, user: User) -> User:
        """Create a new user in the database.

        Args:
            user: User object to create.

        Returns:
            User with assigned ID.
        """
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO users (telegram_id, username, first_name, last_name, timezone)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user.telegram_id, user.username, user.first_name, user.last_name, user.timezone),
            )
            user.id = cursor.lastrowid
        return user

    def get_by_id(self, user_id: int) -> Optional[User]:
        """Retrieve a user by ID.

        Args:
            user_id: Database ID of the user.

        Returns:
            User if found, None otherwise.
        """
        conn = self.db.get_connection()
        cursor = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return self._row_to_user(row) if row else None

    def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        """Retrieve a user by Telegram ID.

        Args:
            telegram_id: Telegram user ID.

        Returns:
            User if found, None otherwise.
        """
        conn = self.db.get_connection()
        cursor = conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        row = cursor.fetchone()
        return self._row_to_user(row) if row else None

    def update(self, user: User) -> User:
        """Update an existing user.

        Args:
            user: User object with updated fields.

        Returns:
            Updated user.

        Raises:
            ValueError: If user has no ID.
        """
        if user.id is None:
            raise ValueError("Cannot update user without ID")
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE users
                SET username = ?, first_name = ?, last_name = ?, timezone = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (user.username, user.first_name, user.last_name, user.timezone, user.id),
            )
        return user

    def delete(self, user_id: int) -> bool:
        """Delete a user by ID.

        Args:
            user_id: Database ID of the user to delete.

        Returns:
            True if user was deleted, False if not found.
        """
        with self.db.transaction() as conn:
            cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            return cursor.rowcount > 0

    def list_all(self) -> list[User]:
        """Retrieve all users.

        Returns:
            List of all users.
        """
        conn = self.db.get_connection()
        cursor = conn.execute("SELECT * FROM users ORDER BY created_at DESC")
        return [self._row_to_user(row) for row in cursor.fetchall()]

    def _row_to_user(self, row: sqlite3.Row) -> User:
        """Convert a database row to a User object.

        Args:
            row: Database row.

        Returns:
            User object.
        """
        return User(
            id=row["id"],
            telegram_id=row["telegram_id"],
            username=row["username"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            timezone=row["timezone"],
            created_at=self._parse_datetime(row["created_at"]),
            updated_at=self._parse_datetime(row["updated_at"]),
        )

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        """Parse a datetime string from the database.

        Args:
            value: Datetime string or None.

        Returns:
            datetime object or None.
        """
        if value is None:
            return None
        try:
            return datetime.fromisoformat(value.replace(" ", "T"))
        except (ValueError, AttributeError):
            return None


class BookRepository:
    """Repository for Book CRUD operations."""

    def __init__(self, db_manager: DatabaseConnectionManager) -> None:
        """Initialize the repository.

        Args:
            db_manager: Database connection manager.
        """
        self.db = db_manager

    def create(self, book: Book) -> Book:
        """Create a new book in the database.

        Args:
            book: Book object to create.

        Returns:
            Book with assigned ID.
        """
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO books (title, author, file_path, file_type, status, total_snippets)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    book.title,
                    book.author,
                    book.file_path,
                    book.file_type.value,
                    book.status.value,
                    book.total_snippets,
                ),
            )
            book.id = cursor.lastrowid
        return book

    def get_by_id(self, book_id: int) -> Optional[Book]:
        """Retrieve a book by ID.

        Args:
            book_id: Database ID of the book.

        Returns:
            Book if found, None otherwise.
        """
        conn = self.db.get_connection()
        cursor = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,))
        row = cursor.fetchone()
        return self._row_to_book(row) if row else None

    def update(self, book: Book) -> Book:
        """Update an existing book.

        Args:
            book: Book object with updated fields.

        Returns:
            Updated book.

        Raises:
            ValueError: If book has no ID.
        """
        if book.id is None:
            raise ValueError("Cannot update book without ID")
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE books
                SET title = ?, author = ?, file_path = ?, file_type = ?, status = ?,
                    total_snippets = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    book.title,
                    book.author,
                    book.file_path,
                    book.file_type.value,
                    book.status.value,
                    book.total_snippets,
                    book.id,
                ),
            )
        return book

    def delete(self, book_id: int) -> bool:
        """Delete a book by ID.

        Args:
            book_id: Database ID of the book to delete.

        Returns:
            True if book was deleted, False if not found.
        """
        with self.db.transaction() as conn:
            cursor = conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
            return cursor.rowcount > 0

    def list_all(self) -> list[Book]:
        """Retrieve all books.

        Returns:
            List of all books.
        """
        conn = self.db.get_connection()
        cursor = conn.execute("SELECT * FROM books ORDER BY created_at DESC")
        return [self._row_to_book(row) for row in cursor.fetchall()]

    def list_by_status(self, status: BookStatus) -> list[Book]:
        """Retrieve books by status.

        Args:
            status: Book status to filter by.

        Returns:
            List of books with the given status.
        """
        conn = self.db.get_connection()
        cursor = conn.execute(
            "SELECT * FROM books WHERE status = ? ORDER BY created_at DESC",
            (status.value,),
        )
        return [self._row_to_book(row) for row in cursor.fetchall()]

    def _row_to_book(self, row: sqlite3.Row) -> Book:
        """Convert a database row to a Book object.

        Args:
            row: Database row.

        Returns:
            Book object.
        """
        return Book(
            id=row["id"],
            title=row["title"],
            author=row["author"],
            file_path=row["file_path"],
            file_type=FileType(row["file_type"]),
            status=BookStatus(row["status"]),
            total_snippets=row["total_snippets"],
            created_at=self._parse_datetime(row["created_at"]),
            updated_at=self._parse_datetime(row["updated_at"]),
        )

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        """Parse a datetime string from the database."""
        if value is None:
            return None
        try:
            return datetime.fromisoformat(value.replace(" ", "T"))
        except (ValueError, AttributeError):
            return None


class SnippetRepository:
    """Repository for Snippet CRUD operations."""

    def __init__(self, db_manager: DatabaseConnectionManager) -> None:
        """Initialize the repository.

        Args:
            db_manager: Database connection manager.
        """
        self.db = db_manager

    def create(self, snippet: Snippet) -> Snippet:
        """Create a new snippet in the database.

        Args:
            snippet: Snippet object to create.

        Returns:
            Snippet with assigned ID.
        """
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO snippets (book_id, position, content)
                VALUES (?, ?, ?)
                """,
                (snippet.book_id, snippet.position, snippet.content),
            )
            snippet.id = cursor.lastrowid
        return snippet

    def create_bulk(self, snippets: list[Snippet]) -> list[Snippet]:
        """Create multiple snippets in a single transaction.

        Args:
            snippets: List of Snippet objects to create.

        Returns:
            List of Snippets with assigned IDs.
        """
        with self.db.transaction() as conn:
            for snippet in snippets:
                cursor = conn.execute(
                    """
                    INSERT INTO snippets (book_id, position, content)
                    VALUES (?, ?, ?)
                    """,
                    (snippet.book_id, snippet.position, snippet.content),
                )
                snippet.id = cursor.lastrowid
        return snippets

    def get_by_id(self, snippet_id: int) -> Optional[Snippet]:
        """Retrieve a snippet by ID.

        Args:
            snippet_id: Database ID of the snippet.

        Returns:
            Snippet if found, None otherwise.
        """
        conn = self.db.get_connection()
        cursor = conn.execute("SELECT * FROM snippets WHERE id = ?", (snippet_id,))
        row = cursor.fetchone()
        return self._row_to_snippet(row) if row else None

    def get_by_book_and_position(self, book_id: int, position: int) -> Optional[Snippet]:
        """Retrieve a snippet by book ID and position.

        Args:
            book_id: Database ID of the book.
            position: Position of the snippet in the book.

        Returns:
            Snippet if found, None otherwise.
        """
        conn = self.db.get_connection()
        cursor = conn.execute(
            "SELECT * FROM snippets WHERE book_id = ? AND position = ?",
            (book_id, position),
        )
        row = cursor.fetchone()
        return self._row_to_snippet(row) if row else None

    def list_by_book(self, book_id: int) -> list[Snippet]:
        """Retrieve all snippets for a book.

        Args:
            book_id: Database ID of the book.

        Returns:
            List of snippets ordered by position.
        """
        conn = self.db.get_connection()
        cursor = conn.execute(
            "SELECT * FROM snippets WHERE book_id = ? ORDER BY position ASC",
            (book_id,),
        )
        return [self._row_to_snippet(row) for row in cursor.fetchall()]

    def update(self, snippet: Snippet) -> Snippet:
        """Update an existing snippet.

        Args:
            snippet: Snippet object with updated fields.

        Returns:
            Updated snippet.

        Raises:
            ValueError: If snippet has no ID.
        """
        if snippet.id is None:
            raise ValueError("Cannot update snippet without ID")
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE snippets SET book_id = ?, position = ?, content = ?
                WHERE id = ?
                """,
                (snippet.book_id, snippet.position, snippet.content, snippet.id),
            )
        return snippet

    def delete(self, snippet_id: int) -> bool:
        """Delete a snippet by ID.

        Args:
            snippet_id: Database ID of the snippet to delete.

        Returns:
            True if snippet was deleted, False if not found.
        """
        with self.db.transaction() as conn:
            cursor = conn.execute("DELETE FROM snippets WHERE id = ?", (snippet_id,))
            return cursor.rowcount > 0

    def delete_by_book(self, book_id: int) -> int:
        """Delete all snippets for a book.

        Args:
            book_id: Database ID of the book.

        Returns:
            Number of snippets deleted.
        """
        with self.db.transaction() as conn:
            cursor = conn.execute("DELETE FROM snippets WHERE book_id = ?", (book_id,))
            return cursor.rowcount

    def count_by_book(self, book_id: int) -> int:
        """Count snippets for a book.

        Args:
            book_id: Database ID of the book.

        Returns:
            Number of snippets.
        """
        conn = self.db.get_connection()
        cursor = conn.execute(
            "SELECT COUNT(*) as count FROM snippets WHERE book_id = ?",
            (book_id,),
        )
        row = cursor.fetchone()
        return row["count"] if row else 0

    def _row_to_snippet(self, row: sqlite3.Row) -> Snippet:
        """Convert a database row to a Snippet object.

        Args:
            row: Database row.

        Returns:
            Snippet object.
        """
        return Snippet(
            id=row["id"],
            book_id=row["book_id"],
            position=row["position"],
            content=row["content"],
            created_at=self._parse_datetime(row["created_at"]),
        )

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        """Parse a datetime string from the database."""
        if value is None:
            return None
        try:
            return datetime.fromisoformat(value.replace(" ", "T"))
        except (ValueError, AttributeError):
            return None


class UserProgressRepository:
    """Repository for UserProgress CRUD operations."""

    def __init__(self, db_manager: DatabaseConnectionManager) -> None:
        """Initialize the repository.

        Args:
            db_manager: Database connection manager.
        """
        self.db = db_manager

    def create(self, progress: UserProgress) -> UserProgress:
        """Create a new user progress record.

        Args:
            progress: UserProgress object to create.

        Returns:
            UserProgress with assigned ID.
        """
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO user_progress (user_id, book_id, current_position, is_completed)
                VALUES (?, ?, ?, ?)
                """,
                (
                    progress.user_id,
                    progress.book_id,
                    progress.current_position,
                    1 if progress.is_completed else 0,
                ),
            )
            progress.id = cursor.lastrowid
        return progress

    def get_by_id(self, progress_id: int) -> Optional[UserProgress]:
        """Retrieve a progress record by ID.

        Args:
            progress_id: Database ID of the progress record.

        Returns:
            UserProgress if found, None otherwise.
        """
        conn = self.db.get_connection()
        cursor = conn.execute("SELECT * FROM user_progress WHERE id = ?", (progress_id,))
        row = cursor.fetchone()
        return self._row_to_progress(row) if row else None

    def get_by_user_and_book(self, user_id: int, book_id: int) -> Optional[UserProgress]:
        """Retrieve progress for a specific user and book.

        Args:
            user_id: Database ID of the user.
            book_id: Database ID of the book.

        Returns:
            UserProgress if found, None otherwise.
        """
        conn = self.db.get_connection()
        cursor = conn.execute(
            "SELECT * FROM user_progress WHERE user_id = ? AND book_id = ?",
            (user_id, book_id),
        )
        row = cursor.fetchone()
        return self._row_to_progress(row) if row else None

    def list_by_user(self, user_id: int) -> list[UserProgress]:
        """Retrieve all progress records for a user.

        Args:
            user_id: Database ID of the user.

        Returns:
            List of progress records.
        """
        conn = self.db.get_connection()
        cursor = conn.execute(
            "SELECT * FROM user_progress WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,),
        )
        return [self._row_to_progress(row) for row in cursor.fetchall()]

    def update(self, progress: UserProgress) -> UserProgress:
        """Update an existing progress record.

        Args:
            progress: UserProgress object with updated fields.

        Returns:
            Updated progress record.

        Raises:
            ValueError: If progress has no ID.
        """
        if progress.id is None:
            raise ValueError("Cannot update progress without ID")
        with self.db.transaction() as conn:
            completed_at = progress.completed_at.isoformat() if progress.completed_at else None
            conn.execute(
                """
                UPDATE user_progress
                SET current_position = ?, is_completed = ?, completed_at = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    progress.current_position,
                    1 if progress.is_completed else 0,
                    completed_at,
                    progress.id,
                ),
            )
        return progress

    def delete(self, progress_id: int) -> bool:
        """Delete a progress record by ID.

        Args:
            progress_id: Database ID of the progress record to delete.

        Returns:
            True if record was deleted, False if not found.
        """
        with self.db.transaction() as conn:
            cursor = conn.execute("DELETE FROM user_progress WHERE id = ?", (progress_id,))
            return cursor.rowcount > 0

    def _row_to_progress(self, row: sqlite3.Row) -> UserProgress:
        """Convert a database row to a UserProgress object.

        Args:
            row: Database row.

        Returns:
            UserProgress object.
        """
        return UserProgress(
            id=row["id"],
            user_id=row["user_id"],
            book_id=row["book_id"],
            current_position=row["current_position"],
            is_completed=bool(row["is_completed"]),
            started_at=self._parse_datetime(row["started_at"]),
            completed_at=self._parse_datetime(row["completed_at"]),
            updated_at=self._parse_datetime(row["updated_at"]),
        )

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        """Parse a datetime string from the database."""
        if value is None:
            return None
        try:
            return datetime.fromisoformat(value.replace(" ", "T"))
        except (ValueError, AttributeError):
            return None


class DeliveryScheduleRepository:
    """Repository for DeliverySchedule CRUD operations."""

    def __init__(self, db_manager: DatabaseConnectionManager) -> None:
        """Initialize the repository.

        Args:
            db_manager: Database connection manager.
        """
        self.db = db_manager

    def create(self, schedule: DeliverySchedule) -> DeliverySchedule:
        """Create a new delivery schedule.

        Args:
            schedule: DeliverySchedule object to create.

        Returns:
            DeliverySchedule with assigned ID.
        """
        with self.db.transaction() as conn:
            next_delivery = schedule.next_delivery_at.isoformat() if schedule.next_delivery_at else None
            cursor = conn.execute(
                """
                INSERT INTO delivery_schedules
                    (user_id, book_id, delivery_time, frequency, is_paused, next_delivery_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    schedule.user_id,
                    schedule.book_id,
                    schedule.delivery_time,
                    schedule.frequency.value,
                    1 if schedule.is_paused else 0,
                    next_delivery,
                ),
            )
            schedule.id = cursor.lastrowid
        return schedule

    def get_by_id(self, schedule_id: int) -> Optional[DeliverySchedule]:
        """Retrieve a schedule by ID.

        Args:
            schedule_id: Database ID of the schedule.

        Returns:
            DeliverySchedule if found, None otherwise.
        """
        conn = self.db.get_connection()
        cursor = conn.execute("SELECT * FROM delivery_schedules WHERE id = ?", (schedule_id,))
        row = cursor.fetchone()
        return self._row_to_schedule(row) if row else None

    def get_by_user_and_book(self, user_id: int, book_id: int) -> Optional[DeliverySchedule]:
        """Retrieve schedule for a specific user and book.

        Args:
            user_id: Database ID of the user.
            book_id: Database ID of the book.

        Returns:
            DeliverySchedule if found, None otherwise.
        """
        conn = self.db.get_connection()
        cursor = conn.execute(
            "SELECT * FROM delivery_schedules WHERE user_id = ? AND book_id = ?",
            (user_id, book_id),
        )
        row = cursor.fetchone()
        return self._row_to_schedule(row) if row else None

    def list_by_user(self, user_id: int) -> list[DeliverySchedule]:
        """Retrieve all schedules for a user.

        Args:
            user_id: Database ID of the user.

        Returns:
            List of delivery schedules.
        """
        conn = self.db.get_connection()
        cursor = conn.execute(
            "SELECT * FROM delivery_schedules WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        return [self._row_to_schedule(row) for row in cursor.fetchall()]

    def list_pending_deliveries(self, before: datetime) -> list[DeliverySchedule]:
        """Retrieve schedules with pending deliveries before a given time.

        Args:
            before: Datetime threshold.

        Returns:
            List of schedules ready for delivery.
        """
        conn = self.db.get_connection()
        cursor = conn.execute(
            """
            SELECT * FROM delivery_schedules
            WHERE is_paused = 0 AND next_delivery_at <= ?
            ORDER BY next_delivery_at ASC
            """,
            (before.isoformat(),),
        )
        return [self._row_to_schedule(row) for row in cursor.fetchall()]

    def update(self, schedule: DeliverySchedule) -> DeliverySchedule:
        """Update an existing schedule.

        Args:
            schedule: DeliverySchedule object with updated fields.

        Returns:
            Updated schedule.

        Raises:
            ValueError: If schedule has no ID.
        """
        if schedule.id is None:
            raise ValueError("Cannot update schedule without ID")
        with self.db.transaction() as conn:
            last_delivered = schedule.last_delivered_at.isoformat() if schedule.last_delivered_at else None
            next_delivery = schedule.next_delivery_at.isoformat() if schedule.next_delivery_at else None
            conn.execute(
                """
                UPDATE delivery_schedules
                SET delivery_time = ?, frequency = ?, is_paused = ?,
                    last_delivered_at = ?, next_delivery_at = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    schedule.delivery_time,
                    schedule.frequency.value,
                    1 if schedule.is_paused else 0,
                    last_delivered,
                    next_delivery,
                    schedule.id,
                ),
            )
        return schedule

    def delete(self, schedule_id: int) -> bool:
        """Delete a schedule by ID.

        Args:
            schedule_id: Database ID of the schedule to delete.

        Returns:
            True if schedule was deleted, False if not found.
        """
        with self.db.transaction() as conn:
            cursor = conn.execute("DELETE FROM delivery_schedules WHERE id = ?", (schedule_id,))
            return cursor.rowcount > 0

    def _row_to_schedule(self, row: sqlite3.Row) -> DeliverySchedule:
        """Convert a database row to a DeliverySchedule object.

        Args:
            row: Database row.

        Returns:
            DeliverySchedule object.
        """
        return DeliverySchedule(
            id=row["id"],
            user_id=row["user_id"],
            book_id=row["book_id"],
            delivery_time=row["delivery_time"],
            frequency=Frequency(row["frequency"]),
            is_paused=bool(row["is_paused"]),
            last_delivered_at=self._parse_datetime(row["last_delivered_at"]),
            next_delivery_at=self._parse_datetime(row["next_delivery_at"]),
            created_at=self._parse_datetime(row["created_at"]),
            updated_at=self._parse_datetime(row["updated_at"]),
        )

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        """Parse a datetime string from the database."""
        if value is None:
            return None
        try:
            return datetime.fromisoformat(value.replace(" ", "T"))
        except (ValueError, AttributeError):
            return None


class MigrationManager:
    """Manages database migrations."""

    def __init__(self, db_manager: DatabaseConnectionManager) -> None:
        """Initialize the migration manager.

        Args:
            db_manager: Database connection manager.
        """
        self.db = db_manager

    def ensure_migration_table(self) -> None:
        """Create the migrations tracking table if it doesn't exist."""
        conn = self.db.get_connection()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()

    def is_applied(self, migration_name: str) -> bool:
        """Check if a migration has been applied.

        Args:
            migration_name: Name of the migration.

        Returns:
            True if migration has been applied.
        """
        conn = self.db.get_connection()
        cursor = conn.execute(
            "SELECT 1 FROM migrations WHERE name = ?", (migration_name,)
        )
        return cursor.fetchone() is not None

    def mark_applied(self, migration_name: str) -> None:
        """Mark a migration as applied.

        Args:
            migration_name: Name of the migration.
        """
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO migrations (name) VALUES (?)",
                (migration_name,),
            )

    def run_migration(self, migration_name: str, sql: str) -> bool:
        """Run a migration if not already applied.

        Args:
            migration_name: Unique name for the migration.
            sql: SQL to execute.

        Returns:
            True if migration was run, False if already applied.
        """
        self.ensure_migration_table()
        if self.is_applied(migration_name):
            return False
        with self.db.transaction() as conn:
            conn.executescript(sql)
        self.mark_applied(migration_name)
        return True

    def list_applied(self) -> list[str]:
        """List all applied migrations.

        Returns:
            List of migration names.
        """
        self.ensure_migration_table()
        conn = self.db.get_connection()
        cursor = conn.execute("SELECT name FROM migrations ORDER BY applied_at ASC")
        return [row["name"] for row in cursor.fetchall()]
