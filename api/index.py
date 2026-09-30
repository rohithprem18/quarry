"""Vercel entry point: every /api/* request is routed here."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from quarry.app import app  # noqa: E402,F401
