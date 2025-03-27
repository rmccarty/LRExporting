#!/usr/bin/env python3

from pathlib import Path
import sys
from PIL import Image
import subprocess
import logging

from config import JPEG_QUALITY, JPEG_COMPRESS
from processors.media_processor import MediaProcessor

class JPEGExifProcessor(MediaProcessor):
    """A class to process JPEG images and their EXIF data using exiftool."""
    
    def __init__(self, input_path: str, output_path: str = None, sequence: str = None):
        """
        Initialize the JPEG processor with input and output paths.
        Validates file type and username requirements.
        
        Args:
            input_path (str): Path to input JPEG file
            output_path (str): Optional path for output file. If None, will use input directory
            sequence (str): Optional sequence number for filename
        """
        super().__init__(input_path, sequence=sequence)
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
            
    def compress_image(self) -> bool:
        """
        Compress JPEG image while preserving metadata.
        
        Uses Pillow for compression and exiftool to preserve metadata.
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create temporary file for compressed image
            temp_path = self.file_path.with_stem(self.file_path.stem + '_temp')
            
            # Open and compress image
            with Image.open(self.file_path) as img:
                # Convert to RGB if needed (some JPEGs can be RGBA)
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                    
                # Save compressed image to temporary file
                img.save(temp_path, 'JPEG', quality=JPEG_QUALITY, optimize=True)
                
            # Copy metadata from original to compressed file
            if not self.exiftool.copy_metadata(self.file_path, temp_path):
                self.logger.error("Failed to copy metadata to compressed file")
                if temp_path.exists():
                    temp_path.unlink()
                return False
                
            # Replace original with compressed file
            temp_path.replace(self.file_path)
            self.logger.info(f"Compressed image saved to: {self.file_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error compressing image: {e}")
            if temp_path.exists():
                temp_path.unlink()
            return False
            
    def get_metadata_components(self):
        """Get metadata components for JPEG files."""
        # Read EXIF data if not already read
        if not self.exif_data:
            self.read_exif()
            
        # Extract date
        date_str = None
        for key in self.exif_data:
            if key.endswith(':DateTimeOriginal'):
                date_str = self.exif_data[key]
                # Convert YYYY:MM:DD HH:MM:SS to YYYY_MM_DD
                if date_str:
                    try:
                        date_parts = date_str.split(' ')[0].split(':')
                        date_str = '_'.join(date_parts)
                    except Exception as e:
                        self.logger.error(f"Error parsing date: {e}")
                        date_str = None
                break
                
        # Get title and location data
        title = self.get_exif_title()
        location, city, country = self.get_location_data()
        
        return date_str, title, location, city, country
        
    def process_image(self) -> Path:
        """
        Main method to process an image - reads EXIF, updates keywords and title, and renames file.
        
        Returns:
            Path: Path to the processed file
        """
        # Skip if already processed
        if self.file_path.stem.endswith('__LRE'):
            self.logger.info(f"Skipping already processed file: {self.file_path}")
            return self.file_path
            
        # Read EXIF data
        self.read_exif()
        
        # Set the title only if one doesn't exist
        title = self.get_exif_title()
        if title and not self.exif_data.get('Title'):
            try:
                cmd = ['exiftool', '-overwrite_original',
                      '-Title=' + title,
                      '-XPTitle=' + title,
                      '-XMP:Title=' + title,
                      '-IPTC:ObjectName=' + title,
                      '-IPTC:Headline=' + title,
                      str(self.file_path)]
                result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                self.logger.info(f"Title set to: {title}")
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Error setting title: {e.stderr}")
                raise
            
        # Update keywords and compress if needed
        self.update_keywords_with_rating_and_export_tags()
        if JPEG_COMPRESS:
            self.compress_image()
            
        # Rename the file
        return self.rename_file()
