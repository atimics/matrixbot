"""
Simple colorized logging for arweave service.
"""

import logging
import sys
import os


class SimpleColoredFormatter(logging.Formatter):
    """Simple formatter with ANSI color codes for different log levels."""
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[37m',       # White (default)
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m'        # Reset to default
    }
    
    def format(self, record):
        original_format = super().format(record)
        
        # Only add colors if output supports it
        if self._supports_color():
            level_name = record.levelname
            color_code = self.COLORS.get(level_name, self.COLORS['RESET'])
            reset_code = self.COLORS['RESET']
            return f"{color_code}{original_format}{reset_code}"
        
        return original_format
    
    def _supports_color(self) -> bool:
        """Check if the current environment supports color output."""
        return (
            hasattr(sys.stdout, 'isatty') and sys.stdout.isatty() or
            'TERM' in os.environ or
            'VSCODE_INJECTION' in os.environ
        )


def setup_colored_logging():
    """Setup colorized logging for arweave service."""
    formatter = SimpleColoredFormatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    
    logging.basicConfig(
        level=logging.INFO,
        handlers=[handler],
        force=True
    )
