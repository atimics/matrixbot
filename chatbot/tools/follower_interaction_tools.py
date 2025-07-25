"""
Follower Interaction Management Tools

Tools for managing and summarizing interactions with followers,
similar to the mini-app recommendation system but for user relationships.
"""

import logging
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict

from .base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


@dataclass
class FollowerProfile:
    """Profile information for a follower interaction."""
    username: str
    fid: Optional[str] = None
    display_name: Optional[str] = None
    bio: Optional[str] = None
    follower_count: Optional[int] = None
    following_count: Optional[int] = None
    ai_summary: Optional[str] = None  # AI-generated summary of interaction style
    interaction_count: int = 0
    last_interaction: Optional[float] = None
    interests: Optional[List[str]] = None
    interaction_style: Optional[str] = None  # "casual", "technical", "supportive", etc.
    
    def __post_init__(self):
        if self.interests is None:
            self.interests = []


class UpdateFollowerProfileTool(ToolInterface):
    """Tool for updating or creating follower profiles with AI summaries."""

    @property
    def name(self) -> str:
        return "update_follower_profile"

    @property
    def description(self) -> str:
        return ("Update or create a follower profile with AI-generated summary. "
                "This helps the bot understand interaction patterns and preferences.")

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "username": {
                    "type": "string",
                    "description": "The follower's username"
                },
                "fid": {
                    "type": "string",
                    "description": "The follower's Farcaster ID"
                },
                "display_name": {
                    "type": "string",
                    "description": "The follower's display name"
                },
                "bio": {
                    "type": "string",
                    "description": "The follower's bio/description"
                },
                "ai_summary": {
                    "type": "string",
                    "description": "AI-generated summary of the follower's interaction style and interests"
                },
                "interests": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of interests or topics the follower engages with"
                },
                "interaction_style": {
                    "type": "string",
                    "description": "Interaction style: casual, technical, supportive, inquisitive, etc."
                }
            },
            "required": ["username"]
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """Update or create a follower profile."""
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        if not context.world_state_manager:
            error_msg = "World state manager not available"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        username = params.get("username")
        if not username:
            error_msg = "Username is required"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            # Get existing profile or create new one
            existing_profile = context.world_state_manager.state.follower_profiles.get(username)
            
            if existing_profile:
                # Update existing profile
                profile = existing_profile
                profile.interaction_count += 1
                profile.last_interaction = time.time()
                
                # Update fields if provided
                if params.get("fid"):
                    profile.fid = params["fid"]
                if params.get("display_name"):
                    profile.display_name = params["display_name"]
                if params.get("bio"):
                    profile.bio = params["bio"]
                if params.get("ai_summary"):
                    profile.ai_summary = params["ai_summary"]
                if params.get("interests"):
                    profile.interests = params["interests"]
                if params.get("interaction_style"):
                    profile.interaction_style = params["interaction_style"]
                    
                logger.info(f"Updated existing profile for {username}")
            else:
                # Create new profile
                profile = FollowerProfile(
                    username=username,
                    fid=params.get("fid"),
                    display_name=params.get("display_name"),
                    bio=params.get("bio"),
                    ai_summary=params.get("ai_summary"),
                    interests=params.get("interests", []),
                    interaction_style=params.get("interaction_style"),
                    interaction_count=1,
                    last_interaction=time.time()
                )
                logger.info(f"Created new profile for {username}")

            # Store in world state
            context.world_state_manager.state.follower_profiles[username] = profile
            
            return {
                "status": "success",
                "message": f"Updated follower profile for {username}",
                "profile": asdict(profile),
                "timestamp": time.time()
            }

        except Exception as e:
            error_msg = f"Error updating follower profile: {e}"
            logger.exception(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}


