"""
Simplified Mini-app recommendation tools for Farcaster ecosystem integration.

This module provides a streamlined approach to mini-app recommendations based on
AI-generated summaries. The system is essentially a curated list of "digital index cards"
where each card has a name, URL, and AI-generated summary that serves as the "brain"
for recommendations.
"""
import logging
import time
from typing import Any, Dict, List

from ..core.world_state.structures import MiniAppEntry
from .base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


class UpdateMiniAppSummaryTool(ToolInterface):
    """
    Tool for managing the simplified mini-app database.
    
    This tool allows adding new apps or updating AI summaries for existing apps.
    The focus is on maintaining high-quality AI-generated summaries that capture
    what each app does, who it's for, and its main purpose.
    """

    @property
    def name(self) -> str:
        return "update_mini_app_summary"

    @property
    def description(self) -> str:
        return """Manage the mini-app database with AI-generated summaries.
        
        Use this tool to:
        - Add new Farcaster mini-apps with AI-generated summaries
        - Update existing app summaries to improve recommendation quality
        - Remove outdated or broken applications
        
        The AI summary is the core of the system - it should explain what the app does,
        who might find it useful, and its main purpose in a casual, searchable way."""

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "name": "string (the official name of the mini-app)",
            "url": "string (direct URL to access the mini-app)",
            "ai_summary": "string (AI-generated casual summary explaining what it does, who it's for, and purpose)",
            "action": "string (add, update, or remove - default: add)",
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """
        Execute the mini-app database operation.
        
        Args:
            params: The tool parameters (name, url, ai_summary, action)
            context: The current action context with world state access
            
        Returns:
            Dictionary with status and result information
        """
        try:
            if not context.world_state_manager:
                return {
                    "status": "failure",
                    "error": "World state manager not available",
                    "timestamp": time.time(),
                }

            # Extract parameters
            app_name = params.get("name", "").strip()
            action = params.get("action", "add").lower()
            
            if not app_name:
                return {
                    "status": "failure",
                    "error": "Mini-app name is required",
                    "timestamp": time.time(),
                }
            
            # Normalize the app name as the key
            app_key = app_name.lower().replace(" ", "_")
            
            if action == "remove":
                if app_key in context.world_state_manager.state.mini_app_database:
                    del context.world_state_manager.state.mini_app_database[app_key]
                    logger.info(f"Removed mini-app from database: {app_name}")
                    return {
                        "status": "success",
                        "message": f"Successfully removed '{app_name}' from mini-app database",
                        "timestamp": time.time(),
                    }
                else:
                    return {
                        "status": "failure",
                        "error": f"Mini-app '{app_name}' not found in database",
                        "timestamp": time.time(),
                    }
            
            # For add/update operations, validate required fields
            url = params.get("url", "").strip()
            ai_summary = params.get("ai_summary", "").strip()
            
            if not url:
                return {
                    "status": "failure",
                    "error": "Mini-app URL is required",
                    "timestamp": time.time(),
                }
            if not ai_summary:
                return {
                    "status": "failure",
                    "error": "AI summary is required - this is the core of the recommendation system",
                    "timestamp": time.time(),
                }
            
            current_time = time.time()
            
            if action == "update" and app_key in context.world_state_manager.state.mini_app_database:
                # Update existing entry
                existing_entry = context.world_state_manager.state.mini_app_database[app_key]
                existing_entry.url = url
                existing_entry.ai_summary = ai_summary
                existing_entry.last_updated = current_time
                
                logger.info(f"Updated mini-app summary: {app_name}")
                return {
                    "status": "success",
                    "message": f"Successfully updated '{app_name}' summary in mini-app database",
                    "timestamp": time.time(),
                }
            else:
                # Add new entry
                mini_app_entry = MiniAppEntry(
                    name=app_name,
                    url=url,
                    ai_summary=ai_summary,
                    added_timestamp=current_time,
                    last_updated=current_time
                )
                
                context.world_state_manager.state.mini_app_database[app_key] = mini_app_entry
                
                logger.info(f"Added mini-app to database: {app_name}")
                return {
                    "status": "success",
                    "message": f"Successfully added '{app_name}' to mini-app database",
                    "timestamp": time.time(),
                }
                
        except Exception as e:
            error_msg = f"Error updating mini-app database: {str(e)}"
            logger.error(error_msg)
            return {
                "status": "failure",
                "error": error_msg,
                "timestamp": time.time(),
            }


