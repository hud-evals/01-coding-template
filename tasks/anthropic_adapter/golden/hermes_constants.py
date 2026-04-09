"""Stub for hermes_constants."""

import os
from pathlib import Path

def get_hermes_home() -> Path:
    """Return the Hermes home directory (default: ~/.hermes).

    Reads HERMES_HOME env var, falls back to ~/.hermes.
    This is the single source of truth — all other copies should import this.
    """
    return Path(os.getenv("HERMES_HOME", Path.home() / ".hermes"))
