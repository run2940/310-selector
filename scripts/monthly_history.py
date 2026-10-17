"""Monthly SQLite storage shared by the Streamlit and static-site importers."""

from __future__ import annotations

import calendar
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import date, datetime
from pathlib import Path

TABLE = "xq_history"
YEARS = 5


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def cutoff_date(latest: str, years: int = YEARS) -> str:
    value = date.fromisoformat(latest)
    year = value.year - years
    return value.replace(year=year, day=min(value.day, calendar.monthrange(year, value.month)[1])).isoformat()


def history_dir(path: Path) -> Path:
    path = Path(path)
    return path.parent / "history" if path.suffix == ".db" else path


def legacy_path(path: Path) -> Path:
    path = Path(path)
    return path if path.suffix == ".db" else path.parent / "stock_selector.db"


def read_connection(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)


def database_paths(path: Path, report_date: str | None = None) -> list[Path]:
    legacy = legacy_path(path)
    # Until migration is complete, readers keep using the intact original.
    if legacy.exists():
        return [legacy]
    root = history_dir(path)
    if report_date:
        month = date.fromisoformat(report_date).strftime("%Y-%m")
        candidate = root / f"{month}.db"
        return [candidate] if candidate.exists() else []
    return sorted(root.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9].db"))


def monthly_path(path: Path, report_date: str) -> Path:
    return history_dir(path) / f"{date.fromisoformat(report_date):%Y-%m}.db"


def ensure_schema(conn: sqlite3.Connection, columns: dict[str, str]) -> None:
    conn.execute(f'CREATE TABLE IF NOT EXISTS {TABLE} ("資料日期" TEXT, "來源檔案" TEXT)')
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({TABLE})")}
    for name, kind in columns.items():
        if name not in existing:
            kind = kind.upper() if kind.upper() in {"TEXT", "REAL", "INTEGER", "BLOB", "NUMERIC"} else "TEXT"
            conn.execute(f"ALTER TABLE {TABLE} ADD COLUMN {quote(name)} {kind}")
    conn.execute(f'CREATE INDEX IF NOT EXISTS history_date_source ON {TABLE} ("資料日期", "來源檔案")')


def write_group(path: Path, report_date: str, source: str, rows: list[dict], types: dict[str, str],
                verify: bool = False) -> int:
    target = monthly_path(path, report_date)
    if any(row.get("資料日期") != report_date or row.get("來源檔案") != source for row in rows):
        raise ValueError("歷史資料日期或來源與歸檔目標不一致")
    target.parent.mkdir(parents=True, exist_ok=True)
    columns = list(types)
    for row in rows:
        for column in row:
            if column not in columns:
                columns.append(column)
    with closing(sqlite3.connect(target)) as conn, conn:
        ensure_schema(conn, {column: types.get(column, "TEXT") for column in columns})
        conn.execute(f'DELETE FROM {TABLE} WHERE "資料日期"=? AND "來源檔案"=?', (report_date, source))
        conn.executemany(
            f'INSERT INTO {TABLE} ({",".join(map(quote, columns))}) VALUES ({",".join("?" for _ in columns)})',
            [[row.get(column) for column in columns] for row in rows],
        )
        if verify:
            actual = conn.execute(
                f'SELECT {",".join(map(quote, columns))} FROM {TABLE} WHERE "資料日期"=? AND "來源檔案"=?',
                (report_date, source),
            ).fetchall()
            if Counter(tuple(row.get(column) for column in columns) for row in rows) != Counter(actual):
                raise RuntimeError("轉檔核對失敗，本次寫入已回復")
    return len(rows)


def migrate_legacy(path: Path) -> dict:
    """Backup first; verify every copied group before retiring the original."""
    legacy = legacy_path(path)
    if not legacy.exists():
        return {"migrated": False, "rows": 0}
    backup_root = legacy.parent / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    backup = backup_root / f"stock_selector-{datetime.now():%Y%m%d-%H%M%S-%f}.db"
    copied = 0
    with closing(read_connection(legacy)) as source:
        if source.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("原始資料庫完整性檢查失敗，停止轉檔")
        with closing(sqlite3.connect(backup)) as saved:
            source.backup(saved)
        schema = {row[1]: row[2] or "TEXT" for row in source.execute(f"PRAGMA table_info({TABLE})")}
        if not {"資料日期", "來源檔案"}.issubset(schema):
            raise RuntimeError("原始資料庫缺少歷史資料欄位")
        columns = list(schema)
        groups = source.execute(f'SELECT DISTINCT "資料日期", "來源檔案" FROM {TABLE}').fetchall()
        for day, name in groups:
            target = monthly_path(path, day)
            if target.exists():
                with closing(read_connection(target)) as conn:
                    if conn.execute(f'SELECT 1 FROM {TABLE} WHERE "資料日期"=? AND "來源檔案"=? LIMIT 1', (day, name)).fetchone():
                        continue
            rows = source.execute(f'SELECT * FROM {TABLE} WHERE "資料日期"=? AND "來源檔案"=?', (day, name)).fetchall()
            write_group(path, day, name, [dict(zip(columns, row)) for row in rows], schema, verify=True)
            with closing(read_connection(target)) as conn:
                actual = conn.execute(
                    f'SELECT {",".join(map(quote, columns))} FROM {TABLE} WHERE "資料日期"=? AND "來源檔案"=?', (day, name)
                ).fetchall()
            if Counter(rows) != Counter(actual):
                raise RuntimeError(f"{day} {name} 轉檔核對失敗，原始資料庫已保留")
            copied += len(rows)
    # The verified backup remains local; Git keeps the previous committed version too.
    legacy.unlink()
    return {"migrated": True, "rows": copied, "backup": str(backup)}


def latest_date(path: Path) -> str | None:
    for filename in reversed(database_paths(path)):
        with closing(read_connection(filename)) as conn:
            value = conn.execute(f'SELECT MAX("資料日期") FROM {TABLE}').fetchone()[0]
            if value:
                return value
    return None


def prune_history(path: Path) -> str | None:
    latest = latest_date(path)
    if not latest:
        return None
    cutoff = cutoff_date(latest)
    for filename in database_paths(path):
        with closing(read_connection(filename)) as conn:
            oldest, newest = conn.execute(f'SELECT MIN("資料日期"), MAX("資料日期") FROM {TABLE}').fetchone()
        if newest and newest < cutoff:
            filename.unlink()
        elif oldest and oldest < cutoff:
            with closing(sqlite3.connect(filename)) as conn:
                with conn:
                    conn.execute(f'DELETE FROM {TABLE} WHERE "資料日期" < ?', (cutoff,))
                conn.execute("VACUUM")
    return cutoff


def check_sizes(path: Path) -> list[str]:
    warnings = []
    for filename in database_paths(path):
        if filename.stat().st_size >= 20 * 1024 * 1024:
            message = f"注意：{filename.name} 已達 {filename.stat().st_size / 1024**2:.1f} MiB，接近網頁上傳單檔 25 MiB 上限。"
            print(message)
            warnings.append(message)
    return warnings


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="備份並將舊資料庫轉為每月歷史檔")
    parser.add_argument("--db", type=Path, default=Path("data/stock_selector.db"))
    args = parser.parse_args()
    print(migrate_legacy(args.db))
    check_sizes(args.db)
