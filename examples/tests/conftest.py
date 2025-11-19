"""Pytest configuration for examples tests."""

import sys
from pathlib import Path

# Add parent directory (examples/) to path so views can be imported
examples_dir = Path(__file__).parent.parent
sys.path.insert(0, str(examples_dir))
