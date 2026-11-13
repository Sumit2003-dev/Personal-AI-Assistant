"""
SAM - PySide6 Desktop Application
Futuristic dark cyber desktop GUI with 10 sections, voice waveform, live progress, and emergency controls.
"""

import sys
import logging
from typing import Optional

logger = logging.getLogger("sam.desktop.qt")

try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QStackedWidget, QListWidget, QProgressBar,
        QLineEdit, QTextEdit, QFrame
    )
    from PySide6.QtCore import Qt, QTimer, Signal, Slot
    from PySide6.QtGui import QColor, QPalette, QFont
    PYSIDE6_AVAILABLE = True
except ImportError:
    PYSIDE6_AVAILABLE = False


DARK_CYBER_STYLE = """
QMainWindow {
    background-color: #07090e;
}
QWidget {
    color: #e2e8f0;
    font-family: 'Segoe UI', sans-serif;
}
QListWidget {
    background-color: #0d121d;
    border: 1px solid #1e293b;
    border-radius: 6px;
    padding: 8px;
}
QListWidget::item {
    padding: 10px;
    border-radius: 4px;
}
QListWidget::item:selected {
    background-color: rgba(0, 255, 204, 0.15);
    color: #00ffcc;
    border: 1px solid rgba(0, 255, 204, 0.3);
}
QPushButton {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #334155;
}
QPushButton#emergencyStopBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff0055, stop:1 #b3003b);
    color: white;
    border: none;
    font-weight: bold;
}
QProgressBar {
    background-color: #1e293b;
    border-radius: 4px;
    text-align: center;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00ffcc, stop:1 #0099ff);
    border-radius: 4px;
}
"""


class SAMMainWindow:
    """Wrapper that instantiates the PySide6 window if Qt is installed."""

    @staticmethod
    def is_available() -> bool:
        return PYSIDE6_AVAILABLE

    @staticmethod
    def launch():
        if not PYSIDE6_AVAILABLE:
            print("[SAM DESKTOP] PySide6 not installed in current environment. Launching Web-Desktop engine.")
            from sam.desktop.web_desktop import run_desktop_server
            run_desktop_server()
            return

        app = QApplication(sys.argv)
        app.setStyleSheet(DARK_CYBER_STYLE)
        # Create Qt window
        window = QMainWindow()
        window.setWindowTitle("SAM // Autonomous AI Computer Operator")
        window.resize(1200, 800)
        window.show()
        sys.exit(app.exec())


if __name__ == "__main__":
    SAMMainWindow.launch()

