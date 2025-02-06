#!/usr/bin/env python3

from pathlib import Path
import subprocess
import json
import logging
import sys
from datetime import datetime
import shutil

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
            SystemExit: If file is not JPEG or username cannot be extracted
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
            
        # Validate username in original filename
        try:
            original_name = self.input_path.stem
            if '_' not in original_name:
                self.logger.error(f"Original filename must contain username followed by underscore. Found: {original_name}")
                sys.exit(1)
            
            username = original_name.split('_')[0]
            if not username:
                self.logger.error("Username cannot be empty")
                sys.exit(1)
                
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
            
            # Create exiftool command to update keywords
            cmd = ['exiftool', '-overwrite_original']
            for keyword in keywords:
                cmd.append(f'-keywords={keyword}')
            cmd.append(str(self.input_path))
            
            subprocess.run(cmd, check=True, capture_output=True)
            self.logger.info(f"Updated keywords with rating: {rating_keyword}")
            if 'Export_Claudia' in keywords:
                self.logger.info("Added Export_Claudia keyword")
            self.logger.info(f"Added export keywords: Lightroom_Export, {export_date_keyword}")
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error updating keywords: {e.stderr}")
            raise
            
    def get_username_from_original(self) -> str:
        """
        Extract username from original filename (characters before first underscore).
        
        Returns:
            str: Username from original filename
        """
        original_name = self.input_path.stem  # Get filename without extension
        return original_name.split('_')[0]

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
        title = self.get_exif_title()
        _, city, country = self.get_location_data()
        
        if title:
            components.append(title.replace(' ', '_'))
        if city:
            components.append(city.replace(' ', '_'))
        if country:
            components.append(country.replace(' ', '_'))
            
        # Get username from original filename
        username = self.get_username_from_original()
        
        # Add user and LRE tags
        base_name = '_'.join(components)
        filename = f"{base_name}_{username}__LRE.jpg"
        
        # Replace any slashes in the final filename
        return filename.replace('/', '-').replace('\\', '-')
        
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

if __name__ == "__main__":
    import time
    from pathlib import Path
    
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    # Get user's Downloads directory
    if sys.platform == "win32":
        WATCH_DIR = Path.home() / "Downloads"
    elif sys.platform == "darwin":  # macOS
        WATCH_DIR = Path.home() / "Downloads"
    else:  # Linux and others
        WATCH_DIR = Path.home() / "Downloads"
    
    # List of allowed filename prefixes
    ALLOWED_PREFIXES = ['ron_', 'claudia_', 'both_']
    
    logger.info(f"Watching directory: {WATCH_DIR}")
    
    while True:
        try:
            found_files = False
            # Find all JPEG files
            for file in WATCH_DIR.glob('*.[Jj][Pp][Gg]'):
                # Handle both_ files first
                if file.name.lower().startswith('both_'):
                    found_files = True
                    logger.info(f"Found 'both_' file to process: {file}")
                    
                    # Create base names with new prefixes
                    ron_name = file.name.replace('both_', 'ron_', 1)
                    claudia_name = file.name.replace('both_', 'claudia_', 1)
                    
                    try:
                        # Handle ron_ file
                        ron_path = file.parent / ron_name
                        counter = 1
                        while ron_path.exists():
                            name_parts = ron_name.rsplit('.', 1)
                            ron_path = file.parent / f"{name_parts[0]}_{counter:03d}.{name_parts[1]}"
                            counter += 1
                            
                        # Handle claudia_ file
                        claudia_path = file.parent / claudia_name
                        counter = 1
                        while claudia_path.exists():
                            name_parts = claudia_name.rsplit('.', 1)
                            claudia_path = file.parent / f"{name_parts[0]}_{counter:03d}.{name_parts[1]}"
                            counter += 1
                        
                        # Copy files with final names
                        shutil.copy2(file, ron_path)
                        shutil.copy2(file, claudia_path)
                        logger.info(f"Created copies: {ron_path.name} and {claudia_path.name}")
                        
                        # Delete the original both_ file
                        file.unlink()
                        logger.info(f"Deleted original file: {file.name}")
                        
                    except Exception as e:
                        logger.error(f"Error creating copies: {e}")
                    continue
                
                # Process ron_ and claudia_ files
                if file.name.lower().startswith(('ron_', 'claudia_')):
                    found_files = True
                    logger.info(f"Found file to process: {file}")
                    
                    # Process the image
                    processor = JPEGExifProcessor(str(file))
                    try:
                        new_path = processor.process_image()
                        logger.info(f"Image processed successfully: {new_path}")
                    except Exception as e:
                        logger.error(f"Error processing image: {e}")
            
            # Only sleep if no files were found
            if not found_files:
                time.sleep(3)
                
        except KeyboardInterrupt:
            logger.info("Stopping directory watch")
            break
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            time.sleep(3)  # Sleep before retrying