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
        
    def _get_photoshop_location(self, rdf) -> tuple[str | None, str | None, str | None]:
        """Extract location data from photoshop namespace."""
        for desc in rdf.iter('{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description'):
            city = desc.get('{http://ns.adobe.com/photoshop/1.0/}City')
            country = desc.get('{http://ns.adobe.com/photoshop/1.0/}Country')
            state = desc.get('{http://ns.adobe.com/photoshop/1.0/}State')
            
            location = self._build_location_string(city, state, country)
            
            if city or country:
                self.logger.debug(f"Found Photoshop location data: {location} ({city}, {country})")
                return location, city, country
                
        return None, None, None
        
    def _build_location_string(self, city: str | None, state: str | None, country: str | None) -> str | None:
        """Build a location string from city, state, and country parts."""
        location_parts = []
        if city:
            location_parts.append(city)
        if state:
            location_parts.append(state)
        if country:
            location_parts.append(country)
            
        return ", ".join(location_parts) if location_parts else None

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

    def write_metadata_to_video(self, metadata: tuple) -> bool:
        """
        Write metadata to video file using exiftool.
        
        Args:
            metadata (tuple): Tuple containing metadata to write
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Prepare metadata fields
            title, keywords, date_str, caption, location_data = metadata
            fields = {
                'Title': title,
                'Subject': keywords,
                'DateTimeOriginal': date_str,
                'Description': caption,
            }
            
            if location_data:
                location, city, country = location_data
                fields.update({
                    'Location': location,
                    'City': city,
                    'Country': country
                })
                
            # Write metadata using exiftool wrapper
            return self.exiftool.write_metadata(self.file_path, fields)
            
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
        
    def _verify_subject_field(self, expected: list, current: str | list) -> bool:
        """
        Verify that Subject/keywords match.
        
        Args:
            expected (list): Expected keywords
            current (str | list): Current keywords value
            
        Returns:
            bool: True if keywords match, False otherwise
        """
        if not current:
            return False
            
        # Convert string keywords to list
        if isinstance(current, str):
            current = [current]
            
        # Compare keywords as sets to ignore order
        return set(expected) == set(current)
        
    def _verify_field(self, field: str, expected: str | list, current: str | list) -> bool:
        """
        Verify that a field matches its expected value.
        
        Args:
            field (str): Field name
            expected (str | list): Expected value
            current (str | list): Current value
            
        Returns:
            bool: True if values match, False otherwise
        """
        if not current:
            self.logger.error(f"Metadata verification failed for {field}\nExpected: {expected}\nNot found")
            return False
            
        # Handle different field types
        if field == 'Subject':
            if not self._verify_subject_field(expected, current):
                self.logger.error(f"Metadata verification failed for {field}\nExpected: {expected}\nGot: {current}")
                return False
        elif field == 'DateTimeOriginal':
            if not self.dates_match(expected, current):
                self.logger.error(f"Metadata verification failed for {field}\nExpected: {expected}\nGot: {current}")
                return False
        else:
            if expected != current:
                self.logger.error(f"Metadata verification failed for {field}\nExpected: {expected}\nGot: {current}")
                return False
                
        return True
        
    def _get_current_metadata(self) -> dict | None:
        """
        Get current metadata, handling errors.
        
        Returns:
            dict | None: Current metadata or None if error
        """
        try:
            current = self.read_exif()
            if not current:
                self.logger.error("Failed to read current metadata")
                return None
            return current
        except Exception as e:
            self.logger.error(f"Error reading metadata: {e}")
            return None
            
    def _verify_all_fields(self, expected_fields: dict, current: dict) -> bool:
        """
        Verify all expected fields against current metadata.
        
        Args:
            expected_fields (dict): Dictionary of expected field values
            current (dict): Current metadata values
            
        Returns:
            bool: True if all fields match, False otherwise
        """
        for field, expected in expected_fields.items():
            if not expected:
                continue
                
            if not self._verify_field(field, expected, current.get(field)):
                return False
                
        return True
        
    def verify_metadata(self, expected_metadata: tuple) -> bool:
        """
        Verify that metadata was written correctly.
        
        Args:
            expected_metadata (tuple): Tuple containing expected metadata values
            
        Returns:
            bool: True if verification passes, False otherwise
        """
        # Get current metadata
        current = self._get_current_metadata()
        if not current:
            return False
            
        # Build expected fields dictionary
        expected_fields = self._build_expected_fields(expected_metadata)
        
        # Verify all fields
        return self._verify_all_fields(expected_fields, current)
            
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
        if xmp_path.exists():
            try:
                xmp_path.unlink()
                self.logger.debug(f"Deleted XMP file: {xmp_path}")
            except Exception as e:
                self.logger.error(f"Failed to delete XMP file: {e}")
                return self.file_path
                
        # Then rename the video file
        new_path = self.file_path.with_name(f"{self.file_path.stem}{LRE_SUFFIX}{self.file_path.suffix}")
        try:
            self.file_path.rename(new_path)
            self.logger.info(f"Renamed {self.file_path} to {new_path}")
            return new_path
        except Exception as e:
            self.logger.error(f"Failed to rename file: {e}")
            return self.file_path

    def process_video(self) -> Path:
        """Main method to process a video file - reads XMP metadata and writes to video."""
        try:
            # Check if file should be skipped first
            if self._should_skip_processing():
                return self.file_path
                
            # Get and validate metadata
            metadata = self._get_and_validate_metadata()
            if not metadata:
                return self._cleanup_and_rename()
                
            # Write and verify metadata
            if not self._write_and_verify_metadata(metadata):
                return self.file_path
                
            # Clean up and rename
            return self._cleanup_and_rename()
            
        except Exception as e:
            self.logger.error(f"Error processing video: {e}")
            return self.file_path

    def _get_title_from_dc_alt(self, rdf) -> str | None:
        """Get title from dc:title/rdf:Alt/rdf:li path."""
        ns = XML_NAMESPACES
        title_elem = rdf.find(f'.//{{{ns["dc"]}}}title/{{{ns["rdf"]}}}Alt/{{{ns["rdf"]}}}li')
        if title_elem is not None and title_elem.text:
            self.logger.debug(f"Found title in dc:title: {title_elem.text}")
            return title_elem.text
        return None
        
    def _get_title_from_dc_li(self, rdf) -> str | None:
        """Get title from dc:title/rdf:li path."""
        ns = XML_NAMESPACES
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
    
    def get_metadata_components(self):
        """
        Get metadata components for video files.
        
        Returns:
            tuple: (date_str, title, location, city, country)
        """
        # Get date from stored metadata
        date_str = self.exif_data.get('CreateDate')
        if date_str:
            try:
                # Handle both date-only and datetime formats
                if ' ' in date_str:
                    date_str = date_str.split()[0]  # Get just the date part
                date_str = date_str.replace(':', '-')  # Convert : to - in date
                # Validate it's a proper date
                datetime.strptime(date_str, '%Y-%m-%d')
            except (ValueError, TypeError):
                self.logger.warning(f"Invalid date format: {date_str}")
                date_str = datetime.now().strftime('%Y-%m-%d')
        else:
            date_str = datetime.now().strftime('%Y-%m-%d')
            
        # Get title from stored metadata
        title = self.exif_data.get('Title')
        if title:
            self.logger.debug(f"Using title from stored metadata: {title}")
            
        # Get location data from stored metadata
        location_data = self.exif_data.get('Location', (None, None, None))
        if isinstance(location_data, tuple):
            location, city, country = location_data
        else:
            location = location_data
            city = None
            country = None
            
        self.logger.debug(f"Metadata components: date={date_str}, title={title}, location={location}, city={city}, country={country}")
        return date_str, title, location, city, country
            
    def rename_file(self) -> Path:
        """
        Rename the file using stored metadata.
        
        Returns:
            Path: Path to the renamed file
        """
        # Get metadata components
        date_str, title, location, city, country = self.get_metadata_components()
        
        # Build filename components
        filename_parts = [date_str]
        if title:
            filename_parts.append(title)
        if location:
            filename_parts.append(location)
        if city:
            filename_parts.append(city)
        if country:
            filename_parts.append(country)
            
        # Join filename parts with underscores
        filename = '_'.join(filename_parts)
        
        # Replace special characters
        filename = re.sub(r'[^a-zA-Z0-9_\-\. ]', '', filename)
        
        # Add LRE suffix
        filename += LRE_SUFFIX
        
        # Replace file extension
        new_path = self.file_path.with_name(f"{filename}{self.file_path.suffix}")
        
        # Rename the file
        try:
            self.file_path.rename(new_path)
            self.logger.info(f"Renamed {self.file_path} to {new_path}")
            return new_path
        except Exception as e:
            self.logger.error(f"Failed to rename file: {e}")
            return self.file_path
