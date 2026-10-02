"""Evidence normalization only: this package never decides a dispute."""

from .core import CaseRepository, InputError, normalize_evidence
from .tools import EvidenceTools
from .version import __version__

__all__ = ["CaseRepository", "EvidenceTools", "InputError", "normalize_evidence"]
