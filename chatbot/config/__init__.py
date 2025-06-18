# RatiChat Configuration Package

"""
Configuration management for RatiChat.

This package provides unified configuration handling across the application,
including settings for AI, integrations, storage, and security.
"""

# Import from the working config.py file instead of enhanced_config.py
import sys
from pathlib import Path

# Add the parent directory to the path to import from config.py
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import settings, AppConfig as UnifiedSettings

__all__ = ['UnifiedSettings', 'settings']
