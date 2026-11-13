import subprocess
import time
import ctypes
import sys
from pathlib import Path

SAM_ROOT = Path(__file__).resolve().parent.parent
if str(SAM_ROOT) not in sys.path:
    sys.path.insert(0, str(SAM_ROOT))

from sam.computer_use.keyboard import keyboard_controller
from sam.vision.screen_observer import screen_observer

user32 = ctypes.windll.user32

test_file = Path("test_save_notepad.txt").resolve()
test_file.write_text("INIT\n", encoding="utf-8")

p = subprocess.Popen(["notepad.exe", str(test_file)])
time.sleep(1.5)

h = user32.FindWindowW("Notepad", None)
print("Notepad window:", h)
if h:
    # Force bring to foreground using Alt trick + AttachThreadInput
    kernel32 = ctypes.windll.kernel32
    cur_thread = kernel32.GetCurrentThreadId()
    win_thread = user32.GetWindowThreadProcessId(h, None)
    user32.AttachThreadInput(cur_thread, win_thread, True)
    user32.keybd_event(0x12, 0, 0, 0)
    user32.SetForegroundWindow(h)
    user32.keybd_event(0x12, 0, 2, 0)
    user32.SetFocus(h)
    user32.AttachThreadInput(cur_thread, win_thread, False)
    time.sleep(0.5)

    # Click on the client area to guarantee text focus
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(rect))
    from sam.computer_use.mouse import mouse_controller
    mouse_controller.click(rect.left + 250, rect.top + 250)
    time.sleep(0.5)

    # Select existing text and delete
    keyboard_controller.hotkey("ctrl", "a")
    time.sleep(0.2)

    # Type new text directly
    new_content = "SAM Windows 11 Live Computer-Use Operator Verified Successfully."
    keyboard_controller.write_text(new_content, delay_per_char=0.01)
    time.sleep(0.5)

    # Save via Ctrl+S
    keyboard_controller.hotkey("ctrl", "s")
    time.sleep(1.0)

    # Capture screenshot
    img, shot_path = screen_observer.capture_fullscreen(save=True)
    print("Screenshot saved to:", shot_path)

    # Close Notepad
    user32.PostMessageW(h, 0x0010, 0, 0)
    time.sleep(0.5)
    if p.poll() is None:
        p.terminate()

time.sleep(0.5)
content = test_file.read_text(encoding="utf-8")
print("Saved file content:", repr(content))
print("Verified match:", (new_content in content))
