#!/usr/bin/env python3

import osxphotos
import subprocess
import logging
from typing import List, Tuple

class PhotosFinder:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        try:
            self.photosdb = osxphotos.PhotosDB()
        except Exception as e:
            self.logger.error(f"Error connecting to Photos library: {e}")
            raise
            
    def execute_applescript(self, script: str) -> str:
        """Execute AppleScript and return the result."""
        try:
            result = subprocess.run(['osascript', '-e', script], 
                                 capture_output=True, 
                                 text=True, 
                                 check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            self.logger.error(f"AppleScript error: {e.stderr}")
            self.logger.error(f"Error code: {e.returncode}")
            raise
            
    def create_album_if_needed(self, album_name: str) -> bool:
        """Create album if it doesn't exist in the correct folder structure."""
        # Escape special characters in the album name
        safe_name = album_name.replace('"', '\\"').replace('/', '-').replace('&', 'and')
        
        # Get category from album name (text before colon)
        category = album_name.split(':')[0].strip() if ':' in album_name else None
        if not category:
            self.logger.error(f"Could not determine category for album: {album_name}")
            return False
            
        folder_path = f"02_What/{category}"
        self.logger.info(f"Creating/verifying album '{safe_name}' in folder '{folder_path}'")
        
        script = f'''
        tell application "Photos"
            try
                -- First ensure the root folder exists
                if not (exists folder "02_What") then
                    make new folder named "02_What"
                end if
                
                -- Then ensure the category folder exists
                if not (exists folder "{folder_path}") then
                    make new folder named "{category}" at folder "02_What"
                end if
                
                -- Check if album exists anywhere
                if not (exists album "{safe_name}") then
                    -- Create new album in the correct folder
                    tell folder "{folder_path}"
                        make new album named "{safe_name}"
                    end tell
                end if
                return true
            on error errMsg
                log errMsg
                return false
            end try
        end tell
        '''
        try:
            result = self.execute_applescript(script)
            self.logger.info(f"Album creation result for '{safe_name}' in '{folder_path}': {result}")
            return result.lower() == "true"
        except Exception as e:
            self.logger.error(f"Error creating album: {e}")
            return False
            
    def is_photo_in_album(self, photo_uuid: str, album_name: str) -> bool:
        """Check if photo is already in the album."""
        safe_name = album_name.replace('"', '\\"').replace('/', '-').replace('&', 'and')
        script = f'''
        tell application "Photos"
            try
                set albumName to "{safe_name}"
                if exists album albumName then
                    set theAlbum to album albumName
                    repeat with aPhoto in media items of theAlbum
                        if id of aPhoto is "{photo_uuid}" then
                            return true
                        end if
                    end repeat
                end if
                return false
            on error errMsg
                log errMsg
                return false
            end try
        end tell
        '''
        try:
            result = self.execute_applescript(script)
            return result.lower() == "true"
        except Exception as e:
            self.logger.error(f"Error checking if photo is in album: {e}")
            return False

    def add_to_album(self, photo_uuid: str, album_name: str) -> bool:
        """Add a photo to an album using AppleScript."""
        # Escape special characters in the album name
        safe_name = album_name.replace('"', '\\"').replace('/', '-').replace('&', 'and')
        
        try:
            # Check if photo is already in the album
            if self.is_photo_in_album(photo_uuid, album_name):
                self.logger.info(f"Photo {photo_uuid} already in album '{safe_name}' - skipping")
                return True
                
            # Only log adding if we're actually going to add it
            self.logger.info(f"Adding to album: '{safe_name}' (original: '{album_name}')")
            
            # Verify album exists
            verify_script = f'''
            tell application "Photos"
                if exists album "{safe_name}" then
                    return true
                else
                    return false
                end if
            end tell
            '''
            
            album_exists = self.execute_applescript(verify_script).lower() == "true"
            if not album_exists:
                self.logger.error(f"Album '{safe_name}' does not exist before adding photo")
                # Try to create it again
                if not self.create_album_if_needed(album_name):
                    return False
                # Verify again
                album_exists = self.execute_applescript(verify_script).lower() == "true"
                if not album_exists:
                    self.logger.error(f"Album still doesn't exist after creation attempt")
                    return False
            
            # Now try to add the photo
            script = f'''
        tell application "Photos"
            try
                set albumName to "{safe_name}"
                if exists media item id "{photo_uuid}" then
                    if exists album albumName then
                        add {{media item id "{photo_uuid}"}} to album albumName
                        return true
                    else
                        error "Album not found after verification" number -1729
                    end if
                else
                    error "Photo not found" number -1728
                end if
            on error errMsg number errorNumber
                log "Error " & errorNumber & ": " & errMsg
                return "error:" & errorNumber & ":" & errMsg
            end try
        end tell
        '''
            result = self.execute_applescript(script)
            self.logger.info(f"Add to album result for '{safe_name}': {result}")
            if result.startswith("error:"):
                _, error_num, error_msg = result.split(":", 2)
                self.logger.error(f"Photos error {error_num}: {error_msg}")
                self.logger.error(f"Failed to add photo to album. Album name: '{safe_name}', Photo UUID: {photo_uuid}")
                return False
            return True
        except Exception as e:
            self.logger.error(f"Error adding photo to album: {e}")
            self.logger.error(f"Script that failed: {script}")
            return False
            
    def find_photos_with_titles(self) -> List[Tuple[str, str]]:
        """Find photos with titles containing specific prefixes followed by colon."""
        matching_photos = []
        
        try:
            # Get all photos
            photos = self.photosdb.photos()
            
            # Find photos with titles containing colon
            for photo in photos:
                if photo.title and ":" in photo.title:
                    # Get the prefix (text before the colon)
                    title_prefix = photo.title.split(':')[0].strip()
                    
                    # Check if prefix:
                    # 1. Starts with capital letter
                    # 2. Contains only letters
                    # 3. Ends with a colon in the full title
                    if (title_prefix and 
                        title_prefix[0].isupper() and 
                        title_prefix.isalpha()):
                        
                        # Get the album name from the title
                        album_name = photo.title.strip()
                        matching_photos.append((photo.uuid, album_name))
                        self.logger.info(f"Found matching photo: {album_name}")
                    else:
                        self.logger.debug(f"Skipping photo with invalid prefix: {photo.title}")
                        
            if not matching_photos:
                self.logger.info("No photos found with valid title prefixes")
                self.logger.info("Title prefix must:")
                self.logger.info("1. Start with a capital letter")
                self.logger.info("2. Contain only letters")
                self.logger.info("3. End with a colon")
                self.logger.info("Example: 'Wedding:' is valid, 'W@dding:' is not")
            else:
                self.logger.info(f"Found {len(matching_photos)} matching photos")
            
            return matching_photos
            
        except Exception as e:
            self.logger.error(f"Error searching photos: {e}")
            raise
            
    def organize_existing_albums(self):
        """Move existing albums to their category folders."""
        script = '''
        tell application "Photos"
            set albumList to {}
            repeat with anAlbum in albums
                set albumList to albumList & {(name of anAlbum as string)}
            end repeat
            return albumList
        end tell
        '''
        try:
            result = self.execute_applescript(script)
            albums = [name.strip() for name in result.split(',') if ':' in name]
            
            if not albums:
                self.logger.info("No existing albums found with category prefixes")
                return
                
            # Get unique categories
            categories = set()
            for album_name in albums:
                if ':' in album_name:
                    category = album_name.split(':')[0].strip()
                    if category:
                        categories.add(category)
            
            self.logger.info(f"Found {len(albums)} albums across {len(categories)} categories")
            print("\nOrganizing existing albums:")
            print("-" * 50)
            
            # Create any missing category folders and organize albums
            for category in categories:
                folder_path = f"02_What/{category}"
                script = f'''
                tell application "Photos"
                    try
                        -- First ensure the root folder exists
                        if not (exists folder "02_What") then
                            make new folder named "02_What"
                        end if
                        
                        -- Then ensure the category folder exists
                        if not (exists folder "{folder_path}") then
                            make new folder named "{category}" at folder "02_What"
                            return "created"
                        end if
                        return "exists"
                    on error errMsg
                        log errMsg
                        return "error"
                    end try
                end tell
                '''
                try:
                    result = self.execute_applescript(script)
                    if result == "created":
                        print(f"Created new category folder: {folder_path}")
                    elif result == "exists":
                        print(f"Category folder already exists: {folder_path}")
                    else:
                        print(f"Failed to create category folder: {folder_path}")
                except Exception as e:
                    self.logger.error(f"Error creating category folder {folder_path}: {e}")
            
            # Then move albums to their folders
            for album_name in albums:
                category = album_name.split(':')[0].strip()
                if not category:
                    self.logger.debug(f"Skipping album without category: {album_name}")
                    continue
                    
                folder_path = f"02_What/{category}"
                print(f"Processing album: {album_name}")
                
                # Move album to correct folder
                script = f'''
                tell application "Photos"
                    try
                        if exists album "{album_name}" then
                            move album "{album_name}" to folder "{folder_path}"
                            return true
                        end if
                        return false
                    on error errMsg
                        log errMsg
                        return false
                    end try
                end tell
                '''
                try:
                    result = self.execute_applescript(script)
                    if result.lower() == "true":
                        print(f"Successfully organized album: {album_name} to {folder_path}")
                    else:
                        print(f"Failed to organize album: {album_name}")
                except Exception as e:
                    self.logger.error(f"Error organizing album {album_name}: {e}")
                    
            print("-" * 50)
            
        except Exception as e:
            self.logger.error(f"Error getting album list: {e}")
            raise
            
    def process_photos(self):
        """Main method to find and organize photos into albums."""
        try:
            # First organize existing albums
            self.organize_existing_albums()
            
            # Then process new photos
            album_photos = {}
            photos = self.find_photos_with_titles()
            
            if not photos:
                self.logger.info("No matching photos found")
                return
                
            # Group photos by album name
            for uuid, album_name in photos:
                if album_name not in album_photos:
                    album_photos[album_name] = []
                album_photos[album_name].append(uuid)
                
            self.logger.info(f"Found {len(photos)} photos across {len(album_photos)} albums")
            print("\nProcessing albums:")
            print("-" * 50)
            
            # Process each album's photos together
            for album_name, photo_uuids in album_photos.items():
                print(f"\nProcessing album: {album_name}")
                print(f"Found {len(photo_uuids)} photos for this album")
                
                # Create album if needed
                if self.create_album_if_needed(album_name):
                    # Process all photos for this album
                    successful_adds = 0
                    already_in_album = 0
                    for i, uuid in enumerate(photo_uuids, 1):
                        if self.is_photo_in_album(uuid, album_name):
                            already_in_album += 1
                            print(f"Photo {i}/{len(photo_uuids)} already exists in album: {album_name}")
                        elif self.add_to_album(uuid, album_name):
                            successful_adds += 1
                            print(f"Successfully added photo {i}/{len(photo_uuids)} to album: {album_name}")
                        else:
                            print(f"Failed to add photo {i}/{len(photo_uuids)} to album: {album_name}")
                    print(f"Added {successful_adds} new photos to album")
                    print(f"Found {already_in_album} photos already in album")
                    print(f"Total processed: {len(photo_uuids)} photos for album: {album_name}")
                else:
                    print(f"Failed to create/verify album: {album_name}")
                print("-" * 50)
                
        except Exception as e:
            self.logger.error(f"Error processing photos: {e}")
            raise

    def move_album_to_folder(self, album_name: str, folder_path: str) -> bool:
        """Move album to specified folder."""
        self.logger.info(f"Attempting to move album '{album_name}' to folder '{folder_path}'")
        script = f'''
        tell application "Photos"
            try
                if exists album "{album_name}" then
                    if exists folder "{folder_path}" then
                        move album "{album_name}" to folder "{folder_path}"
                        return true
                    else
                        error "Folder not found" number -1730
                    end if
                else
                    error "Album not found" number -1729
                end if
            on error errMsg number errorNumber
                log "Error " & errorNumber & ": " & errMsg
                return "error:" & errorNumber & ":" & errMsg
            end try
        end tell
        '''
        try:
            result = self.execute_applescript(script)
            if result.startswith("error:"):
                _, error_num, error_msg = result.split(":", 2)
                self.logger.error(f"Failed to move album: Error {error_num}: {error_msg}")
                return False
            elif result.lower() == "true":
                self.logger.info(f"Successfully moved album '{album_name}' to folder '{folder_path}'")
                return True
            else:
                self.logger.error(f"Failed to move album '{album_name}' to folder '{folder_path}'")
                return False
        except Exception as e:
            self.logger.error(f"Error moving album: {e}")
            self.logger.error(f"Script that failed: {script}")
            return False

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    finder = PhotosFinder()
    try:
        finder.process_photos()
    except KeyboardInterrupt:
        logging.info("Process interrupted by user")
    except Exception as e:
        logging.error(f"Process failed: {e}") 