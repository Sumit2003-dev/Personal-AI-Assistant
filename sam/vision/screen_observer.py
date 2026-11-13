"""
SAM - Screen Observation & Visual Change Verification
Captures desktop frames, computes perceptual diffs, and verifies visual state changes.
"""

from pathlib import Path
from typing import Optional, Tuple
import time
import hashlib
from PIL import Image, ImageGrab
import numpy as np
import cv2
from sam.config.settings import settings

SCREENSHOT_DIR = settings.data_dir / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


class ScreenObserver:
    """Captures and analyzes desktop frames."""

    def __init__(self):
        self.screenshot_dir = SCREENSHOT_DIR

    def _capture_gdi(self) -> Image.Image:
        """Captures primary screen via native Win32 GDI BitBlt as a reliable fallback."""
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        w = user32.GetSystemMetrics(0) or 1920
        h = user32.GetSystemMetrics(1) or 1080

        hdesktop = user32.GetDesktopWindow()
        hdc = user32.GetWindowDC(hdesktop)
        memdc = gdi32.CreateCompatibleDC(hdc)
        hbitmap = gdi32.CreateCompatibleBitmap(hdc, w, h)
        old_bmp = gdi32.SelectObject(memdc, hbitmap)

        SRCCOPY = 0x00CC0020
        gdi32.BitBlt(memdc, 0, 0, w, h, hdc, 0, 0, SRCCOPY)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = w
        bmi.biHeight = -h  # top-down
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0

        buffer = (ctypes.c_ubyte * (w * h * 4))()
        gdi32.GetDIBits(hdc, hbitmap, 0, h, ctypes.byref(buffer), ctypes.byref(bmi), 0)

        gdi32.SelectObject(memdc, old_bmp)
        gdi32.DeleteObject(hbitmap)
        gdi32.DeleteDC(memdc)
        user32.ReleaseDC(hdesktop, hdc)

        return Image.frombuffer("RGBA", (w, h), buffer, "raw", "BGRA", 0, 1).convert("RGB")

    def capture_fullscreen(self, save: bool = True) -> Tuple[Image.Image, Optional[Path]]:
        img = None
        for attempt in range(2):
            try:
                img = ImageGrab.grab(all_screens=True)
                break
            except Exception:
                try:
                    img = ImageGrab.grab()
                    break
                except Exception:
                    time.sleep(0.1)

        if img is None:
            try:
                img = self._capture_gdi()
            except Exception:
                # Last resort fallback image matching display metrics
                import ctypes
                w = ctypes.windll.user32.GetSystemMetrics(0) or 1920
                h = ctypes.windll.user32.GetSystemMetrics(1) or 1080
                img = Image.new("RGB", (w, h), color=(30, 30, 30))

        saved_path = None
        if save:
            filename = f"frame_{int(time.time() * 1000)}.png"
            saved_path = self.screenshot_dir / filename
            img.save(saved_path, format="PNG")
        return img, saved_path

    def capture_region(self, bbox: Tuple[int, int, int, int], save: bool = False) -> Tuple[Image.Image, Optional[Path]]:
        """bbox is (left, top, right, bottom)."""
        try:
            img = ImageGrab.grab(bbox=bbox)
        except Exception:
            full_img, _ = self.capture_fullscreen(save=False)
            img = full_img.crop(bbox)

        saved_path = None
        if save:
            filename = f"region_{int(time.time() * 1000)}.png"
            saved_path = self.screenshot_dir / filename
            img.save(saved_path, format="PNG")
        return img, saved_path

    @staticmethod
    def compute_visual_hash(img: Image.Image) -> str:
        """Computes a 64-bit difference hash (dHash) for visual comparison."""
        resized = img.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
        pixels = list(resized.tobytes())
        diff = []
        for row in range(8):
            for col in range(8):
                idx = row * 9 + col
                diff.append(pixels[idx] > pixels[idx + 1])
        return "".join(["1" if b else "0" for b in diff])

    @staticmethod
    def compute_diff_ratio(img1: Image.Image, img2: Image.Image) -> float:
        """Returns visual difference ratio between 0.0 (identical) and 1.0 (completely different)."""
        arr1 = np.array(img1.convert("RGB"))
        arr2 = np.array(img2.convert("RGB"))

        if arr1.shape != arr2.shape:
            # Resize img2 to match img1
            arr2 = cv2.resize(arr2, (arr1.shape[1], arr1.shape[0]))

        diff = cv2.absdiff(arr1, arr2)
        gray = cv2.cvtColor(diff, cv2.COLOR_RGB2GRAY)
        changed_pixels = np.count_nonzero(gray > 15)
        total_pixels = gray.size
        return round(changed_pixels / total_pixels, 4)

    def verify_action_effect(self, before_img: Image.Image, after_img: Image.Image, min_diff: float = 0.005) -> bool:
        """Verifies if an action produced an observable visual change on screen."""
        diff_ratio = self.compute_diff_ratio(before_img, after_img)
        return diff_ratio >= min_diff


screen_observer = ScreenObserver()