class SearchFollowerProfilesTool(ToolInterface):
    """Tool for searching follower profiles based on interests or interaction style."""

    @property
    def name(self) -> str:
        return "search_follower_profiles"

    @property
    def description(self) -> str:
        return ("Search follower profiles by interests, interaction style, or natural language query. "
                "Helps find relevant followers for engagement opportunities.")

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query for follower interests or characteristics"
                },
                "interaction_style": {
                    "type": "string",
                    "description": "Filter by interaction style: casual, technical, supportive, etc."
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 5)",
                    "default": 5
                }
            },
            "required": ["query"]
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """Search follower profiles."""
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        if not context.world_state_manager:
            error_msg = "World state manager not available"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        query = params.get("query", "").lower()
        interaction_style = params.get("interaction_style", "").lower()
        limit = params.get("limit", 5)

        try:
            profiles = context.world_state_manager.state.follower_profiles
            if not profiles:
                return {
                    "status": "success",
                    "message": "No follower profiles found in database",
                    "results": [],
                    "timestamp": time.time()
                }

            matches = []

            for username, profile in profiles.items():
                score = 0
                
                # Search in AI summary
                if profile.ai_summary and query in profile.ai_summary.lower():
                    score += 3
                
                # Search in interests
                for interest in profile.interests:
                    if query in interest.lower():
                        score += 2
                
                # Search in bio
                if profile.bio and query in profile.bio.lower():
                    score += 1
                
                # Search in username/display name
                if query in username.lower():
                    score += 1
                if profile.display_name and query in profile.display_name.lower():
                    score += 1
                
                # Filter by interaction style if specified
                if interaction_style:
                    if profile.interaction_style and interaction_style not in profile.interaction_style.lower():
                        continue
                
                if score > 0:
                    matches.append({
                        "username": username,
                        "profile": asdict(profile),
                        "relevance_score": score
                    })

            # Sort by relevance score
            matches.sort(key=lambda x: x["relevance_score"], reverse=True)
            
            # Limit results
            matches = matches[:limit]

            # Format results for display
            results = []
            for match in matches:
                profile = match["profile"]
                results.append({
                    "username": profile["username"],
                    "display_name": profile.get("display_name"),
                    "ai_summary": profile.get("ai_summary"),
                    "interests": profile.get("interests", []),
                    "interaction_style": profile.get("interaction_style"),
                    "interaction_count": profile.get("interaction_count", 0),
                    "relevance_score": match["relevance_score"]
                })

            message = f"Found {len(results)} follower profiles matching '{query}'"
            if interaction_style:
                message += f" with style '{interaction_style}'"

            return {
                "status": "success",
                "message": message,
                "results": results,
                "query": query,
                "timestamp": time.time()
            }

        except Exception as e:
            error_msg = f"Error searching follower profiles: {e}"
            logger.exception(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}


class GenerateFollowerSummaryTool(ToolInterface):
    """Tool for generating AI summaries of follower interactions."""

    @property
    def name(self) -> str:
        return "generate_follower_summary"

    @property
    def description(self) -> str:
        return ("Generate an AI summary of a follower's interaction style and interests "
                "based on their profile and recent interactions.")

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "username": {
                    "type": "string",
                    "description": "The follower's username"
                },
                "bio": {
                    "type": "string",
                    "description": "The follower's bio/description"
                },
                "recent_casts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Recent cast content from the follower"
                },
                "interaction_context": {
                    "type": "string",
                    "description": "Context of recent interactions with the bot"
                }
            },
            "required": ["username"]
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """Generate an AI summary of a follower."""
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        username = params.get("username")
        bio = params.get("bio", "")
        recent_casts = params.get("recent_casts", [])
        interaction_context = params.get("interaction_context", "")

        try:
            # Generate AI summary based on available information
            summary_parts = []
            interests = []
            interaction_style = "casual"

            if bio:
                summary_parts.append(f"Profile: {bio}")
                
                # Extract interests from bio
                if "crypto" in bio.lower() or "blockchain" in bio.lower():
                    interests.append("cryptocurrency")
                if "dev" in bio.lower() or "engineer" in bio.lower():
                    interests.append("development")
                    interaction_style = "technical"
                if "art" in bio.lower() or "design" in bio.lower():
                    interests.append("art")
                if "defi" in bio.lower():
                    interests.append("defi")

            if recent_casts:
                cast_content = " ".join(recent_casts[:3])  # Use last 3 casts
                summary_parts.append(f"Recent activity shows interest in: {cast_content[:200]}")
                
                # Analyze cast content for interests
                content_lower = cast_content.lower()
                if "gm" in content_lower or "good morning" in content_lower:
                    interaction_style = "friendly"
                if any(word in content_lower for word in ["question", "help", "how"]):
                    interaction_style = "inquisitive"

            if interaction_context:
                summary_parts.append(f"Bot interaction: {interaction_context}")

            # Generate comprehensive summary
            if summary_parts:
                ai_summary = f"Follower @{username} appears to be {interaction_style} in their interactions. " + " ".join(summary_parts)
            else:
                ai_summary = f"Follower @{username} with limited profile information available."

            # Ensure interests list is not empty
            if not interests:
                interests = ["general"]

            return {
                "status": "success",
                "ai_summary": ai_summary,
                "interests": interests,
                "interaction_style": interaction_style,
                "timestamp": time.time()
            }

        except Exception as e:
            error_msg = f"Error generating follower summary: {e}"
            logger.exception(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}
