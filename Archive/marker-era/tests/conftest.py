# Prepend archive root so "extraction" and "broadening" resolve to Archive/marker-era.
import sys
from pathlib import Path

_archive_root = Path(__file__).resolve().parent.parent
_str_root = str(_archive_root)
if _str_root not in sys.path:
    sys.path.insert(0, _str_root)
