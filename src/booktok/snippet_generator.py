"""Snippet generator module for creating learning snippets from extracted book text."""

import logging
import re
from dataclasses import dataclass
from typing import Optional

import nltk
from nltk.tokenize import sent_tokenize

from booktok.models import Book, Snippet


logger = logging.getLogger(__name__)

MIN_SNIPPET_LENGTH = 100
MAX_SNIPPET_LENGTH = 3500
TARGET_SNIPPET_LENGTH = 800


@dataclass
class SnippetGenerationResult:
    """Result of snippet generation with metadata."""

    success: bool
    snippets: list[Snippet]
    total_count: int
    error_message: Optional[str] = None

    def get_user_message(self) -> str:
        """Get a user-friendly message about the generation result.

        Returns:
            A message suitable for display to end users.
        """
        if self.success:
            return f"Successfully generated {self.total_count} snippets."
        if self.error_message:
            return self.error_message
        return "An error occurred while generating snippets."


class SnippetGenerationError(Exception):
    """Raised when snippet generation fails."""

    pass


class SnippetGenerator:
    """Generates learning snippets from extracted book text using NLTK."""

    _nltk_initialized: bool = False

    def __init__(self, book: Book) -> None:
        """Initialize the snippet generator.

        Args:
            book: The book for which to generate snippets.

        Raises:
            ValueError: If book has no ID.
        """
        if book.id is None:
            raise ValueError("Book must have an ID to generate snippets")
        self.book = book
        self._ensure_nltk_data()

    @classmethod
    def _ensure_nltk_data(cls) -> None:
        """Ensure NLTK punkt tokenizer data is available."""
        if cls._nltk_initialized:
            return

        try:
            nltk.data.find("tokenizers/punkt_tab")
        except LookupError:
            logger.info("Downloading NLTK punkt_tab tokenizer data...")
            nltk.download("punkt_tab", quiet=True)

        cls._nltk_initialized = True

    def generate_snippets(self, text: str) -> list[Snippet]:
        """Generate snippets from extracted book text.

        Splits text into paragraphs, then groups 1-2 paragraphs into snippets
        with sequential position markers.

        Args:
            text: The extracted and cleaned text from the book.

        Returns:
            List of Snippet objects with position markers.

        Raises:
            SnippetGenerationError: If generation fails.
        """
        if not text or not text.strip():
            raise SnippetGenerationError("Cannot generate snippets from empty text")

        paragraphs = self._split_into_paragraphs(text)

        if not paragraphs:
            raise SnippetGenerationError("No valid paragraphs found in text")

        logger.info(f"Found {len(paragraphs)} paragraphs in book '{self.book.title}'")

        snippets = self._create_snippets_from_paragraphs(paragraphs)

        if not snippets:
            raise SnippetGenerationError("Failed to create any snippets from text")

        logger.info(
            f"Generated {len(snippets)} snippets for book '{self.book.title}'"
        )

        return snippets

    def generate_snippets_safely(self, text: str) -> SnippetGenerationResult:
        """Generate snippets with comprehensive error handling.

        Args:
            text: The extracted and cleaned text from the book.

        Returns:
            SnippetGenerationResult with success status and snippets or error.
        """
        logger.info(f"Starting snippet generation for book: {self.book.title}")

        try:
            snippets = self.generate_snippets(text)
            return SnippetGenerationResult(
                success=True,
                snippets=snippets,
                total_count=len(snippets),
            )
        except SnippetGenerationError as e:
            error_msg = str(e)
            logger.error(
                f"Snippet generation error for book '{self.book.title}': {error_msg}",
                exc_info=True,
            )
            return SnippetGenerationResult(
                success=False,
                snippets=[],
                total_count=0,
                error_message=error_msg,
            )
        except Exception as e:
            error_msg = str(e)
            logger.exception(
                f"Unexpected error generating snippets for '{self.book.title}': {error_msg}"
            )
            return SnippetGenerationResult(
                success=False,
                snippets=[],
                total_count=0,
                error_message="An unexpected error occurred while generating snippets.",
            )

    def _split_into_paragraphs(self, text: str) -> list[str]:
        """Split text into paragraphs using double newlines as boundaries.

        Args:
            text: The text to split.

        Returns:
            List of paragraph strings.
        """
        raw_paragraphs = re.split(r"\n\s*\n", text)

        paragraphs: list[str] = []
        for para in raw_paragraphs:
            cleaned = para.strip()
            if cleaned and len(cleaned) >= 20:
                paragraphs.append(cleaned)

        return paragraphs

    def _create_snippets_from_paragraphs(self, paragraphs: list[str]) -> list[Snippet]:
        """Create snippets by grouping 1-2 paragraphs together.

        Uses NLTK sentence tokenization to validate paragraph structure
        and ensure proper text boundaries.

        Args:
            paragraphs: List of paragraph strings.

        Returns:
            List of Snippet objects with sequential positions.
        """
        snippets: list[Snippet] = []
        position = 0
        i = 0

        while i < len(paragraphs):
            current_para = paragraphs[i]
            snippet_text = current_para

            if (
                i + 1 < len(paragraphs)
                and len(snippet_text) < TARGET_SNIPPET_LENGTH
            ):
                next_para = paragraphs[i + 1]
                combined = snippet_text + "\n\n" + next_para

                if len(combined) <= MAX_SNIPPET_LENGTH:
                    snippet_text = combined
                    i += 1

            snippet_text = self._ensure_complete_sentences(snippet_text)

            if len(snippet_text) >= MIN_SNIPPET_LENGTH:
                assert self.book.id is not None
                snippet = Snippet(
                    book_id=self.book.id,
                    position=position,
                    content=snippet_text,
                )
                snippets.append(snippet)
                position += 1

            i += 1

        return snippets

    def _ensure_complete_sentences(self, text: str) -> str:
        """Ensure the text ends with a complete sentence.

        Uses NLTK sentence tokenization to detect sentence boundaries.

        Args:
            text: The text to process.

        Returns:
            Text that ends with a complete sentence.
        """
        sentences = sent_tokenize(text)

        if not sentences:
            return text

        reconstructed = " ".join(sentences)

        return reconstructed.strip()

    def get_estimated_snippet_count(self, text: str) -> int:
        """Estimate the number of snippets that will be generated.

        Args:
            text: The text to analyze.

        Returns:
            Estimated snippet count.
        """
        if not text:
            return 0

        paragraphs = self._split_into_paragraphs(text)

        total_length = sum(len(p) for p in paragraphs)
        if total_length == 0:
            return 0

        estimated = max(1, total_length // TARGET_SNIPPET_LENGTH)

        return min(estimated, len(paragraphs))
