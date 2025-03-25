#!/usr/bin/env python3

from pathlib import Path

# Directory paths
RON_INCOMING = Path("/Users/rmccarty/Transfers/Ron/Ron_Incoming")
CLAUDIA_INCOMING = Path("/Users/rmccarty/Transfers/Claudia/Claudia_Incoming")
BOTH_INCOMING = Path("/Users/rmccarty/Transfers/Both/Both_Incoming")

# Watch directories configuration
WATCH_DIRS = [RON_INCOMING, CLAUDIA_INCOMING]

# Logging configuration
LOG_LEVEL = "INFO"

# Sleep time when no files are found (in seconds)
SLEEP_TIME = 10

# File patterns
JPEG_PATTERN = '*.[Jj][Pp][Gg]'
VIDEO_PATTERNS = ('.mp4', '.mov', '.m4v')

# XML/RDF Namespaces
XML_NAMESPACES = {
    'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'Iptc4xmpCore': 'http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/',
    'photoshop': 'http://ns.adobe.com/photoshop/1.0/',
    'exif': 'http://ns.adobe.com/exif/1.0/'
}

# Exiftool configuration
EXIFTOOL_BASE_ARGS = [
    'exiftool',
    '-overwrite_original',
    '-handler=mdta'
]

# Metadata field mappings
METADATA_FIELDS = {
    'title': ['-Title', '-DisplayName', '-ItemList:Title'],
    'date': [
        '-CreateDate',
        '-ModifyDate',
        '-TrackCreateDate',
        '-TrackModifyDate',
        '-MediaCreateDate',
        '-MediaModifyDate'
    ],
    'location': ['-LocationName'],
    'city': ['-City'],
    'state': ['-State'],
    'country': ['-Country'],
    'gps': ['-GPSLatitude', '-GPSLongitude'],
    'caption': ['-Description']
}

# Verification fields to check
VERIFY_FIELDS = [
    '-DisplayName',
    '-Title',
    '-ItemList:Title',
    '-Keywords',
    '-Subject',
    '-CreateDate',
    '-ModifyDate',
    '-TrackCreateDate',
    '-TrackModifyDate',
    '-MediaCreateDate',
    '-MediaModifyDate',
    '-LocationName',
    '-City',
    '-State',
    '-Country',
    '-GPSLatitude',
    '-GPSLongitude',
    '-Description'
]

# File naming configuration
FILENAME_REPLACEMENTS = {
    ':': ' -',
    '/': '_'
}
LRE_SUFFIX = '__LRE'
MCCARTYS_PREFIX = 'The McCartys '
MCCARTYS_REPLACEMENT = 'The McCartys: '
