#!/usr/bin/env python3

# Requires: pip install mutagen
from mutagen.mp4 import MP4
import xml.etree.ElementTree as ET
import os
import time
from datetime import datetime
import subprocess

def log_message(message):
    """Log a message with timestamp."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}")

def get_metadata_from_xmp(file_path):
    """Get metadata from XMP sidecar file."""
    xmp_path = os.path.splitext(file_path)[0] + ".xmp"
    if not os.path.exists(xmp_path):
        log_message(f"No XMP file found for: {os.path.basename(file_path)}")
        return (None, None, [], None, None)  # Added None for caption
    
    try:
        # Parse XMP file
        log_message(f"Reading metadata from XMP file: {os.path.basename(xmp_path)}")
        tree = ET.parse(xmp_path)
        root = tree.getroot()
        
        log_message(f"XMP root tag: {root.tag}")
        
        # Look for RDF inside xmpmeta
        rdf = root.find('.//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF')
        if rdf is not None:
            log_message("Found RDF data in XMP")
            title = None
            keywords = []
            creation_date = None
            caption = None
            
            # Look for title using exact XMP structure
            title_path = './/{http://purl.org/dc/elements/1.1/}title/{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Alt/{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li'
            title_elem = rdf.find(title_path)
            
            if title_elem is not None and title_elem.text:
                title = title_elem.text.strip()
                log_message(f"Found XMP title: '{title}'")
            else:
                log_message("No XMP title found in standard format")
            
            # Look for caption/description
            description_path = './/{http://purl.org/dc/elements/1.1/}description/{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Alt/{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li'
            description_elem = rdf.find(description_path)
            
            if description_elem is not None and description_elem.text:
                caption = description_elem.text.strip()
                log_message(f"Found XMP caption: '{caption}'")
            else:
                log_message("No XMP caption found")
            
            # Look for keywords in all possible formats
            log_message("Looking for keywords in XMP metadata...")
            
            # Try dc:subject/rdf:Seq format
            keyword_path_seq = './/{http://purl.org/dc/elements/1.1/}subject/{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Seq/{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li'
            seq_keywords = rdf.findall(keyword_path_seq)
            if seq_keywords:
                log_message("Found keywords in dc:subject/rdf:Seq format:")
                for keyword_elem in seq_keywords:
                    if keyword_elem.text and keyword_elem.text.strip():
                        keywords.append(keyword_elem.text.strip())
                        log_message(f"  - '{keyword_elem.text.strip()}'")
            
            # Try dc:subject/rdf:Bag format
            keyword_path_bag = './/{http://purl.org/dc/elements/1.1/}subject/{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Bag/{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li'
            bag_keywords = rdf.findall(keyword_path_bag)
            if bag_keywords:
                log_message("Found keywords in dc:subject/rdf:Bag format:")
                for keyword_elem in bag_keywords:
                    if keyword_elem.text and keyword_elem.text.strip():
                        if keyword_elem.text.strip() not in keywords:  # Avoid duplicates
                            keywords.append(keyword_elem.text.strip())
                            log_message(f"  - '{keyword_elem.text.strip()}'")
            
            # Try direct dc:subject format
            keyword_path_direct = './/{http://purl.org/dc/elements/1.1/}subject'
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
            
            return (datetime.now(), title, keywords, tree, caption)  # Added caption to return tuple
        else:
            return (None, None, [], None, None)  # Added None for caption
            
    except Exception as e:
        log_message(f"Error reading XMP file: {e}")
        return (None, None, [], None, None)  # Added None for caption

def add_metadata(file_path):
    # Try to get metadata from XMP - always unpack the tuple
    video_date, xmp_title, keywords, tree, caption = get_metadata_from_xmp(file_path) or (None, None, [], None, None)
    
    try:
        if keywords:  # If we have keywords to add
            keywords_string = ", ".join(keywords)
            
            # Format the title - if using filename and contains "The McCartys ", replace with "The McCartys: "
            if not xmp_title:  # If we're using the filename
                base_name = os.path.splitext(os.path.basename(file_path))[0]
                if "The McCartys " in base_name:
                    display_title = base_name.replace("The McCartys ", "The McCartys: ")
                    log_message("Converting 'The McCartys ' to 'The McCartys: ' in media file title")
                else:
                    display_title = base_name
            else:
                display_title = xmp_title
            
            # Build exiftool command using ItemList format
            exiftool_args = [
                'exiftool',
                '-overwrite_original',
                '-handler=mdta',  # Use mdta handler
                f'-DisplayName={display_title}',
                f'-Subject={keywords_string}',
                f'-Keywords={keywords_string}',
                f'-ItemList:Title={display_title}'
            ]
            
            # Add caption if it exists
            if caption:
                exiftool_args.extend([
                    f'-Description={caption}',
                    f'-Caption-Abstract={caption}'
                ])
            
            # Add the file path at the end
            exiftool_args.append(file_path)
            
            # Run exiftool
            result = subprocess.run(exiftool_args, capture_output=True, text=True, check=True)
            log_message("Added ItemList metadata using exiftool")
            log_message("Verifying metadata in saved file:")
            
            # Verify metadata using QuickTime format
            verify_args = [
                'exiftool',
                '-s3',
                '-DisplayName',
                '-Keywords',
                '-Description',  # Added Description to verification
                file_path
            ]
            result = subprocess.run(verify_args, capture_output=True, text=True, check=True)
            if result.stdout:
                lines = result.stdout.strip().splitlines()
                if lines:
                    log_message(f"Title: {lines[0]}")
                    if len(lines) > 1:
                        log_message(f"Keywords: {lines[1]}")
                    if len(lines) > 2 and caption:
                        log_message(f"Caption: {lines[2]}")
            else:
                log_message("No metadata found in verification")
            
            # Delete the source XMP file after successful processing
            xmp_source = file_path.rsplit('.', 1)[0] + '.xmp'
            if os.path.exists(xmp_source):
                os.remove(xmp_source)
                log_message(f"Removed XMP file: {os.path.basename(xmp_source)}")
            
    except Exception as e:
        log_message(f"Error processing {os.path.basename(file_path)}: {e}")
        raise

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

def watch_folder(folder_path):
    while True:
        try:
            # Look for video files
            for filename in os.listdir(folder_path):
                if "The McCartys" in filename and not "__LRE" in filename and filename.lower().endswith(('.mov', '.mp4')):
                    file_path = os.path.join(folder_path, filename)
                    
                    # Process the video
                    if process_video(file_path):
                        log_message(f"Successfully processed: {filename}")
                    
            time.sleep(1)  # Wait before checking again
            
        except Exception as e:
            log_message(f"Error in watch loop: {e}")
            time.sleep(1)  # Wait before retrying

if __name__ == "__main__":
    downloads_folder = os.path.expanduser("~/Downloads")
    log_message("Watching Downloads folder for 'The McCartys' video files...")
    watch_folder(downloads_folder)