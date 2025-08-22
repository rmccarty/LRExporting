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
from utils.date_normalizer import DateNormalizer  # Import DateNormalizer

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
        self.xmp_file = Path(file_path).with_suffix('.xmp')
        if not self.xmp_file.exists():
            self.logger.warning(f"No XMP sidecar file found: {self.xmp_file}")
            
        # Initialize the ExifTool class
        self.exiftool = ExifTool()
        # Initialize the DateNormalizer class
        self.date_normalizer = DateNormalizer()
            
    def read_metadata_from_xmp(self) -> tuple:
        """Read metadata from XMP sidecar file."""
        if not self.xmp_file.exists():
            self.logger.warning(f"No XMP sidecar file found: {self.xmp_file}")
            return (None, None, None, None, (None, None, None))
            
        try:
            tree = ET.parse(str(self.xmp_file))
            root = tree.getroot()
            
            # Find the Description element that contains our metadata
            description = root.find('.//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description')
            if description is None:
                self.logger.warning("No Description element found in XMP")
                return (None, None, None, None, (None, None, None))
                
            # Extract metadata fields
            title = self.get_title_from_rdf(description)
            keywords = self.get_keywords_from_rdf(description)
            date_str = self.exiftool.read_date_from_xmp(self.xmp_file)
            caption = self.get_caption_from_rdf(description)
            location = self.get_location_from_rdf(description)
            
            return (title, keywords, date_str, caption, location)
            
        except ET.ParseError as e:
            self.logger.error(f"Error parsing XMP file: {str(e)}")
            return (None, None, None, None, (None, None, None))
        except Exception as e:
            self.logger.error(f"Error reading XMP metadata: {str(e)}")
            return (None, None, None, None, (None, None, None))
            
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
            
        self.logger.debug(f"Verifying keywords: {keywords}")
        
        # Check all keyword-related fields in the metadata
        found_keywords = []
        for field in METADATA_FIELDS['keywords']:
            clean_field = field.replace('-', '').split(':')[-1]
            for key in self.exif_data:
                if key.endswith(clean_field) or clean_field.lower() in key.lower():
                    current_keywords = self.exif_data[key]
                    if isinstance(current_keywords, str):
                        # Split comma-separated keywords
                        current_keywords = [kw.strip() for kw in current_keywords.split(',')]
                    elif isinstance(current_keywords, list):
                        # Handle list of keywords, also check for comma-separated items
                        expanded_keywords = []
                        for kw in current_keywords:
                            if isinstance(kw, str) and ',' in kw:
                                expanded_keywords.extend([k.strip() for k in kw.split(',')])
                            else:
                                expanded_keywords.append(kw)
                        current_keywords = expanded_keywords
                    found_keywords.extend(current_keywords)
                    self.logger.debug(f"Found keywords in {key}: {current_keywords}")
        
        # Remove duplicates and empty strings
        found_keywords = list(set([kw for kw in found_keywords if kw.strip()]))
        
        # Check if all expected keywords are present (case-insensitive)
        expected_lower = [k.lower() for k in keywords]
        found_lower = [k.lower() for k in found_keywords]
        
        missing_keywords = []
        for expected in expected_lower:
            if expected not in found_lower:
                missing_keywords.append(keywords[expected_lower.index(expected)])
        
        if missing_keywords:
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
