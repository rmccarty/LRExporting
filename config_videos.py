#!/usr/bin/env python3

"""
Video-specific configuration for LRExporting video processing.
This file contains all video metadata field mappings and settings optimized for Apple Photos compatibility.
"""

# Video file patterns
VIDEO_PATTERN = ['*.mp4', '*.mov', '*.m4v', '*.mpg', '*.mpeg']  # Will handle case sensitivity in the watcher

# Video metadata field mappings - optimized for Apple Photos compatibility
VIDEO_METADATA_FIELDS = {
    'title': [
        '-XMP:Title',               # XMP Title (Apple Photos recognizes)
        '-QuickTime:Title',         # QuickTime Title 
        '-ItemList:Title',          # MP4 ItemList Title
        '-DC:Title'                 # Dublin Core Title
    ],
    'date': [
        '-QuickTime:CreateDate',        # Primary QuickTime date
        '-QuickTime:MediaCreateDate',   # Media creation date
        '-CreateDate',                  # Generic create date
        '-MediaCreateDate',             # Media create date
        '-XMP:CreateDate',              # XMP create date
        '-XMP:DateTimeOriginal',        # XMP original date
        '-Photoshop:DateCreated'        # Photoshop date created
    ],
    'keywords': [
        # Apple Photos compatible fields (tested working)
        '-QuickTime:Keywords',          # PRIMARY: Apple Photos reads this for videos!
        '-XMP:Subject',                 # PRIMARY: Apple Photos reads this for videos!
        '-IPTC:Keywords',               # IPTC keywords (string format)
        
        # Additional compatibility fields
        '-ItemList:Keyword',            # MP4 ItemList keywords
        '-Keys:Keywords',               # iTunes-style keywords
        '-XMP-dc:Subject',              # XMP Dublin Core subject
        '-DC:Subject',                  # Direct Dublin Core subject
        '-UserData:Keywords',           # MP4 UserData keywords
        '-QuickTime:Keyword'            # Alternative QuickTime keyword field
    ],
    'caption': [
        '-QuickTime:Description',       # PRIMARY: Apple Photos reads this
        '-XMP:Description',             # XMP description
        '-ItemList:Description',        # MP4 ItemList description
        '-UserData:Description'         # MP4 UserData description
    ],
    'location': [
        '-XMP:Location',                # PRIMARY: Apple Photos location
        '-QuickTime:LocationName',      # QuickTime location name
        '-Location',                    # Generic location
        '-LocationName'                 # Location name
    ],
    'city': [
        '-XMP:City',                    # XMP city
        '-QuickTime:City',              # QuickTime city
        '-City'                         # Generic city
    ],
    'state': [
        '-XMP:State',                   # XMP state/province
        '-QuickTime:State',             # QuickTime state
        '-State'                        # Generic state
    ],
    'country': [
        '-XMP:Country',                 # XMP country
        '-QuickTime:Country',           # QuickTime country  
        '-Country'                      # Generic country
    ],
    'gps': [
        # Match iPhone video format EXACTLY - only essential fields
        '-QuickTime:GPSCoordinates',              # PRIMARY: Combined GPS coordinates (Apple Photos key field)
        '-QuickTime:LocationAccuracyHorizontal'   # GPS accuracy (iPhone compatibility)
    ]
}

# Video verification fields to check after writing metadata
VIDEO_VERIFY_FIELDS = [
    'XMP:Title',
    'QuickTime:Title',
    'QuickTime:Keywords', 
    'XMP:Subject',
    'QuickTime:Description',
    'XMP:CreateDate',
    'QuickTime:CreateDate', 
    'XMP:Location',
    'QuickTime:GPSCoordinates',
    'XMP:GPSLatitude',
    'XMP:GPSLongitude'
]

# Video-specific filename configuration
VIDEO_FILENAME_REPLACEMENTS = {
    ':': ' -',
    '/': '_'
}

# Video processing settings
VIDEO_LRE_SUFFIX = '__LRE'
VIDEO_MCCARTYS_PREFIX = 'The McCartys '
VIDEO_MCCARTYS_REPLACEMENT = 'The McCartys: '

# XML/RDF Namespaces for XMP processing
VIDEO_XML_NAMESPACES = {
    'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'Iptc4xmpCore': 'http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/',
    'photoshop': 'http://ns.adobe.com/photoshop/1.0/',
    'exif': 'http://ns.adobe.com/exif/1.0/',
    'lr': 'http://ns.adobe.com/lightroom/1.0/',
    'xml': 'http://www.w3.org/XML/1998/namespace'
}

# GPS coordinate format settings
GPS_DECIMAL_PRECISION = 6          # Decimal places for GPS coordinates
GPS_ALTITUDE_PRECISION = 3         # Decimal places for altitude

# Video quality and compatibility settings
VIDEO_MIN_FILE_AGE = 30            # Minimum age in seconds before processing
VIDEO_MAX_RETRIES = 3              # Maximum processing retries
VIDEO_RETRY_DELAY = 5              # Delay between retries in seconds

# Apple Photos specific optimizations
APPLE_PHOTOS_VIDEO_OPTIMIZATIONS = {
    'use_quicktime_primary': True,      # Use QuickTime fields as primary for Apple Photos
    'convert_gps_decimal': False,       # Keep GPS in degree/minute/second format  
    'keyword_format': 'comma_separated', # Use comma-separated format for keywords
    'preserve_original_dates': True,     # Preserve original timestamp metadata
    'add_composite_fields': True        # Add composite GPS position fields
}

# Debug and logging settings for video processing
VIDEO_DEBUG_SETTINGS = {
    'debug': True,                      # Master debug flag - controls all debug output
    'log_metadata_extraction': True,    # Log metadata reading from XMP
    'log_field_mapping': True,          # Log field mapping during write
    'log_verification': True,           # Log verification results
    'log_keyword_processing': True,     # Log keyword processing details
    'save_debug_metadata': False       # Save debug metadata to file
}