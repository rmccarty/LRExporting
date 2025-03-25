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
    XML_NAMESPACES
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
    xmp_path = os.path.splitext(file_path)[0] + ".xmp"
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
        verify_args = [
            'exiftool',
            '-s',
            '-DisplayName',
            '-Title',
            '-ItemList:Title',
            '-Keywords',
            '-Subject',
            '-DateTimeOriginal',
            '-Location',
            '-LocationName',
            '-City',
            '-State',
            '-Country',
            '-GPSLatitude',
            '-GPSLongitude',
            '-Description',
            '-Caption-Abstract',
            file_path
        ]
        
        result = subprocess.run(verify_args, capture_output=True, text=True, check=True)
        output_lines = result.stdout.splitlines()
        
        # Verify title
        if expected_title:
            title_found = any(expected_title in line for line in output_lines if 'Title' in line or 'DisplayName' in line)
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
            date_found = any(expected_date in line for line in output_lines if 'DateTimeOriginal' in line)
            if date_found:
                log_message(f"Found date: {expected_date}")
            else:
                log_message("△ Date mismatch")
                verification_failed = True

        # Verify caption
        if expected_caption:
            caption_found = any(expected_caption in line for line in output_lines if 'Description' in line or 'Caption-Abstract' in line)
            if caption_found:
                log_message(f"Found caption: {expected_caption}")
            else:
                log_message("△ Caption mismatch")
                verification_failed = True

        # Verify location data
        if expected_location and isinstance(expected_location, dict):
            location_fields = {
                'location': ['Location', 'LocationName'],
                'city': ['City'],
                'state': ['State'],
                'country': ['Country']
            }
            
            # Handle regular location fields
            for field, exiftool_fields in location_fields.items():
                if expected_location.get(field):
                    expected_value = expected_location[field]
                    field_found = any(
                        expected_value in line 
                        for line in output_lines 
                        for field_name in exiftool_fields 
                        if field_name in line
                    )
                    if field_found:
                        log_message(f"Found {field}: {expected_value}")
                    else:
                        log_message(f"△ {field.title()} mismatch")
                        verification_failed = True

            # Special handling for GPS
            if expected_location.get('gps'):
                gps_found = False
                expected_gps = expected_location['gps']
                
                # Log the raw expected format first
                log_message(f"Expected GPS (raw): {expected_gps}")
                
                # Get actual values
                gps_lines = [line for line in output_lines if 'GPS' in line]
                actual_lat = next((line.split(': ')[1] for line in gps_lines if 'Latitude ' in line), 'Not found')
                actual_lon = next((line.split(': ')[1] for line in gps_lines if 'Longitude ' in line), 'Not found')
                
                # Log actual values
                log_message(f"Actual GPS (DMS): {actual_lat}, {actual_lon}")
                
                # Only convert expected to DMS if needed for comparison
                if 'deg' in actual_lat:
                    # Parse expected coordinates
                    lat, lon = expected_gps.split(', ')
                    lat_val = lat.rstrip('N').rstrip('S')
                    lon_val = lon.rstrip('E').rstrip('W')
                    
                    # Convert to DMS format for comparison
                    expected_lat_dms = f"{convert_decimal_to_dms(lat_val)} N"
                    expected_lon_dms = f"{convert_decimal_to_dms(lon_val)} E"
                    
                    log_message(f"Expected GPS (DMS): {expected_lat_dms}, {expected_lon_dms}")
                    
                    if actual_lat.strip() == expected_lat_dms and actual_lon.strip() == expected_lon_dms:
                        log_message("✓ GPS coordinates verified (DMS format)")
                        gps_found = True
                else:
                    # Compare raw formats
                    if f"{actual_lat}, {actual_lon}" == expected_gps:
                        log_message("✓ GPS coordinates verified (raw format)")
                        gps_found = True
                
                if not gps_found:
                    log_message("△ GPS coordinates mismatch")
                    verification_failed = True

        log_message("=== Metadata Verification Complete ===")
        if verification_failed:
            log_message("△ Some metadata verification failed")
        else:
            log_message("✓ All metadata verification passed")
        return not verification_failed

    except Exception as e:
        log_message(f"Error verifying metadata: {e}")
        log_message("=== Metadata Verification Failed ===")
        return False

