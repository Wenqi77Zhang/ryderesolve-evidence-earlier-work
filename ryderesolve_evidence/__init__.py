"""Evidence normalization only: this package never decides a dispute."""

from .core import CaseRepository, InputError, normalize_evidence
from .tools import EvidenceTools

__all__ = ["CaseRepository", "EvidenceTools", "InputError", "normalize_evidence"]
__version__ = "0.1.0"
