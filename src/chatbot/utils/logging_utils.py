"""
Colorized Logging Utilities

This module provides enhanced logging capabilities with colorized output for better
visibility in VS Code terminal and other development environments.
"""

import logging
import sys
from typing import Optional


class ColoredFormatter(logging.Formatter):
    """Custom formatter with ANSI color codes for different log levels."""
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[37m',       # White (default)
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m'        # Reset to default
    }
    
    def __init__(self, *args, use_colors: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.use_colors = use_colors
    
    def format(self, record):
        # Get the original formatted message
        original_format = super().format(record)
        
        # Only add colors if enabled and if output supports it
        if self.use_colors and self._supports_color():
            level_name = record.levelname
            color_code = self.COLORS.get(level_name, self.COLORS['RESET'])
            reset_code = self.COLORS['RESET']
            
            # Color the entire log message
            return f"{color_code}{original_format}{reset_code}"
        
        return original_format
    
    def _supports_color(self) -> bool:
        """Check if the current environment supports color output."""
        # Respect NO_COLOR environment variable (https://no-color.org/)
        if os.environ.get('NO_COLOR'):
            return False
            
        # Check for common CI/CD environments that don't support colors
        if os.environ.get('CI') or os.environ.get('GITHUB_ACTIONS'):
            return False
            
        # VS Code terminal and most modern terminals support ANSI colors
        return (
            hasattr(sys.stdout, 'isatty') and sys.stdout.isatty() or
            'TERM' in os.environ or
            'VSCODE_INJECTION' in os.environ or  # VS Code specific
            os.environ.get('COLORTERM') is not None or  # Modern terminals
            os.environ.get('TERM_PROGRAM') == 'vscode'  # VS Code integrated terminal
        )


def setup_colorized_logging(
    level: int = logging.INFO,
    log_file: Optional[str] = "chatbot.log",
    enable_colors: bool = True,
    format_string: Optional[str] = None
) -> None:
    """
    Set up colorized logging configuration.
    
    Args:
        level: Logging level (default: INFO)
        log_file: Path to log file (default: "chatbot.log", None to disable file logging)
        enable_colors: Enable colorized console output (default: True)
        format_string: Custom format string (default: standard format)
    """
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Clear any existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    handlers = []
    
    # Console handler with optional colors
    console_handler = logging.StreamHandler()
    console_formatter = ColoredFormatter(format_string, use_colors=enable_colors)
    console_handler.setFormatter(console_formatter)
    handlers.append(console_handler)
    
    # File handler without colors (if specified)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_formatter = logging.Formatter(format_string)
        file_handler.setFormatter(file_formatter)
        handlers.append(file_handler)
    
    # Configure root logger
    logging.basicConfig(
        level=level,
        handlers=handlers,
        force=True  # Force reconfiguration
    )


def get_colored_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.
    
    This is a convenience function that returns a standard logger.
    The colorization is handled by the configured formatter.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


# Import os here to avoid issues
import os
