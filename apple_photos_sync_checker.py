#!/usr/bin/env python3
"""
Check if Apple Photos library is fully synced with iCloud.
This helps identify when the local library doesn't have all photos from iCloud.
"""

import sys
import subprocess
import plistlib
import json
from pathlib import Path
from datetime import datetime
import Photos
from Photos import PHPhotoLibrary

def check_photos_sync_status():
    """Check various indicators of Photos sync status."""
    
    status = {
        'is_icloud_enabled': False,
        'library_path': None,
        'last_sync': None,
        'sync_in_progress': False,
        'potential_issues': [],
        'recommendations': []
    }
    
    # 1. Check if iCloud Photos is enabled
    try:
        # Check system preferences for iCloud Photos
        result = subprocess.run(
            ['defaults', 'read', 'com.apple.photolibraryd', 'PLCloudPhotoLibraryEnable'],
            capture_output=True,
            text=True
        )
        status['is_icloud_enabled'] = result.returncode == 0 and '1' in result.stdout
    except Exception as e:
        status['potential_issues'].append(f"Could not check iCloud Photos setting: {e}")
    
    # 2. Check Photos app sync status via SQLite database (if accessible)
    try:
        photos_lib_path = Path.home() / 'Pictures' / 'Photos Library.photoslibrary'
        status['library_path'] = str(photos_lib_path)
        
        if photos_lib_path.exists():
            # Check for sync-related files
            database_path = photos_lib_path / 'database' / 'Photos.sqlite'
            if database_path.exists():
                status['last_sync'] = datetime.fromtimestamp(
                    database_path.stat().st_mtime
                ).isoformat()
    except Exception as e:
        status['potential_issues'].append(f"Could not access Photos library: {e}")
    
    # 3. Check for photolibraryd activity (indicates syncing)
    try:
        result = subprocess.run(
            ['ps', 'aux'],
            capture_output=True,
            text=True
        )
        if 'photolibraryd' in result.stdout and 'cloudphoto' in result.stdout.lower():
            status['sync_in_progress'] = True
            status['potential_issues'].append("Photos appears to be actively syncing with iCloud")
    except Exception as e:
        pass
    
    # 4. Check system logs for sync errors
    try:
        result = subprocess.run(
            ['log', 'show', '--predicate', 'subsystem == "com.apple.photos"', 
             '--last', '1h', '--style', 'compact'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if 'error' in result.stdout.lower() or 'failed' in result.stdout.lower():
            status['potential_issues'].append("Recent Photos sync errors detected in system logs")
    except Exception as e:
        pass
    
    # 5. Check network connectivity to iCloud
    try:
        result = subprocess.run(
            ['ping', '-c', '1', '-t', '2', 'www.icloud.com'],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            status['potential_issues'].append("Cannot reach iCloud servers")
            status['recommendations'].append("Check internet connection")
    except Exception as e:
        pass
    
    # 6. Check available storage
    try:
        result = subprocess.run(
            ['df', '-h', '/'],
            capture_output=True,
            text=True
        )
        lines = result.stdout.strip().split('\n')
        if len(lines) > 1:
            parts = lines[1].split()
            if len(parts) > 4:
                avail = parts[3]
                # Parse available space
                if 'G' in avail:
                    avail_gb = float(avail.rstrip('GgIi'))
                    if avail_gb < 20:
                        status['potential_issues'].append(f"Low disk space: {avail} available")
                        status['recommendations'].append("Free up disk space for Photos to sync properly")
    except Exception as e:
        pass
    
    # Generate recommendations based on findings
    if status['sync_in_progress']:
        status['recommendations'].append("Wait for current sync to complete before downloading")
    
    if not status['is_icloud_enabled']:
        status['recommendations'].append("iCloud Photos may not be enabled - check System Preferences")
    
    if not status['potential_issues']:
        status['recommendations'].append("No sync issues detected, but manually verify in Photos app")
    
    return status


def check_photos_app_status():
    """Check Photos app for sync indicators."""
    
    indicators = {
        'photos_is_running': False,
        'update_status': None,
        'library_size_local': 0,
        'asset_count_local': 0
    }
    
    # Check if Photos app is running
    try:
        result = subprocess.run(
            ['pgrep', '-x', 'Photos'],
            capture_output=True,
            text=True
        )
        indicators['photos_is_running'] = result.returncode == 0
    except:
        pass
    
    # Get asset count from library
    try:
        library = PHPhotoLibrary.sharedPhotoLibrary()
        if library:
            # This gives us the count of assets the library knows about
            fetch_options = Photos.PHFetchOptions.alloc().init()
            assets = Photos.PHAsset.fetchAssetsWithOptions_(fetch_options)
            indicators['asset_count_local'] = assets.count()
    except Exception as e:
        indicators['update_status'] = f"Could not query library: {e}"
    
    return indicators


def suggest_manual_checks():
    """Provide instructions for manual verification."""
    
    suggestions = [
        "\n📋 MANUAL VERIFICATION STEPS:",
        "1. Open Photos app and check bottom of sidebar for sync status",
        "2. Look for 'Updating...' or 'Uploading X items' messages", 
        "3. In Photos > Preferences > iCloud, verify 'Download Originals' or 'Optimize Storage'",
        "4. Check System Preferences > Apple ID > iCloud usage for Photos",
        "5. Visit icloud.com/photos to see total photo count in iCloud",
        "6. Compare iCloud photo count with local library count",
        "\n⚠️  IMPORTANT LIMITATIONS:",
        "- This script can only see photos that Photos.app has indexed locally",
        "- Photos in iCloud but never opened on this Mac won't be visible",
        "- 'Optimize Storage' mode keeps only thumbnails for many photos",
        "- Full sync requires 'Download Originals to this Mac' setting",
        "\n🔄 TO ENSURE FULL SYNC:",
        "1. Open Photos app",
        "2. Go to Photos > Preferences > iCloud",
        "3. Select 'Download Originals to this Mac'",
        "4. Leave Photos open and connected to internet",
        "5. Wait for 'Updated Just Now' message at bottom of sidebar",
        "6. May take hours/days depending on library size and internet speed"
    ]
    
    return suggestions


def main():
    """Main entry point."""
    
    print("=" * 60)
    print("APPLE PHOTOS ICLOUD SYNC STATUS CHECKER")
    print("=" * 60)
    
    # Check sync status
    print("\n🔍 Checking Photos sync status...")
    sync_status = check_photos_sync_status()
    
    print(f"\n📊 Sync Status:")
    print(f"   iCloud Photos Enabled: {sync_status['is_icloud_enabled']}")
    print(f"   Library Path: {sync_status['library_path']}")
    print(f"   Last Activity: {sync_status['last_sync'] or 'Unknown'}")
    print(f"   Sync In Progress: {sync_status['sync_in_progress']}")
    
    # Check Photos app
    print("\n📸 Checking Photos app...")
    app_status = check_photos_app_status()
    
    print(f"   Photos Running: {app_status['photos_is_running']}")
    print(f"   Local Asset Count: {app_status['asset_count_local']:,}")
    
    # Report issues
    if sync_status['potential_issues']:
        print("\n⚠️  Potential Issues Detected:")
        for issue in sync_status['potential_issues']:
            print(f"   - {issue}")
    
    # Provide recommendations
    if sync_status['recommendations']:
        print("\n💡 Recommendations:")
        for rec in sync_status['recommendations']:
            print(f"   - {rec}")
    
    # Show manual check suggestions
    suggestions = suggest_manual_checks()
    for suggestion in suggestions:
        print(suggestion)
    
    # Save status to file for other scripts
    status_file = Path('.photos_sync_status.json')
    combined_status = {
        'timestamp': datetime.now().isoformat(),
        'sync': sync_status,
        'app': app_status
    }
    
    with open(status_file, 'w') as f:
        json.dump(combined_status, f, indent=2)
    
    print(f"\n💾 Status saved to {status_file}")
    
    # Return code indicates if sync issues detected
    return 1 if sync_status['potential_issues'] else 0


if __name__ == "__main__":
    sys.exit(main())