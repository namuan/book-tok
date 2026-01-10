"""Book scanner module for discovering books in a directory."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from booktok.models import FileType


logger = logging.getLogger(__name__)


@dataclass
class BookFile:
    """Represents a book file found in the books directory."""

    path: Path
    filename: str
    file_type: FileType
    size_bytes: int

    @property
    def display_name(self) -> str:
        """Get a user-friendly display name for the book.

        Returns:
            Book filename without extension.
        """
        return self.path.stem


class BookScanner:
    """Scanner for discovering book files in a directory."""

    # Supported file extensions mapped to FileType
    SUPPORTED_EXTENSIONS = {
        ".pdf": FileType.PDF,
        ".epub": FileType.EPUB,
    }

    def __init__(self, books_directory: str) -> None:
        """Initialize the book scanner.

        Args:
            books_directory: Path to the directory containing book files.
        """
        self.books_directory = Path(books_directory).expanduser()

    def scan(self) -> List[BookFile]:
        """Scan the books directory for supported book files.

        Returns:
            List of BookFile objects found in the directory, sorted by filename.
        """
        if not self.books_directory.exists():
            logger.warning(f"Books directory does not exist: {self.books_directory}")
            return []

        if not self.books_directory.is_dir():
            logger.error(f"Books path is not a directory: {self.books_directory}")
            return []

        book_files: List[BookFile] = []

        for file_path in self.books_directory.iterdir():
            if not file_path.is_file():
                continue

            extension = file_path.suffix.lower()
            if extension not in self.SUPPORTED_EXTENSIONS:
                continue

            try:
                size = file_path.stat().st_size
                book_file = BookFile(
                    path=file_path,
                    filename=file_path.name,
                    file_type=self.SUPPORTED_EXTENSIONS[extension],
                    size_bytes=size,
                )
                book_files.append(book_file)
                logger.debug(f"Found book: {file_path.name}")
            except OSError as e:
                logger.warning(f"Failed to read file {file_path}: {e}")
                continue

        book_files.sort(key=lambda x: x.filename.lower())
        logger.info(f"Found {len(book_files)} book(s) in {self.books_directory}")

        return book_files

    def get_book_by_name(self, filename: str) -> Optional[BookFile]:
        """Get a specific book file by filename.

        Args:
            filename: Name of the book file to retrieve.

        Returns:
            BookFile if found, None otherwise.
        """
        books = self.scan()
        for book in books:
            if book.filename == filename:
                return book
        return None

    def format_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format.

        Args:
            size_bytes: Size in bytes.

        Returns:
            Human-readable size string (e.g., "1.5 MB").
        """
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
