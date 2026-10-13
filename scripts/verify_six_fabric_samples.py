#!/usr/bin/env python3
"""Verify uploaded original & unmarked zoom files; no assistant annotations."""
from import_six_fabric_for_manual_annotation import validate_local

if __name__ == "__main__":
    raise SystemExit(validate_local(require_images=True))
