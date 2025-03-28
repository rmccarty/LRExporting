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
        country = self._get_exif_field_with_group('Country')
        return location, city, country
        
    def _join_location_parts(self, parts: list) -> str:
        """Join non-empty location parts with spaces."""
        return ' '.join(part for part in parts if part)

    def generate_title(self) -> str:
        """
        Generate a title from location information if no title exists.
        
        Returns:
            str: Generated title from location or empty string
        """
        location, city, country = self.get_location_data()
        return self._join_location_parts([location, city, country])
        
    def get_image_rating(self) -> int:
        """
        Get image rating from EXIF data.
        
        Returns:
            int: Rating value (0-5), defaults to 0 if not found
        """
        rating = self.exif_data.get('Rating', 0)
        try:
            return int(rating)
        except (ValueError, TypeError):
            return 0
            
    def translate_rating_to_keyword(self, rating: int) -> str:
        """
        Translate numeric rating to keyword format.
        
        Args:
            rating (int): Numeric rating value
            
        Returns:
            str: Rating keyword (e.g., "0-star", "1-star", etc.)
        """
        if rating <= 1:
            return "0-star"
        stars = rating - 1
        return f"{stars}-star"
        
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
        """Get base keywords including existing and rating."""
        keywords = self.exif_data.get('Keywords', [])
        if isinstance(keywords, str):
            keywords = [keywords]
        rating_keyword = self.translate_rating_to_keyword(self.get_image_rating())
        return list(set(keywords + [rating_keyword]))

    def _get_export_keywords(self) -> list:
        """Get export-related keywords."""
        keywords = ['Lightroom_Export']
        
        # Add date-specific export tag
        today = datetime.now().strftime('%Y_%m_%d')
        keywords.append(f'Lightroom_Export_on_{today}')
        
        # Add Claudia tag if needed
        if 'claudia_' in self.file_path.name.lower():
            keywords.append('Export_Claudia')
            
        return keywords

    def update_keywords_with_rating_and_export_tags(self):
        """Update image keywords with rating and export tags."""
        # Get all keywords
        keywords = self._get_base_keywords()
        keywords.extend(self._get_export_keywords())
        
        # Update keywords in file
        if not self.exiftool.update_keywords(self.file_path, keywords):
            self.logger.error("Error updating keywords: Failed to update keywords")
            raise RuntimeError("Failed to update keywords")
            
    def _clean_location_component(self, component: str) -> str:
        """Clean a single location component."""
        return self.clean_component(component)

    def _build_base_components(self) -> tuple:
        """Get and clean base filename components."""
        date_str, title, _, _, _ = self.get_metadata_components()
        if not date_str:
            self.logger.error("No date found for file")
            return None, None
        title = self.clean_component(title)
        return date_str, title

    def _build_location_components(self, existing_text: str) -> list:
        """Get and clean location components, skipping if in existing text."""
        _, _, location, city, country = self.get_metadata_components()
        components = []
        
        # Clean all components first
        location = self._clean_location_component(location)
        city = self._clean_location_component(city)
        country = self._clean_location_component(country)
        
        # Add unique components in order
        if self._is_component_unique(location, existing_text):
            components.append(location)
        if self._is_component_unique(city, existing_text, location):
            components.append(city)
        if self._is_component_unique(country, existing_text, location):
            components.append(country)
            
        return components

    def _build_filename_with_sequence(self, parts: list) -> str:
        """Build filename with sequence number if provided."""
        if self.sequence:
            parts.append(self.sequence)
        return '_'.join(parts) + '__LRE'

    def generate_filename(self):
        """Generate new filename based on metadata."""
        # Get base components
        date_str, title = self._build_base_components()
        if not date_str:
            return None
            
        # Build parts list
        parts = [date_str]
        if title:
            parts.append(title)
            
        # Add location components
        existing_text = '_'.join(parts)
        location_parts = self._build_location_components(existing_text)
        parts.extend(location_parts)
                
        # Build final filename
        base = self._build_filename_with_sequence(parts)
        return base + self.file_path.suffix.lower()

    def rename_file(self):
        """Rename file with LRE suffix."""
        new_name = self.generate_filename()
        if not new_name:
            return None
            
        new_path = self.file_path.parent / new_name
        try:
            self.file_path.rename(new_path)
            self.logger.info(f"Renamed file to: {new_name}")
            return new_path
        except Exception as e:
            self.logger.error(f"Error renaming file: {e}")
            return None

    @abstractmethod
    def get_metadata_components(self):
        """
        Get metadata components for filename. Each subclass should implement this.
        Returns:
            tuple: (date_str, title, location, city, country)
        """
        pass
