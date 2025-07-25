"""
Async utilities for file processing and analysis.

This module provides optimized async file operations with concurrency control
and error handling for the developer tools system.
"""
import asyncio
import aiofiles
import logging
from typing import List, Optional, Dict, Any, Callable
from pathlib import Path
import time

logger = logging.getLogger(__name__)


class AsyncFileProcessor:
    """
    Async file processor with concurrency control and error handling.
    
    Provides utilities for reading multiple files concurrently while
    respecting system limits and handling errors gracefully.
    """
    
    def __init__(self, max_concurrent_files: int = 5, max_file_size: int = 1_000_000):
        """
        Initialize the async file processor.
        
        Args:
            max_concurrent_files: Maximum number of files to process simultaneously
            max_file_size: Maximum file size in bytes (default 1MB)
        """
        self.max_concurrent_files = max_concurrent_files
        self.max_file_size = max_file_size
        self.semaphore = asyncio.Semaphore(max_concurrent_files)
    
    async def read_file_safe(self, file_path: Path) -> Optional[str]:
        """
        Safely read a file with error handling and size checks.
        
        Args:
            file_path: Path to the file to read
            
        Returns:
            File content as string, or None if reading failed
        """
        try:
            # Check file size first
            if not file_path.exists():
                logger.warning(f"File does not exist: {file_path}")
                return None
            
            if not file_path.is_file():
                logger.warning(f"Path is not a file: {file_path}")
                return None
            
            file_size = file_path.stat().st_size
            if file_size > self.max_file_size:
                logger.warning(f"File too large ({file_size} bytes): {file_path}")
                return None
            
            # Read file content asynchronously
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                return content
                
        except UnicodeDecodeError:
            logger.warning(f"Binary file or encoding issue: {file_path}")
            return None
        except PermissionError:
            logger.warning(f"Permission denied: {file_path}")
            return None
        except Exception as e:
            logger.exception(f"Error reading file {file_path}: {e}")
            return None
    
    async def read_files_concurrent(
        self, 
        file_paths: List[Path],
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Optional[str]]:
        """
        Read multiple files concurrently with progress tracking.
        
        Args:
            file_paths: List of file paths to read
            progress_callback: Optional callback function called with (completed, total)
            
        Returns:
            Dictionary mapping file path strings to content (or None if failed)
        """
        async def read_with_semaphore(file_path: Path, index: int) -> tuple[str, Optional[str]]:
            async with self.semaphore:
                content = await self.read_file_safe(file_path)
                
                # Call progress callback if provided
                if progress_callback:
                    progress_callback(index + 1, len(file_paths))
                
                return str(file_path), content
        
        # Start all read tasks
        tasks = [
            read_with_semaphore(file_path, i) 
            for i, file_path in enumerate(file_paths)
        ]
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Build results dictionary, handling exceptions
        file_contents = {}
        for result in results:
            if isinstance(result, tuple):
                file_path, content = result
                file_contents[file_path] = content
            elif isinstance(result, Exception):
                logger.error(f"File read task failed: {result}")
        
        return file_contents
    
    async def process_files_with_function(
        self,
        file_paths: List[Path],
        process_func: Callable[[Path, str], Any],
        filter_valid: bool = True
    ) -> Dict[str, Any]:
        """
        Process multiple files with a custom processing function.
        
        Args:
            file_paths: List of file paths to process
            process_func: Function to apply to each (file_path, content) pair
            filter_valid: If True, only process files that read successfully
            
        Returns:
            Dictionary mapping file paths to processing results
        """
        # First read all files
        file_contents = await self.read_files_concurrent(file_paths)
        
        # Filter out failed reads if requested
        if filter_valid:
            valid_files = {
                path: content for path, content in file_contents.items() 
                if content is not None
            }
        else:
            valid_files = file_contents
        
        # Apply processing function with concurrency control
        async def process_with_semaphore(file_path: str, content: str) -> tuple[str, Any]:
            async with self.semaphore:
                try:
                    # Run processing function in thread pool to avoid blocking
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        None, process_func, Path(file_path), content
                    )
                    return file_path, result
                except Exception as e:
                    logger.exception(f"Error processing {file_path}: {e}")
                    return file_path, None
        
        # Process valid files
        if valid_files:
            tasks = [
                process_with_semaphore(file_path, content)
                for file_path, content in valid_files.items()
                if content is not None
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Build results dictionary
            processed_results = {}
            for result in results:
                if isinstance(result, tuple):
                    file_path, proc_result = result
                    processed_results[file_path] = proc_result
                elif isinstance(result, Exception):
                    logger.error(f"File processing task failed: {result}")
            
            return processed_results
        
        return {}


class StructuredError:
    """
    Structured error information for better error handling and UI feedback.
    """
    
    def __init__(
        self, 
        error_type: str, 
        message: str, 
        file_path: Optional[str] = None,
        line_number: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        suggested_action: Optional[str] = None
    ):
        self.error_type = error_type
        self.message = message
        self.file_path = file_path
        self.line_number = line_number
        self.context = context or {}
        self.suggested_action = suggested_action
        self.timestamp = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "error_type": self.error_type,
            "message": self.message,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "context": self.context,
            "suggested_action": self.suggested_action,
            "timestamp": self.timestamp
        }
    
    def __str__(self) -> str:
        """String representation for logging."""
        parts = [f"{self.error_type}: {self.message}"]
        if self.file_path:
            location = self.file_path
            if self.line_number:
                location += f":{self.line_number}"
            parts.append(f"at {location}")
        
        if self.suggested_action:
            parts.append(f"(Suggestion: {self.suggested_action})")
        
        return " ".join(parts)


