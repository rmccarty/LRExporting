#!/usr/bin/env python3

from pathlib import Path

# Directory paths
RON_INCOMING = Path("/Users/rmccarty/Transfers/Ron/Ron_Incoming")
CLAUDIA_INCOMING = Path("/Users/rmccarty/Transfers/Claudia/Claudia_Incoming")
BOTH_INCOMING = Path("/Users/rmccarty/Transfers/Both/Both_Incoming")

# Watch directories configuration
WATCH_DIRS = [RON_INCOMING, CLAUDIA_INCOMING]

# Logging configuration
LOG_LEVEL = "INFO"

# Sleep time when no files are found (in seconds)
SLEEP_TIME = 10
