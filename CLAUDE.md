# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LRExporting is a macOS-specific photo and video management system that processes media files exported from Adobe Lightroom and integrates them with Apple Photos. The system has been refactored into separate standalone programs for different workflows.

## Key Architecture

### Standalone Programs
1. **`incoming_watcher.py`** - Main file processing program:
   - Monitors Ron_Incoming, Claudia_Incoming, and Both_Incoming directories
   - Processes JPEG and video files with XMP metadata
   - Outputs files with `__LRE` suffix ready for transfer
   - Distributes files from Both_Incoming to user-specific directories

2. **`incoming_mover.py`** - File transfer program:
   - Moves processed `__LRE` files to destination directories
   - Handles Ron → Apple Photos path and Claudia → iCloud path

3. **`apple_watching_ingest.py`** - Apple Photos integration:
   - Monitors Ron's Apple Photos directory for processed files
   - Imports files to Apple Photos "Watching" album
   - Manages batch processing and throttling

4. **`directory_monitor.py`** - System monitoring:
   - Provides overview of directory states and file counts
   - Useful for debugging and system health checks

### Core Components
1. **Processors** (`/processors/`) - Handle media file processing:
   - `JPEGExifProcessor` - Processes JPEG images with EXIF/XMP metadata
   - `VideoProcessor` - Processes video files with metadata preservation (supports both Lightroom rdf:Bag and Apple Photos rdf:Seq keyword formats)
   - `MediaProcessor` - Base class for all processors

2. **Apple Photos SDK** (`/apple_photos_sdk/`) - Handles Apple Photos integration:
   - Album management based on location metadata from `album.yaml`
   - Batch importing with configurable sizes
   - "Watching" album management for processing queue

3. **Watchers** (`/watchers/`) - Reusable watcher components:
   - `ApplePhotoWatcher` - Manages Apple Photos integration with watermark-based throttling
   - `BaseWatcher` - Base class for directory monitoring
   - `TransferWatcher` - Handles file transfers between directories

4. **Configuration** - Key files:
   - `config.py` - Main configuration (directories, metadata mappings, thresholds)
   - `album.yaml` - Maps location metadata to Apple Photos album hierarchy

### Important Patterns
- Uses ExifTool wrapper (`utils/exiftool.py`) for metadata operations
- Implements batch processing to avoid overwhelming Apple Photos
- Special filename handling: "__LRE" suffix and "The McCartys" prefix
- Multi-user support (separate directories for "Ron" and "Claudia")
- Watermark-based throttling prevents "Watching" album from growing too large

## Development Commands

### Running the Application
```bash
# Install dependencies
pipenv install

# Run individual programs (each monitors continuously)
pipenv run python incoming_watcher.py    # Process incoming files with metadata
pipenv run python incoming_mover.py      # Move processed files to destinations  
pipenv run python apple_watching_ingest.py  # Import files to Apple Photos
pipenv run python directory_monitor.py   # Check system status

# Or with activated virtual environment
pipenv shell
python incoming_watcher.py
python incoming_mover.py
python apple_watching_ingest.py
```

### Testing
```bash
# Run all tests
pipenv run pytest

# Run specific test file
pipenv run pytest tests/test_video_processor.py

# Run tests with coverage
pipenv run coverage run -m pytest
pipenv run coverage html  # Generate HTML report in htmlcov/

# Run a specific test class or method
pipenv run pytest tests/test_video_processor.py::TestVideoProcessor::test_process_video_success
```

### Code Quality
```bash
# Check code complexity (radon is installed)
pipenv run radon cc . -a  # Cyclomatic complexity
pipenv run radon mi .     # Maintainability index

# Security audit
pipenv run pip-audit

# Generate SBOM
pipenv run cyclonedx-py -i requirements.txt -o sbom.json
```

### Linting
Currently no linting tools are configured. To check code quality manually:
```bash
# Install linting tools (not in Pipfile)
pip install flake8 black mypy

# Run linters
flake8 .
black --check .
mypy .
```

## Testing Guidelines

- Tests use `unittest` framework with extensive mocking
- Mock external dependencies (file system, ExifTool, Apple Photos)
- Test files follow pattern: `test_<module_name>.py`
- Use `setUp`/`tearDown` methods for test isolation
- Separate test classes for normal operation vs error handling

## Important Considerations

1. **macOS Only** - This project requires macOS due to Apple Photos integration
2. **ExifTool Dependency** - Requires ExifTool binary installed on system
3. **File Paths** - Many paths in `config.py` are hard-coded and may need adjustment
4. **Modular Architecture** - Each program runs independently and can be started/stopped separately
5. **Continuous Services** - Programs run indefinitely until interrupted (Ctrl+C)
6. **Metadata Preservation** - Extensive metadata mapping for both images and videos
7. **Album Management** - Uses `album.yaml` to organize photos by location automatically
8. **Keyword Compatibility** - VideoProcessor supports both Lightroom (rdf:Bag) and Apple Photos (rdf:Seq) keyword formats