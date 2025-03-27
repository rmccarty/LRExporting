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
            
    def get_metadata_from_xmp(self):
        """Get metadata from XMP file."""
        metadata = self.read_metadata_from_xmp()
        title, keywords, date_str, caption, location_data = metadata
        
        # Log what metadata we found
        if not any(metadata):
            self.logger.warning("No metadata found in XMP file")
        else:
            if not title:
                self.logger.info("No title found in XMP")
            if not keywords:
                self.logger.info("No keywords found in XMP")
            if not date_str:
                self.logger.info("No date found in XMP")
            if not caption:
                self.logger.info("No caption found in XMP")
            if not any(location_data):
                self.logger.info("No location data found in XMP")
                
        return metadata

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
            
    def verify_metadata(self, expected_metadata: tuple) -> bool:
        """
        Verify that metadata was written correctly.
        
        Args:
            expected_metadata (tuple): Tuple containing expected metadata values
            
        Returns:
            bool: True if verification passes, False otherwise
        """
        try:
            # Read current metadata
            current_metadata = self.read_exif()
            
            # Check each field we care about
            title, keywords, date_str, caption, location_data = expected_metadata
            expected_fields = {
                'Title': title,
                'Subject': keywords,
                'DateTimeOriginal': date_str,
                'Description': caption,
            }
            if location_data:
                location, city, country = location_data
                expected_fields['Location'] = location
                expected_fields['City'] = city
                expected_fields['Country'] = country
            
            for field, expected in expected_fields.items():
                if not expected:
                    continue
                    
                # Look for field in current metadata, checking both with and without namespace
                found = False
                for key, value in current_metadata.items():
                    # Check if key ends with the field name (handles namespaces like QuickTime:Title or XMP:Subject)
                    if key.endswith(':' + field) or key == field:
                        # For keywords/subject, handle both list and string formats
                        if field == 'Subject' and isinstance(expected, list):
                            if isinstance(value, list) and set(value) == set(expected):
                                found = True
                                break
                            elif value == ','.join(expected):
                                found = True
                                break
                        # For other fields, direct comparison
                        elif value == expected:
                            found = True
                            break
                        
                if not found:
                    self.logger.error(f"Metadata verification failed for {field}")
                    self.logger.error(f"Expected: {expected}")
                    self.logger.error(f"Not found in: {current_metadata}")
                    return False
                    
            return True
            
        except Exception as e:
            self.logger.error(f"Error verifying metadata: {e}")
            return False
            
    def normalize_date(self, date_str):
        """Normalize date format to YYYY:MM:DD HH:MM:SS format that exiftool expects."""
        if not date_str:
            return None
            
        try:
            # Split into date and time parts
            parts = date_str.split(' ')
            if len(parts) < 2:
                return None
                
            date_part = parts[0].replace('-', ':')  # Convert YYYY-MM-DD to YYYY:MM:DD
            time_part = parts[1]
            
            # Handle timezone if present
            if len(parts) > 2:
                tz_part = parts[2]
                if tz_part.startswith(('-', '+')):
                    # Already in correct format (-0500)
                    return f"{date_part} {time_part}{tz_part}"
                else:
                    # Try to convert to offset format
                    try:
                        hours = int(tz_part)
                        offset = f"{'-' if hours < 0 else '+'}{abs(hours):02d}00"
                        return f"{date_part} {time_part}{offset}"
                    except ValueError:
                        pass
            
            # No timezone, just return date and time
            return f"{date_part} {time_part}"
            
        except Exception as e:
            self.logger.error(f"Error normalizing date {date_str}: {e}")
            return None

    def get_title_from_rdf(self, rdf):
        """Extract title from RDF data."""
        try:
            ns = XML_NAMESPACES
            self.logger.debug("Searching for title in RDF...")
            
            # First try the simple dc:title/rdf:Alt/rdf:li path
            title_elem = rdf.find(f'.//{{{ns["dc"]}}}title/{{{ns["rdf"]}}}Alt/{{{ns["rdf"]}}}li')
            if title_elem is not None and title_elem.text:
                self.logger.debug(f"Found title in dc:title: {title_elem.text}")
                return title_elem.text
                
            # If that fails, try finding any rdf:li element under dc:title
            for elem in rdf.findall(f'.//{{{ns["dc"]}}}title/{{{ns["rdf"]}}}li'):
                if elem.text:
                    self.logger.debug(f"Found title in dc:title/li: {elem.text}")
                    return elem.text
                    
            # Try as attribute in Description
            for desc in rdf.iter('{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description'):
                # Try Iptc4xmpCore:Location
                location = desc.get('{http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/}Location')
                if location:
                    self.logger.debug(f"Using Location as title: {location}")
                    return location
                    
            self.logger.debug("No title found in any expected location")
            
        except Exception as e:
            self.logger.error(f"Error getting title from RDF: {e}")
            self.logger.debug("Full error:", exc_info=True)
            try:
                import xml.etree.ElementTree as ET
                self.logger.debug("XML content:")
                self.logger.debug(ET.tostring(rdf, encoding='unicode'))
            except Exception as e2:
                self.logger.debug(f"Could not print XML: {e2}")
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
    
    def get_keywords_from_rdf(self, rdf):
        """Extract keywords from RDF data."""
        try:
            ns = XML_NAMESPACES
            keywords = []
            
            # Try hierarchical subjects first
            subject_path = f'.//{{{ns["lr"]}}}hierarchicalSubject/{{{ns["rdf"]}}}Bag/{{{ns["rdf"]}}}li'
            for elem in rdf.findall(subject_path):
                if elem.text:
                    keywords.append(elem.text)
                    
            # If no hierarchical subjects, try flat subject list
            if not keywords:
                subject_path = f'.//{{{ns["dc"]}}}subject/{{{ns["rdf"]}}}Bag/{{{ns["rdf"]}}}li'
                for elem in rdf.findall(subject_path):
                    if elem.text:
                        keywords.append(elem.text)
            
            if keywords:
                self.logger.debug(f"Found keywords: {keywords}")
            return keywords
            
        except Exception as e:
            self.logger.error(f"Error getting keywords from RDF: {e}")
            return []
    
    def get_location_from_rdf(self, rdf):
        """Extract location data from RDF."""
        try:
            # Look for location in photoshop namespace
            for desc in rdf.iter('{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description'):
                city = desc.get('{http://ns.adobe.com/photoshop/1.0/}City')
                country = desc.get('{http://ns.adobe.com/photoshop/1.0/}Country')
                state = desc.get('{http://ns.adobe.com/photoshop/1.0/}State')
                
                # Construct location string
                location_parts = []
                if city:
                    location_parts.append(city)
                if state:
                    location_parts.append(state)
                if country:
                    location_parts.append(country)
                    
                location = ", ".join(location_parts) if location_parts else None
                
                # Return first instance of location data found
                if city or country:
                    self.logger.debug(f"Found location data: {location} ({city}, {country})")
                    return location, city, country
                    
        except Exception as e:
            self.logger.error(f"Error extracting location from RDF: {e}")
            
        return None, None, None

    def normalize_timezone(self, date_str):
        """Normalize timezone format for comparison."""
        if not date_str:
            return date_str
        # Convert -05:00 to -0500 or +05:00 to +0500
        if date_str.endswith(':00'):
            return date_str[:-3].replace(':', '')
        return date_str

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
            # Strip any timezone info for comparison
            date1 = date1.split('-')[0] if date1 and '-' in date1 else date1
            date2 = date2.split('-')[0] if date2 and '-' in date2 else date2
            
            # Clean up any extra spaces
            date1 = date1.strip() if date1 else None
            date2 = date2.strip() if date2 else None
            
            if not date1 or not date2:
                return False
                
            # Convert to common format YYYY:MM:DD HH:MM:SS
            def normalize_date(date_str):
                # Remove any timezone offset
                date_str = date_str.split('-')[0].strip()
                # Remove any subsecond precision
                date_str = date_str.split('.')[0].strip()
                return date_str
                
            return normalize_date(date1) == normalize_date(date2)
            
        except Exception as e:
            self.logger.error(f"Error comparing dates {date1} and {date2}: {e}")
            return False

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
            
    def process_video(self) -> Path:
        """
        Main method to process a video file - reads XMP metadata and writes to video.
        
        Returns:
            Path: Path to the processed file
        """
        # 1. Skip if already processed
        if self.file_path.stem.endswith(LRE_SUFFIX):
            self.logger.info(f"Skipping already processed file: {self.file_path}")
            return self.file_path
            
        # 2. Read metadata from XMP and store it
        metadata = self.get_metadata_from_xmp()
        title, keywords, date_str, caption, location_data = metadata
            
        # 3. Write metadata to video if any exists
        if any(metadata):
            if not self.write_metadata_to_video(metadata):
                self.logger.error("Failed to write metadata to video")
                return self.file_path
                
            # 4. Verify metadata was written correctly
            if not self.verify_metadata(metadata):
                self.logger.error("Metadata verification failed")
                return self.file_path
                
            # Store metadata for filename generation
            self.exif_data = {
                'Title': title,
                'Keywords': keywords,
                'CreateDate': date_str,
                'Caption-Abstract': caption,
                'Location': location_data
            }
                
        # 5. Delete XMP file
        xmp_path = self.file_path.with_suffix('.xmp')
        try:
            if xmp_path.exists():
                os.remove(xmp_path)
                self.logger.info(f"Deleted XMP file: {xmp_path}")
        except OSError as e:
            self.logger.error(f"Error deleting XMP file: {e}")
            
        # 6. Rename the file using stored metadata
        new_path = self.rename_file()
        return new_path
