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
    XML_NAMESPACES,
    METADATA_FIELDS,
    VERIFY_FIELDS,
    VIDEO_PATTERN,
    MCCARTYS_PREFIX,
    MCCARTYS_REPLACEMENT,
    LRE_SUFFIX
)
from processors.media_processor import MediaProcessor
from utils.exiftool import ExifTool  # Import the new ExifTool class

class VideoProcessor(MediaProcessor):
    """A class to process video files and their metadata using exiftool."""
    
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
        xmp_path = Path(file_path).with_suffix('.xmp')
        if not xmp_path.exists():
            self.logger.warning(f"No XMP sidecar file found: {xmp_path}")
            
        # Initialize the ExifTool class
        self.exiftool = ExifTool()
            
    def read_metadata_from_xmp(self) -> tuple:
        """
        Read metadata from XMP sidecar file.
        
        Returns:
            tuple: (title, keywords, date_str, caption, location_data)
        """
        xmp_path = self.file_path.with_suffix('.xmp')
        if not xmp_path.exists():
            self.logger.warning(f"No XMP sidecar file found: {xmp_path}")
            return None, None, None, None, (None, None, None)
            
        try:
            tree = ET.parse(xmp_path)
            root = tree.getroot()
            
            # Get title
            title = self.get_title_from_rdf(root)
            
            # Get keywords
            keywords = self.get_keywords_from_rdf(root)
            
            # Get caption
            caption = self.get_caption_from_rdf(root)
            
            # Get location data
            location, city, country = self.get_location_from_rdf(root)
            
            # Get date from exiftool for consistency
            date_str = self.exiftool.read_date_from_xmp(xmp_path)
                
            return title, keywords, date_str, caption, (location, city, country)
            
        except ET.ParseError as e:
            self.logger.error(f"Error parsing XMP file: {e}")
            return None, None, None, None, (None, None, None)
            
    def _get_keywords_from_hierarchical(self, rdf) -> list[str] | None:
        """Get keywords from hierarchical subjects."""
        ns = XML_NAMESPACES
        keywords = []
        subject_path = f'.//{{{ns["lr"]}}}hierarchicalSubject/{{{ns["rdf"]}}}Bag/{{{ns["rdf"]}}}li'
        for elem in rdf.findall(subject_path):
            if elem.text:
                keywords.append(elem.text)
        return keywords if keywords else None
        
    def _get_keywords_from_flat(self, rdf) -> list[str] | None:
        """Get keywords from flat subject list."""
        ns = XML_NAMESPACES
        keywords = []
        subject_path = f'.//{{{ns["dc"]}}}subject/{{{ns["rdf"]}}}Bag/{{{ns["rdf"]}}}li'
        for elem in rdf.findall(subject_path):
            if elem.text:
                keywords.append(elem.text)
        return keywords if keywords else None
        
    def get_keywords_from_rdf(self, rdf):
        """Extract keywords from RDF data using multiple strategies."""
        try:
            # Try hierarchical subjects first, then fall back to flat subjects
            strategies = [
                self._get_keywords_from_hierarchical,
                self._get_keywords_from_flat
            ]
            
            for strategy in strategies:
                keywords = strategy(rdf)
                if keywords:
                    self.logger.debug(f"Found keywords: {keywords}")
                    return keywords
                    
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
            location = desc.find(f'.//{{{ns["Iptc4xmpCore"]}}}Location')
            city = desc.find(f'.//{{{ns["Iptc4xmpCore"]}}}City')
            country = desc.find(f'.//{{{ns["Iptc4xmpCore"]}}}CountryName')
            
            location_text = location.text if location is not None else None
            city_text = city.text if city is not None else None
            country_text = country.text if country is not None else None
            
            if any([location_text, city_text, country_text]):
                self.logger.debug(f"Found IPTC location data: {location_text} ({city_text}, {country_text})")
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
        
    def get_metadata_from_xmp(self):
        """Get metadata from XMP file."""
        metadata = self.read_metadata_from_xmp()
        title, keywords, date_str, caption, location_data = metadata
        
        self._log_metadata_status(metadata)
        return metadata
        
    def _log_metadata_status(self, metadata: tuple) -> None:
        """Log status of metadata fields."""
        title, keywords, date_str, caption, location_data = metadata
        
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
                
    def _normalize_date_parts(self, date_str: str) -> tuple[str, str, str] | None:
        """
        Split and normalize date parts.
        
        Args:
            date_str (str): Date string to normalize
            
        Returns:
            tuple[str, str, str] | None: Tuple of (date_part, time_part, tz_part) or None if invalid
        """
        if not self._is_valid_date_string(date_str):
            return None
            
        parts = date_str.split()
        if len(parts) < 2:
            return None
            
        date_part = self._normalize_date_component(parts[0])
        time_part, tz_part = self._extract_time_and_timezone(parts)
        
        if not self._is_valid_time_format(time_part):
            return None
            
        return date_part, time_part, tz_part
        
    def _is_valid_date_string(self, date_str: str) -> bool:
        """Check if date string is valid."""
        return bool(date_str and isinstance(date_str, str))
        
    def _normalize_date_component(self, date_part: str) -> str:
        """Normalize date component to YYYY:MM:DD format."""
        return date_part.replace('-', ':')
        
    def _extract_time_and_timezone(self, parts: list[str]) -> tuple[str, str]:
        """Extract time and timezone components from date parts."""
        time_part = parts[1]
        tz_part = ''
        
        # Handle timezone attached to time
        if any(c in time_part for c in '+-'):
            time_part, tz_part = self._split_time_and_timezone(time_part)
        elif len(parts) > 2:
            tz_part = parts[2]
            
        return time_part, tz_part
        
    def _split_time_and_timezone(self, time_str: str) -> tuple[str, str]:
        """Split time string into time and timezone parts."""
        for i, c in enumerate(time_str):
            if c in '+-':
                return time_str[:i], time_str[i:]
        return time_str, ''
        
    def _is_valid_time_format(self, time_str: str) -> bool:
        """Check if time string is in valid format."""
        return time_str.replace(':', '').isdigit()

    def normalize_date(self, date_str: str) -> str | None:
        """
        Normalize date format to YYYY:MM:DD HH:MM:SS format that exiftool expects.
        
        Args:
            date_str (str): Date string to normalize
            
        Returns:
            str | None: Normalized date string or None if invalid
        """
        if not self._is_valid_date_string(date_str):
            return None
            
        try:
            parts = self._normalize_date_parts(date_str)
            if not parts:
                return None
                
            date_part, time_part, tz_part = parts
            
            if not self._is_valid_date_format(date_part):
                return None
                
            result = self._build_date_string(date_part, time_part, tz_part)
            return result
            
        except Exception as e:
            self.logger.error(f"Error normalizing date {date_str}: {e}")
            return None
            
    def _is_valid_date_format(self, date_str: str) -> bool:
        """Check if date string is in valid YYYY:MM:DD format."""
        return date_str.replace(':', '').isdigit()
        
    def _build_date_string(self, date_part: str, time_part: str, tz_part: str) -> str:
        """Build the final date string with optional timezone."""
        if not date_part or not time_part:
            return ''
            
        result = f"{date_part} {time_part}"
        if tz_part:
            normalized_tz = self._normalize_timezone(tz_part)
            if normalized_tz:
                result += normalized_tz
        return result
        
    def _normalize_timezone(self, tz_part: str) -> str:
        """
        Normalize timezone format to +/-HHMM.
        
        Args:
            tz_part (str): Timezone part of the date string
            
        Returns:
            str: Normalized timezone string
        """
        if not self._is_valid_timezone_input(tz_part):
            return ''
            
        # Already in correct format (-0500)
        if self._is_normalized_timezone_format(tz_part):
            return tz_part
            
        # Convert -5 to -0500
        try:
            clean_tz = self._clean_timezone_string(tz_part)
            if not clean_tz:
                return ''
                
            # Extract sign and number
            sign = clean_tz[0]
            hours = int(clean_tz[1:])
            
            if not self._is_valid_timezone_hours(hours, tz_part):
                return ''
                
            return f"{sign}{hours:02d}00"
        except (ValueError, IndexError):
            return ''
            
    def _is_valid_timezone_input(self, tz_part: str) -> bool:
        """Check if timezone input is valid."""
        return bool(tz_part and isinstance(tz_part, str))
        
    def _is_normalized_timezone_format(self, tz_part: str) -> bool:
        """Check if timezone is already in normalized format."""
        return len(tz_part) == 5 and tz_part[0] in ('+', '-')
        
    def _clean_timezone_string(self, tz_part: str) -> str:
        """Clean timezone string to contain only valid characters."""
        clean_tz = self._extract_valid_timezone_chars(tz_part)
        if not self._is_valid_timezone_chars(clean_tz):
            return ''
            
        return self._ensure_timezone_sign(clean_tz)
        
    def _extract_valid_timezone_chars(self, tz_part: str) -> str:
        """Extract only valid timezone characters (digits, +, -)."""
        return ''.join(c for c in tz_part if c.isdigit() or c in '+-')
        
    def _is_valid_timezone_chars(self, tz_str: str) -> bool:
        """Check if timezone string contains valid characters."""
        return bool(tz_str and tz_str not in '+-')
        
    def _ensure_timezone_sign(self, tz_str: str) -> str:
        """Ensure timezone string has a sign prefix."""
        if tz_str[0] not in '+-':
            return '+' + tz_str
        return tz_str
        
    def _is_valid_timezone_hours(self, hours: int, original_tz: str) -> bool:
        """Check if timezone hours are valid."""
        if hours > 23:  # Invalid timezone
            return False
            
        # If we had to clean non-numeric characters, return False
        if len(original_tz.replace('+', '').replace('-', '')) != len(str(hours)):
            return False
            
        return True
        
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
                
            # Convert to common format YYYY:MM:DD HH:MM:SS
            def normalize_date(date_str):
                # Split into parts
                parts = date_str.split()
                if len(parts) < 2:
                    return None
                    
                # Get date and time parts
                date_part = parts[0].replace('-', ':')
                time_part = parts[1].split('.')[0]  # Remove subseconds
                
                # Remove timezone if present
                time_part = time_part.split('-')[0].split('+')[0]
                
                return f"{date_part} {time_part}"
                
            norm1 = normalize_date(date1)
            norm2 = normalize_date(date2)
            
            if not norm1 or not norm2:
                return False
                
            return norm1 == norm2
            
        except Exception as e:
            self.logger.error(f"Error comparing dates {date1} and {date2}: {e}")
            return False

    def _prepare_title_fields(self, title: str | None) -> dict:
        """Prepare title metadata fields."""
        if not title:
            return {}
        return {field: title for field in METADATA_FIELDS['title']}
        
    def _prepare_date_fields(self, date_str: str | None) -> dict:
        """Prepare date metadata fields."""
        if not date_str:
            return {}
        return {field: date_str for field in METADATA_FIELDS['date']}
        
    def _prepare_caption_fields(self, caption: str | None) -> dict:
        """Prepare caption metadata fields."""
        if not caption:
            return {}
        return {field: caption for field in METADATA_FIELDS['caption']}
        
    def _prepare_keyword_fields(self, keywords: list | None) -> dict:
        """Prepare keyword metadata fields."""
        if not keywords:
            return {}
        return {field: keywords for field in METADATA_FIELDS['keywords']}
        
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
        title, keywords, date_str, caption, location_data = expected_metadata
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
            return True  # Skip verification for empty field
            
        for field in METADATA_FIELDS['keywords']:
            clean_field = field.replace('-', '').split(':')[-1]
            for key in self.exif_data:
                if key.endswith(clean_field):
                    current_keywords = self.exif_data[key]
                    if isinstance(current_keywords, str):
                        current_keywords = [current_keywords]
                    if set(current_keywords) == set(keywords):
                        return True
        self.logger.error(f"Metadata verification failed for Keywords\nExpected: {keywords}\nNot found")
        return False
        
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
                (title, keywords, date_str, caption, location_data)
                
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            title, keywords, date_str, caption, location_data = metadata
            
            # Prepare all metadata fields
            metadata_fields = {}
            metadata_fields.update(self._prepare_title_fields(title))
            metadata_fields.update(self._prepare_date_fields(date_str))
            metadata_fields.update(self._prepare_caption_fields(caption))
            metadata_fields.update(self._prepare_keyword_fields(keywords))
            metadata_fields.update(self._prepare_location_fields(location_data))
            
            if not metadata_fields:
                self.logger.debug("No metadata fields to write")
                return True
                
            # Log metadata fields being written
            self.logger.debug(f"Writing metadata fields: {metadata_fields}")
            
            # Write metadata using exiftool
            return self.exiftool.write_metadata(self.file_path, metadata_fields)
            
        except Exception as e:
            self.logger.error(f"Error writing metadata: {e}")
            return False

    def _build_expected_fields(self, expected_metadata: tuple) -> dict:
        """
        Build a dictionary of expected fields from metadata tuple.
        
        Args:
            expected_metadata (tuple): Tuple containing expected metadata values
            
        Returns:
            dict: Dictionary of expected field values
        """
        title, keywords, date_str, caption, location_data = expected_metadata
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
        metadata = self.get_metadata_from_xmp()
        if not metadata:
            self.logger.warning("No metadata found in XMP file")
            return None
            
        if self._is_metadata_empty(metadata):
            self.logger.info("All metadata fields are empty")
            return None
            
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
        xmp_path = self.file_path.with_suffix('.xmp')
        self.logger.debug(f"Checking for XMP file at: {xmp_path}")
        if xmp_path.exists():
            try:
                self.logger.info("Deleting XMP file before renaming video (critical order)")
                xmp_path.unlink()
                self.logger.debug(f"Successfully deleted XMP file: {xmp_path}")
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
            title, keywords, date_str, caption, location_data = metadata if metadata else (None, None, None, None, None)
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
            tuple: (date_str, title, location, city, country)
        """
        if not hasattr(self, 'metadata_for_filename') or self.metadata_for_filename is None:
            self.logger.error("No metadata available for filename")
            return None, None, None, None, None
            
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
        country = self.metadata_for_filename.get('Country', '')
        
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
            
        return date_str, title, location, city, country

    def rename_file(self) -> Path:
        """
        Rename the file using stored metadata.
        
        Returns:
            Path: Path to the renamed file
        """
        # Generate filename from metadata
        new_name = self.generate_filename()
        if not new_name:
            return self.file_path
            
        # Log filename assembly
        self.logger.info("Final filename assembly:")
        self.logger.info(f"  Original: {self.file_path.name}")
        self.logger.info(f"  New:      {new_name}")
        
        # Rename file
        new_path = self.file_path.parent / new_name
        try:
            self.file_path.rename(new_path)
            self.logger.info(f"Successfully renamed file to: {new_path}")
            return new_path
        except Exception as e:
            self.logger.error(f"Error renaming file: {e}")
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
            caption_path = f'.//{{{ns["dc"]}}}description/{{{ns["rdf"]}}}Alt/{{{ns["rdf"]}}}li'
            caption_elem = rdf.find(caption_path)
            if caption_elem is not None:
                self.logger.debug(f"Found caption: {caption_elem.text}")
                return caption_elem.text
        except Exception as e:
            self.logger.error(f"Error getting caption from RDF: {e}")
        return None
