"""
Mini-app recommendation tools for Farcaster ecosystem integration.

This module provides tools for managing and searching a curated database of
Farcaster mini-apps to help users discover relevant applications based on
their expressed needs and interests.
"""
import logging
import time
from typing import Any, Dict, List

from ..core.world_state.structures import MiniAppEntry
from .base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


class UpdateMiniAppDBTool(ToolInterface):
    """
    Tool for updating the persistent mini-app database.
    
    This tool allows adding, updating, or removing mini-app entries from the
    curated database used for recommendations. It follows the same pattern
    as the research tools for consistency.
    """

    @property
    def name(self) -> str:
        return "update_mini_app_db"

    @property
    def description(self) -> str:
        return """Update the persistent mini-app database with new applications.
        
        Use this tool to:
        - Add new Farcaster mini-apps to the recommendation database
        - Update existing app information (description, category, etc.)
        - Remove outdated or broken applications
        - Maintain accurate metadata for better recommendations
        
        This creates a curated knowledge base of quality mini-apps that can
        be recommended to users based on their expressed needs."""

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "name": "string (the name of the mini-app, will be used as the key)",
            "url": "string (direct URL to access the mini-app)",
            "description": "string (detailed description of what the app does)",
            "developer": "string (name or identifier of the app developer)",
            "category": "string (primary category: games, tools, social, defi, etc.)",
            "tags": "list of strings (keywords for searching and categorization)",
            "popularity_score": "float 0.0-1.0 (optional: popularity metric)",
            "action": "string (add, update, or remove - default: add)",
            "metadata": "dict (optional: additional app-specific information)",
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """
        Execute the mini-app database update operation.
        
        Args:
            params: The tool parameters (name, url, description, etc.)
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
            description = params.get("description", "").strip()
            developer = params.get("developer", "").strip()
            
            if not url:
                return {
                    "status": "failure",
                    "error": "Mini-app URL is required",
                    "timestamp": time.time(),
                }
            if not description:
                return {
                    "status": "failure",
                    "error": "Mini-app description is required",
                    "timestamp": time.time(),
                }
            if not developer:
                return {
                    "status": "failure",
                    "error": "Developer name is required",
                    "timestamp": time.time(),
                }
            
            # Extract optional parameters
            category = params.get("category", "tools").strip()
            tags = params.get("tags", [])
            popularity_score = params.get("popularity_score")
            metadata = params.get("metadata", {})
            
            # Ensure tags is a list
            if isinstance(tags, str):
                tags = [tag.strip() for tag in tags.split(",")]
            elif not isinstance(tags, list):
                tags = []
            
            # Validate popularity score
            if popularity_score is not None:
                try:
                    popularity_score = float(popularity_score)
                    if not 0.0 <= popularity_score <= 1.0:
                        popularity_score = None
                except (ValueError, TypeError):
                    popularity_score = None
            
            # Create or update the mini-app entry
            current_time = time.time()
            
            if action == "update" and app_key in context.world_state_manager.state.mini_app_database:
                # Update existing entry
                existing_entry = context.world_state_manager.state.mini_app_database[app_key]
                existing_entry.url = url
                existing_entry.description = description
                existing_entry.developer = developer
                existing_entry.category = category
                existing_entry.tags = tags
                existing_entry.popularity_score = popularity_score
                existing_entry.last_updated = current_time
                existing_entry.metadata.update(metadata)
                
                logger.info(f"Updated mini-app in database: {app_name}")
                return {
                    "status": "success",
                    "message": f"Successfully updated '{app_name}' in mini-app database",
                    "timestamp": time.time(),
                }
            else:
                # Add new entry
                mini_app_entry = MiniAppEntry(
                    name=app_name,
                    url=url,
                    description=description,
                    developer=developer,
                    category=category,
                    tags=tags,
                    popularity_score=popularity_score,
                    added_timestamp=current_time,
                    last_updated=current_time,
                    metadata=metadata
                )
                
                context.world_state_manager.state.mini_app_database[app_key] = mini_app_entry
                
                logger.info(f"Added mini-app to database: {app_name}")
                return {
                    "status": "success",
                    "message": f"Successfully added '{app_name}' to mini-app database with {len(tags)} tags",
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
    Tool for searching the mini-app database to find relevant applications.
    
    This tool searches through the curated mini-app database based on user
    queries and needs, returning ranked recommendations with metadata.
    """

    @property
    def name(self) -> str:
        return "search_mini_apps"

    @property
    def description(self) -> str:
        return """Search the mini-app database for relevant Farcaster applications.
        
        Use this tool to:
        - Find mini-apps that match user needs or interests
        - Search by keywords, categories, or descriptions
        - Get ranked recommendations based on relevance
        - Help users discover useful applications in the Farcaster ecosystem
        
        This tool searches through name, description, tags, and categories to
        find the most relevant mini-apps for the user's expressed needs."""

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "query": "string (search query - what the user is looking for)",
            "category": "string (optional: filter by category like 'games', 'tools', 'social', 'defi')",
            "limit": "integer (optional: maximum number of results to return, default 5)",
            "include_popularity": "boolean (optional: whether to factor in popularity scores, default true)",
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """
        Execute the mini-app search operation.
        
        Args:
            params: The search parameters (query, category, limit, etc.)
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
            category_filter = params.get("category", "").strip().lower()
            limit = params.get("limit", 5)
            include_popularity = params.get("include_popularity", True)
            
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
            
            # Search and score mini-apps
            scored_apps = []
            
            for app_key, mini_app in mini_apps.items():
                score = 0.0
                
                # Category filter
                if category_filter and category_filter != mini_app.category.lower():
                    continue
                
                # Search in name (highest weight)
                if query in mini_app.name.lower():
                    score += 10.0
                
                # Search in tags (high weight)
                for tag in mini_app.tags:
                    if query in tag.lower():
                        score += 5.0
                
                # Search in description (medium weight)
                if query in mini_app.description.lower():
                    score += 3.0
                
                # Search in category (low weight)
                if query in mini_app.category.lower():
                    score += 2.0
                
                # Search in developer name (low weight)
                if query in mini_app.developer.lower():
                    score += 1.0
                
                # Add popularity bonus if available and requested
                if include_popularity and mini_app.popularity_score is not None:
                    score += mini_app.popularity_score * 2.0
                
                # Only include apps with some relevance
                if score > 0:
                    scored_apps.append((score, mini_app))
            
            if not scored_apps:
                category_text = f" in category '{category_filter}'" if category_filter else ""
                return {
                    "status": "success",
                    "message": f"No mini-apps found matching '{query}'{category_text}. Try different keywords or check the available categories.",
                    "results": [],
                    "timestamp": time.time(),
                }
            
            # Sort by score (descending) and limit results
            scored_apps.sort(key=lambda x: x[0], reverse=True)
            top_apps = scored_apps[:limit]
            
            # Format the results
            results = []
            for score, mini_app in top_apps:
                # Format popularity
                popularity_text = ""
                if mini_app.popularity_score is not None:
                    stars = "⭐" * int(mini_app.popularity_score * 5)
                    popularity_text = f" {stars}"
                
                results.append({
                    "name": mini_app.name,
                    "url": mini_app.url,
                    "description": mini_app.description,
                    "developer": mini_app.developer,
                    "category": mini_app.category,
                    "tags": mini_app.tags,
                    "popularity_score": mini_app.popularity_score,
                    "relevance_score": score,
                    "popularity_display": popularity_text
                })
            
            # Create formatted message for AI response
            result_lines = [f"🎯 Found {len(top_apps)} mini-app recommendation{'s' if len(top_apps) != 1 else ''} for '{query}':\n"]
            
            for i, result in enumerate(results, 1):
                # Format tags
                tags_text = f" #{' #'.join(result['tags'][:3])}" if result['tags'] else ""
                
                result_lines.append(
                    f"{i}. **{result['name']}**{result['popularity_display']}\n"
                    f"   📝 {result['description']}\n"
                    f"   🔗 {result['url']}\n"
                    f"   👨‍💻 by {result['developer']} | 📂 {result['category']}{tags_text}\n"
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
