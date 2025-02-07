#!/usr/bin/env python3

# Requires: pip install mutagen
from mutagen.mp4 import MP4
import xml.etree.ElementTree as ET
import os
import time
from datetime import datetime

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
    video = MP4(file_path)
    
    # Try to get metadata from XMP - always unpack the tuple
    video_date, xmp_title, keywords, tree = get_metadata_from_xmp(file_path) or (None, None, [], None)
    
    if video_date:
        date_str = video_date.strftime('%Y-%m-%d %H:%M:%S')
        log_message(f"Using original video creation date: {date_str}")
    else:
        date_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_message(f"Original creation date not found, using current time: {date_str}")
    
    # Use XMP title if available, otherwise generate from filename
    if xmp_title:
        title = xmp_title
        log_message(f"Found title in XMP metadata, adding to media file: {title}")
    else:
        title = os.path.splitext(os.path.basename(file_path))[0]
        title = title.replace("The McCartys ", "The McCartys: ")
        log_message(f"No title in XMP metadata, using filename as media title: {title}")
    
    try:
        # Add metadata
        video["\xa9nam"] = title  # Title
        video["\xa9day"] = date_str  # Creation date
        
        # Add keywords using multiple standards
        if keywords:
            if isinstance(keywords, str):
                keywords = [keywords]
                
            # Write using Apple's standard
            video["\xa9key"] = keywords
            log_message(f"Added keywords using Apple format: {keywords}")
            
            try:
                # Try to write keywords in a simpler XMP format
                video["©xmp"] = [f"<keywords>{','.join(keywords)}</keywords>"]
                log_message(f"Added keywords using simplified XMP structure")
            except Exception as e:
                log_message(f"Warning: Could not write XMP metadata: {e}")
        
        video.save()
        
        # Verify keywords were written correctly
        log_message("\nVerifying metadata in saved file:")
        verify_video = MP4(file_path)
        
        # Check XMP format
        if "©xmp" in verify_video:
            xmp_content = verify_video["©xmp"]
            log_message(f"Found XMP metadata structure:")
            log_message(f"  {xmp_content}")
        else:
            log_message("No XMP metadata structure found in file")
            
        # Check Apple format
        if "\xa9key" in verify_video:
            saved_keywords_apple = verify_video["\xa9key"]
            log_message(f"Found Apple keywords (©key):")
            for kw in saved_keywords_apple:
                log_message(f"  - '{kw}'")
        else:
            log_message("No Apple keywords (©key) found in file")
        
    except Exception as e:
        log_message(f"Error processing {os.path.basename(file_path)}: {e}")
        raise

def process_video(file_path):
    try:
        log_message(f"Found new McCartys video: {os.path.basename(file_path)}")
        
        # Add metadata
        add_metadata(file_path)
        
        # Remove XMP sidecar file if it exists
        xmp_path = os.path.splitext(file_path)[0] + ".xmp"
        if os.path.exists(xmp_path):
            os.remove(xmp_path)
            log_message(f"Removed XMP file: {os.path.basename(xmp_path)}")
        
        # Rename with "__LRE" suffix
        directory = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        base, ext = os.path.splitext(filename)
        new_filename = f"{base}__LRE{ext}"
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