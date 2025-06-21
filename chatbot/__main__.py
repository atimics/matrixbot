"""
Allow the chatbot package to be executed as a module.

This enables running the chatbot with:
    python -m chatbot
    python -m chatbot --with-ui
"""

from chatbot.main import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
