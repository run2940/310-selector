"""Refresh the static site's Taiwan Futures Exchange stock futures list."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen


SOURCE_URL = "https://www.taifex.com.tw/cht/2/stockLists"
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "site" / "data" / "stock_futures.json"
TAIPEI = timezone(timedelta(hours=8))


class StockListParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.row: list[str] | None = None
        self.cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self.row = []
        elif tag == "td" and self.row is not None:
            self.cell = []

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self.cell is not None and self.row is not None:
            self.row.append("".join(self.cell).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None


def parse_stock_futures(html: str) -> list[str]:
    parser = StockListParser()
    parser.feed(html)
    codes = {
        row[2]
        for row in parser.rows
        if len(row) >= 9
        and re.fullmatch(r"\d{4}", row[2])
        and "是股票期貨標的" in row[4]
        and ("是上市普通股標的證券" in row[7] or "是上櫃普通股標的證券" in row[8])
    }
    if len(codes) < 100:
        raise ValueError(f"Unexpected TAIFEX stock futures count: {len(codes)}")
    return sorted(codes)


def refresh_stock_futures(path: Path = OUTPUT_PATH) -> bool:
    attempted_at = datetime.now(TAIPEI).isoformat(timespec="seconds")
    try:
        request = Request(SOURCE_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=20) as response:
            html = response.read().decode("utf-8-sig")
        codes = parse_stock_futures(html)
        payload = {
            "source": SOURCE_URL,
            "checked_at": attempted_at,
            "last_attempt_at": attempted_at,
            "last_attempt_ok": True,
            "codes": codes,
        }
        write_payload(path, payload)
        print(f"Updated stock futures list: {len(codes)} stocks")
        return True
    except (OSError, UnicodeError, ValueError) as error:
        payload = load_payload(path)
        if payload:
            payload["last_attempt_at"] = attempted_at
            payload["last_attempt_ok"] = False
            write_payload(path, payload)
        print(f"Stock futures update failed; keeping previous list: {error}")
        return False


def write_payload(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def load_payload(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError):
        return {}


if __name__ == "__main__":
    refresh_stock_futures()
