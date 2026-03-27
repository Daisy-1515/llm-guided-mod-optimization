"""Pytest configuration for edge_uav tests.

This conftest.py ensures the project root is in sys.path for test discovery,
allowing pytest and uv run pytest to both work correctly with package=false config.
"""

import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
