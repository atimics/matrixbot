"""
Enhanced Configuration Management System

Provides robust configuration validation, environment management,
and runtime configuration updates for the chatbot system.
"""

import os
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Type, get_type_hints
from dataclasses import dataclass, field
from datetime import datetime
import re
from enum import Enum

logger = logging.getLogger(__name__)


class ConfigValidationLevel(Enum):
    """Configuration validation strictness levels."""
    STRICT = "strict"      # All validations must pass
    MODERATE = "moderate"  # Critical validations must pass
    LENIENT = "lenient"    # Only basic validations


@dataclass
class ConfigRule:
    """Configuration validation rule."""
    key: str
    validator: str  # regex pattern or validator name
    required: bool = False
    default: Any = None
    description: str = ""
    validation_level: ConfigValidationLevel = ConfigValidationLevel.MODERATE


@dataclass
class ConfigSection:
    """Configuration section with validation rules."""
    name: str
    description: str
    rules: List[ConfigRule] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)  # Other sections this depends on


class ConfigurationManager:
    """Enhanced configuration management with validation and environment handling."""
    
    def __init__(self, config_dir: str = "config", validation_level: ConfigValidationLevel = ConfigValidationLevel.MODERATE):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)
        self.validation_level = validation_level
        self.sections: Dict[str, ConfigSection] = {}
        self.current_config: Dict[str, Any] = {}
        self.validation_errors: List[str] = []
        self.warnings: List[str] = []
        
        self._setup_default_sections()
    
    def _setup_default_sections(self):
        """Set up default configuration sections with validation rules."""
        
        # Core System Configuration
        core_section = ConfigSection(
            name="core",
            description="Core system configuration",
            rules=[
                ConfigRule("CHATBOT_DB_PATH", r"^.+\.db$", required=True, default="data/chatbot.db", description="SQLite database path"),
                ConfigRule("LOG_LEVEL", r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$", required=True, default="INFO", description="Logging level"),
                ConfigRule("OBSERVATION_INTERVAL", r"^\d+(\.\d+)?$", required=True, default="2.0", description="Observation cycle interval in seconds"),
                ConfigRule("MAX_CYCLES_PER_HOUR", r"^\d+$", required=True, default="300", description="Maximum observation cycles per hour"),
                ConfigRule("MAX_ACTIONS_PER_HOUR", r"^\d+$", required=True, default="600", description="Maximum actions per hour"),
            ]
        )
        self.sections["core"] = core_section
        
        # AI Configuration
        ai_section = ConfigSection(
            name="ai",
            description="AI service configuration",
            rules=[
                ConfigRule("OPENROUTER_API_KEY", r"^sk-[a-zA-Z0-9_-]+$", required=False, description="OpenRouter API key"),
                ConfigRule("AI_MODEL", r"^[a-zA-Z0-9/_-]+$", required=True, default="openai/gpt-4o-mini", description="Primary AI model"),
                ConfigRule("AI_MULTIMODAL_MODEL", r"^[a-zA-Z0-9/_-]+$", required=True, default="openai/gpt-4o", description="Multimodal AI model"),
                ConfigRule("AI_CONVERSATION_HISTORY_LENGTH", r"^\d+$", required=True, default="3", description="Conversation history length for AI"),
                ConfigRule("AI_ACTION_HISTORY_LENGTH", r"^\d+$", required=True, default="15", description="Action history length for AI"),
                ConfigRule("AI_CONTEXT_TOKEN_THRESHOLD", r"^\d+$", required=True, default="8000", description="Token threshold for context switching"),
                ConfigRule("AI_ENABLE_PROMPT_LOGGING", r"^(true|false)$", required=True, default="true", description="Enable prompt logging"),
                ConfigRule("AI_LOG_TOKEN_USAGE", r"^(true|false)$", required=True, default="true", description="Log token usage"),
            ]
        )
        self.sections["ai"] = ai_section
        
        # Matrix Configuration
        matrix_section = ConfigSection(
            name="matrix",
            description="Matrix platform configuration",
            rules=[
                ConfigRule("MATRIX_HOMESERVER", r"^https?://[a-zA-Z0-9.-]+$", required=False, description="Matrix homeserver URL"),
                ConfigRule("MATRIX_USER_ID", r"^@[a-zA-Z0-9._=-]+:[a-zA-Z0-9.-]+$", required=False, description="Matrix user ID"),
                ConfigRule("MATRIX_PASSWORD", r"^.{8,}$", required=False, description="Matrix password (min 8 chars)"),
                ConfigRule("MATRIX_ROOM_ID", r"^[!#][a-zA-Z0-9._=-]+:[a-zA-Z0-9.-]+$", required=False, description="Matrix room ID"),
                ConfigRule("MATRIX_DEVICE_ID", r"^[a-zA-Z0-9_-]*$", required=False, description="Matrix device ID"),
                ConfigRule("DEVICE_NAME", r"^[a-zA-Z0-9_-]+$", required=True, default="ratichat_bot", description="Device name"),
            ]
        )
        self.sections["matrix"] = matrix_section
        
        # Farcaster Configuration
        farcaster_section = ConfigSection(
            name="farcaster",
            description="Farcaster platform configuration",
            rules=[
                ConfigRule("NEYNAR_API_KEY", r"^[a-zA-Z0-9_-]{32,}$", required=False, description="Neynar API key"),
                ConfigRule("FARCASTER_BOT_FID", r"^\d+$", required=False, description="Farcaster bot FID"),
                ConfigRule("FARCASTER_BOT_SIGNER_UUID", r"^[0-9a-f-]{36}$", required=False, description="Farcaster signer UUID"),
                ConfigRule("FARCASTER_MIN_POST_INTERVAL_MINUTES", r"^\d+$", required=True, default="1", description="Minimum post interval"),
                ConfigRule("FARCASTER_API_TIMEOUT", r"^\d+(\.\d+)?$", required=True, default="30.0", description="API timeout seconds"),
            ]
        )
        self.sections["farcaster"] = farcaster_section
        
        # Performance Configuration
        performance_section = ConfigSection(
            name="performance",
            description="Performance and resource limits",
            rules=[
                ConfigRule("IMAGE_GENERATION_COOLDOWN_SECONDS", r"^\d+$", required=True, default="120", description="Image generation cooldown"),
                ConfigRule("VIDEO_GENERATION_COOLDOWN_SECONDS", r"^\d+$", required=True, default="600", description="Video generation cooldown"),
                ConfigRule("MAX_IMAGE_GENERATIONS_PER_HOUR", r"^\d+$", required=True, default="15", description="Max images per hour"),
                ConfigRule("MAX_VIDEO_GENERATIONS_PER_HOUR", r"^\d+$", required=True, default="5", description="Max videos per hour"),
                ConfigRule("MAX_EXPANDED_NODES", r"^\d+$", required=True, default="8", description="Max expanded nodes"),
            ]
        )
        self.sections["performance"] = performance_section
    
    def load_configuration(self, sources: Optional[List[str]] = None) -> Dict[str, Any]:
        """Load configuration from multiple sources with validation."""
        
        self.current_config = {}
        self.validation_errors = []
        self.warnings = []
        
        # Default sources
        if sources is None:
            sources = [
                ".env",
                "config/default.json",
                "config/local.json",
                "environment"
            ]
        
        # Load from each source
        for source in sources:
            try:
                if source == "environment":
                    self._load_from_environment()
                elif source.endswith(".env"):
                    self._load_from_env_file(source)
                elif source.endswith(".json"):
                    self._load_from_json_file(source)
                else:
                    logger.warning(f"Unknown configuration source type: {source}")
            except Exception as e:
                logger.error(f"Error loading configuration from {source}: {e}")
        
        # Validate configuration
        self._validate_configuration()
        
        # Apply defaults for missing required values
        self._apply_defaults()
        
        # Log configuration status
        self._log_configuration_status()
        
        return self.current_config
    
    def validate_configuration(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """Validate configuration against rules."""
        
        if config is not None:
            self.current_config = config
        
        self.validation_errors = []
        self.warnings = []
        
        return self._validate_configuration()
    
    def get_configuration_schema(self) -> Dict[str, Any]:
        """Get configuration schema for documentation/UI generation."""
        
        schema = {
            "sections": {},
            "validation_level": self.validation_level.value,
            "last_updated": datetime.now().isoformat()
        }
        
        for section_name, section in self.sections.items():
            schema["sections"][section_name] = {
                "name": section.name,
                "description": section.description,
                "depends_on": section.depends_on,
                "rules": [
                    {
                        "key": rule.key,
                        "validator": rule.validator,
                        "required": rule.required,
                        "default": rule.default,
                        "description": rule.description,
                        "validation_level": rule.validation_level.value
                    }
                    for rule in section.rules
                ]
            }
        
        return schema
    
    def export_configuration_template(self, filepath: str, format: str = "env"):
        """Export configuration template with documentation."""
        
        if format == "env":
            self._export_env_template(filepath)
        elif format == "json":
            self._export_json_template(filepath)
        else:
            raise ValueError(f"Unsupported export format: {format}")
    
    def get_configuration_status(self) -> Dict[str, Any]:
        """Get current configuration status and health."""
        
        total_rules = sum(len(section.rules) for section in self.sections.values())
        configured_count = len([key for key in self.current_config.keys() if self.current_config[key] is not None])
        
        return {
            "timestamp": datetime.now().isoformat(),
            "validation_level": self.validation_level.value,
            "total_rules": total_rules,
            "configured_count": configured_count,
            "configuration_coverage": configured_count / total_rules if total_rules > 0 else 0,
            "validation_errors": len(self.validation_errors),
            "warnings": len(self.warnings),
            "is_valid": len(self.validation_errors) == 0,
            "critical_missing": self._get_critical_missing(),
            "optional_missing": self._get_optional_missing(),
            "errors": self.validation_errors,
            "warnings": self.warnings
        }
    
    def _load_from_environment(self):
        """Load configuration from environment variables."""
        
        for section in self.sections.values():
            for rule in section.rules:
                value = os.getenv(rule.key)
                if value is not None:
                    self.current_config[rule.key] = value
    
    def _load_from_env_file(self, filepath: str):
        """Load configuration from .env file."""
        
        env_path = Path(filepath)
        if not env_path.exists():
            logger.debug(f"Env file not found: {filepath}")
            return
        
        try:
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"\'')
                        self.current_config[key] = value
        except Exception as e:
            logger.error(f"Error reading env file {filepath}: {e}")
    
    def _load_from_json_file(self, filepath: str):
        """Load configuration from JSON file."""
        
        json_path = Path(filepath)
        if not json_path.exists():
            logger.debug(f"JSON file not found: {filepath}")
            return
        
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
                self.current_config.update(data)
        except Exception as e:
            logger.error(f"Error reading JSON file {filepath}: {e}")
    
    def _validate_configuration(self) -> bool:
        """Validate current configuration against rules."""
        
        is_valid = True
        
        for section in self.sections.values():
            for rule in section.rules:
                value = self.current_config.get(rule.key)
                
                # Check required fields
                if rule.required and value is None:
                    error_msg = f"Required configuration missing: {rule.key}"
                    if rule.validation_level.value in [ConfigValidationLevel.STRICT.value, ConfigValidationLevel.MODERATE.value]:
                        self.validation_errors.append(error_msg)
                        is_valid = False
                    else:
                        self.warnings.append(error_msg)
                    continue
                
                # Skip validation if value is None and not required
                if value is None:
                    continue
                
                # Validate format
                if not self._validate_value(rule, str(value)):
                    error_msg = f"Invalid format for {rule.key}: {value}. Expected: {rule.description}"
                    if rule.validation_level.value == ConfigValidationLevel.STRICT.value:
                        self.validation_errors.append(error_msg)
                        is_valid = False
                    else:
                        self.warnings.append(error_msg)
        
        return is_valid
    
    def _validate_value(self, rule: ConfigRule, value: str) -> bool:
        """Validate a single configuration value."""
        
        # Special validators
        if rule.validator == "url":
            return self._validate_url(value)
        elif rule.validator == "email":
            return self._validate_email(value)
        elif rule.validator == "path":
            return self._validate_path(value)
        else:
            # Regex validation
            return bool(re.match(rule.validator, value))
    
    def _validate_url(self, value: str) -> bool:
        """Validate URL format."""
        url_pattern = r"^https?://[a-zA-Z0-9.-]+(?:\:[0-9]+)?(?:/.*)?$"
        return bool(re.match(url_pattern, value))
    
    def _validate_email(self, value: str) -> bool:
        """Validate email format."""
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return bool(re.match(email_pattern, value))
    
    def _validate_path(self, value: str) -> bool:
        """Validate file path."""
        try:
            Path(value)
            return True
        except Exception:
            return False
    
    def _apply_defaults(self):
        """Apply default values for missing configuration."""
        
        for section in self.sections.values():
            for rule in section.rules:
                if rule.key not in self.current_config and rule.default is not None:
                    self.current_config[rule.key] = rule.default
                    logger.debug(f"Applied default value for {rule.key}: {rule.default}")
    
    def _get_critical_missing(self) -> List[str]:
        """Get list of critical missing configuration items."""
        
        critical_missing = []
        for section in self.sections.values():
            for rule in section.rules:
                if (rule.required and 
                    rule.validation_level in [ConfigValidationLevel.STRICT, ConfigValidationLevel.MODERATE] and
                    self.current_config.get(rule.key) is None):
                    critical_missing.append(rule.key)
        
        return critical_missing
    
    def _get_optional_missing(self) -> List[str]:
        """Get list of optional missing configuration items."""
        
        optional_missing = []
        for section in self.sections.values():
            for rule in section.rules:
                if (not rule.required and self.current_config.get(rule.key) is None):
                    optional_missing.append(rule.key)
        
        return optional_missing
    
    def _log_configuration_status(self):
        """Log configuration loading status."""
        
        status = self.get_configuration_status()
        
        logger.debug(f"Configuration loaded: {status['configured_count']}/{status['total_rules']} items configured")
        logger.debug(f"Configuration coverage: {status['configuration_coverage']:.1%}")
        
        if status['validation_errors']:
            logger.error(f"Configuration validation errors: {len(status['validation_errors'])}")
            for error in status['validation_errors']:
                logger.error(f"  - {error}")
        
        if status['warnings']:
            logger.warning(f"Configuration warnings: {len(status['warnings'])}")
            for warning in status['warnings']:
                logger.warning(f"  - {warning}")
        
        if status['critical_missing']:
            logger.error(f"Critical configuration missing: {', '.join(status['critical_missing'])}")
    
    def _export_env_template(self, filepath: str):
        """Export .env template file."""
        
        with open(filepath, 'w') as f:
            f.write("# RatiChat Configuration Template\n")
            f.write(f"# Generated on {datetime.now().isoformat()}\n\n")
            
            for section_name, section in self.sections.items():
                f.write(f"# {section.description.upper()}\n")
                f.write("# " + "=" * 50 + "\n\n")
                
                for rule in section.rules:
                    f.write(f"# {rule.description}\n")
                    if rule.required:
                        f.write(f"# REQUIRED\n")
                    else:
                        f.write(f"# OPTIONAL\n")
                    
                    if rule.default is not None:
                        f.write(f"{rule.key}={rule.default}\n")
                    else:
                        f.write(f"# {rule.key}=\n")
                    f.write("\n")
                
                f.write("\n")
        
        logger.debug(f"Configuration template exported to {filepath}")
    
    def _export_json_template(self, filepath: str):
        """Export JSON template file."""
        
        template = {
            "_metadata": {
                "description": "RatiChat Configuration Template",
                "generated": datetime.now().isoformat(),
                "validation_level": self.validation_level.value
            }
        }
        
        for section_name, section in self.sections.items():
            template[section_name] = {
                "_description": section.description,
                "_depends_on": section.depends_on
            }
            
            for rule in section.rules:
                template[section_name][rule.key] = {
                    "value": rule.default,
                    "description": rule.description,
                    "required": rule.required,
                    "validator": rule.validator
                }
        
        with open(filepath, 'w') as f:
            json.dump(template, f, indent=2)
        
        logger.debug(f"JSON configuration template exported to {filepath}")


# Global configuration manager instance
config_manager = ConfigurationManager()
