# File: site_scout/bruteforce/__init__.py
"""site_scout.bruteforce: Модуль для перебора скрытых директорий на сайте."""

from .brute_force import BruteForcer, HiddenResource, brute_force_hidden_dirs

__all__ = ["HiddenResource", "BruteForcer", "brute_force_hidden_dirs"]
