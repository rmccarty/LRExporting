import os

def find_video_files(directory):
    """Find all video files in directory."""
    video_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            # Add .m4v to the list of valid extensions
            if file.lower().endswith(('.mp4', '.mov', '.m4v')):
                video_files.append(os.path.join(root, file))
    return video_files 