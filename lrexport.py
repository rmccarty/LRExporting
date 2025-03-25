#!/usr/bin/env python3

from pathlib import Path
import subprocess
import json
import logging
import sys
from datetime import datetime
import shutil
import time
from config import WATCH_DIRS, BOTH_INCOMING, LOG_LEVEL, SLEEP_TIME

class JPEGExifProcessor:
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
        self.input_path = Path(input_path)
        self.output_path = (Path(output_path) if output_path 
                          else self.input_path.parent)
        self.exif_data = {}
        self.logger = logging.getLogger(__name__)
        
        # Verify exiftool is available
        if not shutil.which('exiftool'):
            self.logger.error("exiftool is not installed or not in PATH")
            sys.exit(1)
            
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
            
    def read_exif(self) -> dict:
        """
        Read EXIF data from the JPEG file using exiftool.
        
        Returns:
            dict: Dictionary containing the EXIF data
        """
        try:
            cmd = ['exiftool', '-j', '-n', str(self.input_path)]
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
            if (self.input_path.stem.lower().startswith('claudia_') and 
                'Export_Claudia' not in keywords):
                keywords.append('Export_Claudia')
            
            # Add Lightroom export keywords
            keywords.append('Lightroom_Export')
            keywords.append(export_date_keyword)
            
            # Create exiftool command to update keywords - use a single -keywords argument
            cmd = ['exiftool', '-overwrite_original', f'-keywords={",".join(keywords)}', str(self.input_path)]
            
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
            new_path = self.output_path / new_filename
            
            # Handle duplicates
            counter = 1
            while new_path.exists():
                date_part, rest = new_filename.split('_', 1)
                new_path = self.output_path / f"{date_part}-{counter:03d}_{rest}"
                counter += 1
                
            # Use exiftool to copy the file with metadata
            cmd = [
                'exiftool',
                '-overwrite_original',
                '-all:all',  # Preserve all metadata
                f'-filename={new_path}',
                str(self.input_path)
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
                      str(self.input_path)]
                result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                self.logger.info(f"Title set to: {title}")
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Error setting title: {e.stderr}")
                raise
            
        self.update_keywords_with_rating_and_export_tags()
        return self.rename_file()

class DirectoryWatcher:
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
        self.watch_dirs = [Path(d) for d in watch_dirs]
        self.both_incoming = Path(both_incoming_dir) if both_incoming_dir else None
        self.logger = logging.getLogger(__name__)
        self.sleep_time = SLEEP_TIME
    
    def process_both_incoming(self):
        """Check Both_Incoming directory and copy files to individual incoming directories."""
        if not self.both_incoming:
            return False
            
        found_files = False
        try:
            # Iterate through all files in the Both_Incoming directory
            for file in self.both_incoming.glob('*'):
                # Check if the file is open
                try:
                    with open(file, 'r+'):
                        pass  # File is not open, proceed to copy
                except IOError:
                    self.logger.warning(f"File {file.name} is currently open. Skipping copy.")
                    continue  # Skip to the next file
                
                found_files = True
                # Copy the file to all incoming directories
                for incoming_dir in self.watch_dirs:
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
    
    def watch_directories(self):
        """Main loop to watch directories for new files."""
        self.logger.info(f"Watching directories: {', '.join(str(dir) for dir in self.watch_dirs)}")
        if self.both_incoming:
            self.logger.info(f"Also watching {self.both_incoming} for files to copy to both directories")
        
        while True:
            try:
                found_files = self.process_both_incoming()  # Check Both_Incoming first
                
                # Iterate through each directory
                for watch_dir in self.watch_dirs:
                    self.logger.info(f"\nChecking {watch_dir} for new files...")
                    for file in watch_dir.glob('*.[Jj][Pp][Gg]'):
                        self.process_file(file)
                        found_files = True
                
                # Only sleep if no files were found
                if not found_files:
                    time.sleep(self.sleep_time)
                    
            except KeyboardInterrupt:
                self.logger.info("Stopping directory watch")
                break
            except Exception as e:
                self.logger.error(f"Unexpected error: {e}")

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=getattr(logging, LOG_LEVEL))
    
    # Initialize and start the watcher
    watcher = DirectoryWatcher(
        watch_dirs=WATCH_DIRS,
        both_incoming_dir=BOTH_INCOMING
    )
    
    watcher.watch_directories()