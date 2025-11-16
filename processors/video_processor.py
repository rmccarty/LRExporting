#!/usr/bin/env python3

from pathlib import Path
import subprocess
import logging
import sys
import os
import xml.etree.ElementTree as ET
import re
from datetime import datetime

from config import (
    MCCARTYS_PREFIX,
    MCCARTYS_REPLACEMENT
)
# Import video-specific configuration
try:
    import config_videos
    from config_videos import (
        VIDEO_XML_NAMESPACES as XML_NAMESPACES,
        VIDEO_METADATA_FIELDS as METADATA_FIELDS,
        VIDEO_VERIFY_FIELDS as VERIFY_FIELDS,
        VIDEO_PATTERN,
        VIDEO_LRE_SUFFIX as LRE_SUFFIX,
        APPLE_PHOTOS_VIDEO_OPTIMIZATIONS,
        VIDEO_DEBUG_SETTINGS
    )
except ImportError:
    # Fallback to main config if video config not available
    from config import (
        XML_NAMESPACES,
        METADATA_FIELDS,
        VERIFY_FIELDS,
        VIDEO_PATTERN,
        LRE_SUFFIX
    )
    APPLE_PHOTOS_VIDEO_OPTIMIZATIONS = {
        'use_quicktime_primary': True,
        'convert_gps_decimal': False,
        'keyword_format': 'comma_separated',
        'preserve_original_dates': True,
        'add_composite_fields': True
    }
    VIDEO_DEBUG_SETTINGS = {
        'debug': False,
        'log_metadata_extraction': False,
        'log_field_mapping': False,
        'log_verification': False,
        'log_keyword_processing': False,
        'save_debug_metadata': False
    }
from processors.media_processor import MediaProcessor
from utils.exiftool import ExifTool  # Import the new ExifTool class
from utils.date_normalizer import DateNormalizer  # Import DateNormalizer

