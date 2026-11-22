"""FirmAlways Gate: open-source AI privacy gateway for Thai personal data."""

__version__ = "0.3.0"

from .analyzer import ENTITY_TYPES, analyze  # noqa: E402
from .engine import ContentNotAllowed, Gate, Protection, restore_completion  # noqa: E402
from .entities import Entity  # noqa: E402
from .policy import Client, Policy, PolicyError, Upstream, load_policy  # noqa: E402
from .pseudonymize import Pseudonymizer, StreamRestorer  # noqa: E402

__all__ = [
    "ENTITY_TYPES",
    "Client",
    "ContentNotAllowed",
    "Entity",
    "Gate",
    "Policy",
    "PolicyError",
    "Protection",
    "Pseudonymizer",
    "StreamRestorer",
    "Upstream",
    "analyze",
    "load_policy",
    "restore_completion",
]
