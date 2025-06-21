"""
AI Summary Generation Service for Node Summarization

This service generates concise, informative summaries of collapsed nodes
using AI to help the main AI understand what's in each node without
expanding it fully.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import httpx

from chatbot.config import settings

logger = logging.getLogger(__name__)


class NodeSummaryService:
    """Service for generating AI summaries of world state nodes."""
    
    def __init__(self, api_key: str, model: Optional[str] = None):
        self.api_key = api_key
        self.summary_model = model or settings.ai.summary_model
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
    
    async def generate_node_summary(
        self, 
        node_path: str, 
        node_data: Any, 
        node_type: Optional[str] = None
    ) -> str:
        """
        Generate a concise summary of a node's data.
        
        Args:
            node_path: The path identifier of the node
            node_data: The actual data content of the node
            node_type: Optional hint about the type of node (channel, user, thread, etc.)
        
        Returns:
            A one-sentence summary string
        """
        try:
            # Determine node type from path if not provided
            if node_type is None:
                node_type = self._infer_node_type(node_path)
            
            # Create appropriate summary prompt based on node type
            prompt = self._create_summary_prompt(node_path, node_data, node_type)
            
            # Generate summary using OpenRouter API (same as main AI engine)
            payload = {
                "model": self.summary_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 100,
                "temperature": 0.3
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.base_url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://github.com/ratimics/chatbot",
                        "X-Title": "Ratimics Chatbot Node Summary",
                    },
                )
                
                if response.status_code != 200:
                    logger.warning(f"Summary API request failed with {response.status_code}, using fallback")
                    return self._create_fallback_summary(node_path, node_data, node_type)
                
                result = response.json()
                if not result.get("choices") or not result["choices"]:
                    logger.warning("Empty response from summary API, using fallback")
                    return self._create_fallback_summary(node_path, node_data, node_type)
                
                ai_response = result["choices"][0]["message"]["content"]
                summary = self._extract_summary(ai_response)
            
            logger.debug(f"Generated summary for {node_path}: {summary}")
            return summary
            
        except Exception as e:
            logger.error(f"Failed to generate summary for {node_path}: {e}")
            # Return a fallback heuristic summary
            return self._create_fallback_summary(node_path, node_data, node_type)
    
    async def generate_multiple_summaries(
        self, 
        node_requests: List[Dict[str, Any]]
    ) -> Dict[str, str]:
        """
        Generate summaries for multiple nodes efficiently.
        
        Args:
            node_requests: List of dicts with keys: node_path, node_data, node_type
        
        Returns:
            Dictionary mapping node_path to summary string
        """
        if not node_requests:
            return {}
        
        # Generate summaries concurrently for efficiency
        tasks = [
            self.generate_node_summary(
                req["node_path"], 
                req["node_data"], 
                req.get("node_type")
            )
            for req in node_requests
        ]
        
        try:
            summaries = await asyncio.gather(*tasks, return_exceptions=True)
            
            results = {}
            for i, summary in enumerate(summaries):
                node_path = node_requests[i]["node_path"]
                if isinstance(summary, Exception):
                    logger.error(f"Summary generation failed for {node_path}: {summary}")
                    # Use fallback summary
                    results[node_path] = self._create_fallback_summary(
                        node_path, 
                        node_requests[i]["node_data"], 
                        node_requests[i].get("node_type")
                    )
                else:
                    results[node_path] = summary
            
            return results
            
        except Exception as e:
            logger.error(f"Batch summary generation failed: {e}")
            # Generate fallback summaries for all
            return {
                req["node_path"]: self._create_fallback_summary(
                    req["node_path"], 
                    req["node_data"], 
                    req.get("node_type")
                )
                for req in node_requests
            }
    
    def _infer_node_type(self, node_path: str) -> str:
        """Infer the type of node from its path."""
        path_parts = node_path.split(".")
        if len(path_parts) >= 2:
            return path_parts[1]  # e.g., "channels.matrix.room" -> "matrix"
        elif len(path_parts) >= 1:
            return path_parts[0]  # e.g., "system" -> "system"
        else:
            return "unknown"
    
    def _create_summary_prompt(self, node_path: str, node_data: Any, node_type: str) -> str:
        """Create an appropriate summary prompt based on node type."""
        
        # Convert data to JSON string for the prompt
        try:
            if isinstance(node_data, (dict, list)):
                data_str = json.dumps(node_data, indent=2, default=str)
            else:
                data_str = str(node_data)
        except Exception:
            data_str = str(node_data)
        
        # Truncate if too long for summary generation
        if len(data_str) > 2000:
            data_str = data_str[:2000] + "... [truncated]"
        
        base_prompt = f"""You are summarizing a node in a chatbot's world state for overview purposes.

Node Path: {node_path}
Node Type: {node_type}

Create a single, informative sentence that summarizes the key information in this node. The summary should help an AI assistant understand what's in this node without seeing the full details.

Node Data:
{data_str}

Summary Guidelines:
- One sentence only
- Include the most relevant/recent information
- Mention key numbers (message counts, user counts, etc.) if applicable
- Be specific about what makes this node important or interesting
- Focus on current state and recent activity

Summary:"""

        return base_prompt
    
    def _extract_summary(self, ai_response: str) -> str:
        """Extract and clean the summary from AI response."""
        # Remove any extra whitespace and common prefixes
        summary = ai_response.strip()
        
        # Remove common prefixes that the AI might add
        prefixes_to_remove = [
            "Summary:", "The summary is:", "Here's a summary:", 
            "This node", "The node", "Summary of"
        ]
        
        for prefix in prefixes_to_remove:
            if summary.lower().startswith(prefix.lower()):
                summary = summary[len(prefix):].strip()
                if summary.startswith(":"):
                    summary = summary[1:].strip()
        
        # Ensure it ends with a period
        if summary and not summary.endswith(('.', '!', '?')):
            summary += "."
        
        # Truncate if still too long
        if len(summary) > 200:
            summary = summary[:197] + "..."
        
        return summary
    
    def _create_fallback_summary(self, node_path: str, node_data: Any, node_type: str) -> str:
        """Create a heuristic summary when AI generation fails."""
        try:
            if node_type in ["matrix", "farcaster"] and isinstance(node_data, dict):
                # Channel-like data
                if "messages" in node_data:
                    msg_count = len(node_data.get("messages", []))
                    return f"Channel {node_path} with {msg_count} recent messages."
                elif "recent_messages" in node_data:
                    msg_count = len(node_data.get("recent_messages", []))
                    return f"Channel {node_path} with {msg_count} recent messages."
            
            elif node_type == "users" and isinstance(node_data, dict):
                # User data
                username = node_data.get("username") or node_data.get("display_name") or "unknown"
                return f"User {username} profile and activity data."
            
            elif node_type == "threads" and isinstance(node_data, dict):
                # Thread data
                reply_count = len(node_data.get("replies", [])) if "replies" in node_data else 0
                return f"Thread with {reply_count} replies."
            
            elif node_type == "system":
                # System data
                return f"System information: {node_path.split('.')[-1]}."
            
            else:
                # Generic fallback
                if isinstance(node_data, dict):
                    key_count = len(node_data)
                    return f"Node {node_path} containing {key_count} data fields."
                elif isinstance(node_data, list):
                    item_count = len(node_data)
                    return f"Node {node_path} containing {item_count} items."
                else:
                    return f"Node {node_path} with {node_type} data."
        
        except Exception as e:
            logger.warning(f"Fallback summary generation failed for {node_path}: {e}")
            return f"Node {node_path} (summary unavailable)."
