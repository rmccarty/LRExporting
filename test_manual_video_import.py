#!/usr/bin/env python3

"""
Manual Video Import Test - Test the complete video processing and Apple Photos import pipeline
"""

import logging
import sys
from pathlib import Path
import shutil
import tempfile

# Add the project root to the path
sys.path.insert(0, '/Users/rmccarty/src/LRExporting')

from processors.video_processor import VideoProcessor
from apple_photos_sdk import ApplePhotos
from config import APPLE_PHOTOS_WATCHING

def setup_logging():
    """Setup logging for the test."""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

def find_test_video():
    """Find a video file in Downloads directory."""
    downloads_dir = Path("/Users/rmccarty/Downloads")
    
    print(f"🔍 Looking for video files in {downloads_dir}")
    
    # First, look specifically for the Ludendorff video (we know it has XMP)
    ludendorff_video = downloads_dir / "The McCartys 1969 - Ritzals in Ludwigsburg - 1969 – 1970.mov"
    if ludendorff_video.exists():
        print(f"   🎯 Found target video: {ludendorff_video.name}")
        return ludendorff_video
    
    # Otherwise look for any video files (but skip temp files)
    video_patterns = ['*.mp4', '*.mov', '*.m4v', '*.MP4', '*.MOV', '*.M4V']
    
    for pattern in video_patterns:
        for video_file in downloads_dir.glob(pattern):
            if (video_file.is_file() and 
                video_file.stat().st_size > 0 and 
                not video_file.name.startswith('.') and
                'Tmp' not in video_file.name):
                print(f"   ✅ Found: {video_file.name}")
                return video_file
                
    print(f"   ❌ No suitable video files found in Downloads")
    return None

def process_and_import_video(video_path: Path):
    """Process a video file and import to Apple Photos."""
    
    print(f"\n{'='*60}")
    print(f"🎬 MANUAL VIDEO IMPORT TEST")
    print(f"{'='*60}")
    print(f"📁 Source video: {video_path}")
    
    # Create a temporary working directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Copy the video to temp directory for processing
        temp_video = temp_path / video_path.name
        shutil.copy2(video_path, temp_video)
        print(f"📋 Copied to temp: {temp_video}")
        
        # Look for XMP sidecar file
        xmp_file = video_path.with_suffix('.xmp')
        temp_xmp = None
        if xmp_file.exists():
            temp_xmp = temp_video.with_suffix('.xmp')
            shutil.copy2(xmp_file, temp_xmp)
            print(f"📋 Copied XMP: {temp_xmp}")
        else:
            print(f"⚠️  No XMP sidecar found: {xmp_file}")
            print(f"   This test will show what happens without Lightroom metadata")
        
        # Step 1: Process the video with our video processor
        print(f"\n🎨 STEP 1: Processing video with VideoProcessor")
        print(f"-" * 40)
        
        try:
            processor = VideoProcessor(str(temp_video), sequence="TEST")
            success = processor.process_video()
            
            if success:
                # Get the renamed file
                processed_name = processor.generate_filename()
                processed_video = temp_path / processed_name
                print(f"✅ Video processing succeeded: {processed_name}")
            else:
                print(f"❌ Video processing failed")
                return False
                
        except Exception as e:
            print(f"❌ Video processing error: {e}")
            return False
        
        # Step 2: Import to Apple Photos
        print(f"\n📸 STEP 2: Importing to Apple Photos")
        print(f"-" * 40)
        print(f"📁 Processed video: {processed_video}")
        print(f"🎯 Target album: {APPLE_PHOTOS_WATCHING}")
        
        try:
            apple_photos = ApplePhotos()
            success = apple_photos.import_photo(processed_video, album_paths=[str(APPLE_PHOTOS_WATCHING)])
            
            if success:
                print(f"✅ Apple Photos import succeeded!")
                print(f"📸 Video should now be in '{APPLE_PHOTOS_WATCHING}' album with native metadata")
            else:
                print(f"❌ Apple Photos import failed")
                return False
                
        except Exception as e:
            print(f"❌ Apple Photos import error: {e}")
            return False
        
        print(f"\n{'='*60}")
        print(f"✅ MANUAL VIDEO IMPORT TEST COMPLETE")
        print(f"📸 Check Apple Photos '{APPLE_PHOTOS_WATCHING}' album for the imported video")
        print(f"🔍 Verify that keywords appear as blue tags (if XMP had keywords)")
        print(f"{'='*60}")
        
        return True

def main():
    """Main test function."""
    setup_logging()
    
    # Find a test video
    video_path = find_test_video()
    if not video_path:
        print("❌ No video file found in Downloads directory")
        print("   Please add a .mp4, .mov, or .m4v file to Downloads and try again")
        return 1
    
    # Process and import the video
    try:
        success = process_and_import_video(video_path)
        return 0 if success else 1
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())