class ErrorCollector:
    """
    Collects and categorizes errors during analysis operations.
    
    Provides structured error reporting and recovery suggestions.
    """
    
    def __init__(self):
        self.errors: List[StructuredError] = []
        self.warnings: List[StructuredError] = []
    
    def add_error(
        self, 
        error_type: str, 
        message: str,
        file_path: Optional[str] = None,
        line_number: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None,
        suggested_action: Optional[str] = None
    ) -> None:
        """Add an error to the collection."""
        error = StructuredError(
            error_type=error_type,
            message=message,
            file_path=file_path,
            line_number=line_number,
            context=context,
            suggested_action=suggested_action
        )
        self.errors.append(error)
        logger.error(str(error))
    
    def add_warning(
        self,
        warning_type: str,
        message: str,
        file_path: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add a warning to the collection."""
        warning = StructuredError(
            error_type=warning_type,
            message=message,
            file_path=file_path,
            context=context
        )
        self.warnings.append(warning)
        logger.warning(str(warning))
    
    def has_errors(self) -> bool:
        """Check if any errors were collected."""
        return len(self.errors) > 0
    
    def has_warnings(self) -> bool:
        """Check if any warnings were collected."""
        return len(self.warnings) > 0
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of collected errors and warnings."""
        error_types = {}
        for error in self.errors:
            error_types[error.error_type] = error_types.get(error.error_type, 0) + 1
        
        warning_types = {}
        for warning in self.warnings:
            warning_types[warning.error_type] = warning_types.get(warning.error_type, 0) + 1
        
        return {
            "total_errors": len(self.errors),
            "total_warnings": len(self.warnings),
            "error_types": error_types,
            "warning_types": warning_types,
            "most_common_error": max(error_types.items(), key=lambda x: x[1])[0] if error_types else None,
            "most_common_warning": max(warning_types.items(), key=lambda x: x[1])[0] if warning_types else None
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "errors": [error.to_dict() for error in self.errors],
            "warnings": [warning.to_dict() for warning in self.warnings],
            "summary": self.get_summary()
        }


async def discover_source_files(
    workspace_path: Path,
    extensions: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None,
    max_files: int = 100
) -> List[Path]:
    """
    Discover source files in a workspace with filtering.
    
    Args:
        workspace_path: Root path to search
        extensions: File extensions to include (default: common source extensions)
        exclude_patterns: Directory patterns to exclude (default: common build/cache dirs)
        max_files: Maximum number of files to return
        
    Returns:
        List of discovered file paths
    """
    if extensions is None:
        extensions = ['.py', '.js', '.ts', '.java', '.cpp', '.c', '.go', '.rs', '.rb', '.php']
    
    if exclude_patterns is None:
        exclude_patterns = [
            'node_modules', '__pycache__', '.git', '.svn', 'build', 'dist',
            'target', 'bin', '.idea', '.vscode', 'venv', '.env'
        ]
    
    discovered_files = []
    
    def should_exclude_dir(dir_path: Path) -> bool:
        """Check if directory should be excluded."""
        dir_name = dir_path.name
        return any(pattern in dir_name for pattern in exclude_patterns)
    
    def should_include_file(file_path: Path) -> bool:
        """Check if file should be included."""
        return file_path.suffix.lower() in extensions
    
    try:
        # Use asyncio.to_thread to avoid blocking the event loop during filesystem traversal
        def scan_directory():
            files = []
            for root, dirs, filenames in workspace_path.walk():
                # Filter out excluded directories
                dirs[:] = [d for d in dirs if not should_exclude_dir(root / d)]
                
                for filename in filenames:
                    file_path = root / filename
                    if should_include_file(file_path) and len(files) < max_files:
                        files.append(file_path)
                
                if len(files) >= max_files:
                    break
            
            return files
        
        discovered_files = await asyncio.to_thread(scan_directory)
        
    except Exception as e:
        logger.exception(f"Error discovering files in {workspace_path}: {e}")
    
    return discovered_files


class ProgressTracker:
    """
    Simple progress tracker for long-running operations.
    """
    
    def __init__(self, total: int, description: str = "Processing"):
        self.total = total
        self.completed = 0
        self.description = description
        self.start_time = time.time()
        self.last_update = 0
    
    def update(self, increment: int = 1) -> None:
        """Update progress and optionally log."""
        self.completed += increment
        current_time = time.time()
        
        # Log progress every 5 seconds or at completion
        if current_time - self.last_update > 5.0 or self.completed >= self.total:
            self.log_progress()
            self.last_update = current_time
    
    def log_progress(self) -> None:
        """Log current progress."""
        if self.total > 0:
            percentage = (self.completed / self.total) * 100
            elapsed = time.time() - self.start_time
            
            if self.completed > 0 and elapsed > 0:
                rate = self.completed / elapsed
                eta = (self.total - self.completed) / rate if rate > 0 else 0
                logger.info(
                    f"{self.description}: {self.completed}/{self.total} "
                    f"({percentage:.1f}%) - ETA: {eta:.1f}s"
                )
            else:
                logger.info(f"{self.description}: {self.completed}/{self.total} ({percentage:.1f}%)")
    
    def is_complete(self) -> bool:
        """Check if processing is complete."""
        return self.completed >= self.total
