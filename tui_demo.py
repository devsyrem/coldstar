#!/usr/bin/env python3
"""
Launch the new Coldstar TUI interface
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from tui_app import run_tui

if __name__ == "__main__":
    print("Launching Coldstar TUI Dashboard...")
    print("Press 'q' or ESC to quit\n")
    run_tui()
