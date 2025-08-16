#!/usr/bin/env python3
"""
Simple test script to check if RhetTbull photokit can access Apple Photos captions.
"""

import sys
import logging
from pathlib import Path

# Add the project root to Python path
sys.path.append(str(Path(__file__).parent))

import Photos
from objc import autorelease_pool
import photokit

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_photokit_captions():
    """Test if photokit can access captions from Apple Photos."""
    try:
        with autorelease_pool():
            logger.info("Testing photokit caption access...")
            
            # Get all photos from library
            fetch_options = Photos.PHFetchOptions.alloc().init()
            fetch_options.setFetchLimit_(10)  # Only test first 10 photos
            all_assets = Photos.PHAsset.fetchAssetsWithOptions_(fetch_options)
            
            logger.info(f"Found {all_assets.count()} assets to test")
            
            for i in range(min(10, all_assets.count())):
                asset = all_assets.objectAtIndex_(i)
                asset_id = asset.localIdentifier()
                title = asset.valueForKey_('title')
                
                logger.info(f"\n--- Asset {i+1} ---")
                logger.info(f"Asset ID: {asset_id}")
                logger.info(f"Title: {title}")
                
                try:
                    # Test photokit access
                    photo_asset = photokit.PhotoAsset(asset_id)
                    logger.info(f"PhotoAsset created successfully")
                    
                    # Check available attributes
                    attrs = dir(photo_asset)
                    caption_attrs = [attr for attr in attrs if 'caption' in attr.lower() or 'description' in attr.lower() or 'comment' in attr.lower()]
                    logger.info(f"Caption-related attributes: {caption_attrs}")
                    
                    # Try to get caption/description
                    found_caption = False
                    for attr in ['description', 'caption', 'comment', 'title']:
                        if hasattr(photo_asset, attr):
                            try:
                                value = getattr(photo_asset, attr)
                                if value and isinstance(value, str) and value.strip():
                                    logger.info(f"Found {attr}: '{value}'")
                                    if ':' in value:
                                        logger.info(f"*** CATEGORY FORMAT FOUND in {attr}: '{value}' ***")
                                    found_caption = True
                                else:
                                    logger.info(f"{attr}: {value} (empty or None)")
                            except Exception as e:
                                logger.info(f"Error accessing {attr}: {e}")
                        else:
                            logger.info(f"No {attr} attribute")
                    
                    if not found_caption:
                        logger.info("No caption/description found for this asset")
                        
                except Exception as e:
                    logger.error(f"Error creating PhotoAsset: {e}")
                
                if i >= 4:  # Only show first 5 in detail
                    break
                    
    except Exception as e:
        logger.error(f"Error in test: {e}")

if __name__ == "__main__":
    test_photokit_captions()
