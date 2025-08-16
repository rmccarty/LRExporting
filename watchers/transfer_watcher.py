#!/usr/bin/env python3

from pathlib import Path
import logging

from config import WATCH_DIRS, SLEEP_TIME
from transfers import Transfer

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
        # Extract title and caption to check for category format (enhanced logic)
        title = None
        caption = None
        if file_path.suffix.lower() in ['.jpg', '.jpeg']:
            try:
                from processors.jpeg_processor import JPEGExifProcessor
                processor = JPEGExifProcessor(str(file_path))
                _, title, _, _, _, _ = processor.get_metadata_components()
                self.logger.info(f"Extracted title: '{title}'")
                
                # Extract caption from EXIF data
                caption = self._extract_caption_from_exif(processor)
                self.logger.info(f"Extracted caption: '{caption}'")
                
            except Exception as e:
                self.logger.warning(f"Could not extract metadata from {file_path}: {e}")
        
        # Check if either title or caption has category format (contains colon) for Watching album
        has_title_category = title and ':' in title
        has_caption_category = caption and ':' in caption
        
        if has_title_category or has_caption_category:
            from config import APPLE_PHOTOS_WATCHING
            category_sources = []
            if has_title_category:
                category_sources.append(f"title: '{title}'")
            if has_caption_category:
                category_sources.append(f"caption: '{caption}'")
            
            self.logger.info(f"Category format detected in {', '.join(category_sources)} - importing to Apple Photos and adding to Watching album")
            # Import to Apple Photos with Watching album for further processing
            watching_album_path = str(APPLE_PHOTOS_WATCHING).rstrip('/')
            return self.transfer.transfer_file(file_path, album_paths=[watching_album_path])
        else:
            self.logger.info(f"No category format detected (title: '{title}', caption: '{caption}') - importing to Apple Photos only")
            # Import to Apple Photos without any specific album
            return self.transfer.transfer_file(file_path, album_paths=[])
    
    def _extract_caption_from_exif(self, processor) -> str:
        """
        Extract caption/description from EXIF data.
        
        Args:
            processor: JPEGExifProcessor instance with EXIF data loaded
            
        Returns:
            str: Caption text if found, None otherwise
        """
        try:
            # Ensure EXIF data is loaded
            if not processor.exif_data:
                processor.read_exif()
            
            # Try multiple EXIF fields for caption/description
            caption_fields = [
                'XMP:Description',
                'IPTC:Caption-Abstract', 
                'EXIF:ImageDescription',
                'XMP:Subject'
            ]
            
            for field in caption_fields:
                caption = processor.exif_data.get(field, '')
                if caption and isinstance(caption, str) and caption.strip():
                    self.logger.debug(f"Found caption in {field}: '{caption}'")
                    return caption.strip()
            
            self.logger.debug("No caption found in any EXIF fields")
            return None
            
        except Exception as e:
            self.logger.warning(f"Error extracting caption from EXIF: {e}")
            return None
        
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
