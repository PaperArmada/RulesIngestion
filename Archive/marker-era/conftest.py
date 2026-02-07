# Ensure the marker-era archive root is first on sys.path so "extraction" and
# "broadening" resolve to this archive when running pytest from anywhere.
import sys
from pathlib import Path

_archive_root = Path(__file__).resolve().parent
if str(_archive_root) not in sys.path:
    sys.path.insert(0, str(_archive_root))
