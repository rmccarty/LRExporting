"""Configuration for the Apple Photos SDK."""

# File extensions that are considered images
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".gif", ".tiff", ".tif"}

# File extensions that are considered videos
VIDEO_EXTENSIONS = {".mov", ".mp4", ".m4v", ".avi", ".mpg", ".mpeg", ".3gp", ".3g2"}

# Whether to delete original files after import
DELETE_ORIGINAL = True

# Keywords that indicate targeted albums (hierarchical keywords starting with top-level folder numbers)
TARGETED_ALBUM_PREFIXES = ["01/", "02/", "03/", "04/"]

# Maximum time to wait for Photos library changes to complete (in seconds)
PHOTOS_CHANGE_TIMEOUT = 10

# How often to check if Photos library changes are complete (in seconds)
PHOTOS_CHANGE_CHECK_INTERVAL = 0.1
