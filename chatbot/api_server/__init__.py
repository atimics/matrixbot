"""
API Server package for the chatbot management interface.

This package provides a modular FastAPI-based REST API for monitoring and controlling
the chatbot system, with organized routers for different functional areas.
"""

__all__ = ["ChatbotAPIServer", "create_api_server"]


def __getattr__(name):
    """Avoid importing the full FastAPI/orchestrator graph for helper modules."""
    if name in __all__:
        from .main import ChatbotAPIServer, create_api_server

        return {
            "ChatbotAPIServer": ChatbotAPIServer,
            "create_api_server": create_api_server,
        }[name]
    raise AttributeError(name)
