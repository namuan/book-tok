"""Book processing module for extracting text from PDF and EPUB files."""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub
from PyPDF2 import PdfReader
from PyPDF2.errors import PdfReadError

from booktok.models import Book, BookStatus, FileType


logger = logging.getLogger(__name__)

# File size limits
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB
MIN_FILE_SIZE_BYTES = 100  # 100 bytes (smaller files are likely invalid)

# PDF magic bytes
PDF_MAGIC_BYTES = b"%PDF"

# EPUB is a ZIP file with specific structure
ZIP_MAGIC_BYTES = b"PK\x03\x04"


@dataclass
class ProcessingResult:
    """Result of book processing with user-friendly error information."""

    success: bool
    text: Optional[str] = None
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    details: Optional[str] = None

    def get_user_message(self) -> str:
        """Get a user-friendly error message.

        Returns:
            A message suitable for display to end users.
        """
        if self.success:
            return "Book processed successfully."
        if self.error_message:
            return self.error_message
        return "An error occurred while processing the book."


class BookProcessingError(Exception):
    """Raised when book processing fails."""


class InvalidFileError(BookProcessingError):
    """Raised when the file is invalid or corrupted."""


class UnsupportedFileTypeError(BookProcessingError):
    """Raised when the file type is not supported."""


class BookProcessor:
    """Processes book files and extracts text content."""

    def __init__(self, book: Book) -> None:
        """Initialize the book processor.

        Args:
            book: The book to process.
        """
        self.book = book
        self._extracted_text: Optional[str] = None

    def validate_file(self) -> None:
        """Validate the book file before processing.

        Raises:
            InvalidFileError: If file validation fails.
            UnsupportedFileTypeError: If file type is not supported.
        """
        file_path = Path(self.book.file_path)

        if not file_path.exists():
            logger.error(f"File not found: {self.book.file_path}")
            raise InvalidFileError(
                f"The file could not be found: {self.book.file_path}"
            )

        if not file_path.is_file():
            logger.error(f"Path is not a file: {self.book.file_path}")
            raise InvalidFileError(
                f"The path is not a valid file: {self.book.file_path}"
            )

        try:
            file_size = file_path.stat().st_size
        except OSError as e:
            logger.error(f"Failed to get file stats for {self.book.file_path}: {e}")
            raise InvalidFileError(f"Cannot access file: {e}") from e

        if file_size < MIN_FILE_SIZE_BYTES:
            logger.error(f"File too small: {self.book.file_path} ({file_size} bytes)")
            raise InvalidFileError(
                f"File is too small ({file_size} bytes). "
                "The file may be empty or corrupted."
            )

        if file_size > MAX_FILE_SIZE_BYTES:
            logger.error(f"File too large: {self.book.file_path} ({file_size} bytes)")
            raise InvalidFileError(
                f"File is too large ({file_size // (1024 * 1024)} MB). "
                f"Maximum allowed size is {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB."
            )

        self._validate_file_magic_bytes(file_path)

    def _validate_file_magic_bytes(self, file_path: Path) -> None:
        """Validate file type by checking magic bytes.

        Args:
            file_path: Path to the file.

        Raises:
            InvalidFileError: If file cannot be read or magic bytes don't match.
            UnsupportedFileTypeError: If file type doesn't match expected type.
        """
        try:
            with open(file_path, "rb") as f:
                header = f.read(16)
        except OSError as e:
            logger.error(f"Failed to read file header for {file_path}: {e}")
            raise InvalidFileError(f"Cannot read file: {e}") from e

        if len(header) < 4:
            logger.error(f"File too small to contain valid header: {file_path}")
            raise InvalidFileError("File is too small to be a valid book file.")

        if self.book.file_type == FileType.PDF:
            if not header.startswith(PDF_MAGIC_BYTES):
                logger.error(f"Invalid PDF magic bytes in {file_path}: {header[:4]!r}")
                raise InvalidFileError(
                    "The file does not appear to be a valid PDF. "
                    "Please ensure you have uploaded a proper PDF file."
                )
        elif self.book.file_type == FileType.EPUB:
            if not header.startswith(ZIP_MAGIC_BYTES):
                logger.error(
                    f"Invalid EPUB (ZIP) magic bytes in {file_path}: {header[:4]!r}"
                )
                raise InvalidFileError(
                    "The file does not appear to be a valid EPUB. "
                    "EPUB files must be valid ZIP archives."
                )
        else:
            raise UnsupportedFileTypeError(
                f"Unsupported file type: {self.book.file_type.value}"
            )

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

        self.validate_file()

        file_path = Path(self.book.file_path)

        if self.book.file_type == FileType.PDF:
            self._extracted_text = self._extract_pdf_text(file_path)
        elif self.book.file_type == FileType.EPUB:
            self._extracted_text = self._extract_epub_text(file_path)
        else:
            raise UnsupportedFileTypeError(
                f"Unsupported file type: {self.book.file_type}"
            )

        return self._extracted_text

    def process_book_safely(self) -> ProcessingResult:
        """Process the book with comprehensive error handling.

        This method catches all exceptions and returns a ProcessingResult
        with user-friendly error messages. It also marks the book status
        as FAILED if processing fails.

        Returns:
            ProcessingResult with success status and text or error details.
        """
        logger.info(
            f"Starting processing for book: {self.book.title} (ID: {self.book.id})"
        )
        self.book.status = BookStatus.PROCESSING

        try:
            text = self.extract_text()
            self.book.status = BookStatus.COMPLETED
            logger.info(
                f"Successfully processed book: {self.book.title} "
                f"(extracted {len(text)} characters)"
            )
            return ProcessingResult(success=True, text=text)

        except InvalidFileError as e:
            error_msg = str(e)
            logger.error(
                f"Invalid file error for book '{self.book.title}': {error_msg}",
                exc_info=True,
            )
            self._mark_as_failed()
            return ProcessingResult(
                success=False,
                error_message=error_msg,
                error_type="invalid_file",
                details=f"Book ID: {self.book.id}, File: {self.book.file_path}",
            )

        except UnsupportedFileTypeError as e:
            error_msg = str(e)
            logger.error(
                f"Unsupported file type for book '{self.book.title}': {error_msg}",
                exc_info=True,
            )
            self._mark_as_failed()
            return ProcessingResult(
                success=False,
                error_message="The file type is not supported. Please upload a PDF or EPUB file.",
                error_type="unsupported_file_type",
                details=error_msg,
            )

        except BookProcessingError as e:
            error_msg = str(e)
            logger.error(
                f"Processing error for book '{self.book.title}': {error_msg}",
                exc_info=True,
            )
            self._mark_as_failed()
            return ProcessingResult(
                success=False,
                error_message="An error occurred while processing the book. Please try again or upload a different file.",
                error_type="processing_error",
                details=error_msg,
            )

        except Exception as e:
            error_msg = str(e)
            logger.exception(
                f"Unexpected error processing book '{self.book.title}': {error_msg}"
            )
            self._mark_as_failed()
            return ProcessingResult(
                success=False,
                error_message="An unexpected error occurred. Please try again later.",
                error_type="unexpected_error",
                details=error_msg,
            )

    def _mark_as_failed(self) -> None:
        """Mark the book status as FAILED."""
        self.book.status = BookStatus.FAILED
        logger.warning(
            f"Marked book '{self.book.title}' (ID: {self.book.id}) as FAILED"
        )

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
            raise BookProcessingError(f"Failed to open PDF file: {e}") from e

        if len(reader.pages) == 0:
            raise InvalidFileError("PDF file has no pages")

        text_parts: list[str] = []

        for page_num, page in enumerate(reader.pages):
            try:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            except Exception as e:
                logger.warning(f"Failed to extract text from page {page_num + 1}: {e}")
                continue

        if not text_parts:
            raise InvalidFileError(
                "Could not extract any text from PDF (may be image-based)"
            )

        raw_text = "\n\n".join(text_parts)
        return self._clean_and_normalize_text(raw_text)

    def _extract_epub_text(self, file_path: Path) -> str:
        """Extract text from an EPUB file.

        Args:
            file_path: Path to the EPUB file.

        Returns:
            The extracted and cleaned text content.

        Raises:
            InvalidFileError: If the EPUB is invalid or corrupted.
            BookProcessingError: If extraction fails.
        """
        try:
            book = epub.read_epub(str(file_path), options={"ignore_ncx": True})
        except ebooklib.epub.EpubException as e:
            logger.error(f"Failed to read EPUB {file_path}: {e}")
            raise InvalidFileError(f"Invalid or corrupted EPUB file: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error reading EPUB {file_path}: {e}")
            raise BookProcessingError(f"Failed to open EPUB file: {e}") from e

        text_parts: list[str] = []

        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            try:
                content = item.get_content()
                soup = BeautifulSoup(content, "html.parser")

                for script in soup(["script", "style"]):
                    script.decompose()

                text = soup.get_text(separator="\n")
                if text.strip():
                    text_parts.append(text)
            except Exception as e:
                logger.warning(f"Failed to extract text from EPUB item: {e}")
                continue

        if not text_parts:
            raise InvalidFileError("Could not extract any text from EPUB")

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
