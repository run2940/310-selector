"""Record XQ Selection Center click points relative to its window."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pyautogui
from pynput import keyboard
from pywinauto import Desktop
import win32con
import win32gui


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config" / "xq_automation.json"
TARGETS = [
    ("common_category", "Common category in the left panel"),
    ("rs_weighted", "RS weighted strategy row"),
    ("deviation_rebound", "Deviation rebound strategy row"),
    ("main_buy_up", "Main-buy-up strategy row"),
    ("disposition", "Disposition strategy row"),
    ("start", "Start button"),
    ("export", "Export button in the result toolbar"),
]
RESULTS_TOP_OFFSET = 410


def selection_center():
    windows = [
        window
        for window in Desktop(backend="uia").windows()
        if window.class_name() == "AfxFrameOrView140"
    ]
    if not windows:
        raise RuntimeError("Open XQ Selection Center before running calibration.")
    return windows[0]


def activate_window(window) -> None:
    """Force the XQ window above the batch/terminal before coordinate actions."""
    handle = window.handle
    win32gui.ShowWindow(handle, win32con.SW_MAXIMIZE)
    win32gui.SetWindowPos(
        handle,
        win32con.HWND_TOPMOST,
        0,
        0,
        0,
        0,
        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE,
    )
    win32gui.SetForegroundWindow(handle)
    time.sleep(0.3)
    win32gui.SetWindowPos(
        handle,
        win32con.HWND_NOTOPMOST,
        0,
        0,
        0,
        0,
        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE,
    )
    if win32gui.GetForegroundWindow() != handle:
        raise RuntimeError("Could not bring XQ Selection Center to the foreground.")


def normalize_layout(window) -> None:
    """Move XQ's horizontal splitter so calibrated controls stay in one place."""
    activate_window(window)
    time.sleep(1)
    rect = window.rectangle()
    if rect.width() < 1800:
        raise RuntimeError("Could not maximize XQ Selection Center for calibration.")

    dialog = Desktop(backend="uia").window(handle=window.handle)
    result_panes = [
        pane
        for pane in dialog.descendants(control_type="Pane")
        if pane.element_info.automation_id == "59664"
    ]
    if not result_panes:
        raise RuntimeError("Could not find XQ's result pane.")

    current_top = result_panes[0].rectangle().top
    target_top = rect.top + RESULTS_TOP_OFFSET
    if abs(current_top - target_top) < 8:
        return

    splitter_x = rect.left + min(800, rect.width() // 2)
    pyautogui.moveTo(splitter_x, current_top - 3)
    pyautogui.dragTo(splitter_x, target_top, duration=0.6, button="left")
    time.sleep(0.8)

    updated_top = result_panes[0].rectangle().top
    if abs(updated_top - target_top) > 24:
        raise RuntimeError("Could not reset the XQ panel layout. Please check the splitter.")


def main() -> None:
    window = selection_center()
    normalize_layout(window)
    rect = window.rectangle()
    captured: dict[str, dict[str, int]] = {}
    index = 0

    print("Keep XQ visible and maximized.")
    print("Move the mouse to each point and press F8. Press F12 to cancel.")
    print(f"Target 1/{len(TARGETS)}: {TARGETS[0][1]}")

    def on_press(key):
        nonlocal index
        if key == keyboard.Key.f12:
            return False
        if index >= len(TARGETS):
            return
        if key != keyboard.Key.f8:
            return

        name, label = TARGETS[index]
        x, y = pyautogui.position()
        if not (rect.left <= x <= rect.right and rect.top <= y <= rect.bottom):
            print("Mouse must be inside the XQ Selection Center window.")
            return

        captured[name] = {"x": x - rect.left, "y": y - rect.top}
        print(f"Captured {label}: {captured[name]}")
        index += 1
        if index == len(TARGETS):
            return False
        print(f"Target {index + 1}/{len(TARGETS)}: {TARGETS[index][1]}")

    with keyboard.Listener(on_press=on_press) as key_listener:
        key_listener.join()

    expected_targets = {name for name, _ in TARGETS}
    if set(captured) != expected_targets:
        print("Calibration cancelled. No configuration was saved.")
        return

    config = {
        "schema": 5,
        "wait_after_start_seconds": 20,
        "wait_after_export_seconds": 2,
        "points": captured,
    }
    CONFIG_PATH.parent.mkdir(exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"Saved calibration to {CONFIG_PATH}")


if __name__ == "__main__":
    main()
