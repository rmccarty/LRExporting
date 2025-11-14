#!/usr/bin/env python3

from pathlib import Path
import sys
import subprocess
import logging
import time

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
        except Exception as e:
            self.logger.error(f"Error validating filename: {str(e)}")
            sys.exit(1)
            
    def get_metadata_components(self):
        """Get metadata components for JPEG files."""
        # Read EXIF data if not already read
        if not self.exif_data:
            self.read_exif()
            
        # Extract date
        date_str = None
        for key in self.exif_data:
            if key.endswith(':DateTimeOriginal'):
                raw_date = self.exif_data[key]
                # Convert YYYY:MM:DD HH:MM:SS to YYYY_MM_DD
                if raw_date and ' ' in raw_date:  # Must have space between date and time
                    try:
                        date_parts = raw_date.split(' ')[0].split(':')
                        if len(date_parts) == 3:  # Must have year, month, day
                            date_str = '_'.join(date_parts)
                        else:
                            self.logger.error(f"Invalid date format: {raw_date}")
                            date_str = None
                    except Exception as e:
                        self.logger.error(f"Error parsing date: {e}")
                        date_str = None
                break
                
        # Get title and location data
        title = self.get_exif_title()
        location, city, state, country = self.get_location_data()
        self.logger.info(f"Extracted city from EXIF: {city}")
        self.logger.info(f"Extracted state from EXIF: {state}")
        
        return date_str, title, location, city, state, country
    
    def _validate_file_ready(self) -> bool:
        """
        Validate that the file is ready for processing (not zero bytes and stable).
        
        Returns:
            bool: True if file is ready, False otherwise
        """
        try:
            # Check if file exists
            if not self.file_path.exists():
                return False
            
            # Check initial file size
            initial_size = self.file_path.stat().st_size
            if initial_size == 0:
                self.logger.warning(f"File is zero bytes: {self.file_path}")
                return False
            
            # Wait a short time and check size again to ensure file writing is complete
            time.sleep(0.1)
            
            # Check if file still exists (might have been moved/deleted)
            if not self.file_path.exists():
                return False
                
            final_size = self.file_path.stat().st_size
            
            # If size changed, file might still be writing
            if initial_size != final_size:
                self.logger.warning(f"File size changed during validation: {self.file_path} ({initial_size} -> {final_size})")
                return False
                
            # Additional check - ensure file is at least 1KB (minimum viable JPEG)
            if final_size < 1024:
                self.logger.warning(f"File too small to be valid JPEG: {self.file_path} ({final_size} bytes)")
                return False
                
            return True
            
        except (OSError, IOError) as e:
            self.logger.error(f"Error validating file: {self.file_path} - {e}")
            return False
        
    def process_image(self) -> Path:
        """
        Main method to process an image - reads EXIF and renames file.
        
        Returns:
            Path: Path to the processed file
        """
        # Skip if already processed
        if self.file_path.stem.endswith('__LRE'):
            self.logger.info(f"Skipping already processed file: {self.file_path}")
            return self.file_path
        
        # Validate file is not zero bytes and is complete
        if not self._validate_file_ready():
            self.logger.warning(f"File not ready for processing: {self.file_path}")
            raise ValueError(f"File not ready for processing: {self.file_path}")
            
        # Read EXIF data for filename generation
        self.read_exif()
            
        # Rename the file
        return self.rename_file()
