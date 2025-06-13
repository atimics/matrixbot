"""
S3 Service Package

Drop-in replacement for Arweave service using S3-compatible storage.
Provides the same API interface for seamless migration.
"""

try:
    from s3_uploader_client import S3UploaderClient, ArweaveUploaderClient
    from s3_service import S3Service, ArweaveService, s3_service, arweave_service
except ImportError:
    # Handle relative imports when module is run directly
    try:
        from .s3_uploader_client import S3UploaderClient, ArweaveUploaderClient
        from .s3_service import S3Service, ArweaveService, s3_service, arweave_service
    except ImportError:
        # For testing and development scenarios
        S3UploaderClient = None
        ArweaveUploaderClient = None
        S3Service = None
        ArweaveService = None
        s3_service = None
        arweave_service = None

__version__ = "1.0.0"
__all__ = [
    "S3UploaderClient",
    "ArweaveUploaderClient",  # Alias for compatibility
    "S3Service", 
    "ArweaveService",  # Alias for compatibility
    "s3_service",
    "arweave_service",  # Alias for compatibility
]
