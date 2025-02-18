def extract_xmp(file_path):
    """Extract XMP data from video file."""
    # This should work for .m4v as exiftool handles it the same as .mp4
    try:
        result = subprocess.run([
            'exiftool',
            '-xmp',
            '-b',
            file_path
        ], capture_output=True, text=True)
        return result.stdout
    except Exception as e:
        log_message(f"Error extracting XMP: {e}")
        return None 