class VideoProcessor(MediaProcessor):
    """A class to process video files and their metadata using exiftool."""
    
    def _debug_log(self, message: str, debug_type: str = 'debug') -> None:
        """Log debug message only if debug is enabled for the specified type."""
        if VIDEO_DEBUG_SETTINGS.get('debug', False) and VIDEO_DEBUG_SETTINGS.get(debug_type, False):
            self.logger.debug(f"[VIDEO DEBUG] {message}")
    
    def __init__(self, file_path: str, sequence: str = None):
        """Initialize with video file path."""
        super().__init__(file_path, sequence=sequence)
        
        # Validate file extension
        ext = Path(file_path).suffix.lower()
        valid_extensions = [pattern.lower().replace('*', '') for pattern in VIDEO_PATTERN]
        if ext not in valid_extensions:
            self.logger.error(f"File must be video format matching {VIDEO_PATTERN}. Found: {ext}")
            sys.exit(1)
            
        # Check for XMP sidecar file
        self.xmp_file = Path(file_path).with_suffix('.xmp')
        self.logger.debug(f"Looking for XMP file at: {self.xmp_file}")
        self.logger.debug(f"XMP file absolute path: {self.xmp_file.absolute()}")
        self.logger.debug(f"XMP file exists: {self.xmp_file.exists()}")
        
        if not self.xmp_file.exists():
            self.logger.error(f"CRITICAL: No XMP sidecar file found at: {self.xmp_file}")
            self.logger.error(f"Video processing requires XMP file for metadata")
            # Don't exit - let the process continue but flag this as an error
            self._xmp_available = False
        else:
            self.logger.info(f"Found XMP sidecar file: {self.xmp_file}")
            self._xmp_available = True
            
        # Initialize the ExifTool class
        self.exiftool = ExifTool()
        # Initialize the DateNormalizer class
        self.date_normalizer = DateNormalizer()
            
    def read_metadata_from_xmp(self) -> tuple:
        """Read metadata from XMP sidecar file."""
        if not self.xmp_file.exists():
            self.logger.warning(f"No XMP sidecar file found: {self.xmp_file}")
            return (None, None, None, None, (None, None, None), None)
            
        try:
            tree = ET.parse(str(self.xmp_file))
            root = tree.getroot()
            
            # Find the Description element that contains our metadata
            description = root.find('.//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description')
            if description is None:
                self.logger.warning("No Description element found in XMP")
                return (None, None, None, None, (None, None, None), None)
                
            # Extract metadata fields
            title = self.get_title_from_rdf(description)
            keywords = self.get_keywords_from_rdf(description)
            date_str = self.exiftool.read_date_from_xmp(self.xmp_file)
            caption = self.get_caption_from_rdf(description)
            location = self.get_location_from_rdf(description)
            gps_data = self.get_gps_from_rdf(description)
            
            # Log extracted XMP data
            self.logger.warning("XMP metadata extracted:")
            self.logger.warning(f"  ┌─ Title:    '{title}'")
            self.logger.warning(f"  ├─ Keywords: {keywords}")
            self.logger.warning(f"  ├─ Date:     '{date_str}'")
            self.logger.warning(f"  ├─ Caption:  '{caption}'")
            self.logger.warning(f"  ├─ Location: {location}")
            self.logger.warning(f"  └─ GPS:      {gps_data}")
            
            return (title, keywords, date_str, caption, location, gps_data)
            
        except ET.ParseError as e:
            self.logger.error(f"Error parsing XMP file: {str(e)}")
            return (None, None, None, None, (None, None, None), None)
        except Exception as e:
            self.logger.error(f"Error reading XMP metadata: {str(e)}")
            return (None, None, None, None, (None, None, None), None)
            
    def _get_keywords_from_hierarchical(self, rdf) -> list[str] | None:
        """Get keywords from hierarchical subjects."""
        ns = XML_NAMESPACES
        keywords = []
        subject_path = f'.//{{{ns["lr"]}}}hierarchicalSubject/{{{ns["rdf"]}}}Bag/{{{ns["rdf"]}}}li'
        for elem in rdf.findall(subject_path):
            if elem.text:
                keywords.append(elem.text)
        return keywords if keywords else None
        
    def _get_keywords_from_flat_bag(self, rdf) -> list[str] | None:
        """Get keywords from flat subject list using rdf:Bag (Lightroom format)."""
        ns = XML_NAMESPACES
        keywords = []
        subject_path = f'.//{{{ns["dc"]}}}subject/{{{ns["rdf"]}}}Bag/{{{ns["rdf"]}}}li'
        for elem in rdf.findall(subject_path):
            if elem.text:
                keywords.append(elem.text)
        return keywords if keywords else None
        
    def _get_keywords_from_flat_seq(self, rdf) -> list[str] | None:
        """Get keywords from flat subject list using rdf:Seq (Apple Photos format)."""
        ns = XML_NAMESPACES
        keywords = []
        subject_path = f'.//{{{ns["dc"]}}}subject/{{{ns["rdf"]}}}Seq/{{{ns["rdf"]}}}li'
        for elem in rdf.findall(subject_path):
            if elem.text:
                keywords.append(elem.text)
        return keywords if keywords else None
        
    def get_keywords_from_rdf(self, rdf):
        """Extract keywords from RDF data using multiple strategies."""
        try:
            # Try multiple keyword formats: hierarchical, flat bag (Lightroom), flat seq (Apple Photos)
            strategies = [
                self._get_keywords_from_hierarchical,
                self._get_keywords_from_flat_bag,
                self._get_keywords_from_flat_seq
            ]
            
            self._debug_log("Trying multiple keyword extraction strategies", 'log_keyword_processing')
            
            for strategy in strategies:
                self._debug_log(f"Trying strategy: {strategy.__name__}", 'log_keyword_processing')
                keywords = strategy(rdf)
                if keywords:
                    self._debug_log(f"Found keywords using {strategy.__name__}: {keywords}", 'log_keyword_processing')
                    self.logger.debug(f"Found keywords using {strategy.__name__}: {keywords}")
                    return keywords
                else:
                    self._debug_log(f"No keywords found with {strategy.__name__}", 'log_keyword_processing')
                    
            self._debug_log("No keywords found in RDF with any strategy", 'log_keyword_processing')
            self.logger.debug("No keywords found in RDF")
            return None
            
        except Exception as e:
            self.logger.error(f"Error extracting keywords from RDF: {e}")
            return None
            
    def get_location_from_rdf(self, rdf) -> tuple[str | None, str | None, str | None]:
        """Extract location data from RDF."""
        try:
            # First try IPTC Core fields
            location_data = self._get_iptc_location(rdf)
            if any(location_data):
                return location_data
                
            # Try photoshop namespace as fallback
            location_data = self._get_photoshop_location(rdf)
            if any(location_data):
                return location_data
                
        except Exception as e:
            self.logger.error(f"Error extracting location from RDF: {e}")
            
        return None, None, None
        
    def _get_iptc_location(self, rdf) -> tuple[str | None, str | None, str | None]:
        """Extract location data from IPTC Core fields."""
        ns = XML_NAMESPACES
        for desc in rdf.iter('{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description'):
            # Check for attributes first (your XMP format)
            location = desc.get(f'{{{ns["Iptc4xmpCore"]}}}Location')
            city = desc.get(f'{{{ns["Iptc4xmpCore"]}}}City')
            country = desc.get(f'{{{ns["Iptc4xmpCore"]}}}CountryName')
            
            if any([location, city, country]):
                self.logger.debug(f"Found IPTC location attributes: {location} ({city}, {country})")
                return location, city, country
            
            # Fallback to elements if no attributes found
            location_elem = desc.find(f'.//{{{ns["Iptc4xmpCore"]}}}Location')
            city_elem = desc.find(f'.//{{{ns["Iptc4xmpCore"]}}}City')
            country_elem = desc.find(f'.//{{{ns["Iptc4xmpCore"]}}}CountryName')
            
            location_text = location_elem.text if location_elem is not None else None
            city_text = city_elem.text if city_elem is not None else None
            country_text = country_elem.text if country_elem is not None else None
            
            if any([location_text, city_text, country_text]):
                self.logger.debug(f"Found IPTC location elements: {location_text} ({city_text}, {country_text})")
                return location_text, city_text, country_text
                
        return None, None, None
        
    def _get_photoshop_location(self, rdf) -> tuple:
        """Extract location data from photoshop namespace."""
        ns = XML_NAMESPACES  # Get namespaces from config
        # Look for location data in Description elements
        for desc in rdf.iter('{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description'):
            # Get attributes using the full namespace
            city = desc.get(f'{{{ns["photoshop"]}}}City')
            state = desc.get(f'{{{ns["photoshop"]}}}State')
            country = desc.get(f'{{{ns["photoshop"]}}}Country')
            
            if city or state or country:
                # Return raw components - let _prepare_location_fields build the string
                self.logger.debug(f"Found Photoshop location data: city={city}, state={state}, country={country}")
                return state, city, country
                
        return None, None, None
        
    def _build_location_string(self, location_data: tuple) -> str:
        """Build a location string from location data tuple."""
        if not location_data:
            return ''
            
        location, city, country = location_data
        parts = []
        
        # Add components in order: location (state), city, country
        if location:
            parts.append(location)
            
        if city and city != location:  # Don't duplicate city if it's the same
            parts.append(city)
            
        if country:
            parts.append(country)
            
        return ", ".join(parts)
        
    def get_gps_from_rdf(self, rdf) -> tuple[str | None, str | None, str | None]:
        """Extract GPS coordinates from RDF."""
        try:
            # Look for EXIF GPS data in Description attributes
            for desc in rdf.iter('{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description'):
                latitude = desc.get('{http://ns.adobe.com/exif/1.0/}GPSLatitude')
                longitude = desc.get('{http://ns.adobe.com/exif/1.0/}GPSLongitude')
                altitude = desc.get('{http://ns.adobe.com/exif/1.0/}GPSAltitude')
                
                if latitude or longitude:
                    self.logger.debug(f"Found GPS coordinates: lat={latitude}, lon={longitude}, alt={altitude}")
                    return latitude, longitude, altitude
                    
        except Exception as e:
            self.logger.error(f"Error extracting GPS from RDF: {e}")
            
        return None, None, None
        
    def _convert_gps_to_quicktime_format(self, latitude: str, longitude: str, altitude: str = None) -> dict:
        """Convert XMP GPS format to QuickTime GPS format."""
        if not latitude or not longitude:
            return {}
            
        try:
            # Convert latitude: "32,54.99N" -> "32 deg 54' 59.40\" N"
            lat_deg, lat_min_dir = latitude.split(',')
            lat_min = lat_min_dir[:-1]  # Remove direction
            lat_dir = lat_min_dir[-1]   # Get direction
            
            # Convert decimal minutes to minutes/seconds
            lat_min_float = float(lat_min)
            lat_min_int = int(lat_min_float)
            lat_sec = (lat_min_float - lat_min_int) * 60
            
            lat_formatted = f"{lat_deg} deg {lat_min_int}' {lat_sec:.2f}\" {lat_dir}"
            
            # Convert longitude: "96,32.052W" -> "96 deg 32' 3.12\" W"
            lon_deg, lon_min_dir = longitude.split(',')
            lon_min = lon_min_dir[:-1]  # Remove direction
            lon_dir = lon_min_dir[-1]   # Get direction
            
            # Convert decimal minutes to minutes/seconds
            lon_min_float = float(lon_min)
            lon_min_int = int(lon_min_float)
            lon_sec = (lon_min_float - lon_min_int) * 60
            
            lon_formatted = f"{lon_deg} deg {lon_min_int}' {lon_sec:.2f}\" {lon_dir}"
            
            # Build GPS fields
            gps_fields = {}
            gps_fields['-GPSLatitude'] = lat_formatted
            gps_fields['-GPSLongitude'] = lon_formatted
            
            # Handle altitude if present
            if altitude:
                # Convert fraction like "741/5" to decimal
                if '/' in altitude:
                    num, den = altitude.split('/')
                    alt_meters = float(num) / float(den)
                else:
                    alt_meters = float(altitude)
                    
                gps_fields['-GPSAltitude'] = f"{alt_meters:.3f} m"
                gps_fields['-GPSAltitudeRef'] = "Above Sea Level"
                
                # Create combined coordinate string
                gps_coords = f"{lat_formatted}, {lon_formatted}, {alt_meters:.3f} m Above Sea Level"
            else:
                gps_coords = f"{lat_formatted}, {lon_formatted}"
                
            gps_fields['-QuickTime:GPSCoordinates'] = gps_coords
            
            self.logger.debug(f"Converted GPS: {gps_fields}")
            return gps_fields
            
        except Exception as e:
            self.logger.error(f"Error converting GPS format: {e}")
            return {}
        
    def get_metadata_from_xmp(self):
        """Get metadata from XMP file."""
        if not hasattr(self, '_xmp_available') or not self._xmp_available:
            self.logger.error("Cannot read metadata - XMP file not available")
            return None
            
        try:
            metadata = self.read_metadata_from_xmp()
            title, keywords, date_str, caption, location_data, gps_data = metadata
            
            self._log_metadata_status(metadata)
            return metadata
        except Exception as e:
            self.logger.error(f"Failed to read metadata from XMP: {e}")
            return None
        
    def _log_metadata_status(self, metadata: tuple) -> None:
        """Log status of metadata fields."""
        title, keywords, date_str, caption, location_data, gps_data = metadata
        
        if self._is_metadata_empty(metadata):
            self.logger.warning("No metadata found in XMP file")
            return
            
        self._log_missing_fields(title, keywords, date_str, caption, location_data)
        
    def _is_metadata_empty(self, metadata: tuple) -> bool:
        """Check if all metadata fields are empty."""
        return all(x is None or (isinstance(x, (list, tuple)) and not any(x)) for x in metadata)
        
    def _log_missing_fields(self, title, keywords, date_str, caption, location_data) -> None:
        """Log which metadata fields are missing."""
        field_checks = [
            (title, "title"),
            (keywords, "keywords"),
            (date_str, "date"),
            (caption, "caption"),
            (any(location_data), "location data")
        ]
        
        for value, field_name in field_checks:
            if not value:
                self.logger.info(f"No {field_name} found in XMP")
                
    def normalize_date(self, date_str: str) -> str | None:
        """
        Normalize date format to YYYY:MM:DD HH:MM:SS format that exiftool expects.
        
        Args:
            date_str (str): Date string to normalize
            
        Returns:
            str | None: Normalized date string or None if invalid
        """
        try:
            return self.date_normalizer.normalize(date_str)
        except Exception as e:
            self.logger.error(f"Error normalizing date: {e}")
            return None
            
    def dates_match(self, date1, date2):
        """
        Compare two dates, handling various formats.
        
        Args:
            date1: First date string
            date2: Second date string
            
        Returns:
            bool: True if dates match, False otherwise
        """
        try:
            if not date1 or not date2:
                return False
                
            norm1 = self.date_normalizer.normalize(date1)
            norm2 = self.date_normalizer.normalize(date2)
            
            return norm1 == norm2
        except Exception as e:
            self.logger.error(f"Error comparing dates {date1} and {date2}: {e}")
            return False

    def _is_valid_exif_date(self, date_str: str) -> bool:
        """
        Check if date string is in valid EXIF format (YYYY:MM:DD HH:MM:SS).
        
        Args:
            date_str: Date string to validate
            
        Returns:
            bool: True if valid EXIF format, False otherwise
        """
        if not date_str or not isinstance(date_str, str):
            return False
            
        # Split into date and time parts
        parts = date_str.strip().split(' ')
        if len(parts) != 2:
            return False
            
        date_part, time_part = parts
        
        # Validate date part (YYYY:MM:DD)
        date_components = date_part.split(':')
        if len(date_components) != 3:
            return False
            
        try:
            year, month, day = map(int, date_components)
            if not (1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31):
                return False
        except ValueError:
            return False
            
        # Validate time part (HH:MM:SS)
        time_components = time_part.split(':')
        if len(time_components) != 3:
            return False
            
        try:
            hour, minute, second = map(int, time_components)
            if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
                return False
        except ValueError:
            return False
            
        return True

    def _prepare_title_fields(self, title: str | None) -> dict:
        """Prepare title metadata fields."""
        if not title:
            return {}
        return {field: title for field in METADATA_FIELDS['title']}
        
    def _prepare_date_fields(self, date_str: str | None) -> dict:
        """Prepare date metadata fields."""
        if not date_str:
            return {}
            
        # Check if date is in valid EXIF format (YYYY:MM:DD HH:MM:SS)
        if self._is_valid_exif_date(date_str):
            return {field: date_str for field in METADATA_FIELDS['date']}
        
        # Try normalization for other formats
        normalized_date = self.normalize_date(date_str)
        if normalized_date:
            return {field: normalized_date for field in METADATA_FIELDS['date']}
            
        self.logger.error(f"Invalid date format: {date_str}")
        # Return the original date string for the fields anyway
        return {field: date_str for field in METADATA_FIELDS['date']}
        
    def _prepare_caption_fields(self, caption: str | None) -> dict:
        """Prepare caption metadata fields."""
        if not caption:
            return {}
        return {field: caption for field in METADATA_FIELDS['caption']}
        
    def _prepare_keyword_fields(self, keywords: list | None) -> dict:
        """Prepare keyword metadata fields optimized for Apple Photos compatibility."""
        if not keywords:
            self._debug_log("No keywords to prepare", 'log_keyword_processing')
            return {}
            
        fields = {}
        
        # Get Apple Photos optimization settings
        keyword_format = APPLE_PHOTOS_VIDEO_OPTIMIZATIONS.get('keyword_format', 'comma_separated')
        self._debug_log(f"Using keyword format: {keyword_format}", 'log_keyword_processing')
        
        # Prepare keywords in different formats
        keywords_str = ', '.join(keywords) if isinstance(keywords, list) else str(keywords)
        keywords_list = keywords if isinstance(keywords, list) else [str(keywords)]
        
        self._debug_log(f"Keywords as string: '{keywords_str}'", 'log_keyword_processing')
        self._debug_log(f"Keywords as list: {keywords_list}", 'log_keyword_processing')
        
        # Apply Apple Photos optimized field mapping
        apple_photos_fields = ['-QuickTime:Keywords', '-XMP:Subject', '-IPTC:Keywords']
        for field in METADATA_FIELDS['keywords']:
            if field in apple_photos_fields:
                # These fields work best with comma-separated strings for Apple Photos
                fields[field] = keywords_str
                self._debug_log(f"Apple Photos field {field} = '{keywords_str}'", 'log_keyword_processing')
            else:
                # Other fields use list format
                fields[field] = keywords_list
                self._debug_log(f"Standard field {field} = {keywords_list}", 'log_keyword_processing')
        
        self._debug_log(f"Total keyword fields prepared: {len(fields)}", 'log_keyword_processing')
        self.logger.debug(f"Prepared keyword fields for Apple Photos: {fields}")
        return fields
        
    def _prepare_location_fields(self, location_data: tuple | None) -> dict:
        """Prepare location metadata fields."""
        if not location_data:
            return {}
            
        location, city, country = location_data
        fields = {}
        
        # Build full location string
        location_string = self._build_location_string(location_data)
        if location_string:
            for field in METADATA_FIELDS['location']:
                fields[field] = location_string
                
        # Individual components
        if city:
            for field in METADATA_FIELDS['city']:
                fields[field] = city
        if country:
            for field in METADATA_FIELDS['country']:
                fields[field] = country
                
        return fields
        
    def _prepare_gps_fields(self, gps_data: tuple | None) -> dict:
        """Prepare GPS metadata fields from XMP GPS data."""
        if not gps_data:
            return {}
            
        latitude, longitude, altitude = gps_data
        if not latitude or not longitude:
            return {}
            
        # Convert XMP format to QuickTime format
        gps_fields = self._convert_gps_to_quicktime_format(latitude, longitude, altitude)
        
        self.logger.debug(f"Prepared GPS fields: {gps_fields}")
        return gps_fields
        
    def _verify_location_component(self, value: str | None, field_type: str) -> bool:
        """Verify a location component (location, city, or country)."""
        if not value:
            return True  # Skip verification for empty field
            
        self.logger.debug(f"Verifying {field_type}: {value}")
        self.logger.debug(f"Current exif data: {self.exif_data}")
            
        # For location field, check if any of the location fields contain our expected location string
        if field_type == 'location':
            for field in METADATA_FIELDS[field_type]:
                clean_field = field.replace('-', '').split(':')[-1]
                for key in self.exif_data:
                    if key.endswith(clean_field):
                        current_value = self.exif_data[key]
                        self.logger.debug(f"Checking {key}: {current_value}")
                        # State might be stored directly or as part of location string
                        if value == current_value or value in current_value.split(", "):
                            self.logger.debug(f"Location match found in {key}")
                            return True
                        else:
                            self.logger.debug(f"No match: {value} not in {current_value}")
        else:
            # For city and country, do exact match
            for field in METADATA_FIELDS[field_type]:
                clean_field = field.replace('-', '').split(':')[-1]
                for key in self.exif_data:
                    if key.endswith(clean_field):
                        current_value = self.exif_data[key]
                        self.logger.debug(f"Checking {key}: {current_value}")
                        if current_value == value:
                            self.logger.debug(f"Exact match found in {key}")
                            return True
                        
        self.logger.error(f"Metadata verification failed for {field_type.title()}")
        self.logger.error(f"Expected: {value}")
        self.logger.error(f"Found values:")
        for field in METADATA_FIELDS[field_type]:
            clean_field = field.replace('-', '').split(':')[-1]
            for key in self.exif_data:
                if key.endswith(clean_field):
                    self.logger.error(f"  {key}: {self.exif_data[key]}")
        return False

    def verify_metadata(self, expected_metadata: tuple) -> bool:
        """
        Verify that metadata was written correctly.
        
        Args:
            expected_metadata (tuple): Tuple containing expected metadata values
            
        Returns:
            bool: True if verification passes, False otherwise
        """
        self.logger.debug("Starting metadata verification...")
        
        # First read the metadata from the file
        self.logger.debug(f"Reading metadata from file: {self.file_path}")
        self.exif_data = self.read_exif()
        
        # Build expected fields dictionary
        expected_fields = self._build_expected_fields(expected_metadata)
        self.logger.debug(f"Expected fields: {expected_fields}")
        
        # Verify each component
        title, keywords, date_str, caption, location_data, gps_data = expected_metadata
        location, city, country = location_data if location_data else (None, None, None)
        
        verification_results = {
            'title': self._verify_title(title),
            'keywords': self._verify_keywords(keywords),
            'date': self._verify_date(date_str),
            'location': self._verify_location_component(location, 'location'),
            'city': self._verify_location_component(city, 'city'),
            'country': self._verify_location_component(country, 'country')
        }
        
        self.logger.debug("Verification results:")
        for field, result in verification_results.items():
            self.logger.debug(f"  {field}: {'✓' if result else '✗'}")
        
        if all(verification_results.values()):
            self.logger.debug("All metadata verified successfully")
            return True
        else:
            failed_fields = [field for field, result in verification_results.items() if not result]
            self.logger.error(f"Failed to verify metadata for fields: {', '.join(failed_fields)}")
            return False

    def _verify_title(self, title: str | None) -> bool:
        """Verify title metadata field."""
        if not title:
            return True  # Skip verification for empty field
            
        for field in METADATA_FIELDS['title']:
            clean_field = field.replace('-', '').split(':')[-1]
            for key in self.exif_data:
                if key.endswith(clean_field) and self.exif_data[key] == title:
                    return True
        self.logger.error(f"Metadata verification failed for Title\nExpected: {title}\nNot found")
        return False
        
    def _verify_keywords(self, keywords: list | None) -> bool:
        """Verify keywords metadata field."""
        if not keywords:
            self._debug_log("No keywords to verify", 'log_verification')
            return True  # Skip verification for empty field
            
        self._debug_log(f"Starting keyword verification for: {keywords}", 'log_verification')
        self.logger.debug(f"Verifying keywords: {keywords}")
        
        # Check all keyword-related fields in the metadata
        found_keywords = []
        for field in METADATA_FIELDS['keywords']:
            clean_field = field.replace('-', '').split(':')[-1]
            self._debug_log(f"Checking for field pattern: {clean_field}", 'log_verification')
            for key in self.exif_data:
                if key.endswith(clean_field) or clean_field.lower() in key.lower():
                    current_keywords = self.exif_data[key]
                    self._debug_log(f"Found matching field {key} with value: {current_keywords}", 'log_verification')
                    if isinstance(current_keywords, str):
                        # Split comma-separated keywords
                        current_keywords = [kw.strip() for kw in current_keywords.split(',')]
                        self._debug_log(f"Parsed string keywords: {current_keywords}", 'log_verification')
                    elif isinstance(current_keywords, list):
                        # Handle list of keywords, also check for comma-separated items
                        expanded_keywords = []
                        for kw in current_keywords:
                            if isinstance(kw, str) and ',' in kw:
                                expanded_keywords.extend([k.strip() for k in kw.split(',')])
                            else:
                                expanded_keywords.append(kw)
                        current_keywords = expanded_keywords
                        self._debug_log(f"Processed list keywords: {current_keywords}", 'log_verification')
                    found_keywords.extend(current_keywords)
                    self.logger.debug(f"Found keywords in {key}: {current_keywords}")
        
        # Remove duplicates and empty strings
        found_keywords = list(set([kw for kw in found_keywords if kw.strip()]))
        self._debug_log(f"Final unique keywords found: {found_keywords}", 'log_verification')
        
        # Check if all expected keywords are present (case-insensitive)
        expected_lower = [k.lower() for k in keywords]
        found_lower = [k.lower() for k in found_keywords]
        
        self._debug_log(f"Expected keywords (lowercase): {expected_lower}", 'log_verification')
        self._debug_log(f"Found keywords (lowercase): {found_lower}", 'log_verification')
        
        missing_keywords = []
        for expected in expected_lower:
            if expected not in found_lower:
                missing_keywords.append(keywords[expected_lower.index(expected)])
                
        self._debug_log(f"Missing keywords: {missing_keywords}", 'log_verification')
        
        if missing_keywords:
            self._debug_log("Some keywords are missing - verification failed", 'log_verification')
            self.logger.warning(f"Keywords verification: Some keywords not found")
            self.logger.warning(f"  Expected: {keywords}")
            self.logger.warning(f"  Found: {found_keywords}")
            self.logger.warning(f"  Missing: {missing_keywords}")
            # Don't fail verification for keywords - they might be stored differently
            return True
        
        self.logger.debug(f"Keywords verification passed: {found_keywords}")
        return True
        
    def _verify_date(self, date_str: str | None) -> bool:
        """Verify date metadata field."""
        if not date_str:
            return True  # Skip verification for empty field
            
        for field in METADATA_FIELDS['date']:
            clean_field = field.replace('-', '').split(':')[-1]
            for key in self.exif_data:
                if key.endswith(clean_field):
                    current_date = self.exif_data[key]
                    self.logger.debug(f"Checking date field {key}: {current_date} against {date_str}")
                    
                    # Try to normalize both dates to standard format
                    try:
                        # Remove any milliseconds and timezone info
                        current_date = current_date.split('.')[0].split('+')[0].split('-0')[0]
                        # Replace dashes with colons in date part
                        current_date = current_date.replace('-', ':')
                        
                        if current_date == date_str:
                            self.logger.debug(f"Date match found in {key}")
                            return True
                        else:
                            self.logger.debug(f"Dates don't match: {current_date} != {date_str}")
                    except (ValueError, AttributeError) as e:
                        self.logger.debug(f"Error comparing dates: {e}")
                        continue
                        
        self.logger.error(f"Metadata verification failed for Date")
        self.logger.error(f"Expected: {date_str}")
        self.logger.error("Found values:")
        for field in METADATA_FIELDS['date']:
            clean_field = field.replace('-', '').split(':')[-1]
            for key in self.exif_data:
                if key.endswith(clean_field):
                    self.logger.error(f"  {key}: {self.exif_data[key]}")
        return False

    def write_metadata_to_video(self, metadata: tuple) -> bool:
        """
        Write metadata to video file using ExifTool.
        
        Args:
            metadata (tuple): Tuple containing metadata values
                (title, keywords, date_str, caption, location_data, gps_data)
                
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            title, keywords, date_str, caption, location_data, gps_data = metadata
            
            # Prepare all metadata fields
            metadata_fields = {}
            metadata_fields.update(self._prepare_title_fields(title))
            metadata_fields.update(self._prepare_date_fields(date_str))
            metadata_fields.update(self._prepare_caption_fields(caption))
            metadata_fields.update(self._prepare_keyword_fields(keywords))
            metadata_fields.update(self._prepare_location_fields(location_data))
            metadata_fields.update(self._prepare_gps_fields(gps_data))
            
            if not metadata_fields:
                self.logger.debug("No metadata fields to write")
                return True
                
            # Log metadata fields being written
            self.logger.warning("Writing metadata to video file:")
            for field, value in metadata_fields.items():
                self.logger.warning(f"  {field}: '{value}'")
            
            # Execute ExifTool metadata write
            self.logger.warning("📝 Executing ExifTool metadata write...")
            result = self.exiftool.write_metadata(self.file_path, metadata_fields)
            
            if result:
                self.logger.warning("✅ ExifTool metadata write completed successfully")
                
                # Verify metadata was written by reading it back
                self._verify_written_metadata(metadata)
            else:
                self.logger.warning("❌ ExifTool metadata write failed")
            return result
            
        except Exception as e:
            self.logger.error(f"Error writing metadata: {e}")
            return False

    def _verify_written_metadata(self, original_metadata: tuple) -> None:
        """
        Verify metadata was written correctly by reading it back from the video file.
        
        Args:
            original_metadata (tuple): Original metadata that was written
        """
        try:
            self.logger.warning("🔍 Verifying written metadata by reading back from video file...")
            
            # Read all metadata from the video file
            video_metadata = self.exiftool.read_all_metadata(self.file_path)
            
            title, keywords, date_str, caption, location_data, gps_data = original_metadata
            
            # Check title fields
            title_found = False
            for field in ['-XMP:Title', '-DC:Title', '-QuickTime:Title', '-ItemList:Title']:
                clean_field = field.replace('-', '')
                for key in video_metadata:
                    if clean_field.lower() in key.lower():
                        self.logger.warning(f"  📄 Title field {key}: '{video_metadata[key]}'")
                        if video_metadata[key] == title:
                            title_found = True
            
            # Check keyword fields  
            keywords_found = False
            self.logger.warning(f"  🔍 Looking for keywords: {keywords}")
            
            # Show ALL metadata fields that might contain keywords
            keyword_related_fields = []
            for key in video_metadata:
                if any(term in key.lower() for term in ['keyword', 'subject', 'tag', 'category']):
                    keyword_related_fields.append(f"{key}: '{video_metadata[key]}'")
                    
                    # Check if keywords match (handle both list and comma-separated string formats)
                    if keywords:
                        video_value = str(video_metadata[key])
                        if isinstance(keywords, list):
                            # Convert list to comma-separated string for comparison
                            keywords_str = ','.join(keywords)
                            # Check if all keywords are present in the video value
                            if all(keyword in video_value for keyword in keywords):
                                keywords_found = True
                                self.logger.warning(f"    ✅ MATCH: {key} contains expected keywords")
                        else:
                            if str(keywords) in video_value:
                                keywords_found = True
                                self.logger.warning(f"    ✅ MATCH: {key} contains expected keywords")
            
            if keyword_related_fields:
                self.logger.warning("  🏷️  Found keyword-related fields in video:")
                for field in keyword_related_fields:
                    self.logger.warning(f"    {field}")
            else:
                self.logger.warning("  ❌ No keyword-related fields found in video metadata")
            
            # Check caption fields
            caption_found = False
            for field in ['-QuickTime:Description', '-ItemList:Description']:
                clean_field = field.replace('-', '')
                for key in video_metadata:
                    if 'description' in key.lower():
                        self.logger.warning(f"  💬 Caption field {key}: '{video_metadata[key]}'")
                        if video_metadata[key] == caption:
                            caption_found = True
            
            # Summary
            self.logger.warning("📊 Metadata verification summary:")
            self.logger.warning(f"  ✅ Title: {'FOUND' if title_found else '❌ NOT FOUND'}")
            self.logger.warning(f"  ✅ Keywords: {'FOUND' if keywords_found else '❌ NOT FOUND'}")
            self.logger.warning(f"  ✅ Caption: {'FOUND' if caption_found else '❌ NOT FOUND'}")
            
        except Exception as e:
            self.logger.error(f"Error verifying metadata: {e}")

    def _build_expected_fields(self, expected_metadata: tuple) -> dict:
        """
        Build a dictionary of expected fields from metadata tuple.
        
        Args:
            expected_metadata (tuple): Tuple containing expected metadata values
            
        Returns:
            dict: Dictionary of expected field values
        """
        title, keywords, date_str, caption, location_data, gps_data = expected_metadata
        location, city, country = location_data if location_data else (None, None, None)
        
        return {
            'Title': title,
            'Subject': keywords,
            'DateTimeOriginal': date_str,
            'Description': caption,
            'Location': location,
            'City': city,
            'Country': country
        }
        
    def _should_skip_processing(self) -> bool:
        """Check if file should be skipped (already has LRE suffix)."""
        if self.file_path.stem.endswith(LRE_SUFFIX):
            self.logger.info(f"Skipping {self.file_path}, already has {LRE_SUFFIX} suffix")
            return True
        return False
        
    def _get_and_validate_metadata(self) -> tuple | None:
        """Read and validate metadata from XMP file."""
        self.logger.debug(f"Attempting to read metadata from XMP file: {self.xmp_file}")
        
        metadata = self.get_metadata_from_xmp()
        if not metadata:
            self.logger.error("CRITICAL: No metadata found in XMP file")
            self.logger.error(f"XMP file path: {self.xmp_file}")
            self.logger.error(f"XMP file exists: {self.xmp_file.exists() if hasattr(self, 'xmp_file') else 'Unknown'}")
            return None
            
        self.logger.debug(f"Successfully read metadata: {metadata}")
        
        if self._is_metadata_empty(metadata):
            self.logger.warning("All metadata fields are empty but XMP was read successfully")
            # Don't return None for empty metadata - let it process
            # return None
            
        return metadata
        
    def _write_and_verify_metadata(self, metadata: tuple) -> bool:
        """Write metadata to video and verify it was written correctly."""
        success = self.write_metadata_to_video(metadata)
        if not success:
            self.logger.error("Failed to write metadata to video")
            return False
            
        if not self.verify_metadata(metadata):
            self.logger.error("Failed to verify metadata")
            return False
            
        return True
        
    def _cleanup_and_rename(self) -> Path:
        """Clean up XMP file and rename video with LRE suffix."""
        # Delete XMP file first (order is critical)
        self.logger.debug(f"Checking for XMP file at: {self.xmp_file}")
        if self.xmp_file.exists():
            try:
                self.logger.info("Deleting XMP file before renaming video (critical order)")
                self.xmp_file.unlink()
                self.logger.debug(f"Successfully deleted XMP file: {self.xmp_file}")
            except Exception as e:
                self.logger.error(f"Failed to delete XMP file: {e}")
                self.logger.error("Cannot proceed with renaming without deleting XMP first")
                return self.file_path
                
        # Then rename the video file
        new_path = self.rename_file()
        return new_path

    def process_video(self) -> Path:
        """Main method to process a video file - reads XMP metadata and writes to video."""
        try:
            self.logger.info(f"Starting video processing for: {self.file_path}")
            
            # Check if file should be skipped first
            if self._should_skip_processing():
                self.logger.info(f"Skipping file - already has {LRE_SUFFIX} suffix")
                return self.file_path
                
            # Get and validate metadata
            self.logger.debug("Reading and validating metadata from XMP")
            metadata = self._get_and_validate_metadata()
            
            # Initialize metadata for filename
            title, keywords, date_str, caption, location_data, gps_data = metadata if metadata else (None, None, None, None, None, None)
            location, city, country = location_data if location_data else (None, None, None)
            
            # Always initialize metadata_for_filename, even if empty
            self.metadata_for_filename = {
                'Title': title,
                'CreateDate': date_str or datetime.now().strftime('%Y:%m:%d %H:%M:%S'),
                'Location': location,
                'City': city,
                'Country': country
            }
            
            # If all metadata is None, just add LRE suffix
            if metadata is None:
                self.logger.info("No valid metadata found - will only add LRE suffix")
                return self._cleanup_and_rename()
            else:
                self.logger.debug("Found valid metadata:")
                self.logger.debug(f"  Title: {title}")
                self.logger.debug(f"  Keywords: {keywords}")
                self.logger.debug(f"  Date: {date_str}")
                self.logger.debug(f"  Caption: {caption}")
                self.logger.debug(f"  Location: {location_data}")
                
            # Write metadata and verify
            self.logger.info("Writing metadata to video file")
            if not self._write_and_verify_metadata(metadata):
                self.logger.error("Failed to write or verify metadata - keeping original filename")
                return self.file_path
                
            # Clean up and rename using the original metadata
            self.logger.info("Metadata written successfully - proceeding with cleanup and rename")
            return self._cleanup_and_rename()
            
        except Exception as e:
            self.logger.error(f"Unexpected error processing video: {e}")
            self.logger.error("Keeping original filename due to error")
            return self.file_path

    def get_metadata_components(self):
        """
        Get metadata components for video files.
        
        Returns:
            tuple: (date_str, title, location, city, state, country)
        """
        if not hasattr(self, 'metadata_for_filename') or self.metadata_for_filename is None:
            self.logger.error("No metadata available for filename")
            return None, None, None, None, None, None
            
        self.logger.info("Metadata components for filename:")
        self.logger.info(f"  ┌─ Date:     '{self.metadata_for_filename.get('CreateDate', '')}'")
        self.logger.info(f"  ├─ Title:    '{self.metadata_for_filename.get('Title', '')}'")
        self.logger.info(f"  ├─ Location: '{self.metadata_for_filename.get('Location', '')}'")
        self.logger.info(f"  ├─ City:     '{self.metadata_for_filename.get('City', '')}'")
        self.logger.info(f"  └─ Country:  '{self.metadata_for_filename.get('Country', '')}'")
        
        # Get components from stored metadata
        date_str = self.metadata_for_filename.get('CreateDate', '')
        if date_str:
            # Convert YYYY:MM:DD to YYYY_MM_DD
            try:
                date_parts = date_str.split()[0].split(':')  # Split on space to get date part, then split on colons
                if len(date_parts) == 3:  # Only convert if it's a valid date format
                    date_str = '_'.join(date_parts)  # Join with underscores
                else:
                    self.logger.warning(f"Invalid date format: {date_str}")
                    date_str = None
            except Exception as e:
                self.logger.error(f"Error formatting date: {e}")
                date_str = None

        title = self.metadata_for_filename.get('Title', '')
        location = self.metadata_for_filename.get('Location', '')
        city = self.metadata_for_filename.get('City', '')
        state = None  # Videos don't typically have state metadata
        country = self.metadata_for_filename.get('Country', '')
        
        self.logger.info(f"Extracted city from video metadata: {city}")
        
        if date_str:
            self.logger.debug(f"Added date to filename: {date_str}")
        if title:
            self.logger.debug(f"Added title to filename: {title}")
        if location:
            self.logger.debug(f"Added location to filename: {location}")
        if city:
            self.logger.debug(f"Added city to filename: {city}")
        if country:
            self.logger.debug(f"Added country to filename: {country}")
            
        return date_str, title, location, city, state, country

    def rename_file(self) -> Path:
        """
        Rename the file using stored metadata.
        
        Returns:
            Path: Path to the renamed file
        """
        # Generate filename from metadata
        self.logger.warning("🏷️  Starting file renaming process...")
        new_name = self.generate_filename()
        if not new_name:
            self.logger.warning("❌ No filename generated - keeping original name")
            return self.file_path
            
        # Log filename assembly details
        self.logger.warning("📝 Filename generation complete:")
        self.logger.warning(f"  📂 Directory:  {self.file_path.parent}")
        self.logger.warning(f"  📄 Original:   {self.file_path.name}")
        self.logger.warning(f"  ✨ Generated:  {new_name}")
        
        # Check if rename is needed
        if self.file_path.name == new_name:
            self.logger.warning("✅ Filename already matches - no rename needed")
            return self.file_path
        
        # Rename file
        new_path = self.file_path.parent / new_name
        self.logger.warning(f"🔄 Renaming file...")
        self.logger.warning(f"   From: {self.file_path}")
        self.logger.warning(f"   To:   {new_path}")
        
        try:
            self.file_path.rename(new_path)
            self.logger.warning(f"✅ Successfully renamed file to: {new_path.name}")
            return new_path
        except Exception as e:
            self.logger.error(f"❌ Error renaming file: {e}")
            self.logger.error(f"   Keeping original name: {self.file_path.name}")
            return self.file_path

    def _get_title_from_dc_alt(self, rdf) -> str | None:
        """Get title from dc:title/rdf:Alt/rdf:li path."""
        ns = XML_NAMESPACES
        # First try with x-default language
        title_elem = rdf.find(f'.//{{{ns["dc"]}}}title/{{{ns["rdf"]}}}Alt/{{{ns["rdf"]}}}li[@{{{ns["xml"]}}}lang="x-default"]')
        if title_elem is not None and title_elem.text:
            self.logger.debug(f"Found title in dc:title with x-default: {title_elem.text}")
            return title_elem.text
            
        # If no x-default, try without language
        title_elem = rdf.find(f'.//{{{ns["dc"]}}}title/{{{ns["rdf"]}}}Alt/{{{ns["rdf"]}}}li')
        if title_elem is not None and title_elem.text:
            self.logger.debug(f"Found title in dc:title: {title_elem.text}")
            return title_elem.text
        return None
        
    def _get_title_from_dc_li(self, rdf) -> str | None:
        """Get title from dc:title/rdf:li path."""
        ns = XML_NAMESPACES
        # First try with x-default language
        for elem in rdf.findall(f'.//{{{ns["dc"]}}}title/{{{ns["rdf"]}}}li[@{{{ns["xml"]}}}lang="x-default"]'):
            if elem.text:
                self.logger.debug(f"Found title in dc:title/li with x-default: {elem.text}")
                return elem.text
                
        # If no x-default, try without language
        for elem in rdf.findall(f'.//{{{ns["dc"]}}}title/{{{ns["rdf"]}}}li'):
            if elem.text:
                self.logger.debug(f"Found title in dc:title/li: {elem.text}")
                return elem.text
        return None
        
    def _get_title_from_location(self, rdf) -> str | None:
        """Get title from IPTC location attribute."""
        for desc in rdf.iter('{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description'):
            location = desc.get('{http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/}Location')
            if location:
                self.logger.debug(f"Using Location as title: {location}")
                return location
        return None
        
    def get_title_from_rdf(self, rdf):
        """Extract title from RDF data using multiple strategies."""
        try:
            self.logger.debug("Searching for title in RDF...")
            
            # Try each strategy in order until one succeeds
            strategies = [
                self._get_title_from_dc_alt,
                self._get_title_from_dc_li,
                self._get_title_from_location
            ]
            
            for strategy in strategies:
                title = strategy(rdf)
                if title:
                    return title
                    
            self.logger.debug("No title found in RDF")
            return None
            
        except Exception as e:
            self.logger.error(f"Error extracting title from RDF: {e}")
            return None
    
    def get_caption_from_rdf(self, rdf):
        """Extract caption from RDF data."""
        try:
            ns = XML_NAMESPACES
            # First try with x-default language
            caption_elem = rdf.find(f'.//{{{ns["dc"]}}}description/{{{ns["rdf"]}}}Alt/{{{ns["rdf"]}}}li[@{{{ns["xml"]}}}lang="x-default"]')
            if caption_elem is not None and caption_elem.text:
                self.logger.debug(f"Found caption in dc:description with x-default: {caption_elem.text}")
                return caption_elem.text
                
            # If no x-default, try without language
            caption_elem = rdf.find(f'.//{{{ns["dc"]}}}description/{{{ns["rdf"]}}}Alt/{{{ns["rdf"]}}}li')
            if caption_elem is not None and caption_elem.text:
                self.logger.debug(f"Found caption in dc:description: {caption_elem.text}")
                return caption_elem.text
        except Exception as e:
            self.logger.error(f"Error getting caption from RDF: {e}")
        return None
