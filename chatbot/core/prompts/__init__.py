"""
Modular AI system prompt management.

This module provides a structured approach to managing AI system prompts
by breaking them into logical components that can be easily maintained,
tested, and customized.
"""

from pathlib import Path
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

# Base prompts directory
PROMPTS_DIR = Path(__file__).parent


class PromptBuilder:
    """Builds AI system prompts from modular components."""
    
    def __init__(self):
        self.sections: Dict[str, str] = {}
        self._load_prompt_sections()
    
    def _load_prompt_sections(self):
        """Load all prompt sections from files."""
        try:
            # Core identity and capabilities
            self.sections["identity"] = self._load_section("identity.txt")
            self.sections["capabilities"] = self._load_section("capabilities.txt") 
            self.sections["world_state_context"] = self._load_section("world_state_context.txt")
            self.sections["tools_context"] = self._load_section("tools_context.txt")
            self.sections["interaction_style"] = self._load_section("interaction_style.txt")
            self.sections["safety_guidelines"] = self._load_section("safety_guidelines.txt")
            
            # Platform-specific sections
            self.sections["matrix_context"] = self._load_section("matrix_context.txt")
            self.sections["farcaster_context"] = self._load_section("farcaster_context.txt")
            
        except Exception as e:
            logger.error(f"Error loading prompt sections: {e}")
            # Fallback to basic prompt if files aren't available
            self._load_fallback_sections()
    
    def _load_section(self, filename: str) -> str:
        """Load a prompt section from file."""
        file_path = PROMPTS_DIR / filename
        if file_path.exists():
            return file_path.read_text(encoding='utf-8').strip()
        else:
            logger.warning(f"Prompt section file not found: {filename}")
            return ""
    
    def _load_fallback_sections(self):
        """Load basic fallback sections if files aren't available."""
        self.sections = {
            "identity": "You are an intelligent AI chatbot assistant.",
            "capabilities": "You can help with various tasks including conversation, information retrieval, and problem-solving.",
            "world_state_context": "You maintain awareness of ongoing conversations and context.",
            "tools_context": "You have access to various tools and integrations.",
            "interaction_style": "Be helpful, informative, and engaging in your responses.",
            "safety_guidelines": "Always prioritize user safety and provide accurate information.",
            "matrix_context": "You can interact with Matrix rooms and users.",
            "farcaster_context": "You can interact with Farcaster channels and users."
        }
    
    def build_system_prompt(
        self, 
        include_sections: Optional[List[str]] = None,
        custom_context: Optional[str] = None
    ) -> str:
        """
        Build a complete system prompt from components.
        
        Args:
            include_sections: List of section names to include. If None, includes all.
            custom_context: Additional context to append to the prompt.
            
        Returns:
            Complete system prompt string.
        """
        if include_sections is None:
            include_sections = list(self.sections.keys())
        
        prompt_parts = []
        
        for section_name in include_sections:
            section_content = self.sections.get(section_name, "")
            if section_content:
                prompt_parts.append(f"## {section_name.replace('_', ' ').title()}\n{section_content}")
        
        if custom_context:
            prompt_parts.append(f"## Additional Context\n{custom_context}")
        
        return "\n\n".join(prompt_parts)
    
    def get_section(self, section_name: str) -> str:
        """Get a specific prompt section."""
        return self.sections.get(section_name, "")
    
    def update_section(self, section_name: str, content: str):
        """Update a prompt section dynamically."""
        self.sections[section_name] = content
    
    def list_sections(self) -> List[str]:
        """List all available prompt sections."""
        return list(self.sections.keys())


# Global prompt builder instance
prompt_builder = PromptBuilder()
