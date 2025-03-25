#!/usr/bin/env python3

# Requires: pip install mutagen
from mutagen.mp4 import MP4
import xml.etree.ElementTree as ET
import os
import time
from datetime import datetime
import subprocess
from config import (
    WATCH_DIRS,
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
    LRE_SUFFIX
)

def log_message(message):
    """Log a message with timestamp."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}")

def get_date_from_exiftool(xmp_path):
    """Get DateTimeOriginal from XMP using exiftool."""
    try:
        exiftool_args = [
            'exiftool',
            '-s',
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

def get_title_from_rdf(rdf):
    """Extract title from RDF data."""
    ns = XML_NAMESPACES
    title_path = f'.//{{{ns["dc"]}}}title/{{{ns["rdf"]}}}Alt/{{{ns["rdf"]}}}li'
    title_elem = rdf.find(title_path)
    if title_elem is not None and title_elem.text:
        title = title_elem.text.strip()
        log_message(f"Found XMP title: '{title}'")
        return title
    log_message("No XMP title found in standard format")
    return None

def get_caption_from_rdf(rdf):
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

def get_keywords_from_rdf(rdf):
    """Extract keywords from RDF data."""
    keywords = []
    log_message("Looking for keywords in XMP metadata...")
    ns = XML_NAMESPACES
    
    # Try dc:subject/rdf:Seq format
    keyword_path_seq = f'.//{{{ns["dc"]}}}subject/{{{ns["rdf"]}}}Seq/{{{ns["rdf"]}}}li'
    seq_keywords = rdf.findall(keyword_path_seq)
    if seq_keywords:
        log_message("Found keywords in dc:subject/rdf:Seq format:")
        for keyword_elem in seq_keywords:
            if keyword_elem.text and keyword_elem.text.strip():
                keywords.append(keyword_elem.text.strip())
                log_message(f"  - '{keyword_elem.text.strip()}'")
    
    # Try dc:subject/rdf:Bag format
    keyword_path_bag = f'.//{{{ns["dc"]}}}subject/{{{ns["rdf"]}}}Bag/{{{ns["rdf"]}}}li'
    bag_keywords = rdf.findall(keyword_path_bag)
    if bag_keywords:
        log_message("Found keywords in dc:subject/rdf:Bag format:")
        for keyword_elem in bag_keywords:
            if keyword_elem.text and keyword_elem.text.strip():
                if keyword_elem.text.strip() not in keywords:  # Avoid duplicates
                    keywords.append(keyword_elem.text.strip())
                    log_message(f"  - '{keyword_elem.text.strip()}'")
    
    # Try direct dc:subject format
    keyword_path_direct = f'.//{{{ns["dc"]}}}subject'
    direct_keywords = rdf.findall(keyword_path_direct)
    if direct_keywords:
        log_message("Found keywords in direct dc:subject format:")
        for keyword_elem in direct_keywords:
            if keyword_elem.text and keyword_elem.text.strip():
                if keyword_elem.text.strip() not in keywords:  # Avoid duplicates
                    keywords.append(keyword_elem.text.strip())
                    log_message(f"  - '{keyword_elem.text.strip()}'")
    
    if keywords:
        log_message(f"Found total of {len(keywords)} unique keywords in XMP")
    else:
        log_message("No keywords found in any XMP format")
    
    return keywords

def get_location_from_rdf(rdf):
    """Extract location data from RDF data."""
    location_data = {
        'location': None,
        'city': None,
        'state': None,
        'country': None,
        'gps': None
    }
    
    log_message("Looking for location data in XMP metadata...")
    
    # Find the rdf:Description element
    ns = XML_NAMESPACES
    desc = rdf.find(f'.//{{{ns["rdf"]}}}Description')
    if desc is not None:
        log_message("Found rdf:Description element")
        
        # Try to get location from Iptc4xmpCore:Location
        location_elem = desc.find(f'.//{{{ns["Iptc4xmpCore"]}}}Location')
        if location_elem is not None and location_elem.text:
            location_data['location'] = location_elem.text.strip()
            log_message(f"Found Location: {location_data['location']}")
        
        # Try to get city from photoshop:City
        city_elem = desc.find(f'.//{{{ns["photoshop"]}}}City')
        if city_elem is not None and city_elem.text:
            location_data['city'] = city_elem.text.strip()
            log_message(f"Found City: {location_data['city']}")
        
        # Try to get state from photoshop:State
        state_elem = desc.find(f'.//{{{ns["photoshop"]}}}State')
        if state_elem is not None and state_elem.text:
            location_data['state'] = state_elem.text.strip()
            log_message(f"Found State: {location_data['state']}")
        
        # Try to get country from photoshop:Country
        country_elem = desc.find(f'.//{{{ns["photoshop"]}}}Country')
        if country_elem is not None and country_elem.text:
            location_data['country'] = country_elem.text.strip()
            log_message(f"Found Country: {location_data['country']}")
        
        # Try to get GPS coordinates
        gps_lat = desc.find(f'.//{{{ns["exif"]}}}GPSLatitude')
        gps_lon = desc.find(f'.//{{{ns["exif"]}}}GPSLongitude')
        if gps_lat is not None and gps_lon is not None:
            location_data['gps'] = (gps_lat.text, gps_lon.text)
            log_message(f"Found GPS coordinates: {location_data['gps']}")
    
    return location_data

def get_metadata_from_xmp(file_path):
    """Get metadata from XMP sidecar file."""
    # First check for XMP with original filename
    xmp_path = os.path.splitext(file_path)[0] + ".xmp"
    if not os.path.exists(xmp_path):
        # If not found, check for XMP with same name as video
        xmp_path = file_path + ".xmp"
        if not os.path.exists(xmp_path):
            log_message(f"No XMP file found for: {os.path.basename(file_path)}")
            return (None, None, [], None, None, None, None)
    
    try:
        # Get DateTimeOriginal using exiftool
        date_time_original = get_date_from_exiftool(xmp_path)
        
        # Parse XMP file
        tree = ET.parse(xmp_path)
        root = tree.getroot()
        log_message(f"XMP root tag: {root.tag}")
        
        # Look for RDF inside xmpmeta
        rdf = root.find('.//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF')
        if rdf is not None:
            log_message("Found RDF data in XMP")
            title = get_title_from_rdf(rdf)
            keywords = get_keywords_from_rdf(rdf)
            caption = get_caption_from_rdf(rdf)
            location_data = get_location_from_rdf(rdf)
            
            return (datetime.now(), title, keywords, tree, caption, date_time_original, location_data)
        
        return (None, None, [], None, None, date_time_original, None)
            
    except Exception as e:
        log_message(f"Error reading XMP file: {e}")
        return (None, None, [], None, None, None, None)

def convert_decimal_to_dms(decimal_str):
    """Convert decimal coordinates to degrees/minutes/seconds format."""
    try:
        # Parse the decimal degrees format like "48,54.48336"
        # First, split on comma to get the degrees and decimal minutes
        deg_min = decimal_str.split(',')
        degrees = int(deg_min[0])  # degrees is the first part
        
        if len(deg_min) > 1:
            # Convert the decimal minutes part
            minutes_str = deg_min[1].replace(',', '.')  # handle any additional commas
            minutes_val = float(minutes_str)
            minutes = int(minutes_val)  # whole minutes
            seconds = round((minutes_val - minutes) * 60, 2)  # decimal part to seconds
            return f"{degrees} deg {minutes}' {seconds:.2f}\""
        else:
            return f"{degrees} deg 0' 0.00\""
            
    except Exception as e:
        log_message(f"Error converting coordinate: {e}")
        return decimal_str

def verify_metadata(file_path, expected_title, expected_keywords, expected_date, expected_caption=None, expected_location=None):
    """Verify metadata was written correctly."""
    verification_failed = False
    
    log_message("=== Starting Metadata Verification ===")
    
    try:
        verify_args = ['exiftool', '-s'] + VERIFY_FIELDS + [file_path]
        
        result = subprocess.run(verify_args, capture_output=True, text=True, check=True)
        output_lines = result.stdout.splitlines()
        
        # Verify title
        if expected_title:
            title_found = any(expected_title in line for line in output_lines if any(
                field.lstrip('-') in line for field in METADATA_FIELDS['title']
            ))
            if title_found:
                log_message(f"Found title: {expected_title}")
            else:
                log_message("△ Title mismatch")
                verification_failed = True

        # Verify keywords
        if expected_keywords:
            for line in output_lines:
                if 'Keywords' in line or 'Subject' in line:
                    log_message(f"Found keywords: {line}")
                    for keyword in expected_keywords:
                        if keyword not in line:
                            log_message(f"△ Missing keyword: {keyword}")
                            verification_failed = True

        # Verify date
        if expected_date:
            date_found = any(expected_date in line for line in output_lines if any(
                field.lstrip('-') in line for field in METADATA_FIELDS['date']
            ))
            if date_found:
                log_message(f"Found date: {expected_date}")
            else:
                log_message("△ Date mismatch")
                verification_failed = True

        # Verify caption
        if expected_caption:
            caption_found = any(expected_caption in line for line in output_lines if any(
                field.lstrip('-') in line for field in METADATA_FIELDS['caption']
            ))
            if caption_found:
                log_message(f"Found caption: {expected_caption}")
            else:
                log_message("△ Caption mismatch")
                verification_failed = True

        # Verify location data
        if expected_location and isinstance(expected_location, dict):
            # Handle regular location fields
            for key, fields in METADATA_FIELDS.items():
                if key in ['location', 'city', 'state', 'country'] and expected_location.get(key):
                    expected_value = expected_location[key]
                    field_found = any(
                        expected_value in line 
                        for line in output_lines 
                        for field_name in fields 
                        if field_name.lstrip('-') in line
                    )
                    if field_found:
                        log_message(f"Found {key}: {expected_value}")
                    else:
                        log_message(f"△ {key.title()} mismatch")
                        verification_failed = True
            
            # Handle GPS coordinates
            if expected_location.get('gps'):
                lat, lon = expected_location['gps']
                gps_found = any(
                    lat in line for line in output_lines if 'GPSLatitude' in line
                ) and any(
                    lon in line for line in output_lines if 'GPSLongitude' in line
                )
                if gps_found:
                    log_message(f"Found GPS coordinates: {lat}, {lon}")
                else:
                    log_message("△ GPS coordinates mismatch")
                    verification_failed = True

        log_message("=== Metadata Verification Complete ===")
        return not verification_failed

    except Exception as e:
        log_message(f"Error verifying metadata: {e}")
        log_message("=== Metadata Verification Failed ===")
        return False

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
    
    def add_metadata(self):
        """Main method to handle metadata operations."""
        try:
            video_date, xmp_title, keywords, tree, caption, date_time_original, location_data = get_metadata_from_xmp(self.file_path) or (None, None, [], None, None, None, None)
            
            # Format the title
            if xmp_title:
                display_title = xmp_title
                log_message(f"Using XMP title: {display_title}")
            else:
                base_name = os.path.splitext(os.path.basename(self.file_path))[0]
                if MCCARTYS_PREFIX in base_name:
                    display_title = base_name.replace(MCCARTYS_PREFIX, MCCARTYS_REPLACEMENT)
                    log_message("Converting 'The McCartys ' to 'The McCartys: ' in media file title")
                else:
                    display_title = base_name
                log_message(f"Using filename as title: {display_title}")
            
            # Start with base exiftool args
            exiftool_args = EXIFTOOL_BASE_ARGS.copy()
            
            # Add title
            for field in METADATA_FIELDS['title']:
                exiftool_args.append(f"{field}={display_title}")
            
            # Add date if available
            if date_time_original:
                for field in METADATA_FIELDS['date']:
                    exiftool_args.append(f"{field}={date_time_original}")
            
            # Add location data if available
            if location_data:
                for key, fields in METADATA_FIELDS.items():
                    if key in ['location', 'city', 'state', 'country'] and location_data.get(key):
                        for field in fields:
                            exiftool_args.append(f"{field}={location_data[key]}")
                
                # Handle GPS separately
                if location_data.get('gps'):
                    lat, lon = location_data['gps']
                    for field, value in zip(METADATA_FIELDS['gps'], [lat, lon]):
                        exiftool_args.append(f"{field}={value}")
            
            # Add keywords if available
            if keywords:
                keywords_str = ', '.join(keywords)
                exiftool_args.append(f"-Keywords={keywords_str}")
            
            # Add caption if available
            if caption:
                for field in METADATA_FIELDS['caption']:
                    exiftool_args.append(f"{field}={caption}")
            
            # Add the file path at the end
            exiftool_args.append(self.file_path)
            
            # Run exiftool
            log_message("Added metadata using exiftool:")
            log_message(f"  Title: {display_title}")
            if date_time_original:
                log_message(f"  Date: {date_time_original}")
            if keywords:
                log_message(f"  Keywords: {keywords}")
            if caption:
                log_message(f"  Caption: {caption}")
            if location_data:
                log_message("  Location data:")
                for key, value in location_data.items():
                    if value:
                        log_message(f"    {key}: {value}")
            
            subprocess.run(exiftool_args, check=True, capture_output=True, text=True)
            
            # Verify the metadata was written correctly
            if not verify_metadata(self.file_path, display_title, keywords, date_time_original, caption, location_data):
                log_message("Metadata verification failed")
                return None
            
            return {
                'title': display_title,
                'keywords': keywords,
                'date': date_time_original,
                'caption': caption,
                'location': location_data
            }
            
        except Exception as e:
            log_message(f"Error processing {os.path.basename(self.file_path)}: {e}")
            return None

def get_new_filename(file_path, title):
    """Generate new filename from title."""
    directory = os.path.dirname(file_path)
    ext = os.path.splitext(file_path)[1].lower()  # Preserve original extension
    clean_title = title
    for old, new in FILENAME_REPLACEMENTS.items():
        clean_title = clean_title.replace(old, new)
    new_name = f"{clean_title}{LRE_SUFFIX}{ext}"
    return os.path.join(directory, new_name)

def process_video(file_path):
    """Process a video file."""
    try:
        log_message(f"Found new McCartys video: {os.path.basename(file_path)}")
        
        # Check for both possible XMP locations
        xmp_paths = [
            os.path.splitext(file_path)[0] + ".xmp",  # Original filename XMP
            file_path + ".xmp"  # Full filename XMP
        ]
        xmp_exists = False
        found_xmp_path = None
        
        for xmp_path in xmp_paths:
            if os.path.exists(xmp_path):
                xmp_exists = True
                found_xmp_path = xmp_path
                break
        
        # Add metadata first
        metadata_result = VideoProcessor(file_path).add_metadata()
        if not metadata_result:
            log_message(f"Failed to add metadata to {os.path.basename(file_path)}")
            return False
            
        # Get the title for renaming
        title = metadata_result.get('title')
        if not title:
            log_message(f"No title found for {os.path.basename(file_path)}")
            return False
            
        # Generate new filename
        new_path = get_new_filename(file_path, title)
        new_xmp_path = new_path + ".xmp"
        
        # Rename video file
        os.rename(file_path, new_path)
        log_message(f"Renamed video to: {os.path.basename(new_path)}")
        
        # Handle XMP file if it exists
        if xmp_exists and found_xmp_path:
            try:
                # First try to rename it
                os.rename(found_xmp_path, new_xmp_path)
                log_message(f"Renamed XMP to: {os.path.basename(new_xmp_path)}")
                
                # Then remove it
                os.remove(new_xmp_path)
                log_message(f"Removed XMP file: {os.path.basename(new_xmp_path)}")
            except Exception as e:
                log_message(f"Error handling XMP file: {e}")
                # Continue even if XMP handling fails - we've already processed the video
            
        return True
        
    except Exception as e:
        log_message(f"Error processing video {os.path.basename(file_path)}: {e}")
        return False

def watch_folders(folder_paths):
    """Watch folders for new video files."""
    while True:
        try:
            found_files = False
            for folder in folder_paths:
                log_message(f"Checking {folder} for new video files...")
                for file in os.scandir(folder):
                    if (file.is_file() and 
                        file.name.lower().endswith(VIDEO_PATTERNS) and
                        "__LRE" not in file.name):  # Skip already processed files
                        found_files = True
                        process_video(file.path)
            
            if not found_files:
                time.sleep(SLEEP_TIME)
                
        except KeyboardInterrupt:
            log_message("Stopping video watch")
            break
        except Exception as e:
            log_message(f"Error in watch_folders: {e}")
            time.sleep(SLEEP_TIME)

if __name__ == "__main__":
    # Configure logging
    import logging
    logging.basicConfig(level=getattr(logging, LOG_LEVEL))
    
    # Start watching the folders
    watch_folders(WATCH_DIRS)
