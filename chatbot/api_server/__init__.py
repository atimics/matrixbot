"""
API Server package for the chatbot management interface.

This package provides a modular FastAPI-based REST API for monitoring and controlling
the chatbot system, with organized routers for different functional areas.
"""

from .secure_server import create_secure_api_server

__all__ = ["create_secure_api_server"]
