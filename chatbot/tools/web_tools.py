"""
Web search and research tools using OpenRouter's online models.
"""
import logging
import time
from typing import Any, Dict

import httpx

from ..config import settings
from .base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


class WebSearchTool(ToolInterface):
    """
    Tool for performing web searches using OpenRouter's :online models.
    These models can access real-time web content to answer questions.
    """

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return """Search the web for current information on any topic using OpenRouter's online AI models.
        
        Use this tool when:
        - You need current, up-to-date information about recent events
        - User asks about topics that might have changed since your training data
        - You need to verify or fact-check information from URLs or claims
        - You want to research trends, news, or current status of projects/companies
        - You need to look up specific technical details or documentation
        
        The tool will use an AI model with web access to provide comprehensive, current information."""

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "query": "string (the search query or question to research online)",
            "focus": "string (optional: 'news', 'technical', 'general' - guides search focus)"
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute web search using OpenRouter's online model."""
        try:
            query = params.get("query", "").strip()
            focus = params.get("focus", "general").strip()
            
            if not query:
                return {
                    "status": "failure",
                    "error": "Query parameter is required",
                    "timestamp": time.time(),
                }

            # Prepare the prompt for the online model
            if focus == "news":
                search_prompt = f"Please search for the latest news and current information about: {query}. Focus on recent developments, updates, and current status."
            elif focus == "technical":
                search_prompt = f"Please search for technical information, documentation, and detailed explanations about: {query}. Focus on accurate technical details, specifications, and implementation information."
            else:
                search_prompt = f"Please search for comprehensive information about: {query}. Provide current, accurate, and well-sourced information."

            # Make request to OpenRouter's online model
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.openrouter_api_key}",
                        "HTTP-Referer": settings.YOUR_SITE_URL or "https://github.com/your-repo",
                        "X-Title": settings.YOUR_SITE_NAME or "Chatbot Web Search",
                    },
                    json={
                        "model": settings.WEB_SEARCH_MODEL,
                        "messages": [
                            {
                                "role": "user",
                                "content": search_prompt
                            }
                        ],
                        "max_tokens": 2000,
                        "temperature": 0.3,  # Lower temperature for more factual responses
                    },
                    timeout=30.0,
                )

                if response.status_code == 200:
                    result = response.json()
                    search_result = result["choices"][0]["message"]["content"]
                    
                    logger.info(f"Web search completed for query: {query}")
                    
                    return {
                        "status": "success",
                        "message": "Web search completed successfully",
                        "timestamp": time.time(),
                        "query": query,
                        "focus": focus,
                        "result": search_result,
                        "model_used": settings.WEB_SEARCH_MODEL,
                    }
                else:
                    logger.error(f"OpenRouter API error: {response.status_code} - {response.text}")
                    return {
                        "status": "failure",
                        "error": f"OpenRouter API error: {response.status_code}",
                        "timestamp": time.time(),
                    }

        except httpx.TimeoutException:
            return {
                "status": "failure",
                "error": "Web search request timed out",
                "timestamp": time.time(),
            }
        except Exception as e:
            logger.error(f"Error during web search: {e}", exc_info=True)
            return {
                "status": "failure",
                "error": f"Web search failed: {str(e)}",
                "timestamp": time.time(),
            }
