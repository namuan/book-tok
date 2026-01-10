"""Input validation and sanitization utilities for security."""

import html
import re
from typing import Optional


class ValidationError(Exception):
    """Raised when input validation fails."""

    pass


def sanitize_text(input_text: Optional[str], max_length: int = 10000) -> str:
    """Sanitize text input by escaping HTML and removing dangerous characters.

    Args:
        input_text: The text to sanitize (can be None).
        max_length: Maximum allowed length.

    Returns:
        Sanitized text string.

    Raises:
        ValidationError: If validation fails.
    """
    if input_text is None:
        return ""

    if not isinstance(input_text, str):
        raise ValidationError("Input must be a string")

    if len(input_text) > max_length:
        raise ValidationError(
            f"Input exceeds maximum length of {max_length} characters"
        )

    sanitized = html.escape(input_text)

    sanitized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", sanitized)

    return sanitized.strip()


def sanitize_filename(filename: Optional[str]) -> str:
    """Sanitize a filename to prevent path traversal attacks.

    Args:
        filename: The filename to sanitize.

    Returns:
        Sanitized filename.

    Raises:
        ValidationError: If filename is invalid.
    """
    if not filename:
        raise ValidationError("Filename cannot be empty")

    if not isinstance(filename, str):
        raise ValidationError("Filename must be a string")

    import os

    basename = os.path.basename(filename)

    if basename.startswith("."):
        raise ValidationError("Filename cannot start with a dot")

    if len(basename) > 255:
        raise ValidationError("Filename exceeds maximum length")

    dangerous_chars = r"[\\/:*?\"<>|]"
    if re.search(dangerous_chars, basename):
        raise ValidationError("Filename contains invalid characters")

    return basename


def validate_telegram_id(telegram_id: int) -> int:
    """Validate that a Telegram ID is valid.

    Args:
        telegram_id: The Telegram user ID to validate.

    Returns:
        The validated Telegram ID.

    Raises:
        ValidationError: If ID is invalid.
    """
    if not isinstance(telegram_id, int):
        raise ValidationError("Telegram ID must be an integer")

    if telegram_id <= 0:
        raise ValidationError("Telegram ID must be a positive integer")

    if telegram_id > 2**63 - 1:
        raise ValidationError("Telegram ID is too large")

    return telegram_id


def validate_book_title(title: Optional[str], max_length: int = 500) -> str:
    """Validate and sanitize a book title.

    Args:
        title: The book title to validate.
        max_length: Maximum allowed length.

    Returns:
        Sanitized title.

    Raises:
        ValidationError: If validation fails.
    """
    if title is None:
        raise ValidationError("Title cannot be None")

    if not isinstance(title, str):
        raise ValidationError("Title must be a string")

    if not title.strip():
        raise ValidationError("Title cannot be empty")

    if len(title) > max_length:
        raise ValidationError(
            f"Title exceeds maximum length of {max_length} characters"
        )

    sanitized = html.escape(title.strip())

    return sanitized


def validate_author(author: Optional[str], max_length: int = 500) -> Optional[str]:
    """Validate and sanitize an author name.

    Args:
        author: The author name to validate (can be None).
        max_length: Maximum allowed length.

    Returns:
        Sanitized author name or None.

    Raises:
        ValidationError: If validation fails.
    """
    if author is None:
        return None

    if not isinstance(author, str):
        raise ValidationError("Author must be a string")

    if len(author) > max_length:
        raise ValidationError(
            f"Author name exceeds maximum length of {max_length} characters"
        )

    sanitized = html.escape(author.strip())

    return sanitized if sanitized else None


def sanitize_for_markdown(text: Optional[str]) -> str:
    """Sanitize text for safe inclusion in Telegram Markdown.

    Args:
        text: The text to sanitize.

    Returns:
        Sanitized text safe for Markdown.
    """
    if text is None:
        return ""

    if not isinstance(text, str):
        return ""

    special_chars = [
        "_",
        "*",
        "[",
        "]",
        "(",
        ")",
        "~",
        "`",
        ">",
        "#",
        "+",
        "-",
        "=",
        "|",
        "{",
        "}",
        ".",
        "!",
    ]
    result = text
    for char in special_chars:
        result = result.replace(char, f"\\{char}")

    return result


def validate_message_text(text: Optional[str], max_length: int = 4096) -> str:
    """Validate message text for Telegram sending.

    Args:
        text: The text to validate.
        max_length: Maximum allowed length.

    Returns:
        Validated text.

    Raises:
        ValidationError: If validation fails.
    """
    if text is None:
        raise ValidationError("Message text cannot be None")

    if not isinstance(text, str):
        raise ValidationError("Message text must be a string")

    if len(text) > max_length:
        raise ValidationError(
            f"Message text exceeds maximum length of {max_length} characters"
        )

    if not text.strip():
        raise ValidationError("Message text cannot be empty")

    return text
