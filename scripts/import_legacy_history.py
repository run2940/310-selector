"""Copy missing historical dates from the old project without overwriting new XQ imports."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

from import_xq_data import DB_PATH, TABLE_NAME, rebuild_strength_history
from monthly_history import database_paths, migrate_legacy, monthly_path, prune_history, read_connection, write_group


OLD_DB_PATH = Path(r"C:\stock_selector\data\stock_selector.db")


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def main() -> None:
    sources = database_paths(OLD_DB_PATH)
    if not sources:
        raise SystemExit(f"找不到舊專案歷史資料：{OLD_DB_PATH}")
    migrate_legacy(DB_PATH)
    copied_rows = 0
    copied_dates = set()
    for filename in sources:
        with closing(read_connection(filename)) as source:
            source.row_factory = sqlite3.Row
            schema = {row[1]: row[2] or "TEXT" for row in source.execute(f"PRAGMA table_info({TABLE_NAME})")}
            groups = source.execute(f'SELECT DISTINCT "資料日期", "來源檔案" FROM {TABLE_NAME}').fetchall()
            for day, name in groups:
                target = monthly_path(DB_PATH, day)
                if target.exists():
                    with closing(read_connection(target)) as connection:
                        if connection.execute(f'SELECT 1 FROM {TABLE_NAME} WHERE "資料日期"=? AND "來源檔案"=?',
                                              (day, name)).fetchone():
                            continue
                rows = [dict(row) for row in source.execute(
                    f'SELECT * FROM {TABLE_NAME} WHERE "資料日期"=? AND "來源檔案"=?', (day, name))]
                copied_rows += write_group(DB_PATH, day, name, rows, schema)
                copied_dates.add(day)
    prune_history(DB_PATH)
    rebuild_strength_history(DB_PATH)
    print(f"已補入 {len(copied_dates)} 個資料日期、{copied_rows} 筆歷史資料。")


if __name__ == "__main__":
    main()
