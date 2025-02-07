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
        return (None, None, [], None)  # Return tuple with default values
    
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
            
            # Look for title using exact XMP structure
            title_path = './/{http://purl.org/dc/elements/1.1/}title/{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Alt/{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li'
            title_elem = rdf.find(title_path)
            
            if title_elem is not None and title_elem.text:
                title = title_elem.text.strip()
                log_message(f"Found XMP title: '{title}'")
            else:
                log_message("No XMP title found in standard format")
            
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
            
            return (datetime.now(), title, keywords, tree)  # Return tuple
        else:
            return (None, None, [], None)  # Return tuple if no RDF found
            
    except Exception as e:
        log_message(f"Error reading XMP file: {e}")
        return (None, None, [], None)  # Return tuple on error

def add_metadata(file_path):
    # Try to get metadata from XMP - always unpack the tuple
    video_date, xmp_title, keywords, tree = get_metadata_from_xmp(file_path) or (None, None, [], None)
    
    # Use XMP title if available, otherwise generate from filename
    if xmp_title:
        title = xmp_title
        log_message(f"Found title in XMP metadata, adding to media file: {title}")
    else:
        title = os.path.splitext(os.path.basename(file_path))[0]
        title = title.replace("The McCartys ", "The McCartys: ")
        log_message(f"No title in XMP metadata, using filename as media title: {title}")
    
    try:
        # Write title using exiftool
        exiftool_args = [
            'exiftool',
            '-overwrite_original',  # Only needed for initial title write
            f'-title={title}',
            file_path
        ]
        
        # Run exiftool for title
        result = subprocess.run(exiftool_args, capture_output=True, text=True, check=True)
        log_message("Added title metadata using exiftool")
        
        # Add keywords one at a time
        if keywords:
            # Add each keyword to both Keywords and XMP:Subject
            for keyword in keywords:
                # Quote the keyword if it contains spaces
                quoted_keyword = f'"{keyword}"' if ' ' in keyword else keyword
                
                # Add to Keywords
                keyword_args = [
                    'exiftool',
                    f'-Keywords+={quoted_keyword}',
                    file_path
                ]
                result = subprocess.run(keyword_args, capture_output=True, text=True, check=True)
                log_message(f"Added Keyword: {keyword}")
                
                # Add to XMP:Subject using RDF Bag structure
                subject_args = [
                    'exiftool',
                    f'-XMP-dc:Subject-={quoted_keyword}',  # Remove if exists
                    f'-XMP-dc:Subject+={quoted_keyword}',  # Add to Bag
                    file_path
                ]
                result = subprocess.run(subject_args, capture_output=True, text=True, check=True)
                log_message(f"Added XMP:Subject: {keyword}")
        
        # Verify metadata
        log_message("\nVerifying metadata in saved file:")
        
        # Verify title
        verify_title = subprocess.run(['exiftool', '-title', file_path], 
                                    capture_output=True, text=True, check=True)
        log_message(verify_title.stdout.strip())
        
        # Verify both keyword formats
        verify_keywords = subprocess.run(['exiftool', '-Keywords', '-XMP-dc:Subject', file_path], 
                                       capture_output=True, text=True, check=True)
        log_message(verify_keywords.stdout.strip())
        
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