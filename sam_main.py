"""
SAM Desktop Application — Main Entry Point
This is the script that PyInstaller uses as the entry point: sam_main.py
"""
import sys

if __name__ == "__main__":
    if "--backend-server" in sys.argv:
        try:
            from sam_backend_runner import main as run_backend
        except ImportError:
            from sam.sam_backend_runner import main as run_backend
        run_backend()
        sys.exit(0)

    from sam.launcher.app_launcher import main
    sys.exit(main())

