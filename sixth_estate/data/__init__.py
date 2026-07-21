"""Public-data adapters. Each returns schema objects and accepts an injectable
transport so tests never touch the network."""
from .fred import fetch_mortgage30us  # noqa: F401
from .bls import fetch_cpi  # noqa: F401
from .coingecko import fetch_crypto  # noqa: F401
from .weather import fetch_forecast  # noqa: F401
from .wikipedia import fetch_on_this_day  # noqa: F401
from .sports import fetch_scores  # noqa: F401
