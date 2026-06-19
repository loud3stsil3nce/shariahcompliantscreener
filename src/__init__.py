"""Shariah compliant screener package."""
from .data.ingestion import run_ingestion
from .analysis.optimizer import run_optimizer
from .analysis.screener import run_screener