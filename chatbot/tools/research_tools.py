"""
Research and knowledge management tools for building a persistent knowledge base.
"""
import hashlib
import logging
import time
from typing import Any, Dict

from ..core.world_state.structures import ResearchEntry
from .base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


class UpdateResearchTool(ToolInterface):
    """
    Tool for updating the persistent research knowledge base.
    
    This tool allows the AI to store and update research findings, creating
    a growing knowledge base that improves reliability over time.
    """

    @property
    def name(self) -> str:
        return "update_research"

    @property
    def description(self) -> str:
        return """Update the persistent research knowledge base with new information.
        
        Use this tool to:
        - Store important findings from web searches for future reference
        - Update existing knowledge with new information
        - Create connections between related topics
        - Track information sources and confidence levels
        - Build a knowledge graph for better context understanding
        
        This creates a persistent memory that helps avoid repeating research and
        improves accuracy of responses over time."""

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "The main topic or subject, will be normalized"
                },
                "summary": {
                    "type": "string",
                    "description": "Concise summary of what you learned about this topic"
                },
                "key_facts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Important facts or data points",
                    "default": []
                },
                "sources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "URLs, documents, or sources where info came from",
                    "default": []
                },
                "confidence_level": {
                    "type": "integer",
                    "description": "Confidence in information accuracy (1-10)",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 5
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for categorization",
                    "default": []
                },
                "related_topics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Related topic keys",
                    "default": []
                },
                "verification_notes": {
                    "type": "string",
                    "description": "Notes about verification or concerns"
                }
            },
            "required": ["topic", "summary"]
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Update the research knowledge base."""
        try:
            if not context.world_state_manager:
                return {
                    "status": "failure",
                    "error": "World state manager not available",
                    "timestamp": time.time(),
                }

            topic = params.get("topic", "").strip().lower()
            summary = params.get("summary", "").strip()
            
            if not topic or not summary:
                return {
                    "status": "failure",
                    "error": "Both topic and summary are required",
                    "timestamp": time.time(),
                }

            key_facts = params.get("key_facts", [])
            sources = params.get("sources", [])
            confidence_level = params.get("confidence_level", 5)
            tags = params.get("tags", [])
            related_topics = [t.strip().lower() for t in params.get("related_topics", [])]
            verification_notes = params.get("verification_notes", "").strip() or None

            # Validate confidence level
            if not isinstance(confidence_level, int) or confidence_level < 1 or confidence_level > 10:
                confidence_level = 5

            # Get existing research entry or create new one
            research_db = context.world_state_manager.state.research_database
            existing_entry = research_db.get(topic)

            if existing_entry:
                # Update existing entry
                entry = ResearchEntry(**existing_entry)
                entry.summary = summary
                entry.key_facts = key_facts if key_facts else entry.key_facts
                entry.sources = list(set(entry.sources + sources))  # Merge and deduplicate
                entry.confidence_level = confidence_level
                entry.last_updated = time.time()
                entry.tags = list(set(entry.tags + tags))  # Merge and deduplicate
                entry.related_topics = list(set(entry.related_topics + related_topics))
                if verification_notes:
                    entry.verification_notes = verification_notes
                    
                action_message = f"Updated research entry for topic '{topic}'"
                logger.debug(f"Updated research entry for topic: {topic}")
            else:
                # Create new entry
                entry = ResearchEntry(
                    topic=topic,
                    summary=summary,
                    key_facts=key_facts,
                    sources=sources,
                    confidence_level=confidence_level,
                    last_updated=time.time(),
                    tags=tags,
                    related_topics=related_topics,
                    verification_notes=verification_notes,
                )
                action_message = f"Created new research entry for topic '{topic}'"
                logger.debug(f"Created new research entry for topic: {topic}")

            # Store in research database as dict
            research_db[topic] = {
                "topic": entry.topic,
                "summary": entry.summary,
                "key_facts": entry.key_facts,
                "sources": entry.sources,
                "confidence_level": entry.confidence_level,
                "last_updated": entry.last_updated,
                "last_verified": entry.last_verified,
                "tags": entry.tags,
                "related_topics": entry.related_topics,
                "verification_notes": entry.verification_notes,
            }

            return {
                "status": "success",
                "message": action_message,
                "timestamp": time.time(),
                "topic": topic,
                "confidence_level": confidence_level,
                "sources_count": len(sources),
                "facts_count": len(key_facts),
                "related_topics": related_topics,
            }

        except Exception as e:
            logger.error(f"Error updating research: {e}", exc_info=True)
            return {
                "status": "failure",
                "error": f"Research update failed: {str(e)}",
                "timestamp": time.time(),
            }


class QueryResearchTool(ToolInterface):
    """
    Tool for querying the persistent research knowledge base.
    
    This tool allows the AI to retrieve previously stored research findings
    to provide better context and avoid repeating research.
    """

    @property
    def name(self) -> str:
        return "query_research"

    @property
    def description(self) -> str:
        return """Query the persistent research knowledge base for relevant information.
        
        Use this tool to:
        - Find previously researched information on topics
        - Get related topics and cross-references
        - Check confidence levels and sources for information
        - Build on existing knowledge rather than starting from scratch
        
        This helps provide consistent, well-sourced answers and avoids unnecessary
        re-research of topics already covered."""

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Specific topic to look up"
                },
                "search_terms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Search for entries containing these terms",
                    "default": []
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Find entries with these tags",
                    "default": []
                },
                "min_confidence": {
                    "type": "integer",
                    "description": "Minimum confidence level filter (1-10)",
                    "minimum": 1,
                    "maximum": 10
                },
                "max_results": {
                    "type": "integer",
                    "description": "Limit number of results",
                    "default": 10,
                    "minimum": 1
                }
            },
            "required": []
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Query the research knowledge base."""
        try:
            if not context.world_state_manager:
                return {
                    "status": "failure",
                    "error": "World state manager not available",
                    "timestamp": time.time(),
                }

            research_db = context.world_state_manager.state.research_database
            
            if not research_db:
                return {
                    "status": "success",
                    "message": "No research entries found in database",
                    "timestamp": time.time(),
                    "results": [],
                    "count": 0,
                }

            topic = params.get("topic", "").strip().lower()
            search_terms = [term.strip().lower() for term in params.get("search_terms", [])]
            tags = [tag.strip().lower() for tag in params.get("tags", [])]
            min_confidence = params.get("min_confidence", 1)
            max_results = params.get("max_results", 10)

            results = []

            # If specific topic requested, try exact match first
            if topic and topic in research_db:
                entry = research_db[topic]
                if entry["confidence_level"] >= min_confidence:
                    results.append(entry)

            # Search through all entries for partial matches
            for entry_topic, entry_data in research_db.items():
                if len(results) >= max_results:
                    break
                    
                # Skip if already included
                if entry_data in results:
                    continue
                    
                # Check confidence level
                if entry_data["confidence_level"] < min_confidence:
                    continue

                match_found = False

                # Check search terms in topic, summary, and key facts
                if search_terms:
                    for term in search_terms:
                        if (term in entry_topic or 
                            term in entry_data["summary"].lower() or
                            any(term in fact.lower() for fact in entry_data["key_facts"])):
                            match_found = True
                            break

                # Check tags
                if tags and not match_found:
                    entry_tags = [tag.lower() for tag in entry_data["tags"]]
                    if any(tag in entry_tags for tag in tags):
                        match_found = True

                # If no specific search criteria, include all entries
                if not topic and not search_terms and not tags:
                    match_found = True

                if match_found:
                    results.append(entry_data)

            # Sort by confidence level and last updated
            results.sort(key=lambda x: (x["confidence_level"], x["last_updated"]), reverse=True)
            results = results[:max_results]

            logger.debug(f"Research query returned {len(results)} results")

            return {
                "status": "success",
                "message": f"Found {len(results)} research entries",
                "timestamp": time.time(),
                "results": results,
                "count": len(results),
                "query_params": {
                    "topic": topic,
                    "search_terms": search_terms,
                    "tags": tags,
                    "min_confidence": min_confidence,
                }
            }

        except Exception as e:
            logger.error(f"Error querying research: {e}", exc_info=True)
            return {
                "status": "failure",
                "error": f"Research query failed: {str(e)}",
                "timestamp": time.time(),
            }
