# Platform Integration Error Handling Patterns

This document outlines the standardized error handling patterns implemented across all platform integration observers (Farcaster, Matrix, etc.).

## BaseObserver Pattern

All platform observers inherit from `BaseObserver` which provides:

### Status Management
- `ObserverStatus` enum: DISCONNECTED, CONNECTING, CONNECTED, ERROR, RECONNECTING
- Automatic status transitions with logging
- Connection attempt tracking and reset

### Common Interface
- `async def connect(credentials: Optional[Dict]) -> bool`
- `async def disconnect() -> None`
- `async def is_healthy() -> bool`
- `def get_status_info() -> Dict[str, Any]`

## Error Handling Best Practices

### 1. Status Setting
```python
# Use _set_status for state changes with error messages
self._set_status(ObserverStatus.ERROR, "Specific error description")

# Clear errors when recovering
self._clear_error()
```

### 2. Connection Management
```python
async def connect(self, credentials: Optional[Dict[str, Any]] = None) -> bool:
    try:
        self._set_status(ObserverStatus.CONNECTING)
        self._increment_connection_attempts()
        
        # ... connection logic ...
        
        self._set_status(ObserverStatus.CONNECTED)
        self._reset_connection_attempts()
        return True
        
    except Exception as e:
        error_msg = f"Failed to connect: {e}"
        self._set_status(ObserverStatus.ERROR, error_msg)
        return False
```

### 3. Comprehensive Logging
```python
# Error logging with stack trace for debugging
logger.error(error_msg, exc_info=True)

# Warning for recoverable issues
logger.warning(f"Retrying operation: {e}")

# Info for status changes
logger.debug(f"Status changed: {old_status} -> {new_status}")
```

### 4. Graceful Degradation
```python
# Always check if components exist before using
if hasattr(self, 'scheduler') and self.scheduler:
    await self.scheduler.stop()

# Provide meaningful error responses
if not self.enabled:
    return {"success": False, "error": "Service not configured"}
```

## Implementation Status

### ✅ Completed
- **BaseObserver**: Common interface and patterns
- **FarcasterObserver**: Updated with BaseObserver patterns
- **MatrixObserver**: Updated with BaseObserver patterns
- **Error handling**: Consistent patterns across all observers

### 📋 Usage Guidelines

1. **Always return booleans from connect()** - Enables proper error handling
2. **Use status enum consistently** - Provides clear state management
3. **Log with appropriate levels** - Debug, info, warning, error as needed
4. **Handle partial failures gracefully** - Don't crash entire observer
5. **Test connectivity when possible** - Implement health checks

## Benefits

1. **Predictable Behavior**: All observers follow the same patterns
2. **Better Debugging**: Consistent logging and status reporting
3. **Improved Reliability**: Graceful error handling and recovery
4. **Easier Testing**: Common interface for mocking and testing
5. **Clear Monitoring**: Status and health information for operations

## Migration Notes

Existing observers have been updated to:
- Inherit from both `Integration` and `BaseObserver`
- Return booleans from `connect()` instead of raising exceptions
- Use `_set_status()` for state management
- Implement proper health checks
- Provide comprehensive status information
