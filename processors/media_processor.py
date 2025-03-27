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
    
    def __init__(self, file_path: str, sequence: str = None):
        """
        Initialize the media processor.
        
        Args:
            file_path (str): Path to input media file
            sequence (str): Optional sequence number for filename
        """
        self.file_path = Path(file_path)
        self.logger = logging.getLogger(__name__)
        self.exif_data = {}  # Initialize exif_data
        self.sequence = sequence  # Store sequence for filename generation
        self.exiftool = ExifTool()
            
    def read_exif(self):
        """
        Read EXIF data from the media file using exiftool.
        
        Returns:
            dict: Dictionary containing the EXIF data
        """
        self.logger.debug(f"Reading metadata from file: {self.file_path}")
        self.exif_data = self.exiftool.read_all_metadata(self.file_path)
        return self.exif_data
        
    def get_exif_title(self) -> str:
        """
        Extract title from EXIF data or generate if not found.
        
        Returns:
            str: EXIF title if found, generated title if not
        """
        # Try different title fields with group prefixes
        title = ''
        for key in self.exif_data:
            if key.endswith(':Title'):
                title = self.exif_data[key]
                if title:
                    break
        
        if not title:
            title = self.generate_title()
        return title
        
    def get_location_data(self) -> tuple:
        """
        Extract location information from EXIF data.
        
        Returns:
            tuple: (location, city, country)
        """
        location = ''
        city = ''
        country = ''
        
        # Try different location fields with group prefixes
        for key in self.exif_data:
            if key.endswith(':Location') and not location:
                location = self.exif_data[key]
            elif key.endswith(':City') and not city:
                city = self.exif_data[key]
            elif key.endswith(':Country') and not country:
                country = self.exif_data[key]
        
        return location, city, country
        
    def generate_title(self) -> str:
        """
        Generate title using location information if available.
        
        Returns:
            str: Generated title from location data, or empty string if none available
        """
        location, city, country = self.get_location_data()
        
        components = []
        if location:
            components.append(location)
        if city:
            components.append(city)
        if country:
            components.append(country)
            
        return ' '.join(components) if components else ''
        
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
        
    def update_keywords_with_rating_and_export_tags(self) -> None:
        """
        Update image keywords to include rating information using exiftool.
        Also adds Export_Claudia keyword for claudia_ files and Lightroom export keywords.
        """
        try:
            # Get current rating and translate to keyword
            rating = self.get_image_rating()
            rating_keyword = self.translate_rating_to_keyword(rating)
            
            # Get today's date for export keyword
            today = datetime.now().strftime('%Y_%m_%d')
            export_date_keyword = f"Lightroom_Export_on_{today}"
            
            # Get existing keywords
            current_keywords = self.exif_data.get('Keywords', [])
            if isinstance(current_keywords, str):
                current_keywords = [current_keywords]
                
            # Remove existing star ratings and add new one
            keywords = [k for k in current_keywords if not k.endswith('-star')]
            keywords.append(rating_keyword)
            
            # Add Export_Claudia keyword for claudia_ files if not present
            if (self.file_path.stem.lower().startswith('claudia_') and 
                'Export_Claudia' not in keywords):
                keywords.append('Export_Claudia')
            
            # Add Lightroom export keywords
            keywords.append('Lightroom_Export')
            keywords.append(export_date_keyword)
            
            # Update keywords using exiftool wrapper
            if not self.exiftool.update_keywords(self.file_path, keywords):
                raise RuntimeError("Failed to update keywords")
                
            self.logger.info(f"Updated keywords with rating: {rating_keyword}")
            if 'Export_Claudia' in keywords:
                self.logger.info("Added Export_Claudia keyword")
            self.logger.info(f"Added export keywords: Lightroom_Export, {export_date_keyword}")
            
        except Exception as e:
            self.logger.error(f"Error updating keywords: {e}")
            raise
            
    def clean_component(self, text):
        """Clean component for filename use"""
        if not text:
            return ""
        # Skip if text looks like JSON
        if text.startswith('{') or text.startswith('['):
            return ""
            
        # Replace problematic characters with underscores
        text = re.sub(r'[\\/:*?"<>|]', '_', text)
        
        # Replace spaces with underscores
        text = text.replace(' ', '_')
        
        # Remove or replace any other problematic characters
        text = ''.join(c for c in text if c.isalnum() or c in '_-()[]')
        
        # Replace multiple underscores with single underscore
        while '__' in text:
            text = text.replace('__', '_')
            
        # Remove leading/trailing underscores
        text = text.strip('_')
        
        # Limit component length
        return text[:50]  # Limit each component to 50 chars

    @abstractmethod
    def get_metadata_components(self):
        """
        Get metadata components for filename. Each subclass should implement this.
        Returns:
            tuple: (date_str, title, location, city, country)
        """
        pass

    def generate_filename(self):
        """Generate new filename based on metadata."""
        # Get metadata components
        date_str, title, location, city, country = self.get_metadata_components()
        
        # Clean components
        title = self.clean_component(title)
        location = self.clean_component(location)
        city = self.clean_component(city)
        country = self.clean_component(country)
        
        # Build filename parts
        parts = []
        
        # Date is required
        if not date_str:
            self.logger.error("No date found for file")
            return None
        parts.append(date_str)
        
        # Add title if available
        if title:
            parts.append(title)
            
        # Only add location components that aren't already part of the title
        if location and location.lower() not in title.lower():
            parts.append(location)
        if city and city.lower() not in title.lower() and city.lower() not in (location or '').lower():
            parts.append(city)
        if country and country.lower() not in title.lower() and country.lower() not in (location or '').lower():
            parts.append(country)
                
        # Add sequence if provided
        if self.sequence:
            parts.append(self.sequence)
                
        # Join parts with underscores and add __LRE suffix
        base = '_'.join(parts)
        base = base + '__LRE'
        
        # Add original extension
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
