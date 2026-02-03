"""Bundle built-in document adapters so they self-register on import."""

from __future__ import annotations

# Import the sub-packages to trigger parser registration side effects.
from . import html as _html  # noqa: F401
from . import xml as _xml  # noqa: F401
from . import pdf as _pdf  # noqa: F401

__all__ = ["html", "xml", "pdf"]
