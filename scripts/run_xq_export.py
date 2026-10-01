"""Run calibrated XQ strategies and export their CSV files."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import pyautogui
import pyperclip
from pywinauto import Desktop
import win32con
import win32gui


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config" / "xq_automation.json"
OUTPUT_DIR = PROJECT_ROOT / "XQ"
LOG_DIR = PROJECT_ROOT / "logs"
TRACE_PATH = LOG_DIR / "xq_export_trace.log"
STRATEGIES = [
    ("rs_weighted", "RS加權.csv"),
    ("deviation_rebound", "天花板地板.csv"),
    ("main_buy_up", "主力買向上.csv"),
    ("disposition", "處置股.csv"),
]
RESULTS_TOP_OFFSET = 410
START_BUTTON_LEFT = 386
STOP_BUTTON_LEFT = 457
SELECTION_START_TIMEOUT_SECONDS = 15
SELECTION_COMPLETE_TIMEOUT_SECONDS = 600


def selection_center():
    windows = [
        window
        for window in Desktop(backend="uia").windows()
        if window.class_name() == "AfxFrameOrView140"
    ]
    if not windows:
        raise RuntimeError("Open XQ Selection Center before running the export.")
    window = windows[0]
    return window


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
    """Restore the splitter position used during coordinate calibration."""
    activate_window(window)
    time.sleep(1)
    rect = window.rectangle()
    if rect.width() < 1800:
        raise RuntimeError("Could not maximize XQ Selection Center for the export.")

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


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise RuntimeError("Run 校正XQ自動化.bat first.")
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if config.get("schema") != 5:
        raise RuntimeError("Run 校正XQ自動化.bat again to update the calibration.")
    return config


def point(window, config: dict, name: str) -> tuple[int, int]:
    try:
        relative = config["points"][name]
    except KeyError as error:
        raise RuntimeError(f"Missing calibration point: {name}") from error
    rect = window.rectangle()
    return rect.left + relative["x"], rect.top + relative["y"]


def select_strategy(window, config: dict, name: str) -> None:
    activate_window(window)
    pyautogui.click(*point(window, config, name))
    time.sleep(0.4)


def start_stop_buttons(window):
    """Find the two stateful XQ toolbar buttons without relying on garbled titles."""
    rect = window.rectangle()
    buttons = [
        button
        for button in window.descendants(control_type="Button")
        if rect.top + 30 <= button.rectangle().top <= rect.top + 70
    ]
    start = next(
        (button for button in buttons if rect.left + START_BUTTON_LEFT <= button.rectangle().left < rect.left + STOP_BUTTON_LEFT),
        None,
    )
    stop = next(
        (button for button in buttons if rect.left + STOP_BUTTON_LEFT <= button.rectangle().left < rect.left + 528),
        None,
    )
    if not start or not stop:
        raise RuntimeError("Could not find XQ's Start and Stop buttons.")
    return start, stop


def wait_for_selection_complete(window) -> None:
    """Wait for XQ's actual running state instead of using a guessed duration."""
    start, stop = start_stop_buttons(window)
    deadline = time.monotonic() + SELECTION_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if stop.is_enabled():
            trace("XQ selection is running")
            break
        time.sleep(0.2)
    else:
        raise RuntimeError("XQ selection did not start; Export was not attempted.")

    deadline = time.monotonic() + SELECTION_COMPLETE_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if start.is_enabled() and not stop.is_enabled():
            trace("XQ selection completed")
            return
        time.sleep(0.5)
    raise RuntimeError("XQ selection did not finish within 10 minutes; Export was not attempted.")


def write_log(lines: list[str]) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    path = LOG_DIR / f"xq_export_{datetime.now():%Y%m%d_%H%M%S}.log"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Log saved to {path}")


def trace(message: str) -> None:
    """Persist progress because the XQ window intentionally takes foreground."""
    LOG_DIR.mkdir(exist_ok=True)
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}"
    with TRACE_PATH.open("a", encoding="utf-8") as file:
        file.write(line + "\n")
    print(line, flush=True)


def preview(window, config: dict, strategies: list[tuple[str, str]]) -> None:
    print("Preview only. No XQ controls will be clicked.")
    for key, filename in strategies:
        print(f"{filename}: strategy={point(window, config, key)}")
    print(f"Common category={point(window, config, 'common_category')}")
    print(f"Start={point(window, config, 'start')}")
    print(f"Export={point(window, config, 'export')}")


def save_csv(output_path: Path, export_wait: float) -> None:
    pyperclip.copy(str(output_path))
    pyautogui.hotkey("alt", "n")
    time.sleep(0.3)
    pyautogui.hotkey("ctrl", "a")
    pyautogui.hotkey("ctrl", "v")
    pyautogui.hotkey("alt", "s")
    time.sleep(export_wait)
    # XQ displays the overwrite confirmation with the Y accelerator.
    pyautogui.hotkey("alt", "y")


def run(window, config: dict, strategies: list[tuple[str, str]]) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    started = time.time()
    log_lines = [f"Started: {datetime.now().isoformat(timespec='seconds')}"]
    pyautogui.PAUSE = 0.4
    pyautogui.FAILSAFE = True
    trace("Activated XQ and selecting Common category")
    activate_window(window)
    pyautogui.click(*point(window, config, "common_category"))
    time.sleep(0.8)

    for key, filename in strategies:
        output_path = OUTPUT_DIR / filename
        trace(f"Selecting strategy for {filename}")
        select_strategy(window, config, key)
        time.sleep(0.8)
        trace(f"Starting selection for {filename}")
        activate_window(window)
        pyautogui.click(*point(window, config, "start"))
        wait_for_selection_complete(window)
        trace(f"Opening export dialog for {filename}")
        activate_window(window)
        pyautogui.click(*point(window, config, "export"))
        time.sleep(0.8)
        trace(f"Saving {output_path}")
        save_csv(output_path, float(config["wait_after_export_seconds"]))
        time.sleep(0.8)
        if not output_path.exists() or output_path.stat().st_mtime < started:
            trace(f"FAILED: XQ did not update {output_path}")
            raise RuntimeError(f"XQ did not update {output_path}")
        trace(f"Exported {output_path}")
        log_lines.append(f"Exported: {output_path}")

    log_lines.append("Result: success")
    write_log(log_lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true", help="Click XQ and export CSV files")
    parser.add_argument(
        "--strategy",
        choices=[key for key, _ in STRATEGIES],
        help="Run only one calibrated strategy",
    )
    args = parser.parse_args()
    try:
        config = load_config()
        window = selection_center()
        normalize_layout(window)
        strategies = [item for item in STRATEGIES if item[0] == args.strategy] if args.strategy else STRATEGIES
        if args.run:
            run(window, config, strategies)
        else:
            preview(window, config, strategies)
    except Exception as error:
        trace(f"ERROR: {type(error).__name__}: {error}")
        raise


if __name__ == "__main__":
    main()
