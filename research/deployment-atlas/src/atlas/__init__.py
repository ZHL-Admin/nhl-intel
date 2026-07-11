"""Deployment Atlas — NHL shift-chart & play-by-play research pipeline.

Reconstructs on-ice presence for every second of every game and produces
context-corrected player ratings and coach deployment fingerprints. Research
repo; isolated from the production site under ``NIR/research/deployment-atlas``.
"""

from . import config

__all__ = ["config"]
__version__ = "0.1.0"
