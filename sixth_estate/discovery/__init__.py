"""Candidate discovery: RSS-first ($0), bounded Brave fallback, optional Google PSE."""
from .candidate import Candidate  # noqa: F401
from .rss import discover_rss  # noqa: F401
from .brave import BraveClient  # noqa: F401
from .google_pse import GooglePSEClient  # noqa: F401
