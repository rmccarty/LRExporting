#!/usr/bin/env python3

from pathlib import Path

# Directory paths
RON_INCOMING = Path("/Users/rmccarty/Transfers/Ron/Ron_Incoming")
CLAUDIA_INCOMING = Path("/Users/rmccarty/Transfers/Claudia/Claudia_Incoming")
BOTH_INCOMING = Path("/Users/rmccarty/Transfers/Both/Both_Incoming")
APPLE_PHOTOS_WATCHING = Path("Watching/")

# Watch directories configuration
WATCH_DIRS = [RON_INCOMING, CLAUDIA_INCOMING]

# Logging configuration
LOG_LEVEL = "DEBUG"  # Temporarily set to DEBUG for more info

# Sleep time when no files are found (in seconds)
SLEEP_TIME = 10

# Apple Photos Watcher configuration
# Maximum number of assets to fetch from Watching album per check (prevents performance issues with large albums)
APPLE_PHOTOS_MAX_ASSETS_PER_CHECK = 5000

# Watching album size management
# Maximum number of assets allowed in Watching album before pausing additions
APPLE_PHOTOS_WATCHING_MAX_SIZE = 1000

# Watermark threshold - resume adding assets when count drops below this number
APPLE_PHOTOS_WATCHING_WATERMARK = 800 

# Processing order for assets in Watching album
# True = LIFO (newest first) - process recently added photos first
# False = FIFO (oldest first) - process oldest photos first (systematic backlog processing)
APPLE_PHOTOS_PROCESS_NEWEST_FIRST = True

# Batch processing configuration
# Enable batch processing to group album operations and reduce Photos API calls
APPLE_PHOTOS_ENABLE_BATCH_PROCESSING = True

# Maximum number of assets to add to a single album in one batch operation
APPLE_PHOTOS_BATCH_ADD_SIZE = 5000

# Maximum number of assets to remove from Watching album in one batch operation  
APPLE_PHOTOS_BATCH_REMOVE_SIZE = 5000

# File patterns
JPEG_PATTERN = '*.[Jj][Pp][Gg]'
VIDEO_PATTERN = ['*.mp4', '*.mov', '*.m4v']  # Will handle case sensitivity in the watcher

# Combined pattern for Apple Photos
ALL_PATTERN = [JPEG_PATTERN] + [pat.upper() for pat in VIDEO_PATTERN] + [pat.lower() for pat in VIDEO_PATTERN]

# XML/RDF Namespaces
XML_NAMESPACES = {
    'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'Iptc4xmpCore': 'http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/',
    'photoshop': 'http://ns.adobe.com/photoshop/1.0/',
    'exif': 'http://ns.adobe.com/exif/1.0/',
    'lr': 'http://ns.adobe.com/lightroom/1.0/',
    'xml': 'http://www.w3.org/XML/1998/namespace'  # Add XML namespace for xml:lang
}

# Metadata field mappings
METADATA_FIELDS = {
    'title': ['-ItemList:Title', '-QuickTime:Title'],
    'date': [
        '-CreateDate',
        '-ModifyDate',
        '-TrackCreateDate',
        '-TrackModifyDate',
        '-MediaCreateDate',
        '-MediaModifyDate',
        '-QuickTime:CreateDate',
        '-QuickTime:MediaCreateDate'
    ],
    'keywords': ['-QuickTime:Keywords', '-XMP:Subject'],  # These are the fields that actually work
    'location': ['-Location', '-XMP:Location', '-LocationName'],
    'city': ['-City', '-XMP:City'],
    'state': ['-State', '-XMP:State'],
    'country': ['-Country', '-XMP:Country'],
    'gps': ['-GPSLatitude', '-GPSLongitude'],
    'caption': ['-ItemList:Description', '-Description']
}

# Verification fields to check
VERIFY_FIELDS = [
    'Title',
    'Keywords',
    'CreateDate',
    'Location',
    'City',
    'Country'
]

# Transfer configuration
TRANSFER_PATHS = {
    RON_INCOMING: Path("/Users/rmccarty/Transfers/Ron/Ron_Apple_Photos"),
    CLAUDIA_INCOMING: Path("/Users/rmccarty/Library/Mobile Documents/com~apple~CloudDocs/Shared/OldPhotographs")
}

# Apple Photos configuration - paths that should be imported to Photos
APPLE_PHOTOS_PATHS = {
    Path("/Users/rmccarty/Transfers/Ron/Ron_Apple_Photos")  # Only Ron's path goes to Apple Photos
}

# Flag to enable/disable Apple Photos processing
ENABLE_APPLE_PHOTOS = True

MIN_FILE_AGE = 30  # Minimum age in seconds before a file can be transferred

# File naming configuration
FILENAME_REPLACEMENTS = {
    ':': ' -',
    '/': '_'
}
LRE_SUFFIX = '__LRE'
MCCARTYS_PREFIX = 'The McCartys '
MCCARTYS_REPLACEMENT = 'The McCartys: '

# Dynamic category-based album prefix
CATEGORY_PREFIX = '02'
