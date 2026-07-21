import sys
from pathlib import Path

# Make the package importable when tests run from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
