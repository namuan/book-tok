"""Book processing module for extracting text from PDF and EPUB files."""

import logging
import re
from pathlib import Path
from typing import Optional

from PyPDF2 import PdfReader
from PyPDF2.errors import PdfReadError

from booktok.models import Book, BookStatus, FileType


logger = logging.getLogger(__name__)


class BookProcessingError(Exception):
    """Raised when book processing fails."""

    pass


class InvalidFileError(BookProcessingError):
    """Raised when the file is invalid or corrupted."""

    pass


class UnsupportedFileTypeError(BookProcessingError):
    """Raised when the file type is not supported."""

    pass


class BookProcessor:
    """Processes book files and extracts text content."""

    def __init__(self, book: Book) -> None:
        """Initialize the book processor.

        Args:
            book: The book to process.
        """
        self.book = book
        self._extracted_text: Optional[str] = None

    def extract_text(self) -> str:
        """Extract text from the book file.

        Returns:
            The extracted and cleaned text content.

        Raises:
            InvalidFileError: If the file is invalid or corrupted.
            UnsupportedFileTypeError: If the file type is not supported.
            BookProcessingError: If processing fails for other reasons.
        """
        if self._extracted_text is not None:
            return self._extracted_text

        file_path = Path(self.book.file_path)

        if not file_path.exists():
            raise InvalidFileError(f"File not found: {self.book.file_path}")

        if self.book.file_type == FileType.PDF:
            self._extracted_text = self._extract_pdf_text(file_path)
        elif self.book.file_type == FileType.EPUB:
            raise UnsupportedFileTypeError("EPUB extraction not yet implemented")
        else:
            raise UnsupportedFileTypeError(
                f"Unsupported file type: {self.book.file_type}"
            )

        return self._extracted_text

    def _extract_pdf_text(self, file_path: Path) -> str:
        """Extract text from a PDF file.

        Args:
            file_path: Path to the PDF file.

        Returns:
            The extracted and cleaned text content.

        Raises:
            InvalidFileError: If the PDF is invalid or corrupted.
            BookProcessingError: If extraction fails.
        """
        try:
            reader = PdfReader(str(file_path))
        except PdfReadError as e:
            logger.error(f"Failed to read PDF {file_path}: {e}")
            raise InvalidFileError(f"Invalid or corrupted PDF file: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error reading PDF {file_path}: {e}")
            raise BookProcessingError(
                f"Failed to open PDF file: {e}"
            ) from e

        if len(reader.pages) == 0:
            raise InvalidFileError("PDF file has no pages")

        text_parts: list[str] = []

        for page_num, page in enumerate(reader.pages):
            try:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            except Exception as e:
                logger.warning(
                    f"Failed to extract text from page {page_num + 1}: {e}"
                )
                continue

        if not text_parts:
            raise InvalidFileError(
                "Could not extract any text from PDF (may be image-based)"
            )

        raw_text = "\n\n".join(text_parts)
        return self._clean_and_normalize_text(raw_text)

    def _clean_and_normalize_text(self, text: str) -> str:
        """Clean and normalize extracted text.

        Args:
            text: The raw extracted text.

        Returns:
            Cleaned and normalized text.
        """
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        text = re.sub(r"[ \t]+", " ", text)

        text = re.sub(r"\n{3,}", "\n\n", text)

        text = re.sub(r" +\n", "\n", text)
        text = re.sub(r"\n +", "\n", text)

        text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)

        lines = text.split("\n")
        cleaned_lines: list[str] = []
        for line in lines:
            line = line.strip()
            if line:
                cleaned_lines.append(line)
            elif cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")

        text = "\n".join(cleaned_lines)

        text = text.strip()

        return text

    def get_book_status(self) -> BookStatus:
        """Get the current processing status of the book.

        Returns:
            The book's processing status.
        """
        return self.book.status

    def update_book_status(self, status: BookStatus) -> None:
        """Update the book's processing status.

        Args:
            status: The new status.
        """
        self.book.status = status
