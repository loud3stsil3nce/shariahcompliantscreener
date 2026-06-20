"""Shariah compliant screener package."""

# Expose commonly-used submodules as top-level attributes for tests and scripts
from .analysis import screener, optimizer, backtester
from .data import ingestion
from .db import helpers, setup

# Convenience function imports
from .data.ingestion import run_ingestion
from .analysis.optimizer import run_optimizer
from .analysis.screener import run_screener