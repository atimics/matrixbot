"""
Base classes for processors in the chatbot system.

This module defines the common interface that all processors must implement
for the Commander/Sub-Agent architecture.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class Processor(ABC):
    """
    Base class for all processors in the system.
    
    This defines the common interface that both the Commander AI (AdaptiveProcessor)
    and Sub-Agents (MissionProcessor) must implement.
    """
    
    @abstractmethod
    async def process_cycle(
        self,
        cycle_id: str,
        primary_channel_id: Optional[str],
        context: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Process a single cycle of operation.
        
        Args:
            cycle_id: Unique identifier for this processing cycle
            primary_channel_id: Primary channel to focus on
            context: Additional context for processing
            
        Returns:
            Processing result (structure varies by processor type)
        """
        pass
    
    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """
        Get current processor status.
        
        Returns:
            Dictionary containing processor status information
        """
        pass