def add_metadata(file_path):
    """Main function to handle metadata operations."""
    video_date, xmp_title, keywords, tree, caption, date_time_original, location_data = get_metadata_from_xmp(file_path) or (None, None, [], None, None, None, None)
    
    try:
        # Format the title
        if xmp_title:
            display_title = xmp_title
            log_message(f"Using XMP title: {display_title}")
        else:
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            if "The McCartys " in base_name:
                display_title = base_name.replace("The McCartys ", "The McCartys: ")
                log_message("Converting 'The McCartys ' to 'The McCartys: ' in media file title")
            else:
                display_title = base_name
            log_message(f"Using filename as title: {display_title}")
        
        # Build exiftool command
        exiftool_args = [
            'exiftool',
            '-overwrite_original',
            '-handler=mdta',
            f'-Title={display_title}',
            f'-DisplayName={display_title}',
            f'-ItemList:Title={display_title}'
        ]
        
        # Add keywords if present
        if keywords:
            keywords_string = ", ".join(keywords)
            exiftool_args.extend([
                f'-Keywords={keywords_string}',
                f'-Subject={keywords_string}'
            ])
        
        # Add caption if present
        if caption:
            exiftool_args.extend([
                f'-Description={caption}',
                f'-Caption-Abstract={caption}'
            ])
        
        # Add location data if present
        if location_data:
            if location_data.get('location'):
                exiftool_args.extend([
                    f'-LocationName={location_data["location"]}',
                    f'-Location={location_data["location"]}'
                ])
            if location_data.get('city'):
                exiftool_args.append(f'-City={location_data["city"]}')
            if location_data.get('state'):
                exiftool_args.append(f'-State={location_data["state"]}')
            if location_data.get('country'):
                exiftool_args.append(f'-Country={location_data["country"]}')
            if location_data.get('gps'):
                # Parse GPS coordinates
                lat, lon = location_data['gps'].split(', ')
                lat_val = lat.rstrip('N').rstrip('S')
                lon_val = lon.rstrip('E').rstrip('W')
                lat_ref = 'N' if 'N' in lat else 'S'
                lon_ref = 'E' if 'E' in lon else 'W'
                
                # Add GPS metadata in format that Apple Photos recognizes
                exiftool_args.extend([
                    '-api', 'QuickTimeUTC',  # Ensure proper GPS format
                    f'-GPSCoordinates={lat_val}"{lat_ref},{lon_val}"{lon_ref}',
                    f'-GPSLatitude={lat_val}',
                    f'-GPSLatitudeRef={lat_ref}',
                    f'-GPSLongitude={lon_val}',
                    f'-GPSLongitudeRef={lon_ref}',
                    '-XMP:GPSLatitude=' + lat_val,
                    '-XMP:GPSLongitude=' + lon_val,
                    '-XMP:GPSLatitudeRef=' + lat_ref,
                    '-XMP:GPSLongitudeRef=' + lon_ref
                ])
                log_message(f"Adding GPS coordinates in Apple Photos format: {lat_val}{lat_ref}, {lon_val}{lon_ref}")
        
        # Add date if present
        if date_time_original:
            exiftool_args.extend([
                f'-DateTimeOriginal={date_time_original}',
                f'-CreateDate={date_time_original}',
                f'-MediaCreateDate={date_time_original}',
                f'-TrackCreateDate={date_time_original}',
                f'-MediaModifyDate={date_time_original}',
                f'-TrackModifyDate={date_time_original}'
            ])
        
        # Add the file path
        exiftool_args.append(file_path)
        
        # Run exiftool
        result = subprocess.run(exiftool_args, capture_output=True, text=True, check=True)
        
        # Log what was written
        log_message("Added metadata using exiftool:")
        log_message(f"  Title: {display_title}")
        if keywords:
            log_message(f"  Keywords: {keywords_string}")
        if date_time_original:
            log_message(f"  Date: {date_time_original}")
        if caption:
            log_message(f"  Caption: {caption}")
        if location_data:
            log_message("  Location data:")
            for key, value in location_data.items():
                if value:
                    log_message(f"    {key}: {value}")
        
        # Verify metadata with full location data
        if not verify_metadata(file_path, display_title, keywords, date_time_original, caption, location_data):
            log_message("△ Some metadata verification failed")
        
        # Delete the source XMP file after successful processing
        xmp_source = file_path.rsplit('.', 1)[0] + '.xmp'
        if os.path.exists(xmp_source):
            os.remove(xmp_source)
            log_message(f"Removed XMP file: {os.path.basename(xmp_source)}")
        
    except Exception as e:
        log_message(f"Error processing {os.path.basename(file_path)}: {e}")
        raise

def get_new_filename(file_path, title):
    """Generate new filename from title."""
    directory = os.path.dirname(file_path)
    ext = os.path.splitext(file_path)[1].lower()  # Preserve original extension
    
    # Clean title for filename
    clean_title = title.replace(':', ' -').replace('/', '_')
    new_name = f"{clean_title}__LRE{ext}"  # Will work with .m4v
    return os.path.join(directory, new_name)

def process_video(file_path):
    try:
        log_message(f"Found new McCartys video: {os.path.basename(file_path)}")
        
        # Add metadata
        add_metadata(file_path)
        
        # Rename with "__LRE" suffix (two underscores before LRE)
        directory = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        base, ext = os.path.splitext(filename)
        new_filename = f"{base}___LRE{ext}"  # Three underscores here to get two in final name
        new_path = os.path.join(directory, new_filename)
        
        os.rename(file_path, new_path)
        log_message(f"Renamed to: {new_filename}")
        
        return True
        
    except Exception as e:
        log_message(f"Error processing {os.path.basename(file_path)}: {e}")
        return False

def watch_folders(folder_paths):
    """Watch folders for new video files."""
    while True:
        try:
            found_files = False
            for folder in folder_paths:
                log_message(f"Checking {folder} for new video files...")
                for file in os.scandir(folder):
                    if file.is_file() and file.name.lower().endswith(VIDEO_PATTERNS):
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
