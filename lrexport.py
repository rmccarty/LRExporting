#!/usr/bin/env python3

from pathlib import Path
import subprocess
import json
import logging
import sys
from datetime import datetime
import shutil
import time
import xml.etree.ElementTree as ET
from mutagen.mp4 import MP4
import re
import glob
import os

from config import (
    WATCH_DIRS, 
    BOTH_INCOMING, 
    LOG_LEVEL, 
    SLEEP_TIME,
    XML_NAMESPACES,
    EXIFTOOL_BASE_ARGS,
    METADATA_FIELDS,
    VERIFY_FIELDS,
    VIDEO_PATTERN,
    MCCARTYS_PREFIX,
    MCCARTYS_REPLACEMENT,
    LRE_SUFFIX
)

class MediaProcessor:
    """Base class for processing media files (JPEG, Video) with exiftool."""
    
    def __init__(self, file_path: str):
        """
        Initialize the media processor.
        
        Args:
            file_path (str): Path to input media file
        """
        self.file_path = Path(file_path)
        self.logger = logging.getLogger(__name__)
        
        # Verify exiftool is available
        if not shutil.which('exiftool'):
            self.logger.error("exiftool is not installed or not in PATH")
            sys.exit(1)
    
    def read_exif(self) -> dict:
        """
        Read EXIF data from the media file using exiftool.
        
        Returns:
            dict: Dictionary containing the EXIF data
        """
        try:
            cmd = ['exiftool', '-j', '-n', str(self.file_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            self.exif_data = json.loads(result.stdout)[0]  # exiftool returns a list
            return self.exif_data
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error running exiftool: {e.stderr}")
            raise
        except json.JSONDecodeError as e:
            self.logger.error(f"Error parsing exiftool output: {str(e)}")
            raise
            
    def get_exif_title(self) -> str:
        """
        Extract title from EXIF data or generate if not found.
        
        Returns:
            str: EXIF title if found, generated title if not
        """
        title = self.exif_data.get('Title', '')
        if not title:
            title = self.generate_title()
        return title
        
    def get_location_data(self) -> tuple:
        """
        Extract location information from EXIF data.
        
        Returns:
            tuple: (location, city, country)
        """
        location = self.exif_data.get('Location', '')
        city = self.exif_data.get('City', '')
        country = self.exif_data.get('Country', '')
        
        return location, city, country
        
    def generate_title(self) -> str:
        """
        Generate title using caption and location information if available.
        
        Returns:
            str: Generated title from caption and location data, or empty string if none available
        """
        caption = self.exif_data.get('Caption-Abstract', '')
        location, city, country = self.get_location_data()
        
        components = []
        if caption:
            components.append(caption)
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
            
            # Create exiftool command to update keywords - use a single -keywords argument
            cmd = ['exiftool', '-overwrite_original', f'-keywords={",".join(keywords)}', str(self.file_path)]
            
            subprocess.run(cmd, check=True, capture_output=True)
            self.logger.info(f"Updated keywords with rating: {rating_keyword}")
            if 'Export_Claudia' in keywords:
                self.logger.info("Added Export_Claudia keyword")
            self.logger.info(f"Added export keywords: Lightroom_Export, {export_date_keyword}")
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error updating keywords: {e.stderr}")
            raise
            
    def generate_filename(self) -> str:
        """
        Generate new filename based on EXIF data and add user/LRE tags.
        
        Returns:
            str: New filename with user and LRE tags
        """
        # Get date from EXIF or use current date
        date_str = self.exif_data.get('CreateDate', '')
        if date_str:
            try:
                date = datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
            except ValueError:
                date = datetime.now()
        else:
            date = datetime.now()
            
        date_str = date.strftime('%Y-%m-%d')
        
        # Get and transform all components
        components = [date_str]
        
        # Skip raw JSON or complex data in title, just use location info
        _, city, country = self.get_location_data()
        
        def clean_component(text):
            """Clean component for filename use"""
            if not text:
                return ""
            # Skip if text looks like JSON
            if text.startswith('{') or text.startswith('['):
                return ""
            # First replace slashes and backslashes with hyphens
            text = text.replace('/', '-').replace('\\', '-')
            # Replace spaces and multiple underscores with single underscore
            text = text.replace(' ', '_')
            while '__' in text:
                text = text.replace('__', '_')
            # Limit component length
            return text[:50]  # Limit each component to 50 chars
        
        # Clean and add each component if it's valid
        if city:
            cleaned_city = clean_component(city)
            if cleaned_city:
                components.append(cleaned_city)
        if country:
            cleaned_country = clean_component(country)
            if cleaned_country:
                components.append(cleaned_country)
            
        # Join with single underscore and ensure no double underscores
        base_name = '_'.join(components)
        while '__' in base_name:
            base_name = base_name.replace('__', '_')
            
        filename = f"{base_name}__LRE.jpg"
        return filename
        
    def rename_file(self) -> Path:
        """
        Rename the file based on EXIF data.
        
        Returns:
            Path: Path to the renamed file
        """
        try:
            new_filename = self.generate_filename()
            new_path = self.file_path.parent / new_filename
            
            # Handle duplicates
            counter = 1
            while new_path.exists():
                date_part, rest = new_filename.split('_', 1)
                new_path = self.file_path.parent / f"{date_part}-{counter:03d}_{rest}"
                counter += 1
                
            # Use exiftool to copy the file with metadata
            cmd = [
                'exiftool',
                '-overwrite_original',
                '-all:all',  # Preserve all metadata
                f'-filename={new_path}',
                str(self.file_path)
            ]
            
            subprocess.run(cmd, check=True, capture_output=True)
            self.logger.info(f"File renamed to: {new_path}")
            return new_path
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error renaming file: {e.stderr}")
            raise
            
    def process_image(self) -> Path:
        """
        Main method to process an image - reads EXIF, updates keywords and title, and renames file.
        
        Returns:
            Path: Path to the processed file
        """
        self.read_exif()
        
        # Set the title only if one doesn't exist
        title = self.get_exif_title()
        if title and not self.exif_data.get('Title'):
            try:
                cmd = ['exiftool', '-overwrite_original',
                      '-Title=' + title,
                      '-XPTitle=' + title,
                      '-Caption-Abstract=' + title,
                      '-ImageDescription=' + title,
                      '-Description=' + title,
                      '-XMP:Title=' + title,
                      '-IPTC:ObjectName=' + title,
                      '-IPTC:Headline=' + title,
                      str(self.file_path)]
                result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                self.logger.info(f"Title set to: {title}")
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Error setting title: {e.stderr}")
                raise
            
        self.update_keywords_with_rating_and_export_tags()
        return self.rename_file()

class BaseWatcher:
    """Base class for watching directories for media files."""
    
    def __init__(self, directories=None):
        """
        Initialize the watcher.
        
        Args:
            directories: List of directories to watch. If None, uses WATCH_DIRS
        """
        self.directories = [Path(d) for d in (directories or WATCH_DIRS)]
        self.running = False
        self.sleep_time = SLEEP_TIME
        self.logger = logging.getLogger(__name__)
    
    def process_file(self, file_path):
        """Process a single media file. Must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement process_file")
    
    def watch(self):
        """Start watching directories for new files."""
        self.running = True
        try:
            while self.running:
                for directory in self.directories:
                    self.logger.info(f"Checking {directory} for new files...")
                    self.check_directory(directory)
                time.sleep(self.sleep_time)
                
        except KeyboardInterrupt:
            self.logger.info("Stopping watch")
            self.running = False
    
    def check_directory(self, directory):
        """Check a directory for new files. Must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement check_directory")
    
    def stop(self):
        """Stop watching directories."""
        self.running = False

class JPEGExifProcessor(MediaProcessor):
    """
    A class to process JPEG images and their EXIF data using exiftool.
    """
    
    def __init__(self, input_path: str, output_path: str = None):
        """
        Initialize the JPEG processor with input and output paths.
        Validates file type and username requirements.
        
        Args:
            input_path (str): Path to input JPEG file
            output_path (str): Optional path for output file. If None, will use input directory
            
        Raises:
            SystemExit: If file is not JPEG
        """
        super().__init__(input_path)
        self.input_path = Path(input_path)
        self.output_path = (Path(output_path) if output_path 
                          else self.input_path.parent)
        
        # Validate file is JPEG
        if self.input_path.suffix.lower() not in ['.jpg', '.jpeg']:
            self.logger.error(f"File must be JPEG format. Found: {self.input_path.suffix}")
            sys.exit(1)
            
        # Remove the username validation logic
        try:
            original_name = self.input_path.stem
            # Removed the check for underscore in the filename
            # if '_' not in original_name:
            #     self.logger.error(f"Original filename must contain username followed by underscore. Found: {original_name}")
            #     sys.exit(1)
            
            # The rest of the logic can remain unchanged
            # username = original_name.split('_')[0]
            # if not username:
            #     self.logger.error("Username cannot be empty")
            #     sys.exit(1)
                
        except Exception as e:
            self.logger.error(f"Error validating filename: {str(e)}")
            sys.exit(1)
            
class VideoProcessor(MediaProcessor):
    """A class to process video files and their metadata using exiftool."""
    
    def __init__(self, file_path: str):
        """Initialize with video file path."""
        super().__init__(file_path)
        
        # Validate file extension
        ext = Path(file_path).suffix.lower()
        if not any(ext.endswith(pattern) for pattern in ['.mp4', '.mov', '.m4v']):
            self.logger.error(f"File must be a video format. Found: {ext}")
            sys.exit(1)
    
    def normalize_date(self, date_str):
        """
        Normalize date format to YYYY:MM:DD HH:MM:SS format that exiftool expects.
        Handles timezone offset correctly.
        """
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
            title_path = f'.//{{{ns["dc"]}}}title/{{{ns["rdf"]}}}Alt/{{{ns["rdf"]}}}li'
            title_elem = rdf.find(title_path)
            if title_elem is not None:
                return title_elem.text
        except Exception as e:
            self.logger.error(f"Error getting title from RDF: {e}")
        return None
    
    def get_caption_from_rdf(self, rdf):
        """Extract caption from RDF data."""
        try:
            ns = XML_NAMESPACES
            caption_path = f'.//{{{ns["dc"]}}}description/{{{ns["rdf"]}}}Alt/{{{ns["rdf"]}}}li'
            caption_elem = rdf.find(caption_path)
            if caption_elem is not None:
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
                self.logger.info(f"Found keywords: {keywords}")
            return keywords
            
        except Exception as e:
            self.logger.error(f"Error getting keywords from RDF: {e}")
            return []
    
    def get_location_from_rdf(self, rdf):
        """Extract location data from RDF."""
        try:
            ns = XML_NAMESPACES
            location = {}
            
            # Get GPS coordinates
            for tag in ['GPSLatitude', 'GPSLongitude']:
                path = f'.//{{{ns["exif"]}}}{tag}'
                elem = rdf.find(path)
                if elem is not None and elem.text:
                    location[tag] = self.parse_gps_coordinate(elem.text)
            
            return location if location else None
            
        except Exception as e:
            self.logger.error(f"Error getting location from RDF: {e}")
            return None
    
    def parse_gps_coordinate(self, coord_str):
        """Parse GPS coordinate from exiftool format to decimal degrees."""
        try:
            if 'deg' in coord_str:
                parts = coord_str.split()
                deg = float(parts[0].rstrip('deg'))
                min_sec = 0
                
                if len(parts) > 1:
                    min_sec = float(parts[1].rstrip("'")) / 60
                if len(parts) > 2:
                    min_sec += float(parts[2].rstrip('"')) / 3600
                    
                return deg + min_sec
            return float(coord_str)
            
        except Exception as e:
            self.logger.error(f"Error parsing GPS coordinate: {e}")
            return None
    
    def get_new_filename(self, title):
        """Generate new filename from title."""
        if not title:
            return None
            
        # Get directory and extension
        directory = self.file_path.parent
        base = self.file_path.stem
        ext = self.file_path.suffix
        
        # Add LRE suffix if not already present
        if not base.endswith(LRE_SUFFIX):
            new_filename = f"{base}{LRE_SUFFIX}{ext}"
            return directory / new_filename
        return self.file_path

    def get_metadata_from_xmp(self):
        """Get metadata from XMP sidecar file."""
        title = None
        keywords = []
        caption = None
        location_data = None
        date_time_original = None
        
        try:
            # Get XMP file path
            xmp_path = os.path.splitext(str(self.file_path))[0] + ".xmp"
            if not os.path.exists(xmp_path):
                xmp_path = str(self.file_path) + ".xmp"
                if not os.path.exists(xmp_path):
                    return None, None, None, None, None
            
            # Get date from exiftool first
            date_time_original = self.get_date_from_exiftool(xmp_path)
            
            # Parse XMP file
            tree = ET.parse(xmp_path)
            root = tree.getroot()
            
            # Find RDF element
            rdf = None
            for elem in root.iter():
                if 'RDF' in elem.tag:
                    rdf = elem
                    break
                    
            if rdf is not None:
                title = self.get_title_from_rdf(rdf)
                keywords = self.get_keywords_from_rdf(rdf)
                caption = self.get_caption_from_rdf(rdf)
                location_data = self.get_location_from_rdf(rdf)
            else:
                self.logger.warning("No RDF data found in XMP")
                
        except ET.ParseError as e:
            self.logger.error(f"Error parsing XMP file: {e}")
        except Exception as e:
            self.logger.error(f"Error processing XMP file: {e}")
        
        self.logger.info("=" * 50)
        self.logger.info("Final metadata values:")
        if title:
            self.logger.info(f"Title: '{title}'")
        if keywords:
            self.logger.info(f"Keywords: {keywords}")
        if caption:
            self.logger.info(f"Caption: '{caption}'")
        
        return title, keywords, date_time_original, caption, location_data
    
    def get_date_from_exiftool(self, xmp_path):
        """Get DateTimeOriginal from XMP using exiftool."""
        try:
            result = subprocess.run(
                ['exiftool', '-json', '-DateTimeOriginal', xmp_path],
                capture_output=True,
                text=True,
                check=True
            )
            
            metadata = json.loads(result.stdout)
            if metadata and isinstance(metadata, list) and len(metadata) > 0:
                date = metadata[0].get('DateTimeOriginal')
                if date:
                    self.logger.info(f"Found date: {date}")
                    return date
            return None
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error getting date from XMP: {e}")
            return None
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Error parsing exiftool output: {e}")
            return None
            
    def process_video(self):
        """
        Process a video file.
        
        CRITICAL: The order of operations must be strictly maintained:
        1. Check if file has __LRE suffix (skip if present)
        2. Read metadata from XMP
        3. Write metadata to video
        4. Verify metadata
        5. Delete XMP file
        6. Rename video file with __LRE suffix
        
        IMPORTANT: The XMP file MUST be deleted BEFORE renaming the video file with __LRE suffix.
        This order is critical because the XMP file path is based on the original video filename.
        
        Returns:
            bool: True if processing was successful, False otherwise.
        """
        try:
            # Skip if already processed
            if self.file_path.stem.endswith(LRE_SUFFIX):
                self.logger.info(f"Skipping already processed file: {self.file_path}")
                return False
            
            # Get metadata from XMP
            title, keywords, date_str, caption, location = self.get_metadata_from_xmp()
            if not any([title, keywords, date_str, caption, location]):
                self.logger.warning("No metadata found in XMP")
                return False
            
            # Normalize date format
            date_str = self.normalize_date(date_str) if date_str else None
            
            # Write metadata to video file
            try:
                cmd = EXIFTOOL_BASE_ARGS + [str(self.file_path)]
                
                if title:
                    cmd.extend(['-title=' + title])
                if keywords:
                    # Write keywords to both Keys and ItemList groups
                    keyword_str = ",".join(keywords)
                    cmd.extend([
                        '-Keys:Keywords=' + keyword_str,
                        '-ItemList:Keywords=' + keyword_str,
                        '-ItemList:Subject=' + keyword_str
                    ])
                if date_str:
                    # Set all date fields for maximum compatibility
                    for date_field in [
                        'DateTimeOriginal',
                        'CreateDate',
                        'ModifyDate',
                        'TrackCreateDate',
                        'TrackModifyDate',
                        'MediaCreateDate',
                        'MediaModifyDate'
                    ]:
                        cmd.extend([f'-{date_field}={date_str}'])
                if caption:
                    cmd.extend(['-description=' + caption])
                if location:
                    if 'GPSLatitude' in location:
                        cmd.extend(['-GPSLatitude=' + str(location['GPSLatitude'])])
                    if 'GPSLongitude' in location:
                        cmd.extend(['-GPSLongitude=' + str(location['GPSLongitude'])])
                
                subprocess.run(cmd, check=True)
                self.logger.info("Metadata written successfully")
                
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Error writing metadata: {e}")
                return False
            
            # Verify metadata was written correctly
            if not self.verify_metadata(title, keywords, date_str, caption, location):
                self.logger.error("Metadata verification failed")
                return False
            
            # Delete XMP file
            xmp_path = os.path.splitext(str(self.file_path))[0] + ".xmp"
            if not os.path.exists(xmp_path):
                xmp_path = str(self.file_path) + ".xmp"
            
            if os.path.exists(xmp_path):
                try:
                    os.remove(xmp_path)
                    self.logger.info(f"Deleted XMP file: {xmp_path}")
                except Exception as e:
                    self.logger.error(f"Error deleting XMP file: {e}")
                    return False
            
            # Rename video file with __LRE suffix
            if title:
                new_name = self.get_new_filename(title)
                if new_name:
                    try:
                        self.file_path.rename(new_name)
                        self.logger.info(f"Renamed to: {new_name}")
                    except Exception as e:
                        self.logger.error(f"Error renaming file: {e}")
                        return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error processing video: {e}")
            return False

    def parse_date(self, date_str):
        """Parse date string into components for comparison."""
        if not date_str:
            return None
        try:
            # Remove timezone part for comparison
            base_date = date_str.rsplit('-', 1)[0] if '-' in date_str else date_str
            return base_date.strip()
        except Exception:
            return None

    def normalize_timezone(self, date_str):
        """Normalize timezone format for comparison."""
        if not date_str:
            return date_str
        # Convert -05:00 to -0500 or +05:00 to +0500
        if date_str.endswith(':00'):
            return date_str[:-3].replace(':', '')
        return date_str

    def verify_metadata(self, expected_title, expected_keywords, expected_date, expected_caption=None, expected_location=None):
        """Verify that metadata was written correctly."""
        try:
            self.logger.info("=== Starting Metadata Verification ===")
            
            # Run exiftool to get all metadata
            exiftool_args = [
                'exiftool',
                '-json',
                '-Title',
                '-Keywords',
                '-Subject',
                '-CreateDate',
                '-Description',
                '-Caption-Abstract',
                '-Location',
                '-QuickTime:Keywords',
                '-XMP:Keywords',
                str(self.file_path)
            ]
            
            result = subprocess.run(exiftool_args, capture_output=True, text=True, check=True)
            metadata = json.loads(result.stdout)[0]
            
            # Check title
            if expected_title:
                title = metadata.get('Title')
                if title == expected_title:
                    self.logger.info(f"Found title: {title}")
                else:
                    self.logger.error(f"Title mismatch. Expected: {expected_title}, Found: {title}")
                    return False
            
            # Check keywords in all possible locations
            if expected_keywords:
                found_keywords = set()
                keyword_fields = [
                    'Keywords',
                    'Subject',
                    'QuickTimeKeywords',
                    'TagsList',
                    'PersonInImage',
                    'Subject',
                    'HierarchicalSubject'
                ]
                
                for field in keyword_fields:
                    if field in metadata:
                        value = metadata[field]
                        if isinstance(value, str):
                            found_keywords.update(value.split(','))
                        elif isinstance(value, list):
                            found_keywords.update(value)
                
                # Clean and sort keywords for comparison
                found_keywords = {k.strip() for k in found_keywords if k.strip()}
                expected_set = set(expected_keywords)
                
                if found_keywords == expected_set:
                    self.logger.info(f"Found keywords: {', '.join(sorted(found_keywords))}")
                else:
                    self.logger.error(f"Keyword mismatch. Expected: {expected_keywords}, Found: {found_keywords}")
                    return False
            
            # Check date
            if expected_date:
                create_date = metadata.get('CreateDate')
                if create_date:
                    # Compare dates without timezone
                    expected_base = self.parse_date(expected_date)
                    actual_base = self.parse_date(create_date)
                    if expected_base and actual_base and expected_base == actual_base:
                        self.logger.info(f"Found matching date in CreateDate: {create_date}")
                    else:
                        self.logger.error(f"Date mismatch. Expected: {expected_date}, Found: {create_date}")
                        return False
                else:
                    self.logger.error(f"No CreateDate found in metadata")
                    return False
            
            # Check caption
            if expected_caption:
                caption = metadata.get('Description') or metadata.get('Caption-Abstract')
                if caption == expected_caption:
                    self.logger.info(f"Found caption: {caption}")
                else:
                    self.logger.error(f"Caption mismatch. Expected: {expected_caption}, Found: {caption}")
                    return False
            
            # Check location
            if expected_location:
                location = metadata.get('Location')
                if location == expected_location:
                    self.logger.info(f"Found location: {location}")
                else:
                    self.logger.error(f"Location mismatch. Expected: {expected_location}, Found: {location}")
                    return False
            
            self.logger.info("=== Metadata Verification Successful ===")
            return True
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error verifying metadata: {e}")
            return False
        except json.JSONDecodeError as e:
            self.logger.error(f"Error parsing exiftool output: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error during verification: {e}")
            return False

class VideoWatcher(BaseWatcher):
    """A class to watch directories for video files."""
    
    def process_file(self, file_path):
        """Process a single video file."""
        try:
            # Check for XMP file
            xmp_path = os.path.splitext(file_path)[0] + ".xmp"
            if not os.path.exists(xmp_path):
                xmp_path = file_path + ".xmp"
                if not os.path.exists(xmp_path):
                    return  # Skip if no XMP file
            
            # Process video
            self.logger.info(f"Found new video: {os.path.basename(file_path)}")
            processor = VideoProcessor(file_path)
            processor.process_video()
            
        except Exception as e:
            self.logger.error(f"Error processing {file_path}: {e}")
    
    def check_directory(self, directory):
        """Check a directory for new video files."""
        directory = Path(directory)
        if not directory.exists():
            return
            
        self.logger.info(f"\nChecking {directory} for new video files...")
        video_files = []
        # Handle both upper and lower case extensions
        for pattern in VIDEO_PATTERN:
            video_files.extend(directory.glob(pattern.lower()))
            video_files.extend(directory.glob(pattern.upper()))
        
        if video_files:
            self.logger.info(f"Found files: {[str(f) for f in video_files]}")
            
        for file_path in video_files:
            self.logger.info(f"Found new video: {file_path.name}")
            processor = VideoProcessor(str(file_path))
            processor.process_video()

class DirectoryWatcher(BaseWatcher):
    """
    A class to watch directories for new JPEG files and process them.
    """
    
    def __init__(self, watch_dirs, both_incoming_dir=None):
        """
        Initialize the directory watcher.
        
        Args:
            watch_dirs: List of Path objects for directories to watch
            both_incoming_dir: Optional Path object for a shared incoming directory
        """
        super().__init__(watch_dirs)
        self.both_incoming = Path(both_incoming_dir) if both_incoming_dir else None
    
    def process_both_incoming(self):
        """Check Both_Incoming directory and copy files to individual incoming directories."""
        if not self.both_incoming:
            return False
            
        found_files = False
        try:
            # Iterate through all files in the Both_Incoming directory
            for file in self.both_incoming.glob("*"):
                # Check if the file is open
                try:
                    with open(file, 'r+'):
                        pass  # File is not open, proceed to copy
                except IOError:
                    self.logger.warning(f"File {file.name} is currently open. Skipping copy.")
                    continue  # Skip to the next file
                
                found_files = True
                # Copy the file to all incoming directories
                for incoming_dir in self.directories:
                    shutil.copy(file, incoming_dir / file.name)
                    self.logger.info(f"Copied {file.name} to {incoming_dir.name} directory.")
                
                # Delete the original file
                file.unlink()
                self.logger.info(f"Deleted {file.name} from Both_Incoming.")
        
        except Exception as e:
            self.logger.error(f"Error processing Both_Incoming: {e}")
        
        return found_files
    
    def process_file(self, file):
        """Process a single JPEG file."""
        if "__LRE" in file.name:  # Skip already processed files
            return
            
        self.logger.info(f"Found file to process: {file}")
        
        # Check for zero-byte files
        if file.stat().st_size == 0:
            self.logger.warning(f"Skipping zero-byte file: {file}")
            return
            
        # Process the file
        processor = JPEGExifProcessor(str(file))
        try:
            new_path = processor.process_image()
            self.logger.info(f"Image processed successfully: {new_path}")
        except Exception as e:
            self.logger.error(f"Error processing image: {e}")
    
    def check_directory(self, directory):
        """Check a directory for new JPEG files."""
        directory = Path(directory)
        if not directory.exists():
            return
            
        self.logger.info(f"\nChecking {directory} for new JPEG files...")
        for file in directory.glob("*.jpg"):
            self.process_file(file)

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=getattr(logging, LOG_LEVEL))
    
    # Create watchers
    jpeg_watcher = DirectoryWatcher(
        watch_dirs=WATCH_DIRS,
        both_incoming_dir=BOTH_INCOMING
    )
    video_watcher = VideoWatcher(directories=WATCH_DIRS)
    
    try:
        # Start both watchers
        while True:
            # Process both incoming directory first for JPEGs
            jpeg_watcher.process_both_incoming()
            
            # Check all watch directories for both types
            for directory in WATCH_DIRS:
                # Check for JPEGs
                jpeg_watcher.check_directory(directory)
                # Check for videos
                video_watcher.check_directory(directory)
            
            time.sleep(SLEEP_TIME)
            
    except KeyboardInterrupt:
        logging.info("Stopping watchers")
        jpeg_watcher.stop()
        video_watcher.stop()