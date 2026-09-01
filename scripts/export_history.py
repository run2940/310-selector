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
from datetime import date, datetime, timedelta
from pathlib import Path


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
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
        encoding="utf-8",
    )


def export_market_strength(source_db: Path, output_dir: Path) -> str | None:
    """Export the small market-atmosphere history when it is available."""
    source_path = source_db.parent / "market_strength.csv"
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


def export_history(source_db: Path, output_dir: Path, days: int) -> tuple[int, int]:
    if not source_db.exists():
        raise FileNotFoundError(f"找不到來源 SQLite：{source_db}")

    with sqlite3.connect(source_db) as connection:
        connection.row_factory = sqlite3.Row
        table_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE_NAME,)
        ).fetchone()
        if table_exists is None:
            raise RuntimeError(f"SQLite 找不到資料表：{TABLE_NAME}")

        latest_date = connection.execute(
            f'SELECT MAX("資料日期") FROM "{TABLE_NAME}"'
        ).fetchone()[0]
        if not latest_date:
            raise RuntimeError("SQLite 尚未有可匯出的歷史資料。")

        start_date = (date.fromisoformat(latest_date) - timedelta(days=days - 1)).isoformat()
        dates = [
            row[0]
            for row in connection.execute(
                f'''SELECT DISTINCT "資料日期" FROM "{TABLE_NAME}"
                    WHERE "資料日期" >= ? ORDER BY "資料日期" DESC''',
                (start_date,),
            )
        ]
        columns = [
            row[1]
            for row in connection.execute(f'PRAGMA table_info("{TABLE_NAME}")')
            if row[1] not in METADATA_COLUMNS
        ]

        snapshot_root = output_dir / "snapshots"
        index_dates = []
        file_count = 0

        for report_date in dates:
            records = connection.execute(
                f'''SELECT * FROM "{TABLE_NAME}"
                    WHERE "資料日期" = ?
                    ORDER BY "來源檔案", "來源順位", "序號"''',
                (report_date,),
            ).fetchall()
            grouped: dict[str, list[sqlite3.Row]] = {}
            for record in records:
                grouped.setdefault(record["來源檔案"], []).append(record)

            strategies = []
            for source_file, strategy_records in grouped.items():
                slug, label = strategy_details(source_file)
                updated_at = max(
                    (record["匯入時間"] for record in strategy_records if record["匯入時間"]),
                    default=None,
                )
                payload = {
                    "schema": 1,
                    "date": report_date,
                    "strategy": {"id": slug, "label": label, "source": source_file},
                    "updated_at": updated_at,
                    "columns": columns,
                    "rows": [[record[column] for column in columns] for record in strategy_records],
                }
                relative_path = Path("snapshots") / report_date / f"{slug}.json"
                write_json(output_dir / relative_path, payload)
                strategies.append(
                    {
                        "id": slug,
                        "label": label,
                        "rows": len(strategy_records),
                        "file": relative_path.as_posix(),
                    }
                )
                file_count += 1

            index_dates.append({"date": report_date, "strategies": strategies})

    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    market_strength_file = export_market_strength(source_db, output_dir)
    write_json(
        output_dir / "index.json",
        {
            "schema": 1,
            "generated_at": generated_at,
            "history_days": days,
            "latest_date": latest_date,
            "dates": index_dates,
            "market_strength_file": market_strength_file,
        },
    )
    return len(index_dates), file_count


def main() -> None:
    parser = argparse.ArgumentParser(description="將舊 SQLite 歷史資料轉為日期分檔 JSON。")
    parser.add_argument("--source-db", type=Path, default=DEFAULT_SOURCE_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--days", type=int, default=365)
    args = parser.parse_args()

    if args.days < 1:
        parser.error("--days 必須大於或等於 1")

    date_count, file_count = export_history(args.source_db, args.output_dir, args.days)
    print(f"已匯出 {date_count} 個資料日期、{file_count} 個策略 JSON。")
    print(f"輸出位置：{args.output_dir}")


if __name__ == "__main__":
    main()
