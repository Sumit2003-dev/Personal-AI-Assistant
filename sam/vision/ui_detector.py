"""
SAM - OpenCV UI Element Detection & Visual Locator
Locates UI elements, buttons, and icons without relying solely on fixed screen coordinates.
"""

from typing import Optional, Tuple, List, Dict, Any
from PIL import Image
import numpy as np
import cv2


class UIDetector:
    """Uses OpenCV template matching and contour detection to locate UI elements."""

    @staticmethod
    def locate_template_on_screen(
        screen_img: Image.Image,
        template_img: Image.Image,
        threshold: float = 0.8,
    ) -> Optional[Dict[str, Any]]:
        """
        Locates a template image inside the screen image.
        Returns {'center_x', 'center_y', 'bbox': (x, y, w, h), 'confidence': float}
        """
        screen_cv = cv2.cvtColor(np.array(screen_img.convert("RGB")), cv2.COLOR_RGB2BGR)
        templ_cv = cv2.cvtColor(np.array(template_img.convert("RGB")), cv2.COLOR_RGB2BGR)

        res = cv2.matchTemplate(screen_cv, templ_cv, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

        if max_val >= threshold:
            h, w = templ_cv.shape[:2]
            top_left = max_loc
            center_x = top_left[0] + w // 2
            center_y = top_left[1] + h // 2
            return {
                "center_x": center_x,
                "center_y": center_y,
                "bbox": (top_left[0], top_left[1], w, h),
                "confidence": round(float(max_val), 3),
            }
        return None

    @staticmethod
    def detect_interactive_regions(screen_img: Image.Image) -> List[Dict[str, Any]]:
        """Detects high-contrast button/input rectangular regions using Canny edges & contours."""
        screen_cv = cv2.cvtColor(np.array(screen_img.convert("RGB")), cv2.COLOR_RGB2GRAY)
        blurred = cv2.GaussianBlur(screen_cv, (5, 5), 0)
        edged = cv2.Canny(blurred, 50, 150)

        contours, _ = cv2.findContours(edged, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        elements = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            # Filter for button-like proportions
            if 30 <= w <= 400 and 15 <= h <= 100:
                elements.append({
                    "bbox": (x, y, w, h),
                    "center": (x + w // 2, y + h // 2),
                    "area": w * h,
                })
        return elements[:50]


ui_detector = UIDetector()

