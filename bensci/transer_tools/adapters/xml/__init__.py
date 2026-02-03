"""XML-based adapters."""

from __future__ import annotations

from . import elsevier  # noqa: F401
from . import acs  # noqa: F401
from . import springer  # noqa: F401

__all__ = ["elsevier", "acs", "springer"]
