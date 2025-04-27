# site_scout/__init__.py
"""
SiteScout package initializer.
Defines package version and exposes CLI.
"""
__version__ = "0.1.0"

# Expose CLI entry point
from site_scout.cli import cli as main_cli
from .cli import cli  # экспорт для pytest
