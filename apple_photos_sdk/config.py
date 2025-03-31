"""Configuration for the Apple Photos SDK."""

# File extensions that are considered images
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".gif", ".tiff", ".tif"}

# File extensions that are considered videos
VIDEO_EXTENSIONS = {".mov", ".mp4", ".m4v", ".avi", ".mpg", ".mpeg", ".3gp", ".3g2"}

# Whether to delete original files after import
DELETE_ORIGINAL = False

# Keywords that indicate targeted albums (hierarchical keywords starting with top-level folder numbers)
TARGETED_ALBUM_PREFIXES = ["01/", "02/", "03/", "04/"]

def is_targeted_album_keyword(keyword: str) -> bool:
    """Check if a keyword indicates a targeted album by matching top-level folder prefixes."""
    return any(keyword.startswith(prefix) for prefix in TARGETED_ALBUM_PREFIXES)
