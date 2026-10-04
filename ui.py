"""Điểm vào giao diện PyQt6. Chạy: python ui.py"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.app import main

if __name__ == "__main__":
    sys.exit(main())
