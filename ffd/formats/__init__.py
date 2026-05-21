"""Miscellaneous small format parsers that don't have a dedicated tab.

Currently just ``parse_form_bin`` (enemy formations).
"""

from .form_bin import parse_form_bin

__all__ = ["parse_form_bin"]
