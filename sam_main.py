"""
SAM Desktop Application — Main Entry Point
This is the script that PyInstaller uses as the entry point: sam_main.py
"""
import sys
from sam.launcher.app_launcher import main

if __name__ == "__main__":
    sys.exit(main())
