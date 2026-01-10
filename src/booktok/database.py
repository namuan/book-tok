"""SQLite database initialization and schema management."""

import logging
import sqlite3
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Base exception for database errors."""


class DatabaseConnectionError(DatabaseError):
    """Raised when database connection fails."""


class DatabaseIntegrityError(DatabaseError):
    """Raised when data integrity check fails."""


class DatabaseCorruptedError(DatabaseError):
    """Raised when database corruption is detected."""


def get_database_path(db_name: str = "booktok.db") -> Path:
    """Get the path to the database file."""
    return Path(db_name)


def initialize_database(
    db_path: str | Path | None = None, max_retries: int = 3
) -> sqlite3.Connection:
    """Initialize the SQLite database with required tables.

    Args:
        db_path: Path to the database file. If None, uses default 'booktok.db'.
        max_retries: Maximum number of connection retries.

    Returns:
        Connection to the initialized database.

    Raises:
        DatabaseConnectionError: If connection fails after max retries.
    """
    if db_path is None:
        db_path = get_database_path()

    last_error: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            conn = sqlite3.connect(db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")

            create_tables(conn)

            logger.info(f"Database initialized successfully at {db_path}")
            return conn
        except sqlite3.OperationalError as e:
            last_error = e
            logger.warning(
                f"Database connection attempt {attempt}/{max_retries} failed: {e}"
            )
            if attempt < max_retries:
                import time

                time.sleep(1.0)

    raise DatabaseConnectionError(
        f"Failed to connect to database after {max_retries} attempts: {last_error}"
    )


def create_tables(conn: sqlite3.Connection, verify_only: bool = False) -> None:
    """Create all required database tables if they don't exist.

    Args:
        conn: Database connection.
        verify_only: If True, only verify tables exist without creating.
    """
    cursor = conn.cursor()

    tables = [
        (
            "users",
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                timezone TEXT DEFAULT 'UTC',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """,
        ),
        (
            "books",
            """
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT,
                file_path TEXT NOT NULL,
                file_type TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                total_snippets INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """,
        ),
        (
            "snippets",
            """
            CREATE TABLE IF NOT EXISTS snippets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
                UNIQUE(book_id, position)
            )
        """,
        ),
        (
            "user_progress",
            """
            CREATE TABLE IF NOT EXISTS user_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                book_id INTEGER NOT NULL,
                current_position INTEGER DEFAULT 0,
                is_completed INTEGER DEFAULT 0,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
                UNIQUE(user_id, book_id)
            )
        """,
        ),
        (
            "delivery_schedules",
            """
            CREATE TABLE IF NOT EXISTS delivery_schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                book_id INTEGER NOT NULL,
                delivery_time TEXT NOT NULL,
                frequency TEXT DEFAULT 'daily',
                is_paused INTEGER DEFAULT 0,
                last_delivered_at TIMESTAMP,
                next_delivery_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
                UNIQUE(user_id, book_id)
            )
        """,
        ),
    ]

    for table_name, create_sql in tables:
        if verify_only:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            )
            if cursor.fetchone() is None:
                raise DatabaseIntegrityError(f"Table {table_name} is missing")
        else:
            cursor.execute(create_sql)

    indexes = [
        (
            "idx_users_telegram_id",
            "CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)",
        ),
        (
            "idx_snippets_book_id",
            "CREATE INDEX IF NOT EXISTS idx_snippets_book_id ON snippets(book_id)",
        ),
        (
            "idx_user_progress_user_id",
            "CREATE INDEX IF NOT EXISTS idx_user_progress_user_id ON user_progress(user_id)",
        ),
        (
            "idx_delivery_schedules_next",
            "CREATE INDEX IF NOT EXISTS idx_delivery_schedules_next ON delivery_schedules(next_delivery_at)",
        ),
    ]

    for index_name, create_sql in indexes:
        if verify_only:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
                (index_name,),
            )
            if cursor.fetchone() is None:
                logger.warning(f"Index {index_name} is missing, creating...")
        cursor.execute(create_sql)

    conn.commit()


def check_database_integrity(conn: sqlite3.Connection) -> bool:
    """Run database integrity checks.

    Args:
        conn: Database connection.

    Returns:
        True if database integrity is valid.
    """
    try:
        cursor = conn.cursor()

        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        if result and result[0] != "ok":
            logger.error(f"Database integrity check failed: {result[0]}")
            return False

        for table in [
            "users",
            "books",
            "snippets",
            "user_progress",
            "delivery_schedules",
        ]:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            cursor.fetchone()[0]

            cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE id IS NULL")
            null_ids = cursor.fetchone()[0]
            if null_ids > 0:
                logger.error(f"Table {table} has records with NULL id")
                return False

        foreign_keys_valid = True
        cursor.execute("PRAGMA foreign_key_check")
        fk_violations = cursor.fetchall()
        if fk_violations:
            for violation in fk_violations:
                logger.error(f"Foreign key violation: {violation}")
            foreign_keys_valid = False

        return foreign_keys_valid
    except sqlite3.Error as e:
        logger.error(f"Database integrity check error: {e}", exc_info=True)
        return False


def recover_database(db_path: Path) -> bool:
    """Attempt to recover a corrupted database.

    Args:
        db_path: Path to the database file.

    Returns:
        True if recovery was successful.
    """
    logger.warning(f"Attempting database recovery for {db_path}")

    import shutil

    backup_path = db_path.with_suffix(db_path.suffix + ".bak")
    try:
        shutil.copy(db_path, backup_path)
        logger.info(f"Backup created at {backup_path}")

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA wal_checkpoint(FULL)")
        logger.info("WAL checkpoint completed")

        cursor.execute("VACUUM")
        logger.info("Database vacuum completed")

        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        if result and result[0] == "ok":
            logger.info("Database recovery successful")
            conn.close()
            return True
        else:
            logger.error(f"Database still corrupted after recovery: {result[0]}")
            conn.close()
            return False
    except Exception as e:
        logger.error(f"Database recovery failed: {e}", exc_info=True)
        return False


def close_database(conn: sqlite3.Connection) -> None:
    """Close the database connection."""
    try:
        conn.close()
        logger.info("Database connection closed")
    except Exception as e:
        logger.error(f"Error closing database connection: {e}")


if __name__ == "__main__":
    db_conn = initialize_database()
    print("Database initialized successfully!")
    close_database(db_conn)
