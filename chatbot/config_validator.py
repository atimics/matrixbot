"""
Configuration validation system.

Provides comprehensive validation of all configuration settings
to ensure proper system startup and operation.
"""

import os
import logging
from typing import Dict, List, Any, Optional, Type, Union
from dataclasses import dataclass
from pathlib import Path

from .exceptions import ConfigurationError
from .config import settings


logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of configuration validation."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    
    def __post_init__(self):
        if self.errors:
            self.is_valid = False


class ConfigValidator:
    """Validates all required configuration at startup."""
    
    # Required settings that must be present for basic operation
    REQUIRED_SETTINGS = {
        'OPENROUTER_API_KEY': str,
        'CHATBOT_DB_PATH': str,
        'LOG_LEVEL': str,
    }
    
    # Settings required for Matrix integration
    MATRIX_REQUIRED = {
        'MATRIX_HOMESERVER': str,
        'MATRIX_USER_ID': str,
        'MATRIX_PASSWORD': str,
        'MATRIX_ROOM_ID': str,
    }
    
    # Settings required for Farcaster integration
    FARCASTER_REQUIRED = {
        'NEYNAR_API_KEY': str,
        'FARCASTER_BOT_FID': str,
        'FARCASTER_BOT_SIGNER_UUID': str,
    }
    
    # Optional settings with defaults
    OPTIONAL_SETTINGS = {
        'AI_MODEL': str,
        'AI_MULTIMODAL_MODEL': str,
        'OBSERVATION_INTERVAL': (int, float),
        'MAX_CYCLES_PER_HOUR': int,
        'MAX_ACTIONS_PER_HOUR': int,
        'DEVICE_NAME': str,
    }
    
    # Settings that should be file paths
    PATH_SETTINGS = {
        'CHATBOT_DB_PATH': {'must_exist_parent': True, 'create_if_missing': True},
    }
    
    # Settings that should be URLs
    URL_SETTINGS = {
        'MATRIX_HOMESERVER': {'schemes': ['http', 'https']},
        'ARWEAVE_GATEWAY_URL': {'schemes': ['http', 'https']},
        'OLLAMA_API_URL': {'schemes': ['http', 'https']},
    }

    @classmethod
    def validate_all(cls) -> ValidationResult:
        """Validate all configuration settings."""
        errors = []
        warnings = []
        
        try:
            # Check core required settings
            core_errors = cls._validate_required_settings(cls.REQUIRED_SETTINGS)
            errors.extend(core_errors)
            
            # Check integration settings
            matrix_errors, matrix_warnings = cls._validate_integration_settings(
                "Matrix", cls.MATRIX_REQUIRED
            )
            errors.extend(matrix_errors)
            warnings.extend(matrix_warnings)
            
            farcaster_errors, farcaster_warnings = cls._validate_integration_settings(
                "Farcaster", cls.FARCASTER_REQUIRED
            )
            errors.extend(farcaster_errors)
            warnings.extend(farcaster_warnings)
            
            # Check optional settings
            optional_warnings = cls._validate_optional_settings()
            warnings.extend(optional_warnings)
            
            # Validate file paths
            path_errors = cls._validate_path_settings()
            errors.extend(path_errors)
            
            # Validate URLs
            url_errors = cls._validate_url_settings()
            errors.extend(url_errors)
            
            # Check for deprecated settings
            deprecated_warnings = cls._check_deprecated_settings()
            warnings.extend(deprecated_warnings)
            
        except Exception as e:
            errors.append(f"Configuration validation failed: {e}")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    @classmethod
    def _validate_required_settings(cls, required_settings: Dict[str, Type]) -> List[str]:
        """Validate required settings."""
        errors = []
        
        for key, expected_type in required_settings.items():
            value = getattr(settings, key, None)
            
            if not value:
                errors.append(f"Missing required setting: {key}")
                continue
            
            if not isinstance(value, expected_type):
                errors.append(
                    f"Invalid type for {key}: expected {expected_type.__name__}, "
                    f"got {type(value).__name__}"
                )
        
        return errors
    
    @classmethod
    def _validate_integration_settings(
        cls, integration_name: str, required_settings: Dict[str, Type]
    ) -> tuple[List[str], List[str]]:
        """Validate settings for a specific integration."""
        errors = []
        warnings = []
        
        # Check if any of the integration settings are present
        has_any_setting = any(
            getattr(settings, key, None) for key in required_settings.keys()
        )
        
        if not has_any_setting:
            warnings.append(
                f"{integration_name} integration disabled: no configuration found"
            )
            return errors, warnings
        
        # If some settings are present, validate all required ones
        missing_settings = []
        for key, expected_type in required_settings.items():
            value = getattr(settings, key, None)
            
            if not value:
                missing_settings.append(key)
                continue
            
            if not isinstance(value, expected_type):
                errors.append(
                    f"Invalid type for {integration_name} setting {key}: "
                    f"expected {expected_type.__name__}, got {type(value).__name__}"
                )
        
        if missing_settings:
            errors.append(
                f"{integration_name} integration partially configured. "
                f"Missing required settings: {', '.join(missing_settings)}"
            )
        
        return errors, warnings
    
    @classmethod
    def _validate_optional_settings(cls) -> List[str]:
        """Validate optional settings."""
        warnings = []
        
        for key, expected_type in cls.OPTIONAL_SETTINGS.items():
            value = getattr(settings, key, None)
            
            if value is None:
                continue
            
            # Handle multiple allowed types
            if isinstance(expected_type, tuple):
                if not isinstance(value, expected_type):
                    warnings.append(
                        f"Invalid type for optional setting {key}: "
                        f"expected one of {[t.__name__ for t in expected_type]}, "
                        f"got {type(value).__name__}"
                    )
            else:
                if not isinstance(value, expected_type):
                    warnings.append(
                        f"Invalid type for optional setting {key}: "
                        f"expected {expected_type.__name__}, got {type(value).__name__}"
                    )
        
        return warnings
    
    @classmethod
    def _validate_path_settings(cls) -> List[str]:
        """Validate file path settings."""
        errors = []
        
        for key, path_config in cls.PATH_SETTINGS.items():
            value = getattr(settings, key, None)
            if not value:
                continue
            
            path = Path(value)
            
            # Check if parent directory exists or can be created
            if path_config.get('must_exist_parent', False):
                parent = path.parent
                if not parent.exists():
                    try:
                        parent.mkdir(parents=True, exist_ok=True)
                        logger.info(f"Created directory: {parent}")
                    except Exception as e:
                        errors.append(f"Cannot create directory for {key} ({parent}): {e}")
            
            # Create file if it doesn't exist and flag is set
            if path_config.get('create_if_missing', False) and not path.exists():
                try:
                    path.touch()
                    logger.info(f"Created file: {path}")
                except Exception as e:
                    errors.append(f"Cannot create file for {key} ({path}): {e}")
        
        return errors
    
    @classmethod
    def _validate_url_settings(cls) -> List[str]:
        """Validate URL settings."""
        errors = []
        
        for key, url_config in cls.URL_SETTINGS.items():
            value = getattr(settings, key, None)
            if not value:
                continue
            
            # Basic URL validation
            if not isinstance(value, str):
                errors.append(f"{key} must be a string URL")
                continue
            
            # Check scheme
            allowed_schemes = url_config.get('schemes', ['http', 'https'])
            if not any(value.startswith(f"{scheme}://") for scheme in allowed_schemes):
                errors.append(
                    f"{key} must start with one of: {', '.join(f'{s}://' for s in allowed_schemes)}"
                )
        
        return errors
    
    @classmethod
    def _check_deprecated_settings(cls) -> List[str]:
        """Check for deprecated settings."""
        warnings = []
        
        deprecated_settings = {
            'OPENAI_API_KEY': 'Use OPENROUTER_API_KEY instead',
            'HUGGINGFACE_API_TOKEN': 'Use OPENROUTER_API_KEY instead',
        }
        
        for old_key, replacement_msg in deprecated_settings.items():
            if hasattr(settings, old_key) and getattr(settings, old_key):
                warnings.append(f"Setting {old_key} is deprecated. {replacement_msg}")
        
        return warnings
    
    @classmethod
    def validate_and_raise(cls) -> None:
        """Validate configuration and raise exception if invalid."""
        result = cls.validate_all()
        
        # Log warnings
        for warning in result.warnings:
            logger.warning(f"Configuration warning: {warning}")
        
        # Raise exception for errors
        if not result.is_valid:
            error_msg = "Configuration validation failed:\n" + "\n".join(
                f"  - {error}" for error in result.errors
            )
            raise ConfigurationError(error_msg, {"errors": result.errors, "warnings": result.warnings})
        
        logger.info("Configuration validation passed")
    
    @classmethod
    def get_validation_summary(cls) -> Dict[str, Any]:
        """Get a summary of configuration validation status."""
        result = cls.validate_all()
        
        return {
            "valid": result.is_valid,
            "error_count": len(result.errors),
            "warning_count": len(result.warnings),
            "errors": result.errors,
            "warnings": result.warnings,
            "integrations": {
                "matrix": cls._check_integration_status("Matrix", cls.MATRIX_REQUIRED),
                "farcaster": cls._check_integration_status("Farcaster", cls.FARCASTER_REQUIRED),
            }
        }
    
    @classmethod
    def _check_integration_status(cls, name: str, required: Dict[str, Type]) -> Dict[str, Any]:
        """Check the status of a specific integration."""
        configured_count = sum(
            1 for key in required.keys() 
            if getattr(settings, key, None)
        )
        
        total_required = len(required)
        is_fully_configured = configured_count == total_required
        is_partially_configured = 0 < configured_count < total_required
        
        return {
            "configured": is_fully_configured,
            "partial": is_partially_configured,
            "configured_settings": configured_count,
            "total_required": total_required,
            "status": (
                "enabled" if is_fully_configured else
                "partial" if is_partially_configured else
                "disabled"
            )
        }
