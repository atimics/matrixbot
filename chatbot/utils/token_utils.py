"""
Token estimation utilities for AI payload optimization.
"""

import json
from typing import Any, Dict

def estimate_token_count(payload: Dict[str, Any]) -> int:
    """
    Estimate the token count for a payload using a heuristic approach.
    
    This uses a simple approximation: roughly 4 characters per token for English text.
    This is conservative to ensure we stay under limits.
    
    Args:
        payload: The payload dictionary to estimate tokens for
        
    Returns:
        Estimated token count
    """
    try:
        # Convert payload to JSON string to get accurate character count
        payload_str = json.dumps(payload, ensure_ascii=False)
        
        # Use conservative estimate: 3.5 characters per token (rounded up to 4)
        # This accounts for the fact that JSON has more punctuation/structure
        estimated_tokens = len(payload_str) // 3.5
        
        return int(estimated_tokens)
    except Exception:
        # Fallback: use string length approximation
        payload_str = str(payload)
        return len(payload_str) // 3.5


def should_use_node_based_payload(payload_size_estimate: int, threshold: int) -> bool:
    """
    Determine if we should switch to node-based payload based on estimated size.
    
    Args:
        payload_size_estimate: Estimated token count for full payload
        threshold: Token threshold from configuration
        
    Returns:
        True if should use node-based payload, False otherwise
    """
    return payload_size_estimate >= threshold
