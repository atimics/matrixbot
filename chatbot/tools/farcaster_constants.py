"""
Farcaster platform constants and configuration.
"""

# Content limits
MAX_FARCASTER_CONTENT_LENGTH = 320
MAX_FARCASTER_IMAGES = 2
MAX_THREAD_LENGTH = 25

# Time limits (in seconds)
RECENT_MEDIA_TIMEOUT = 300  # 5 minutes
CAST_COOLDOWN_PERIOD = 60   # 1 minute between casts

# Rate limiting
DEFAULT_DAILY_CAST_LIMIT = 50
DEFAULT_DAILY_REPLY_LIMIT = 100
DEFAULT_HOURLY_CAST_LIMIT = 10

# Mention detection patterns
MENTION_PATTERN = r'@([a-zA-Z0-9_-]+)'

# Embeds and media
SUPPORTED_MEDIA_TYPES = ["image", "video", "gif"]
SUPPORTED_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif", ".webp"]
SUPPORTED_VIDEO_EXTENSIONS = [".mp4", ".mov", ".webm", ".avi"]

# API response fields
CAST_REQUIRED_FIELDS = ["hash", "text", "author", "timestamp"]
USER_REQUIRED_FIELDS = ["fid", "username", "display_name"]

# Error messages
ERROR_MESSAGES = {
    "no_integration": "Farcaster integration (observer) not configured.",
    "missing_content": "Missing required parameter 'content' for Farcaster post",
    "content_too_long": f"Content exceeds maximum length of {MAX_FARCASTER_CONTENT_LENGTH} characters",
    "duplicate_cast": "Already sent Farcaster post with identical content. Skipping duplicate.",
    "duplicate_reply": "Already replied to cast. Cannot reply to the same cast twice.",
    "self_reply": "Cannot reply to own cast",
    "rate_limited": "Rate limit exceeded for action",
    "cast_not_found": "Cast not found or inaccessible",
    "invalid_media": "Invalid media format or type",
}

# Success messages
SUCCESS_MESSAGES = {
    "cast_scheduled": "Scheduled Farcaster post via scheduler",
    "reply_scheduled": "Scheduled Farcaster reply via scheduler",
    "cast_sent": "Successfully sent Farcaster cast",
    "reply_sent": "Successfully sent Farcaster reply",
    "cast_liked": "Successfully liked Farcaster cast",
    "cast_quoted": "Successfully posted quote cast",
    "user_followed": "Successfully followed user",
    "cast_deleted": "Successfully deleted cast",
}
