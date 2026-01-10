"""SQLite database initialization and schema management."""

import sqlite3
from pathlib import Path


def get_database_path(db_name: str = "booktok.db") -> Path:
    """Get the path to the database file."""
    return Path(db_name)


def initialize_database(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Initialize the SQLite database with required tables.

    Args:
        db_path: Path to the database file. If None, uses default 'booktok.db'.

    Returns:
        Connection to the initialized database.
    """
    if db_path is None:
        db_path = get_database_path()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    create_tables(conn)

    return conn


def create_tables(conn: sqlite3.Connection) -> None:
    """Create all required database tables if they don't exist."""
    cursor = conn.cursor()

    cursor.execute("""
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
    """)

    cursor.execute("""
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
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS snippets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            position INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
            UNIQUE(book_id, position)
        )
    """)

    cursor.execute("""
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
    """)

    cursor.execute("""
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
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_snippets_book_id ON snippets(book_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_progress_user_id ON user_progress(user_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_delivery_schedules_next ON delivery_schedules(next_delivery_at)
    """)

    conn.commit()


def close_database(conn: sqlite3.Connection) -> None:
    """Close the database connection."""
    conn.close()


if __name__ == "__main__":
    db_conn = initialize_database()
    print("Database initialized successfully!")
    close_database(db_conn)
