#!/usr/bin/env python3

from pathlib import Path
import subprocess
import json
import logging
import sys
import shutil
import os
import xml.etree.ElementTree as ET
from datetime import datetime
import time
from mutagen.mp4 import MP4
import re
import glob

from config import (
    LOG_LEVEL,
    SLEEP_TIME,
    VIDEO_PATTERNS,
    XML_NAMESPACES,
    MCCARTYS_PREFIX,
    MCCARTYS_REPLACEMENT,
    EXIFTOOL_BASE_ARGS,
    METADATA_FIELDS,
    VERIFY_FIELDS,
    FILENAME_REPLACEMENTS,
    LRE_SUFFIX,
    WATCH_DIRS
)

def log_message(message):
    """Log a message with timestamp."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}")

class VideoProcessor:
    """
    A class to process video files and their metadata using exiftool.
    """
    
    def __init__(self, file_path: str):
        """
        Initialize the video processor with a file path.
        
        Args:
            file_path (str): Path to input video file
        """
        self.file_path = file_path
        self.logger = logging.getLogger(__name__)
        
        # Verify exiftool is available
        if not shutil.which('exiftool'):
            self.logger.error("exiftool is not installed or not in PATH")
            sys.exit(1)
            
        # Validate file extension
        if Path(file_path).suffix.lower() not in VIDEO_PATTERNS:
            self.logger.error(f"File must be a video format. Found: {Path(file_path).suffix}")
            sys.exit(1)
    
    def get_date_from_exiftool(self, xmp_path):
        """Get DateTimeOriginal from XMP using exiftool."""
        try:
            exiftool_args = [
                'exiftool',
                '-s',
                '-d', '%Y:%m:%d %H:%M:%S',  # Specify consistent date format
                '-DateTimeOriginal',
                xmp_path
            ]
            result = subprocess.run(exiftool_args, capture_output=True, text=True, check=True)
            if result.stdout:
                date_line = result.stdout.strip()
                if ': ' in date_line:
                    date_time_original = date_line.split(': ')[1].strip()
                    log_message(f"Found DateTimeOriginal from exiftool: {date_time_original}")
                    return date_time_original
        except Exception as e:
            log_message(f"Error getting date from exiftool: {e}")
        return None

    def parse_gps_coordinate(self, coord_str):
        """Parse GPS coordinate from exiftool format to decimal degrees."""
        try:
            # Handle format like "32 deg 54' 59.76\" N"
            parts = coord_str.replace('"', '').split()
            degrees = float(parts[0])
            minutes = float(parts[2].rstrip("'"))
            seconds = float(parts[3])
            direction = parts[4]
            
            decimal = degrees + minutes/60 + seconds/3600
            if direction in ['S', 'W']:
                decimal = -decimal
            
            return decimal
        except Exception as e:
            log_message(f"Error parsing GPS coordinate '{coord_str}': {e}")
            return None

    def get_title_from_rdf(self, rdf):
        """Extract title from RDF data."""
        ns = XML_NAMESPACES
        
        # First try dc:title format
        title_path = f'.//{{{ns["dc"]}}}title/{{{ns["rdf"]}}}Alt/{{{ns["rdf"]}}}li'
        title_elem = rdf.find(title_path)
        if title_elem is not None and title_elem.text:
            title = title_elem.text.strip()
            log_message(f"Found XMP title in dc:title format: '{title}'")
            return title
            
        # Try direct dc:title format
        title_path = f'.//{{{ns["dc"]}}}title'
        title_elem = rdf.find(title_path)
        if title_elem is not None and title_elem.text:
            title = title_elem.text.strip()
            log_message(f"Found XMP title in direct format: '{title}'")
            return title
            
        # Try photoshop:Headline format
        title_path = f'.//{{{ns["photoshop"]}}}Headline'
        title_elem = rdf.find(title_path)
        if title_elem is not None and title_elem.text:
            title = title_elem.text.strip()
            log_message(f"Found XMP title in Headline format: '{title}'")
            return title
        
        log_message("No XMP title found in any format")
        return None

    def get_caption_from_rdf(self, rdf):
        """Extract caption from RDF data."""
        ns = XML_NAMESPACES
        description_path = f'.//{{{ns["dc"]}}}description/{{{ns["rdf"]}}}Alt/{{{ns["rdf"]}}}li'
        description_elem = rdf.find(description_path)
        if description_elem is not None and description_elem.text:
            caption = description_elem.text.strip()
            log_message(f"Found XMP caption: '{caption}'")
            return caption
        log_message("No XMP caption found")
        return None

    def get_keywords_from_rdf(self, rdf):
        """Extract keywords from RDF data."""
        ns = XML_NAMESPACES
        keywords = []
        
        # Try hierarchical subject first
        subject_path = f'.//{{{ns["lr"]}}}hierarchicalSubject/{{{ns["rdf"]}}}Bag/{{{ns["rdf"]}}}li'
        subject_elems = rdf.findall(subject_path)
        
        if subject_elems:
            log_message("Found hierarchical subjects")
            for elem in subject_elems:
                if elem.text:
                    # Split hierarchical subject into parts
                    parts = elem.text.split('|')
                    # Add each part as a separate keyword
                    for part in parts:
                        part = part.strip()
                        if part and part not in keywords:
                            keywords.append(part)
                            log_message(f"Added keyword from hierarchical subject: {part}")
        
        # Try flat subject list
        if not keywords:
            subject_path = f'.//{{{ns["dc"]}}}subject/{{{ns["rdf"]}}}Bag/{{{ns["rdf"]}}}li'
            subject_elems = rdf.findall(subject_path)
            
            if subject_elems:
                log_message("Found subject keywords")
                for elem in subject_elems:
                    if elem.text:
                        keyword = elem.text.strip()
                        if keyword and keyword not in keywords:
                            keywords.append(keyword)
                            log_message(f"Added keyword from subject: {keyword}")
        
        if not keywords:
            log_message("No keywords found")
            
        return keywords

    def get_location_from_rdf(self, rdf):
        """Extract location data from RDF data."""
        ns = XML_NAMESPACES
        location_data = {
            'location': None,
            'city': None,
            'state': None,
            'country': None,
            'gps': None
        }
        
        # Get location
        location_path = f'.//{{{ns["Iptc4xmpCore"]}}}Location'
        location_elem = rdf.find(location_path)
        if location_elem is not None and location_elem.text:
            location_data['location'] = location_elem.text.strip()
            log_message(f"Found location: {location_data['location']}")
            
        # Get city
        city_path = f'.//{{{ns["photoshop"]}}}City'
        city_elem = rdf.find(city_path)
        if city_elem is not None and city_elem.text:
            location_data['city'] = city_elem.text.strip()
            log_message(f"Found city: {location_data['city']}")
            
        # Get state
        state_path = f'.//{{{ns["photoshop"]}}}State'
        state_elem = rdf.find(state_path)
        if state_elem is not None and state_elem.text:
            location_data['state'] = state_elem.text.strip()
            log_message(f"Found state: {location_data['state']}")
            
        # Get country
        country_path = f'.//{{{ns["photoshop"]}}}Country'
        country_elem = rdf.find(country_path)
        if country_elem is not None and country_elem.text:
            location_data['country'] = country_elem.text.strip()
            log_message(f"Found country: {location_data['country']}")
            
        # Get GPS coordinates
        lat_path = f'.//{{{ns["exif"]}}}GPSLatitude'
        lon_path = f'.//{{{ns["exif"]}}}GPSLongitude'
        lat_elem = rdf.find(lat_path)
        lon_elem = rdf.find(lon_path)
        
        if lat_elem is not None and lon_elem is not None:
            try:
                lat = float(lat_elem.text)
                lon = float(lon_elem.text)
                location_data['gps'] = (lat, lon)
                log_message(f"Found GPS coordinates: {lat}, {lon}")
            except (ValueError, TypeError) as e:
                log_message(f"Error parsing GPS coordinates: {e}")
        
        return location_data

    def get_metadata_from_xmp(self):
        """Get metadata from XMP sidecar file."""
        log_message("=" * 50)
        log_message("Starting XMP metadata extraction")
        log_message("=" * 50)
        
        # Initialize return values
        title = None
        keywords = []
        caption = None
        location_data = None
        tree = None
        
        # Try both possible XMP file locations
        xmp_path = os.path.splitext(self.file_path)[0] + ".xmp"
        if not os.path.exists(xmp_path):
            xmp_path = self.file_path + ".xmp"
            if not os.path.exists(xmp_path):
                log_message("No XMP file found")
                log_message("=" * 50)
                return None
        
        log_message("Found XMP file")
        
        # Get DateTimeOriginal from exiftool
        date_time_original = self.get_date_from_exiftool(xmp_path)
        if date_time_original:
            log_message(f"Found DateTimeOriginal from exiftool: {date_time_original}")
        
        # Get all metadata using exiftool
        log_message("-" * 30)
        log_message("Extracting metadata using exiftool")
        log_message("-" * 30)
        
        exiftool_args = [
            'exiftool',
            '-s',
            '-j',  # Output as JSON for better parsing
            '-Title',
            '-DisplayName',
            '-ItemList:Title',
            '-Description',
            '-Caption-Abstract',
            '-Subject',  # Keywords/tags
            '-Keywords',
            '-Location',
            '-City',
            '-State',
            '-Country',
            '-GPSLatitude',
            '-GPSLongitude',
            '-DateTimeOriginal',
            '-CreateDate',
            '-ModifyDate',
            xmp_path
        ]
        try:
            result = subprocess.run(exiftool_args, capture_output=True, text=True, check=True)
            if result.stdout:
                metadata = json.loads(result.stdout)
                log_message("Raw exiftool metadata:")
                log_message("-" * 30)
                log_message(json.dumps(metadata, indent=2))
                log_message("-" * 30)
                
                if metadata and isinstance(metadata, list) and len(metadata) > 0:
                    metadata = metadata[0]  # Get first item from array
                    
                    # Extract title
                    for field in ['Title', 'DisplayName', 'ItemList:Title', 'Description', 'Caption-Abstract']:
                        if field in metadata and metadata[field]:
                            title = metadata[field]
                            log_message(f"Found title in {field}: '{title}'")
                            break
                    
                    # Extract keywords/tags
                    for field in ['Subject', 'Keywords']:
                        if field in metadata:
                            if isinstance(metadata[field], list):
                                keywords.extend(metadata[field])
                            elif isinstance(metadata[field], str):
                                keywords.append(metadata[field])
                    if keywords:
                        log_message(f"Found keywords: {keywords}")
                    
                    # Extract caption
                    for field in ['Description', 'Caption-Abstract']:
                        if field in metadata and metadata[field]:
                            caption = metadata[field]
                            log_message(f"Found caption in {field}: '{caption}'")
                            break
                    
                    # Extract location data
                    location_parts = []
                    if 'Location' in metadata and metadata['Location']:
                        location_parts.append(metadata['Location'])
                    if 'City' in metadata and metadata['City']:
                        location_parts.append(metadata['City'])
                    if 'State' in metadata and metadata['State']:
                        location_parts.append(metadata['State'])
                    if 'Country' in metadata and metadata['Country']:
                        location_parts.append(metadata['Country'])
                    
                    if location_parts:
                        location_data = ', '.join(location_parts)
                        log_message(f"Found location: {location_data}")
                    
                    # Add GPS coordinates if available
                    if 'GPSLatitude' in metadata and 'GPSLongitude' in metadata:
                        lat = self.parse_gps_coordinate(metadata['GPSLatitude'])
                        lon = self.parse_gps_coordinate(metadata['GPSLongitude'])
                        if lat is not None and lon is not None:
                            if location_data:
                                location_data = f"{location_data} ({lat:.6f}, {lon:.6f})"
                            else:
                                location_data = f"{lat:.6f}, {lon:.6f}"
                            log_message(f"Found GPS coordinates: {lat:.6f}, {lon:.6f}")
                    
                    # Get date if not already set
                    if not date_time_original:
                        for field in ['DateTimeOriginal', 'CreateDate', 'ModifyDate']:
                            if field in metadata and metadata[field]:
                                date_time_original = metadata[field].replace(':', '-', 2)
                                log_message(f"Found date in {field}: {date_time_original}")
                                break
                
                else:
                    log_message("No metadata found in exiftool output")
        except json.JSONDecodeError as e:
            log_message(f"Error parsing exiftool JSON output: {e}")
            log_message(f"Raw output was: {result.stdout}")
        except Exception as e:
            log_message(f"Error getting metadata from exiftool: {e}")

        # Try to parse XMP for any missing data
        try:
            tree = ET.parse(xmp_path)
            root = tree.getroot()
            log_message("XMP root tag: " + root.tag)
            
            ns = XML_NAMESPACES
            rdf = root.find('.//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF')
            if rdf is not None:
                log_message("Found RDF data in XMP")
                
                # Only get data from XML if we didn't get it from exiftool
                if not title:
                    title = self.get_title_from_rdf(rdf)
                if not keywords:
                    keywords = self.get_keywords_from_rdf(rdf)
                if not caption:
                    caption = self.get_caption_from_rdf(rdf)
                if not location_data:
                    location_data = self.get_location_from_rdf(rdf)
            else:
                log_message("No RDF data found in XMP")
        except ET.ParseError as e:
            log_message(f"Error parsing XMP file: {e}")
        except Exception as e:
            log_message(f"Error processing XMP file: {e}")
        
        log_message("=" * 50)
        log_message("Final metadata values:")
        if title:
            log_message(f"Title: '{title}'")
        if keywords:
            log_message(f"Keywords: {keywords}")
        if caption:
            log_message(f"Caption: '{caption}'")
        if location_data:
            log_message(f"Location: {location_data}")
        if date_time_original:
            log_message(f"Date: {date_time_original}")
        log_message("=" * 50)
        
        return (None, title, keywords, tree, caption, date_time_original, location_data)

    def normalize_date(self, date_str):
        """Normalize date format."""
        if not date_str:
            return None
        # Keep colons in time part but use hyphens in date part
        parts = date_str.split(' ')
        if len(parts) >= 1:
            date_part = parts[0]  # Keep the colons as exiftool expects them
            if len(parts) > 1:
                return f"{date_part} {' '.join(parts[1:])}"
            return date_part
        return date_str

    def get_new_filename(self, title):
        """Generate new filename from title."""
        if not title:
            return None
            
        # Get the directory and filename
        directory = os.path.dirname(self.file_path)
        filename = os.path.basename(self.file_path)
        
        # Add __LRE suffix before the extension
        base, ext = os.path.splitext(filename)
        if not base.endswith('__LRE'):
            new_filename = f"{base}__LRE{ext}"
            return os.path.join(directory, new_filename)
        return self.file_path

    def process_video(self):
        """Process a video file.
        
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
            # 1. Check if file has __LRE suffix - skip if it does
            if '__LRE' in os.path.basename(self.file_path):
                return True
                
            # 2. Read metadata from XMP
            metadata = self.get_metadata_from_xmp()
            if not metadata:
                return False
            video_date, xmp_title, keywords, tree, caption, date_time_original, location_data = metadata
            
            # 3. Write metadata to video file
            metadata_args = [
                '-overwrite_original',
                '-m',  # Ignore minor warnings
                '-P'  # Preserve file modification date/time
            ]
            
            if xmp_title:
                metadata_args.append(f'-Title={xmp_title}')
            
            if caption:
                metadata_args.extend([
                    f'-Description={caption}',
                    f'-Caption-Abstract={caption}'
                ])
            
            if keywords:
                # Clear existing keywords
                metadata_args.extend([
                    '-overwrite_original',
                    '-m',  # Ignore minor warnings
                    '-P',  # Preserve file modification date/time
                    '-QuickTime:Keywords:=',  # Clear QuickTime keywords
                    '-UserData:Keywords:=',   # Clear QuickTime user data keywords
                    '-XMP-apple:Keywords:='   # Clear Apple-specific XMP keywords
                ])
                
                # Add keywords in Apple/QuickTime formats
                keywords_str = ','.join(keywords)
                metadata_args.extend([
                    f'-QuickTime:Keywords={keywords_str}',
                    f'-UserData:Keywords={keywords_str}',
                    f'-XMP-apple:Keywords={keywords_str}'
                ])
            
            if location_data:
                metadata_args.append(f'-Location={location_data}')
            
            if date_time_original:
                normalized_date = self.normalize_date(date_time_original)
                if normalized_date:
                    metadata_args.extend([
                        f'-CreateDate={normalized_date}',
                        f'-ModifyDate={normalized_date}',
                        f'-DateTimeOriginal={normalized_date}'
                    ])
            
            # Run exiftool to write metadata
            exiftool_args = EXIFTOOL_BASE_ARGS.copy()
            exiftool_args.extend(metadata_args)
            exiftool_args.append(self.file_path)
            
            try:
                result = subprocess.run(exiftool_args, capture_output=True, text=True, check=True)
                log_message("Added metadata using exiftool:")
                log_message(result.stdout)
            except subprocess.CalledProcessError as e:
                log_message(f"Error adding metadata using exiftool: {e}")
                log_message(f"Error output: {e.stderr}")
                return False
            
            # 4. Verify metadata was written correctly
            if not self.verify_metadata(xmp_title, keywords, normalized_date, caption, location_data):
                log_message("Metadata verification failed")
                return False
            
            # 5. Delete XMP file
            xmp_path = os.path.splitext(self.file_path)[0] + ".xmp"
            if not os.path.exists(xmp_path):
                xmp_path = self.file_path + ".xmp"
            if os.path.exists(xmp_path):
                os.remove(xmp_path)
                log_message(f"Removed XMP file: {os.path.basename(xmp_path)}")
            
            # 6. Rename video file
            new_path = self.get_new_filename(xmp_title)
            if new_path and new_path != self.file_path:
                os.rename(self.file_path, new_path)
                self.file_path = new_path
                log_message(f"Renamed video to: {os.path.basename(new_path)}")
            
            return True
            
        except Exception as e:
            log_message(f"Error processing video: {e}")
            return False

    def verify_metadata(self, expected_title, expected_keywords, expected_date, expected_caption=None, expected_location=None):
        """Verify that metadata was written correctly."""
        try:
            log_message("=== Starting Metadata Verification ===")
            
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
                self.file_path
            ]
            
            result = subprocess.run(exiftool_args, capture_output=True, text=True, check=True)
            metadata = json.loads(result.stdout)[0]
            
            # Check title
            if expected_title:
                title = metadata.get('Title')
                if title == expected_title:
                    log_message(f"Found title: {title}")
                else:
                    log_message(f"Title mismatch. Expected: {expected_title}, Found: {title}")
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
                    log_message(f"Found keywords: {', '.join(sorted(found_keywords))}")
                else:
                    log_message(f"Keyword mismatch. Expected: {expected_keywords}, Found: {found_keywords}")
                    return False
            
            # Check date
            if expected_date:
                create_date = metadata.get('CreateDate')
                # Convert expected date hyphens to colons for comparison
                expected_date_colons = expected_date.replace('-', ':')
                if create_date and create_date.startswith(expected_date_colons):
                    log_message(f"Found matching date in CreateDate: {create_date}")
                else:
                    log_message(f"Date mismatch. Expected: {expected_date_colons}, Found: {create_date}")
                    return False
            
            # Check caption
            if expected_caption:
                caption = metadata.get('Description') or metadata.get('Caption-Abstract')
                if caption == expected_caption:
                    log_message(f"Found caption: {caption}")
                else:
                    log_message(f"Caption mismatch. Expected: {expected_caption}, Found: {caption}")
                    return False
            
            # Check location
            if expected_location:
                location = metadata.get('Location')
                if location == expected_location:
                    log_message(f"Found location: {location}")
                else:
                    log_message(f"Location mismatch. Expected: {expected_location}, Found: {location}")
                    return False
            
            log_message("=== Metadata Verification Complete ===")
            return True
            
        except Exception as e:
            log_message(f"Error verifying metadata: {e}")
            return False

