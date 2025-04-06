#!/usr/bin/env python3

import subprocess
import json
import logging
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Union, Optional, Tuple

class ExifTool:
    """Wrapper for exiftool operations."""
    
    def __init__(self):
        """Initialize ExifTool wrapper."""
        self.logger = logging.getLogger(__name__)
        
        # Verify exiftool is available
        if not shutil.which('exiftool'):
            self.logger.error("exiftool is not installed or not in PATH")
            sys.exit(1)
            
        self.default_flags = ['-overwrite_original']
        self.date_format = '%Y:%m:%d %H:%M:%S'
        
    def read_all_metadata(self, file_path: Union[str, Path]) -> Dict:
        """
        Read all metadata from a file using exiftool.
        
        Args:
            file_path: Path to the file
            
        Returns:
            dict: Dictionary containing all metadata
        """
        try:
            cmd = ['exiftool', '-j', '-m', '-G', str(file_path)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                self.logger.error(f"Error reading metadata: {result.stderr}")
                return {}
                
            data = json.loads(result.stdout)
            if not data:
                return {}
                
            # Convert any non-string values to strings
            metadata = data[0]
            for key, value in metadata.items():
                if isinstance(value, list):
                    metadata[key] = [str(item) for item in value]
                elif not isinstance(value, str):
                    metadata[key] = str(value)
                
            return metadata
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error reading metadata: {e}")
            return {}
        except json.JSONDecodeError as e:
            self.logger.error(f"Error parsing metadata: {e}")
            return {}
            
    def read_date_from_xmp(self, file_path: Union[str, Path]) -> Optional[str]:
        """
        Read DateTimeOriginal from XMP file.
        
        Args:
            file_path: Path to XMP file
            
        Returns:
            str: Date in YYYY:MM:DD HH:MM:SS format, or None if not found
        """
        try:
            cmd = [
                'exiftool',
                '-s',
                '-d', self.date_format,
                '-DateTimeOriginal',
                str(file_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            if result.stdout:
                date_line = result.stdout.strip()
                if ': ' in date_line:
                    return date_line.split(': ')[1].strip()
            return None
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error reading date from XMP: {e}")
            return None
            
    def write_metadata(self, file_path: Union[str, Path], fields: Dict[str, str]) -> bool:
        """
        Write metadata fields to a file.
        
        Args:
            file_path: Path to the file
            fields: Dictionary of field names and values to write. Field names can include leading dash.
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            cmd = ['exiftool'] + self.default_flags
            
            # Add each field
            for field, value in fields.items():
                if value:
                    # Convert value to string or list of strings
                    if isinstance(value, list):
                        value = [str(item) for item in value]
                        value = ','.join(value)
                    else:
                        value = str(value)
                        
                    # Don't add extra dash if field already starts with one
                    field_arg = field if field.startswith('-') else f'-{field}'
                    cmd.append(f'{field_arg}={value}')
                    
            cmd.append(str(file_path))
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                self.logger.error(f"Error writing metadata: {result.stderr}")
                return False
                
            return True
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error writing metadata: {e}")
            return False
            
    def copy_metadata(self, source_path: Union[str, Path], target_path: Union[str, Path]) -> bool:
        """
        Copy all metadata from source to target file.
        
        Args:
            source_path: Path to source file
            target_path: Path to target file
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            cmd = ['exiftool'] + self.default_flags + ['-TagsFromFile', str(source_path), str(target_path)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                self.logger.error(f"Error copying metadata: {result.stderr}")
                return False
                
            return True
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error copying metadata: {e}")
            return False
            
    def update_keywords(self, file_path: Union[str, Path], keywords: List[str]) -> bool:
        """
        Update keywords metadata field.
        
        Args:
            file_path: Path to the file
            keywords: List of keywords to write
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Ensure all keywords are strings
            keywords = [str(k) for k in keywords]
            
            cmd = ['exiftool'] + self.default_flags + [f'-keywords={",".join(keywords)}', str(file_path)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                self.logger.error(f"Error updating keywords: {result.stderr}")
                return False
                
            return True
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Error updating keywords: {e}")
            return False
