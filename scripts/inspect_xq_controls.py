"""Save a readable inventory of the currently open XQ Selection Center window."""

from __future__ import annotations

from pathlib import Path

from pywinauto import Desktop


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "logs" / "xq_controls.txt"


def main() -> None:
    windows = [
        window
        for window in Desktop(backend="uia").windows()
        if "XQ" in window.window_text() or "選股中心" in window.window_text()
    ]
    if not windows:
        raise RuntimeError("XQ Selection Center is not open.")

    selection_center = next(
        (window for window in windows if "選股中心" in window.window_text()),
        windows[0],
    )
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    dialog = Desktop(backend="uia").window(handle=selection_center.handle)
    dialog.print_control_identifiers(depth=4, filename=str(OUTPUT_PATH))
    print(f"Saved XQ controls to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