class VideoWatcher:
    """Class to watch directories for new video files."""
    
    def __init__(self, directories=None):
        """Initialize with list of directories to watch."""
        self.directories = directories or WATCH_DIRS
        self.running = False
        
    def process_file(self, file_path):
        """Process a single video file."""
        try:
            # Skip if already processed
            if '__LRE' in os.path.basename(file_path):
                return
                
            # Check for XMP file
            xmp_path = os.path.splitext(file_path)[0] + ".xmp"
            if not os.path.exists(xmp_path):
                xmp_path = file_path + ".xmp"
                if not os.path.exists(xmp_path):
                    return  # Skip if no XMP file
            
            # Process new McCartys video
            log_message(f"Found new McCartys video: {os.path.basename(file_path)}")
            processor = VideoProcessor(file_path)
            processor.process_video()
            
        except Exception as e:
            log_message(f"Error processing {file_path}: {e}")
    
    def watch(self):
        """Start watching directories for new video files."""
        self.running = True
        try:
            while self.running:
                for directory in self.directories:
                    log_message(f"Checking {directory} for new video files...")
                    
                    # Get all video files that have XMP files
                    for pattern in VIDEO_PATTERNS:
                        # Debug: print pattern being searched
                        log_message(f"Searching for pattern: *{pattern}")
                        
                        # Debug: print full search path
                        search_path = os.path.join(directory, f"*{pattern}")
                        log_message(f"Search path: {search_path}")
                        
                        # Find matching files
                        files = glob.glob(search_path)
                        
                        # Debug: print found files
                        if files:
                            log_message(f"Found files: {files}")
                        else:
                            log_message("No files found with this pattern")
                        
                        for file_path in files:
                            self.process_file(file_path)
                            
                time.sleep(SLEEP_TIME)
                
        except KeyboardInterrupt:
            log_message("Stopping video watch")
            self.running = False
    
    def stop(self):
        """Stop watching directories."""
        self.running = False

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=getattr(logging, LOG_LEVEL))
    
    # Start watching directories
    watcher = VideoWatcher()
    watcher.watch()