class SearchMiniAppsTool(ToolInterface):
    """
    Tool for searching mini-apps based on AI-generated summaries.
    
    This tool performs intelligent text search across the AI summaries to find
    relevant applications. The AI summaries are rich with context about use cases
    and user types, making the search surprisingly effective.
    """

    @property
    def name(self) -> str:
        return "search_mini_apps"

    @property
    def description(self) -> str:
        return """Search mini-apps using intelligent text matching on AI summaries.
        
        Use this tool to:
        - Find mini-apps that match user needs or interests
        - Search based on natural language queries
        - Get ranked recommendations based on relevance to the query
        
        The search works by analyzing the AI-generated summaries, which contain rich
        context about what each app does, who it's for, and its use cases."""

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "query": "string (natural language search query - what the user is looking for)",
            "limit": "integer (optional: maximum number of results to return, default 5)",
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """
        Execute the mini-app search operation.
        
        Args:
            params: The search parameters (query, limit)
            context: The current action context with world state access
            
        Returns:
            Dictionary with status and result information
        """
        try:
            if not context.world_state_manager:
                return {
                    "status": "failure",
                    "error": "World state manager not available",
                    "timestamp": time.time(),
                }

            # Extract parameters
            query = params.get("query", "").strip().lower()
            limit = params.get("limit", 5)
            
            if not query:
                return {
                    "status": "failure",
                    "error": "Search query is required",
                    "timestamp": time.time(),
                }
            
            try:
                limit = int(limit)
                if limit <= 0:
                    limit = 5
            except (ValueError, TypeError):
                limit = 5
            
            # Get all mini-apps from the database
            mini_apps = context.world_state_manager.state.mini_app_database
            
            if not mini_apps:
                return {
                    "status": "success",
                    "message": "No mini-apps found in the database. The database needs to be populated with applications first.",
                    "results": [],
                    "timestamp": time.time(),
                }
            
            # Simple but effective text matching on AI summaries
            scored_apps = []
            query_words = query.split()
            
            for app_key, mini_app in mini_apps.items():
                score = 0.0
                summary_lower = mini_app.ai_summary.lower()
                name_lower = mini_app.name.lower()
                
                # Exact phrase match in summary (highest weight)
                if query in summary_lower:
                    score += 20.0
                
                # Exact phrase match in name (very high weight)
                if query in name_lower:
                    score += 15.0
                
                # Individual word matches in summary
                for word in query_words:
                    if len(word) > 2:  # Skip very short words
                        if word in summary_lower:
                            score += 5.0
                        if word in name_lower:
                            score += 3.0
                
                # Bonus for apps with richer summaries (more comprehensive)
                summary_length_bonus = min(len(mini_app.ai_summary) / 100.0, 2.0)
                score += summary_length_bonus
                
                # Only include apps with some relevance
                if score > 0:
                    scored_apps.append((score, mini_app))
            
            if not scored_apps:
                return {
                    "status": "success",
                    "message": f"No mini-apps found matching '{query}'. Try different keywords or check what's available in the database.",
                    "results": [],
                    "timestamp": time.time(),
                }
            
            # Sort by score (descending) and limit results
            scored_apps.sort(key=lambda x: x[0], reverse=True)
            top_apps = scored_apps[:limit]
            
            # Format the results
            results = []
            for score, mini_app in top_apps:
                results.append({
                    "name": mini_app.name,
                    "url": mini_app.url,
                    "ai_summary": mini_app.ai_summary,
                    "relevance_score": score
                })
            
            # Create formatted message for AI response
            result_lines = [f"🎯 Found {len(top_apps)} mini-app recommendation{'s' if len(top_apps) != 1 else ''} for '{params.get('query', '')}':\n"]
            
            for i, result in enumerate(results, 1):
                result_lines.append(
                    f"{i}. **{result['name']}**\n"
                    f"   🔗 {result['url']}\n"
                    f"   � {result['ai_summary']}\n"
                )
            
            return {
                "status": "success",
                "message": "\n".join(result_lines),
                "results": results,
                "query": params.get("query", ""),
                "total_found": len(scored_apps),
                "returned_count": len(top_apps),
                "timestamp": time.time(),
            }
            
        except Exception as e:
            error_msg = f"Error searching mini-apps: {str(e)}"
            logger.error(error_msg)
            return {
                "status": "failure",
                "error": error_msg,
                "timestamp": time.time(),
            }
