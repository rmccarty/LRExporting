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
import fcntl
from PIL import Image
from datetime import timedelta
from abc import ABC, abstractmethod

from config import (
    WATCH_DIRS, 
    BOTH_INCOMING, 
    LOG_LEVEL, 
    SLEEP_TIME,
    XML_NAMESPACES,
    METADATA_FIELDS,
    VERIFY_FIELDS,
    VIDEO_PATTERN,
    MCCARTYS_PREFIX,
    MCCARTYS_REPLACEMENT,
    LRE_SUFFIX,
    JPEG_QUALITY,
    JPEG_COMPRESS,
    TRANSFER_PATHS,
    MIN_FILE_AGE
)

from watchers.base_watcher import BaseWatcher
from processors.media_processor import MediaProcessor
from processors.jpeg_processor import JPEGExifProcessor

class VideoProcessor(MediaProcessor):
    """A class to process video files and their metadata using exiftool."""
    
    def __init__(self, file_path: str, sequence: str = None):
        """Initialize with video file path."""
        super().__init__(file_path, sequence=sequence)
        
        # Validate file extension
        ext = Path(file_path).suffix.lower()
        if not any(ext.endswith(pattern) for pattern in ['.mp4', '.mov', '.m4v']):
            self.logger.error(f"File must be a video format. Found: {ext}")
            sys.exit(1)
    
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
            title_path = f'.//{{{ns["dc"]}}}title/{{{ns["rdf"]}}}Alt/{{{ns["rdf"]}}}li'
            title_elem = rdf.find(title_path)
            if title_elem is not None:
                self.logger.debug(f"Found title: {title_elem.text}")
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
    
    def get_new_filename(self, title):
        """Generate new filename from title."""
        try:
            # Get metadata components
            date_str, title, location, city, country = self.get_metadata_components()
            
            if not date_str:
                self.logger.error("Could not get date for filename")
                return None
                
            # Clean title if present
            if title:
                title = self.clean_component(title)
                if title:  # If title is still valid after cleaning
                    base_name = f"{date_str}_{title}"
                else:
                    base_name = date_str
            else:
                base_name = date_str
            
            # Add sequence number if provided
            if self.sequence:
                base_name = f"{base_name}_{self.sequence}"
                
            return f"{base_name}__LRE{self.file_path.suffix}"
            
        except Exception as e:
            self.logger.error(f"Error generating filename: {e}")
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
                return True

            # Get metadata from XMP
            xmp_metadata = self.get_metadata_from_xmp()
            if xmp_metadata is None:
                self.logger.warning("No XMP metadata found")
                return False
                
            # Write metadata to video file
            title, keywords, date_str, caption, location_data = xmp_metadata
            
            # Get location components
            location, city, country = location_data if isinstance(location_data, tuple) else (None, None, None)
            
            # Log metadata values for debugging
            self.logger.info("\n==================================================")
            self.logger.info("Final metadata values:")
            self.logger.info(f"Title: '{title}'")
            self.logger.info(f"Keywords: {keywords}")
            self.logger.info(f"Caption: '{caption}'")
            self.logger.info(f"Location: '{location}'")
            self.logger.info(f"City: '{city}'")
            self.logger.info(f"Country: '{country}'")
            
            # Write metadata with overwrite_original flag
            cmd = ['exiftool', '-overwrite_original', '-api', 'QuickTimeUTF8=1']
            
            if title:
                cmd.extend([
                    '-Title=' + title,
                    '-QuickTime:Title=' + title,
                    '-XMP:Title=' + title,
                    '-ItemList:Title=' + title
                ])
            if keywords:
                # Clean keywords and remove duplicates while preserving order
                clean_keywords = []
                seen = set()
                for k in keywords:
                    k = k.strip()
                    if k and k not in seen:
                        clean_keywords.append(k)
                        seen.add(k)
                
                # Join keywords with comma for ItemList fields
                keyword_str = ",".join(clean_keywords)
                # Log what we're writing
                self.logger.info(f"\nWriting keywords: {keyword_str}")
                cmd.extend([
                    '-QuickTime:Keywords=' + keyword_str,
                    '-XMP:Subject=' + keyword_str
                ])
            else:
                # Clear any existing keywords
                cmd.extend([
                    '-QuickTime:Keywords=',
                    '-XMP:Subject='
                ])
            if date_str:
                cmd.extend([
                    '-CreateDate=' + date_str,
                    '-ModifyDate=' + date_str,
                    '-TrackCreateDate=' + date_str,
                    '-TrackModifyDate=' + date_str,
                    '-MediaCreateDate=' + date_str,
                    '-MediaModifyDate=' + date_str,
                    '-QuickTime:CreateDate=' + date_str,
                    '-QuickTime:MediaCreateDate=' + date_str,
                    '-XMP:CreateDate=' + date_str
                ])
            if caption:
                cmd.extend([
                    '-Description=' + caption,
                    '-Caption-Abstract=' + caption,
                    '-XMP:Description=' + caption,
                    '-ItemList:Description=' + caption
                ])
            if location:
                cmd.extend([
                    '-Location=' + location,
                    '-XMP:Location=' + location,
                    '-LocationName=' + location
                ])
            if city:
                cmd.extend([
                    '-City=' + city,
                    '-XMP:City=' + city
                ])
            if country:
                cmd.extend([
                    '-Country=' + country,
                    '-XMP:Country=' + country
                ])
                
            cmd.append(str(self.file_path))
            
            # Log the full command for debugging
            self.logger.info(f"\nFull exiftool command: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                self.logger.info("Metadata written successfully")
            else:
                self.logger.error(f"Error writing metadata: {result.stderr}")
                return False
                
            # Read metadata back with -m flag to ignore file handler issues
            try:
                cmd = ['exiftool', '-j', '-m', str(self.file_path)]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    data = json.loads(result.stdout)
                    if data:
                        self.exif_data = data[0]
                else:
                    self.logger.error(f"Error reading metadata: {result.stderr}")
                    return False
            except Exception as e:
                self.logger.warning(f"Could not read EXIF data: {e}")
                return False
                
            # Verify metadata was written correctly
            try:
                # Read back EXIF data
                result = subprocess.run(['exiftool', '-json', str(self.file_path)], 
                                     capture_output=True, text=True, check=True)
                self.exif_data = json.loads(result.stdout)[0]
                
                # Log raw EXIF data for debugging
                self.logger.info("\nRaw EXIF data for keyword fields:")
                for key in self.exif_data:
                    if any(field.lower() in key.lower() for field in ['Keywords', 'Subject']):
                        self.logger.info(f"{key}: {self.exif_data[key]}")
                
                if not self.verify_metadata(title, keywords, date_str, caption, location):
                    self.logger.error("Metadata verification failed")
                    return False
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Error reading metadata: {e.stderr}")
                return False
            except Exception as e:
                self.logger.warning(f"Could not read EXIF data: {e}")
                return False
                
            # Delete XMP file BEFORE renaming video
            xmp_path = self.file_path.with_suffix('.xmp')
            if xmp_path.exists():
                xmp_path.unlink()
                self.logger.info(f"Deleted XMP file: {xmp_path}")
                
            # Use the new rename_file method (which will use cached EXIF data)
            new_path = self.rename_file()
            self.logger.info(f"Renamed to: {new_path}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error processing video: {str(e)}")
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

    def verify_metadata(self, expected_title, expected_keywords, expected_date, expected_caption=None, expected_location=None):
        """Verify that metadata was written correctly."""
        try:
            # Log expected values
            self.logger.info("\nExpected values:")
            
            # Title verification
            self.logger.info(f"Title fields to check: {METADATA_FIELDS['title']}")
            self.logger.info(f"Expected title: {expected_title}")
            
            title_found = False
            for field in METADATA_FIELDS['title']:
                clean_field = field.replace('-', '').split(':')[-1]
                for key in self.exif_data:
                    if key.endswith(clean_field) and self.exif_data[key] == expected_title:
                        self.logger.info(f"Found title in {key}: {self.exif_data[key]}")
                        title_found = True
                        break
                if title_found:
                    break
                    
            if not title_found and expected_title:
                self.logger.error(f"Title verification failed. Expected: {expected_title}")
                return False
                
            # Keywords verification
            self.logger.info("\nKeyword fields to check: ['-ItemList:Keywords', '-ItemList:Subject']")
            self.logger.info(f"Expected keywords: {expected_keywords}")
            
            # Skip keyword verification if no keywords expected
            if not expected_keywords:
                self.logger.info("No keywords expected, skipping keyword verification")
                return True
            
            # Clean expected keywords
            expected_set = {k.strip() for k in expected_keywords if k.strip()}
            
            found_keywords = set()
            for field in ['-ItemList:Keywords', '-ItemList:Subject', '-Keys:Keywords', '-QuickTime:Keywords', '-XMP-dc:Subject']:
                clean_field = field.replace('-', '').split(':')[-1]
                for key in self.exif_data:
                    if key.endswith(clean_field):
                        value = self.exif_data[key]
                        if isinstance(value, list):
                            found_keywords.update(k.strip() for k in value if k.strip())
                        elif isinstance(value, str):
                            # Split and clean each keyword
                            keywords = [k.strip() for k in value.split(',') if k.strip()]
                            found_keywords.update(keywords)
            
            # Log all found keywords for debugging
            self.logger.info(f"\nFound keywords in all fields: {sorted(list(found_keywords))}")
            
            if expected_set != found_keywords:
                self.logger.error(f"Keywords verification failed. Expected: {sorted(list(expected_set))}, Found: {sorted(list(found_keywords))}")
                return False
                
            # Date verification
            self.logger.info("\nDate fields to check: {METADATA_FIELDS['date']}")
            self.logger.info(f"Expected date: {expected_date}")
            
            date_found = False
            for field in METADATA_FIELDS['date']:
                clean_field = field.replace('-', '').split(':')[-1]
                for key in self.exif_data:
                    if key.endswith(clean_field):
                        found_date = self.exif_data[key]
                        if found_date and self.dates_match(found_date, expected_date):
                            self.logger.info(f"Found matching date in {key}: {found_date}")
                            date_found = True
                            break
                if date_found:
                    break
                    
            if not date_found and expected_date:
                self.logger.error(f"Date verification failed. Expected: {expected_date}")
                return False
                
            # Location verification
            if expected_location:
                self.logger.info("\nLocation fields to check:")
                self.logger.info(f"Location: {METADATA_FIELDS['location']}")
                self.logger.info(f"City: {METADATA_FIELDS['city']}")
                self.logger.info(f"State: {METADATA_FIELDS['state']}")
                self.logger.info(f"Country: {METADATA_FIELDS['country']}")
                self.logger.info(f"Expected location: {expected_location}")
                
                location_found = False
                for field_type in ['location', 'city', 'state', 'country']:
                    for field in METADATA_FIELDS[field_type]:
                        clean_field = field.replace('-', '').split(':')[-1]
                        for key in self.exif_data:
                            if key.endswith(clean_field) and self.exif_data[key] in expected_location:
                                location_found = True
                                break
                        if location_found:
                            break
                    if location_found:
                        break
                        
                if not location_found:
                    self.logger.error(f"Location verification failed. Expected: {expected_location}")
                    return False
                    
            return True
            
        except Exception as e:
            self.logger.error(f"Error during metadata verification: {e}")
            return False

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
                    self.logger.warning(f"No XMP file found at {xmp_path}")
                    return None
                    
            self.logger.info(f"Reading metadata from XMP sidecar: {xmp_path}")
            
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
                
                self.logger.info("Successfully read metadata from XMP sidecar")
                self.logger.debug(f"XMP metadata - Title: {title}, Keywords: {keywords}, Date: {date_time_original}, Location: {location_data}")
                
                # Return the full tuple only if we found RDF data
                return title, keywords, date_time_original, caption, location_data
            else:
                self.logger.warning("No RDF data found in XMP")
                return None
                
        except ET.ParseError as e:
            self.logger.error(f"Error parsing XMP file: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error reading XMP file: {e}")
            return None

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
            
    def with_exclusive_access(self, file_path, timeout=5):
        """
        Try to get exclusive access to a file using flock.
        
        Args:
            file_path: Path to the file to lock
            timeout: Maximum time to wait for lock in seconds
            
        Returns:
            bool: True if lock was acquired, False if timeout
        """
        try:
            start_time = time.time()
            while True:
                try:
                    with open(file_path, 'rb') as f:
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                        return True
                except (IOError, OSError) as e:
                    if time.time() - start_time > timeout:
                        self.logger.warning(f"Timeout waiting for exclusive access to {file_path}")
                        return False
                    time.sleep(0.1)
        except Exception as e:
            self.logger.error(f"Error trying to get exclusive access to {file_path}: {e}")
            return False
            
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
                return True

            # Get metadata from XMP
            xmp_metadata = self.get_metadata_from_xmp()
            if xmp_metadata is None:
                self.logger.warning("No XMP metadata found")
                return False
                
            # Write metadata to video file
            title, keywords, date_str, caption, location_data = xmp_metadata
            
            # Get location components
            location, city, country = location_data if isinstance(location_data, tuple) else (None, None, None)
            
            # Log metadata values for debugging
            self.logger.info("\n==================================================")
            self.logger.info("Final metadata values:")
            self.logger.info(f"Title: '{title}'")
            self.logger.info(f"Keywords: {keywords}")
            self.logger.info(f"Caption: '{caption}'")
            self.logger.info(f"Location: '{location}'")
            self.logger.info(f"City: '{city}'")
            self.logger.info(f"Country: '{country}'")
            
            # Write metadata with overwrite_original flag
            cmd = ['exiftool', '-overwrite_original', '-api', 'QuickTimeUTF8=1']
            
            if title:
                cmd.extend([
                    '-Title=' + title,
                    '-QuickTime:Title=' + title,
                    '-XMP:Title=' + title,
                    '-ItemList:Title=' + title
                ])
            if keywords:
                # Clean keywords and remove duplicates while preserving order
                clean_keywords = []
                seen = set()
                for k in keywords:
                    k = k.strip()
                    if k and k not in seen:
                        clean_keywords.append(k)
                        seen.add(k)
                
                # Join keywords with comma for ItemList fields
                keyword_str = ",".join(clean_keywords)
                # Log what we're writing
                self.logger.info(f"\nWriting keywords: {keyword_str}")
                cmd.extend([
                    '-QuickTime:Keywords=' + keyword_str,
                    '-XMP:Subject=' + keyword_str
                ])
            else:
                # Clear any existing keywords
                cmd.extend([
                    '-QuickTime:Keywords=',
                    '-XMP:Subject='
                ])
            if date_str:
                cmd.extend([
                    '-CreateDate=' + date_str,
                    '-ModifyDate=' + date_str,
                    '-TrackCreateDate=' + date_str,
                    '-TrackModifyDate=' + date_str,
                    '-MediaCreateDate=' + date_str,
                    '-MediaModifyDate=' + date_str,
                    '-QuickTime:CreateDate=' + date_str,
                    '-QuickTime:MediaCreateDate=' + date_str,
                    '-XMP:CreateDate=' + date_str
                ])
            if caption:
                cmd.extend([
                    '-Description=' + caption,
                    '-Caption-Abstract=' + caption,
                    '-XMP:Description=' + caption,
                    '-ItemList:Description=' + caption
                ])
            if location:
                cmd.extend([
                    '-Location=' + location,
                    '-XMP:Location=' + location,
                    '-LocationName=' + location
                ])
            if city:
                cmd.extend([
                    '-City=' + city,
                    '-XMP:City=' + city
                ])
            if country:
                cmd.extend([
                    '-Country=' + country,
                    '-XMP:Country=' + country
                ])
                
            cmd.append(str(self.file_path))
            
            # Log the full command for debugging
            self.logger.info(f"\nFull exiftool command: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                self.logger.info("Metadata written successfully")
            else:
                self.logger.error(f"Error writing metadata: {result.stderr}")
                return False
                
            # Read metadata back with -m flag to ignore file handler issues
            try:
                cmd = ['exiftool', '-j', '-m', str(self.file_path)]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    data = json.loads(result.stdout)
                    if data:
                        self.exif_data = data[0]
                else:
                    self.logger.error(f"Error reading metadata: {result.stderr}")
                    return False
            except Exception as e:
                self.logger.warning(f"Could not read EXIF data: {e}")
                return False
                
            # Verify metadata was written correctly
            try:
                # Read back EXIF data
                result = subprocess.run(['exiftool', '-json', str(self.file_path)], 
                                     capture_output=True, text=True, check=True)
                self.exif_data = json.loads(result.stdout)[0]
                
                # Log raw EXIF data for debugging
                self.logger.info("\nRaw EXIF data for keyword fields:")
                for key in self.exif_data:
                    if any(field.lower() in key.lower() for field in ['Keywords', 'Subject']):
                        self.logger.info(f"{key}: {self.exif_data[key]}")
                
                if not self.verify_metadata(title, keywords, date_str, caption, location):
                    self.logger.error("Metadata verification failed")
                    return False
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Error reading metadata: {e.stderr}")
                return False
            except Exception as e:
                self.logger.warning(f"Could not read EXIF data: {e}")
                return False
                
            # Delete XMP file BEFORE renaming video
            xmp_path = self.file_path.with_suffix('.xmp')
            if xmp_path.exists():
                xmp_path.unlink()
                self.logger.info(f"Deleted XMP file: {xmp_path}")
                
            # Use the new rename_file method (which will use cached EXIF data)
            new_path = self.rename_file()
            self.logger.info(f"Renamed to: {new_path}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error processing video: {str(e)}")
            return False

    def get_metadata_components(self):
        """Get metadata components for video files."""
        # Read EXIF data first
        exif_data = self.read_exif()
        
        # Try to get metadata from XMP first
        metadata = self.get_metadata_from_xmp()
        if metadata:
            title, keywords, date_str, caption, location_data = metadata
            
            # Get location components from location_data tuple
            location, city, country = location_data if isinstance(location_data, tuple) else (None, None, None)
            
            # Format date
            if date_str:
                try:
                    # Handle both date-only and datetime formats
                    if ' ' in date_str:
                        date_str = date_str.split()[0]  # Get just the date part
                    date_str = date_str.replace(':', '-')  # Convert : to - in date
                    # Validate it's a proper date
                    datetime.strptime(date_str, '%Y-%m-%d')
                except ValueError:
                    self.logger.warning(f"Invalid date format: {date_str}")
                    date_str = datetime.now().strftime('%Y-%m-%d')
            else:
                date_str = datetime.now().strftime('%Y-%m-%d')
                
            return date_str, title, location, city, country
            
        else:
            # Fallback to video file metadata
            date_str = None
            for field in METADATA_FIELDS['date']:
                clean_field = field.replace('-', '').split(':')[-1]
                for key in self.exif_data:
                    if key.endswith(clean_field):
                        date_str = self.exif_data[key]
                        if date_str:
                            try:
                                # Handle both date-only and datetime formats
                                if ' ' in date_str:
                                    date_str = date_str.split()[0]  # Get just the date part
                                date_str = date_str.replace(':', '-')  # Convert : to - in date
                                # Validate it's a proper date
                                datetime.strptime(date_str, '%Y-%m-%d')
                                break
                            except ValueError:
                                self.logger.warning(f"Invalid date format: {date_str}")
                                date_str = None
                                continue
                if date_str:
                    break
            
            if not date_str:
                date_str = datetime.now().strftime('%Y-%m-%d')
            
            # Get title from metadata
            title = None
            for field in METADATA_FIELDS['title']:
                clean_field = field.replace('-', '').split(':')[-1]
                for key in self.exif_data:
                    if key.endswith(clean_field):
                        title = self.exif_data[key]
                        if title:
                            break
                if title:
                    break
            
            # Get location data
            location = None
            city = None
            country = None
            for field_type in ['location', 'city', 'country']:
                for field in METADATA_FIELDS[field_type]:
                    clean_field = field.replace('-', '').split(':')[-1]
                    for key in self.exif_data:
                        if key.endswith(clean_field):
                            value = self.exif_data[key]
                            if value:
                                if field_type == 'location':
                                    location = value
                                elif field_type == 'city':
                                    city = value
                                elif field_type == 'country':
                                    country = value
                                break
                    if (field_type == 'location' and location) or \
                       (field_type == 'city' and city) or \
                       (field_type == 'country' and country):
                        break
            
            return date_str, title, location, city, country

class Transfer:
    """
    Handles safe transfer of processed files to their destination directories.
    Ensures files are not active/being written to before moving them.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
    def _can_access_file(self, file_path: Path, timeout: int = 5) -> bool:
        """
        Try to get exclusive access to a file using flock.
        
        Args:
            file_path: Path to the file to check
            timeout: Maximum time to wait for lock in seconds
            
        Returns:
            bool: True if exclusive access was obtained, False otherwise
        """
        try:
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    with open(file_path, 'rb') as f:
                        # Try non-blocking exclusive lock
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        # If we get here, we got the lock
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                        return True
                except (IOError, OSError):
                    # File is locked or inaccessible
                    time.sleep(0.1)
            return False
        except Exception as e:
            self.logger.error(f"Error checking file access: {e}")
            return False
            
    def _is_file_old_enough(self, file_path: Path) -> bool:
        """
        Check if file's last modification time is at least MIN_FILE_AGE seconds old.
        
        Args:
            file_path: Path to the file to check
            
        Returns:
            bool: True if file is old enough, False otherwise
        """
        try:
            mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
            age_threshold = datetime.now() - timedelta(seconds=MIN_FILE_AGE)
            return mtime <= age_threshold
        except Exception as e:
            self.logger.error(f"Error checking file age: {e}")
            return False
            
    def transfer_file(self, file_path: Path) -> bool:
        """
        Safely transfer a file to its destination directory if conditions are met:
        1. File ends with _LRE
        2. Source directory has a configured destination
        3. File is at least MIN_FILE_AGE seconds old
        4. File can be opened with exclusive access
        
        Args:
            file_path: Path to the file to transfer
            
        Returns:
            bool: True if transfer was successful, False otherwise
        """
        try:
            if not file_path.exists():
                self.logger.error(f"File does not exist: {file_path}")
                return False
                
            # Check if this is a processed file
            if not file_path.name.endswith('__LRE' + file_path.suffix):
                self.logger.debug(f"Not a processed file: {file_path}")
                return False
                
            # Check if we have a destination for this source directory
            source_dir = file_path.parent
            if source_dir not in TRANSFER_PATHS:
                self.logger.error(f"No transfer path configured for: {source_dir}")
                return False
                
            # Check if file is old enough
            if not self._is_file_old_enough(file_path):
                self.logger.debug(f"File too new to transfer: {file_path}")
                return False
                
            # Check if we can get exclusive access
            if not self._can_access_file(file_path):
                self.logger.debug(f"Cannot get exclusive access to file: {file_path}")
                return False
                
            # All checks passed, perform the transfer
            dest_dir = TRANSFER_PATHS[source_dir]
            dest_path = dest_dir / file_path.name
            
            # Create destination directory if it doesn't exist
            dest_dir.mkdir(parents=True, exist_ok=True)
            
            # Move the file
            file_path.rename(dest_path)
            self.logger.info(f"Transferred {file_path.name} to {dest_dir}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error transferring file {file_path}: {e}")
            return False

class TransferWatcher:
    """Watches for _LRE files and transfers them to their destination directories."""
    
    def __init__(self, directories=None):
        self.directories = [Path(d) for d in (directories or WATCH_DIRS)]
        self.running = False
        self.sleep_time = SLEEP_TIME
        self.logger = logging.getLogger(__name__)
        self.transfer = Transfer()
        
    def process_file(self, file_path: Path) -> bool:
        """
        Process a single file by attempting to transfer it.
        
        Args:
            file_path: Path to the file to process
            
        Returns:
            bool: True if transfer was successful or not needed, False if error
        """
        return self.transfer.transfer_file(file_path)
        
    def check_directory(self, directory: Path):
        """
        Check a directory for _LRE files ready to be transferred.
        
        Args:
            directory: Directory to check
        """
        if not directory.exists():
            self.logger.warning(f"Directory does not exist: {directory}")
            return
            
        try:
            for file_path in directory.glob('*__LRE.*'):
                self.process_file(file_path)
                
        except Exception as e:
            self.logger.error(f"Error checking directory {directory}: {e}")

class DirectoryWatcher:
    """
    A class to watch directories for new JPEG files and process them.
    """
    
    # Class-level sequence counter (1-9999)
    _sequence = 0
    
    @classmethod
    def _get_next_sequence(cls) -> str:
        """Get next sequence number as 4-digit string."""
        cls._sequence = (cls._sequence % 9999) + 1  # Roll over to 1 after 9999
        return f"{cls._sequence:04d}"  # Format as 4 digits with leading zeros
    
    def __init__(self, watch_dirs, both_incoming_dir=None):
        """
        Initialize the directory watcher.
        
        Args:
            watch_dirs: List of Path objects for directories to watch
            both_incoming_dir: Optional Path object for a shared incoming directory
        """
        self.directories = [Path(d) for d in watch_dirs]
        self.both_incoming = Path(both_incoming_dir) if both_incoming_dir else None
        self.running = False
        self.sleep_time = SLEEP_TIME
        self.logger = logging.getLogger(__name__)
    
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
        sequence = self._get_next_sequence()
        processor = JPEGExifProcessor(str(file), sequence=sequence)
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

class VideoWatcher:
    """
    A class to watch directories for video files.
    """
    
    # Class-level sequence counter (1-9999)
    _sequence = 0
    
    @classmethod
    def _get_next_sequence(cls) -> str:
        """Get next sequence number as 4-digit string."""
        cls._sequence = (cls._sequence % 9999) + 1  # Roll over to 1 after 9999
        return f"{cls._sequence:04d}"  # Format as 4 digits with leading zeros
    
    def __init__(self, directories=None):
        """
        Initialize the video watcher.
        
        Args:
            directories: List of Path objects for directories to watch
        """
        self.directories = [Path(d) for d in (directories or WATCH_DIRS)]
        self.running = False
        self.sleep_time = SLEEP_TIME
        self.logger = logging.getLogger(__name__)
    
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
            sequence = self._get_next_sequence()
            processor = VideoProcessor(file_path, sequence=sequence)
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
            sequence = self._get_next_sequence()
            processor = VideoProcessor(str(file_path), sequence=sequence)
            processor.process_video()

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=getattr(logging, LOG_LEVEL))
    
    # Create watchers
    jpeg_watcher = DirectoryWatcher(
        watch_dirs=WATCH_DIRS,
        both_incoming_dir=BOTH_INCOMING
    )
    video_watcher = VideoWatcher(directories=WATCH_DIRS)
    transfer_watcher = TransferWatcher(directories=WATCH_DIRS)
    
    try:
        # Start both watchers
        while True:
            # Process both incoming directory first for JPEGs
            jpeg_watcher.process_both_incoming()
            
            # Check all watch directories for both types
            for directory in WATCH_DIRS:
                directory = Path(directory)
                jpeg_watcher.check_directory(directory)
                # Check for videos
                video_watcher.check_directory(directory)
                # Check for transfers
                transfer_watcher.check_directory(directory)
                
            time.sleep(SLEEP_TIME)
            
    except KeyboardInterrupt:
        logging.info("Stopping watchers")
        jpeg_watcher.running = False
        video_watcher.running = False
        transfer_watcher.running = False