"""Export the existing XQ SQLite history into small, date-based JSON files.

This script is read-only with respect to the current Streamlit project. It is
the first migration step for a future static site: the browser will fetch only
the selected date and strategy instead of downloading an entire history.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from monthly_history import cutoff_date, database_paths, history_dir, latest_date, quote, read_connection


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DB = PROJECT_ROOT / "data" / "stock_selector.db"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "site" / "data"
TABLE_NAME = "xq_history"
METADATA_COLUMNS = {"資料日期", "來源檔案", "來源標題", "來源順位", "匯入時間"}
STRATEGY_LABELS = {
    "RS加權.csv": ("rs-weighted", "RS加權"),
    "主力買向上.csv": ("main-buy-up", "主力買向上"),
    "天花板地板.csv": ("deviation-rebound", "乖離大反彈"),
    "處置股.csv": ("disposition", "處置股"),
}
TAIPEI_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Taipei")


def strategy_details(source_file: str) -> tuple[str, str]:
    """Return a stable browser file name and the website label."""
    if source_file in STRATEGY_LABELS:
        return STRATEGY_LABELS[source_file]
    stem = Path(source_file).stem
    slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    if not slug:
        slug = f"strategy-{hashlib.sha1(source_file.encode('utf-8')).hexdigest()[:8]}"
    return slug, stem


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if not path.exists() or path.read_text(encoding="utf-8") != content:
        path.write_text(content, encoding="utf-8")


def export_market_strength(source_db: Path, output_dir: Path) -> str | None:
    """Export the small market-atmosphere history when it is available."""
    source_path = history_dir(source_db).parent / "market_strength.csv"
    if not source_path.exists():
        return None

    with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        rows = [[row.get(column) or None for column in columns] for row in reader]

    relative_path = "market_strength.json"
    write_json(
        output_dir / relative_path,
        {"schema": 1, "columns": columns, "rows": rows},
    )
    return relative_path


def export_history(source_db: Path, output_dir: Path, days: int | None = None) -> tuple[int, int]:
    paths = database_paths(source_db)
    if not paths:
        raise FileNotFoundError(f"找不到歷史資料：{source_db}")
    latest = latest_date(source_db)
    if not latest:
        raise RuntimeError("尚未有可匯出的歷史資料。")
    start_date = ((date.fromisoformat(latest) - timedelta(days=days - 1)).isoformat()
                  if days is not None else cutoff_date(latest))
    columns = []
    for filename in paths:
        with closing(read_connection(filename)) as conn:
            for row in conn.execute(f'PRAGMA table_info("{TABLE_NAME}")'):
                if row[1] not in METADATA_COLUMNS and row[1] not in columns:
                    columns.append(row[1])
    index_dates = []
    file_count = 0
    for filename in paths:
        with closing(read_connection(filename)) as connection:
            connection.row_factory = sqlite3.Row
            dates = [row[0] for row in connection.execute(
                f'SELECT DISTINCT "資料日期" FROM {TABLE_NAME} WHERE "資料日期" >= ? ORDER BY "資料日期" DESC',
                (start_date,))]
            available = {row[1] for row in connection.execute(f'PRAGMA table_info("{TABLE_NAME}")')}
            ordering = ', '.join(quote(column) for column in ("來源檔案", "來源順位", "序號") if column in available)
            for report_date in dates:
                records = connection.execute(
                    f'SELECT * FROM {TABLE_NAME} WHERE "資料日期" = ? ORDER BY {ordering}',
                    (report_date,)).fetchall()
                grouped = {}
                for record in records:
                    grouped.setdefault(record["來源檔案"], []).append(dict(record))
                strategies = []
                for source_file, strategy_records in grouped.items():
                    slug, label = strategy_details(source_file)
                    updated_at = max((record.get("匯入時間") for record in strategy_records
                                      if record.get("匯入時間")), default=None)
                    payload = {
                        "schema": 1, "date": report_date,
                        "strategy": {"id": slug, "label": label, "source": source_file},
                        "updated_at": updated_at, "columns": columns,
                        "rows": [[record.get(column) for column in columns] for record in strategy_records],
                    }
                    relative_path = Path("snapshots") / report_date / f"{slug}.json"
                    write_json(output_dir / relative_path, payload)
                    strategies.append({"id": slug, "label": label, "rows": len(strategy_records),
                                       "file": relative_path.as_posix()})
                    file_count += 1
                index_dates.append({"date": report_date, "strategies": strategies})
    index_dates.sort(key=lambda item: item["date"], reverse=True)
    snapshot_root = output_dir / "snapshots"
    for folder in snapshot_root.iterdir() if snapshot_root.exists() else []:
        if folder.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", folder.name) and folder.name < start_date:
            for filename in folder.glob("*.json"):
                filename.unlink()
            if not any(folder.iterdir()):
                folder.rmdir()
    write_json(output_dir / "index.json", {
        "schema": 1, "generated_at": datetime.now(TAIPEI_TIMEZONE).isoformat(timespec="seconds"),
        "history_days": days, "history_years": 5 if days is None else None,
        "latest_date": latest, "dates": index_dates,
        "market_strength_file": export_market_strength(source_db, output_dir),
    })
    return len(index_dates), file_count


def main() -> None:
    parser = argparse.ArgumentParser(description="將舊 SQLite 歷史資料轉為日期分檔 JSON。")
    parser.add_argument("--source-db", type=Path, default=DEFAULT_SOURCE_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--days", type=int, default=None, help="選填；預設保留最近五個日曆年")
    args = parser.parse_args()

    if args.days is not None and args.days < 1:
        parser.error("--days 必須大於或等於 1")

    date_count, file_count = export_history(args.source_db, args.output_dir, args.days)
    print(f"已匯出 {date_count} 個資料日期、{file_count} 個策略 JSON。")
    print(f"輸出位置：{args.output_dir}")


if __name__ == "__main__":
    main()
