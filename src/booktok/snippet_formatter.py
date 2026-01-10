"""Snippet formatter for Telegram message delivery."""

import logging
from dataclasses import dataclass
from typing import Optional

from booktok.models import Book, Snippet, UserProgress


logger = logging.getLogger(__name__)

TELEGRAM_MAX_MESSAGE_LENGTH = 4096
HEADER_RESERVE = 200
SAFE_CONTENT_LENGTH = TELEGRAM_MAX_MESSAGE_LENGTH - HEADER_RESERVE


@dataclass
class FormattedMessage:
    """A formatted message ready for Telegram delivery."""

    text: str
    is_continuation: bool = False

    def validate(self) -> bool:
        """Check if the message is within Telegram limits.

        Returns:
            True if valid, False otherwise.
        """
        return len(self.text) <= TELEGRAM_MAX_MESSAGE_LENGTH


@dataclass
class FormattedSnippet:
    """Result of formatting a snippet for Telegram delivery."""

    messages: list[FormattedMessage]
    book_title: str
    author: Optional[str]
    current_position: int
    total_snippets: int

    def get_progress_string(self) -> str:
        """Get a human-readable progress string.

        Returns:
            Progress indicator like '5/100 snippets'.
        """
        return f"{self.current_position}/{self.total_snippets} snippets"


class SnippetFormatter:
    """Formats snippets for Telegram message delivery."""

    def __init__(
        self,
        book: Book,
        total_snippets: Optional[int] = None,
    ) -> None:
        """Initialize the formatter.

        Args:
            book: The book the snippets are from.
            total_snippets: Total snippet count (defaults to book.total_snippets).
        """
        self.book = book
        self.total_snippets = total_snippets if total_snippets is not None else book.total_snippets

    def format_snippet(
        self,
        snippet: Snippet,
        progress: Optional[UserProgress] = None,
    ) -> FormattedSnippet:
        """Format a snippet for Telegram delivery with metadata.

        Args:
            snippet: The snippet to format.
            progress: Optional user progress for position info.

        Returns:
            FormattedSnippet with properly formatted message(s).
        """
        current_position = snippet.position + 1
        if progress is not None:
            current_position = progress.current_position + 1

        header = self._build_header(current_position)
        content = self._format_content(snippet.content)

        full_message = f"{header}\n\n{content}"

        if len(full_message) <= TELEGRAM_MAX_MESSAGE_LENGTH:
            messages = [FormattedMessage(text=full_message)]
        else:
            messages = self._split_into_messages(header, content)

        return FormattedSnippet(
            messages=messages,
            book_title=self.book.title,
            author=self.book.author,
            current_position=current_position,
            total_snippets=self.total_snippets,
        )

    def _build_header(self, current_position: int) -> str:
        """Build the message header with book info and progress.

        Args:
            current_position: Current snippet position (1-indexed).

        Returns:
            Formatted header string.
        """
        parts: list[str] = []

        parts.append(f"📚 *{self._escape_markdown(self.book.title)}*")

        if self.book.author:
            parts.append(f"✍️ {self._escape_markdown(self.book.author)}")

        progress = f"📖 {current_position}/{self.total_snippets} snippets"
        parts.append(progress)

        return "\n".join(parts)

    def _format_content(self, content: str) -> str:
        """Format snippet content with proper paragraph breaks.

        Args:
            content: Raw snippet content.

        Returns:
            Formatted content with proper spacing.
        """
        paragraphs = content.split("\n\n")
        formatted_paragraphs: list[str] = []

        for para in paragraphs:
            cleaned = " ".join(para.split())
            if cleaned:
                formatted_paragraphs.append(cleaned)

        return "\n\n".join(formatted_paragraphs)

    def _split_into_messages(
        self,
        header: str,
        content: str,
    ) -> list[FormattedMessage]:
        """Split long content into multiple Telegram messages.

        Args:
            header: The message header (only on first message).
            content: The content to split.

        Returns:
            List of FormattedMessage objects.
        """
        messages: list[FormattedMessage] = []

        first_content_length = TELEGRAM_MAX_MESSAGE_LENGTH - len(header) - 10
        continuation_length = TELEGRAM_MAX_MESSAGE_LENGTH - 20

        chunks = self._split_content_by_length(content, first_content_length, continuation_length)

        for i, chunk in enumerate(chunks):
            if i == 0:
                text = f"{header}\n\n{chunk}"
                messages.append(FormattedMessage(text=text, is_continuation=False))
            else:
                cont_marker = f"📖 _(continued {i + 1}/{len(chunks)})_\n\n"
                text = f"{cont_marker}{chunk}"
                messages.append(FormattedMessage(text=text, is_continuation=True))

        return messages

    def _split_content_by_length(
        self,
        content: str,
        first_length: int,
        subsequent_length: int,
    ) -> list[str]:
        """Split content into chunks respecting paragraph boundaries.

        Args:
            content: The content to split.
            first_length: Max length for first chunk.
            subsequent_length: Max length for subsequent chunks.

        Returns:
            List of content chunks.
        """
        if len(content) <= first_length:
            return [content]

        chunks: list[str] = []
        remaining = content
        max_length = first_length

        while remaining:
            if len(remaining) <= max_length:
                chunks.append(remaining)
                break

            split_point = self._find_split_point(remaining, max_length)
            chunks.append(remaining[:split_point].rstrip())
            remaining = remaining[split_point:].lstrip()

            max_length = subsequent_length

        return chunks

    def _find_split_point(self, text: str, max_length: int) -> int:
        """Find the best point to split text (at paragraph or sentence boundary).

        Args:
            text: Text to analyze.
            max_length: Maximum length for the chunk.

        Returns:
            Index at which to split.
        """
        para_break = text.rfind("\n\n", 0, max_length)
        if para_break > max_length // 2:
            return para_break + 2

        sentence_ends = [". ", "! ", "? "]
        best_sentence = -1
        for end in sentence_ends:
            pos = text.rfind(end, 0, max_length)
            if pos > best_sentence:
                best_sentence = pos

        if best_sentence > max_length // 2:
            return best_sentence + 2

        space = text.rfind(" ", 0, max_length)
        if space > 0:
            return space + 1

        return max_length

    def _escape_markdown(self, text: str) -> str:
        """Escape special Markdown characters for Telegram.

        Args:
            text: Text to escape.

        Returns:
            Escaped text safe for Telegram Markdown.
        """
        special_chars = ["_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"]
        result = text
        for char in special_chars:
            result = result.replace(char, f"\\{char}")
        return result


def validate_message_length(message: str) -> bool:
    """Check if a message is within Telegram's character limit.

    Args:
        message: The message text to validate.

    Returns:
        True if within limit, False otherwise.
    """
    return len(message) <= TELEGRAM_MAX_MESSAGE_LENGTH


def get_safe_content_length() -> int:
    """Get the safe content length accounting for header space.

    Returns:
        Maximum safe content length.
    """
    return SAFE_CONTENT_LENGTH
