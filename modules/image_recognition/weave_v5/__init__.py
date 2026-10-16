"""Standalone V5 fabric weave candidate recognition.

Use run(image, out, rois=3) to receive a structured candidate report.
"""
from .run_photo_weave_v5 import run, choose_rois, summarize

__all__ = ["run", "choose_rois", "summarize"]
