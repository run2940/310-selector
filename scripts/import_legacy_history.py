"""Copy missing historical dates from the old project without overwriting new XQ imports."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from import_xq_data import DB_PATH, TABLE_NAME, rebuild_strength_history


OLD_DB_PATH = Path(r"C:\stock_selector\data\stock_selector.db")


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def main() -> None:
    if not OLD_DB_PATH.exists():
        raise SystemExit(f"找不到舊專案資料庫：{OLD_DB_PATH}")
    if not DB_PATH.exists():
        raise SystemExit(f"找不到新專案資料庫：{DB_PATH}；請先匯入 XQ CSV。")

    with sqlite3.connect(OLD_DB_PATH) as source, sqlite3.connect(DB_PATH) as target:
        source.row_factory = sqlite3.Row
        source_columns = source.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()
        if not source_columns:
            raise SystemExit("舊專案找不到選股歷史資料表。")
        columns = [row[1] for row in source_columns]
        target_columns = {row[1] for row in target.execute(f"PRAGMA table_info({TABLE_NAME})")}
        for row in source_columns:
            name, sql_type = row[1], row[2] or "TEXT"
            if name not in target_columns:
                target.execute(f"ALTER TABLE {TABLE_NAME} ADD COLUMN {quote(name)} {sql_type}")

        latest = source.execute(f"SELECT MAX(\"資料日期\") FROM {TABLE_NAME}").fetchone()[0]
        cutoff = (datetime.fromisoformat(latest) - timedelta(days=365)).strftime("%Y-%m-%d") if latest else "0000-01-01"
        existing_dates = {row[0] for row in target.execute(f"SELECT DISTINCT \"資料日期\" FROM {TABLE_NAME}")}
        missing_dates = [
            row[0] for row in source.execute(
                f"SELECT DISTINCT \"資料日期\" FROM {TABLE_NAME} WHERE \"資料日期\" >= ? ORDER BY \"資料日期\"",
                (cutoff,),
            ) if row[0] not in existing_dates
        ]
        copied_rows = 0
        insert_sql = f"INSERT INTO {TABLE_NAME} ({', '.join(quote(column) for column in columns)}) VALUES ({', '.join('?' for _ in columns)})"
        for date_value in missing_dates:
            records = source.execute(
                f"SELECT {', '.join(quote(column) for column in columns)} FROM {TABLE_NAME} WHERE \"資料日期\" = ?",
                (date_value,),
            ).fetchall()
            target.executemany(insert_sql, [[record[column] for column in columns] for record in records])
            copied_rows += len(records)

        rebuild_strength_history(target)
        target.commit()

    print(f"已補入 {len(missing_dates)} 個資料日期、{copied_rows} 筆歷史資料。")


if __name__ == "__main__":
    main()
