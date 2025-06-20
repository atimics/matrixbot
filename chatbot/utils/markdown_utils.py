"""
Utility functions for converting markdown to Matrix-compatible HTML.
"""
import re
from typing import Dict

import markdown


class MatrixMarkdownFormatter:
    """Utility class for converting markdown to Matrix-compatible HTML."""

    def __init__(self):
        self.md = markdown.Markdown(
            extensions=["fenced_code", "codehilite", "tables", "nl2br", "sane_lists"]
        )

    def convert(self, markdown_text: str) -> Dict[str, str]:
        """Convert markdown to both plain text and HTML for Matrix."""
        # Create a fresh Markdown parser for each conversion with codehilite
        md_parser = markdown.Markdown(
            extensions=["fenced_code", "codehilite", "tables", "nl2br", "sane_lists"]
        )
        html_content = md_parser.convert(markdown_text)
        # Post-process to remove span tags inserted by codehilite, preserving class wrappers
        html_content = re.sub(r"<span[^>]*>", "", html_content)
        html_content = html_content.replace("</span>", "")

        # Create plain text fallback by removing markdown syntax
        plain_text = self._markdown_to_plain(markdown_text)

        return {"plain": plain_text, "html": html_content}

    def _markdown_to_plain(self, markdown_text: str) -> str:
        """Convert markdown to plain text by removing formatting."""
        # Remove code blocks
        text = re.sub(r"```[\s\S]*?```", "[Code Block]", markdown_text)
        text = re.sub(r"`([^`]+)`", r"\1", text)

        # Remove links but keep text
        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)

        # Remove bold/italic
        text = re.sub(r"\*\*([^\*]+)\*\*", r"\1", text)
        text = re.sub(r"\*([^\*]+)\*", r"\1", text)
        text = re.sub(r"__([^_]+)__", r"\1", text)
        text = re.sub(r"_([^_]+)_", r"\1", text)

        # Remove headers
        text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)

        # Remove list markers
        text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)

        # Remove block quotes
        text = re.sub(r"^\s*>\s*", "", text, flags=re.MULTILINE)

        # Clean up extra whitespace
        text = re.sub(r"\n\s*\n", "\n\n", text)

        return text.strip()


# Global formatter instance
_formatter = MatrixMarkdownFormatter()


def format_for_matrix(content: str) -> Dict[str, str]:
    """Convert markdown content for Matrix messaging."""
    return _formatter.convert(content)


def strip_markdown(content: str) -> str:
    """Strip markdown formatting from text for Farcaster and other plain text contexts."""
    return _formatter._markdown_to_plain(content)
