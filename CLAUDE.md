# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LRExporting is a macOS-specific photo and video management system that processes media files exported from Adobe Lightroom and integrates them with Apple Photos. It runs as a continuous service monitoring directories for new media files.

## Key Architecture

### Core Components
1. **Watchers** (`/watchers/`) - Monitor directories for different file types:
   - `ImageWatcher` - Monitors for JPEG files
   - `VideoWatcher` - Monitors for video files (MP4, MOV, M4V)
   - `TransferWatcher` - Handles file transfers between directories
   - `ApplePhotoWatcher` - Manages Apple Photos integration with watermark-based throttling

2. **Processors** (`/processors/`) - Handle media file processing:
   - `JpegProcessor` - Processes JPEG images with EXIF/XMP metadata
   - `VideoProcessor` - Processes video files with metadata preservation
   - All inherit from `MediaProcessor` base class

3. **Apple Photos SDK** (`/apple_photos_sdk/`) - Handles Apple Photos integration:
   - Album management based on location metadata
   - Batch importing with configurable sizes
   - "Watching" album management for processing queue

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

# Run the main application (continuous monitoring)
pipenv run python lrexport.py

# Or with activated virtual environment
pipenv shell
python lrexport.py
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
4. **Continuous Service** - Main script runs indefinitely until interrupted (Ctrl+C)
5. **Metadata Preservation** - Extensive metadata mapping for both images and videos
6. **Album Management** - Uses `album.yaml` to organize photos by location automatically