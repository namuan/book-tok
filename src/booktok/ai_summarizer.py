"""AI Summarizer module for processing book snippets."""

import logging
from typing import Optional

# httpx is a dependency of python-telegram-bot
import httpx

from booktok.config import OpenRouterConfig

logger = logging.getLogger(__name__)


class AISummarizer:
    """Handles interaction with OpenRouter AI for text summarization."""

    def __init__(self, config: OpenRouterConfig) -> None:
        """Initialize the AI summarizer.

        Args:
            config: OpenRouter configuration.
        """
        self.config = config

    async def summarize_snippets(
        self,
        current_snippets: list[str],
        previous_snippet: Optional[str] = None,
    ) -> str:
        """Summarize a list of snippets using AI.

        Args:
            current_snippets: List of text snippets to summarize (the new content).
            previous_snippet: Optional previous snippet for context.

        Returns:
            The AI-generated summary.

        Raises:
            ValueError: If API key is not configured.
            RuntimeError: If the API call fails.
        """
        if not self.config.api_key:
            raise ValueError("OpenRouter API key not configured")

        if not current_snippets:
            return "No content to summarize."

        # Construct the prompt
        prompt = self._build_prompt(current_snippets, previous_snippet)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.config.api_key}",
                        "HTTP-Referer": self.config.site_url,
                        "X-Title": self.config.app_name,
                    },
                    json={
                        "model": self.config.model,
                        "messages": [
                            {
                                "role": "user",
                                "content": prompt,
                            }
                        ],
                    },
                    timeout=60.0,
                )
                response.raise_for_status()
                data = response.json()

                if "choices" in data and len(data["choices"]) > 0:
                    return data["choices"][0]["message"]["content"]

                logger.error(f"Unexpected API response: {data}")
                return "Error: Could not generate summary (unexpected response format)."

        except httpx.HTTPError as e:
            logger.error(f"OpenRouter API error: {e}")
            return f"Error: Failed to communicate with AI service ({str(e)})."
        except Exception as e:
            logger.error(f"Unexpected error in AI summarization: {e}")
            return "Error: An unexpected error occurred during summarization."

    def _build_prompt(
        self,
        current_snippets: list[str],
        previous_snippet: Optional[str] = None,
    ) -> str:
        """Build the prompt for the AI.

        Args:
            current_snippets: List of text snippets.
            previous_snippet: Optional previous snippet context.

        Returns:
            Formatted prompt string.
        """
        prompt_parts = []

        prompt_parts.append(
            "You are a helpful reading assistant. Your task is to summarize the following text from a book."
        )
        prompt_parts.append(
            "Provide a concise and engaging summary that captures the key points."
        )
        prompt_parts.append(
            "Format your response using HTML tags for Telegram: <b>bold</b>, <i>italic</i>, <u>underline</u>, <code>code</code>."
        )
        prompt_parts.append(
            "Use <b>headings</b> for sections, and keep formatting clean and readable."
        )
        prompt_parts.append("\n=== CONTEXT (Previous Page) ===")
        if previous_snippet:
            prompt_parts.append(previous_snippet)
        else:
            prompt_parts.append("(No previous context available)")

        prompt_parts.append("\n=== CURRENT TEXT (To Summarize) ===")
        for i, snippet in enumerate(current_snippets, 1):
            prompt_parts.append(f"--- Part {i} ---")
            prompt_parts.append(snippet)

        prompt_parts.append(
            "\nPlease write a summary of the 'CURRENT TEXT', using the 'CONTEXT' to maintain continuity."
        )

        return "\n".join(prompt_parts)
