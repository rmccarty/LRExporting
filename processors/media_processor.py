#!/usr/bin/env python3

from abc import ABC, abstractmethod
from pathlib import Path
import subprocess
import json
import logging
import sys
import shutil
from datetime import datetime
import re

from config import LRE_SUFFIX
from utils.exiftool import ExifTool

class MediaProcessor(ABC):
    """Base class for processing media files (JPEG, Video) with exiftool."""
    
    def __init__(self, file_path: str, exiftool: ExifTool = None, sequence: str = None):
        """
        Initialize the media processor.
        
        Args:
            file_path (str): Path to input media file
            exiftool (ExifTool, optional): ExifTool instance to use
            sequence (str, optional): Optional sequence number for filename
        """
        self.file_path = Path(file_path)
        self.logger = logging.getLogger(__name__)
        self.exif_data = {}  # Initialize exif_data
        self.sequence = sequence  # Store sequence for filename generation
        self.exiftool = exiftool or ExifTool()
            
    def read_exif(self):
        """
        Read EXIF data from the media file using exiftool.
        
        Returns:
            dict: Dictionary containing the EXIF data
        """
        self.logger.debug(f"Reading metadata from file: {self.file_path}")
        self.exif_data = self.exiftool.read_all_metadata(self.file_path)
        return self.exif_data
        
    def _get_exif_field_with_group(self, field: str) -> str:
        """Get EXIF field value checking different group prefixes."""
        for group in ['XMP:', 'IPTC:', '']:
            value = self.exif_data.get(f'{group}{field}', '')
            if value:
                return value
        return ''

    def get_exif_title(self) -> str:
        """
        Extract title from EXIF data or generate if not found.
        
        Returns:
            str: EXIF title if found, generated title if not
        """
        title = self._get_exif_field_with_group('Title')
        if not title:
            title = self.generate_title()
        return title
        
    def get_location_data(self):
        """Get location data from EXIF metadata."""
        location = self._get_exif_field_with_group('Location')
        city = self._get_exif_field_with_group('City')
        state = self._get_exif_field_with_group('State') or self._get_exif_field_with_group('Province-State')
        country = self._get_exif_field_with_group('Country')
        self.logger.debug(f"Extracted location data: location={location}, city={city}, state={state}, country={country}")
        return location, city, state, country
        
    def _join_location_parts(self, parts: list) -> str:
        """Join non-empty location parts with spaces."""
        return ' '.join(part for part in parts if part)

    def generate_title(self) -> str:
        """
        Generate a title from location information if no title exists.
        
        Returns:
            str: Generated title from location or empty string
        """
        location, city, state, country = self.get_location_data()
        return self._join_location_parts([location, city, state, country])
        
    def get_image_rating(self) -> int:
        """
        Get image rating from EXIF data.
        
        Returns:
            int: Rating value (0-5), defaults to 0 if not found
        """
        rating = self.exif_data.get('XMP:Rating', 0)
        try:
            return int(rating)
        except (ValueError, TypeError):
            return 0
            
    def _is_json_like(self, text: str) -> bool:
        """Check if text looks like JSON."""
        return text.startswith('{') or text.startswith('[')

    def _truncate_if_needed(self, text: str, max_length: int = 100) -> str:
        """Truncate text if it exceeds max_length."""
        return text[:max_length] if len(text) > max_length else text

    def clean_component(self, component: str) -> str:
        """Clean a filename component."""
        if not component or self._is_json_like(component):
            return ''
            
        # Replace invalid characters with underscores
        cleaned = re.sub(r'[^\w\s-]', '_', component)
        # Replace whitespace with underscores
        cleaned = re.sub(r'\s+', '_', cleaned)
        # Remove consecutive underscores
        cleaned = re.sub(r'_+', '_', cleaned)
        # Strip leading/trailing underscores
        cleaned = cleaned.strip('_')
        
        return self._truncate_if_needed(cleaned)

    def _is_text_in_reference(self, text: str, reference: str) -> bool:
        """Check if text appears in reference string."""
        return text.lower() in (reference or '').lower()

    def _is_component_unique(self, component: str, existing_text: str, reference: str = '') -> bool:
        """Check if a component is unique and not already included."""
        if not component:
            return False
        return (component.lower() not in existing_text.lower() and 
                not self._is_text_in_reference(component, reference))

    def _get_base_keywords(self) -> list:
        """Get base keywords including existing."""
        # Get keywords from both IPTC:Keywords and XMP:Subject
        keywords = []
        iptc_keywords = self.exif_data.get('IPTC:Keywords', [])
        xmp_subject = self.exif_data.get('XMP:Subject', [])
        
        # Handle string or list for IPTC:Keywords
        if isinstance(iptc_keywords, str):
            keywords.extend(iptc_keywords.split(','))
        elif isinstance(iptc_keywords, list):
            keywords.extend(iptc_keywords)
            
        # Handle string or list for XMP:Subject
        if isinstance(xmp_subject, str):
            keywords.extend(xmp_subject.split(','))
        elif isinstance(xmp_subject, list):
            keywords.extend(xmp_subject)
            
        # Remove duplicates while preserving order
        seen = set()
        return [k for k in keywords if not (k in seen or seen.add(k))]

    def _clean_location_component(self, component: str) -> str:
        """Clean a single location component."""
        return self.clean_component(component)

    def _build_base_components(self) -> tuple:
        """Get and clean base filename components."""
        date_str, title, _, _, _, _ = self.get_metadata_components()  # Updated for 6-tuple with state
        if not date_str and not title:
            self.logger.info("No valid metadata components found for filename")
            return None, None
        return date_str, title

    def _build_location_components(self, existing_text: str) -> list:
        """Get and clean location components, skipping if in existing text."""
        _, _, location, city, state, country = self.get_metadata_components()  # Updated for 6-tuple with state
        components = []
        
        # Clean all components first
        location = self._clean_location_component(location)
        city = self._clean_location_component(city)
        state = self._clean_location_component(state)  # Clean state component
        country = self._clean_location_component(country)
        
        # Add unique components in order
        if self._is_component_unique(location, existing_text):
            components.append(location)
        if self._is_component_unique(city, existing_text, location):
            components.append(city)
        if self._is_component_unique(state, existing_text, location):
            components.append(state)
        if self._is_component_unique(country, existing_text, location):
            components.append(country)
            
        return components

    def _build_filename_with_sequence(self, parts: list) -> str:
        """Build filename with sequence number if provided."""
        base = '_'.join(filter(None, parts))  # Filter out empty parts
        if self.sequence:
            base = f"{base}_{self.sequence}"
        return base + '__LRE'

    def generate_filename(self) -> str:
        """Generate new filename based on metadata."""
        # Get base components
        date_str, title = self._build_base_components()
        if date_str is None and title is None:
            # If no valid metadata, just add LRE suffix to original name
            return f"{self.file_path.stem}__LRE{self.file_path.suffix}"
            
        # Start with date if available
        parts = []
        if date_str:
            parts.append(date_str)
            
        # Add title if available
        if title:
            parts.append(self.clean_component(title))
            
        # Add location components
        existing_text = '_'.join(parts)
        parts.extend(self._build_location_components(existing_text))
            
        # Build filename with sequence and LRE suffix
        return self._build_filename_with_sequence(parts) + self.file_path.suffix.lower()

    def rename_file(self):
        """Rename file with LRE suffix."""
        try:
            new_name = self.generate_filename()
            if not new_name:
                return self.file_path
                
            new_path = self.file_path.parent / new_name
            self.file_path.rename(new_path)
            self.logger.info(f"Renamed file to: {new_name}")
            return new_path
        except Exception as e:
            self.logger.error(f"Failed to rename file: {e}")
            return self.file_path

    @abstractmethod
    def get_metadata_components(self):
        """
        Get metadata components for filename. Each subclass should implement this.
        Returns:
            tuple: (date_str, title, location, city, country)
        """
        pass
