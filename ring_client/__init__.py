"""ring_client — a small typed client for the Ring Partner API.

Standard library only, no runtime dependencies. Extracted from Threshold and
released separately under the MIT licence, because Ring ships no SDK and the
next person should not have to write this again.
"""

from .client import BASE_URL, RingClient, token_expiry, token_scopes
from .emulator import DEVICE_ID, Emulator
from .errors import (
    Forbidden,
    NotFound,
    RateLimited,
    RingError,
    TokenExpired,
    TokenInvalid,
    Unreachable,
)
from .models import Capabilities, Configurations, Device, Status, User, Zone

__all__ = [
    "BASE_URL",
    "RingClient",
    "Emulator",
    "DEVICE_ID",
    "token_expiry",
    "token_scopes",
    "RingError",
    "TokenExpired",
    "TokenInvalid",
    "Forbidden",
    "NotFound",
    "RateLimited",
    "Unreachable",
    "Device",
    "Zone",
    "Capabilities",
    "Configurations",
    "Status",
    "User",
]
__version__ = "1.0.0"
