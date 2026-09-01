"""Import XQ CSV exports into this project's own SQLite history database."""

from __future__ import annotations

import csv
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
XQ_DIR = PROJECT_ROOT / "XQ"
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "stock_selector.db"
STRENGTH_PATH = DATA_DIR / "market_strength.csv"
TABLE_NAME = "xq_history"

CANONICAL_COLUMNS = [
    "序號", "代碼", "商品", "成交", "漲幅%", "總量", "歐奈爾RS評分(1-99)",
    "距最高收盤跌幅(%)", "產業", "細產業", "所有細產業", "近5日漲幅(%)",
    "近10日漲幅(%)", "近20日漲幅(%)", "月線斜率(%)", "5日籌碼集中度(%)",
    "10日籌碼集中度(%)", "20日籌碼集中度(%)", "布林通道位階",
]
METADATA_COLUMNS = ["資料日期", "來源檔案", "來源標題", "來源順位", "匯入時間"]
NUMERIC_COLUMNS = {
    "序號", "成交", "漲幅%", "總量", "歐奈爾RS評分(1-99)", "距最高收盤跌幅(%)",
    "近5日漲幅(%)", "近10日漲幅(%)", "近20日漲幅(%)", "月線斜率(%)",
    "5日籌碼集中度(%)", "10日籌碼集中度(%)", "20日籌碼集中度(%)", "來源順位",
}
ALIASES = {
    "序號": ["序號", "編號"], "代碼": ["代碼", "商品代號", "證券代號"],
    "商品": ["商品", "名稱", "股票名稱"], "成交": ["成交", "收盤", "收盤價"],
    "漲幅%": ["漲幅%", "漲幅", "漲跌%"], "總量": ["總量", "成交量", "量"],
    "歐奈爾RS評分(1-99)": ["歐奈爾RS評分(1-99)", "歐奈爾RS(1-99)", "RS評分"],
    "距最高收盤跌幅(%)": ["距最高收盤跌幅(%)", "離4年內前高%", "離3年內前高%", "離2年內前高%", "離1年內前高%", "離0.5年內前高%"],
    "產業": ["產業"], "細產業": ["細產業"], "所有細產業": ["所有細產業"],
    "近5日漲幅(%)": ["近5日漲幅(%)", "近5日漲幅%", "近5日漲幅"],
    "近10日漲幅(%)": ["近10日漲幅(%)", "近10日漲幅%", "近10日漲幅"],
    "近20日漲幅(%)": ["近20日漲幅(%)", "近20日漲幅%", "近20日漲幅"],
    "月線斜率(%)": ["月線斜率(%)", "月線斜率%", "月線斜率"],
    "5日籌碼集中度(%)": ["5日籌碼集中度(%)", "5日籌碼集中度%", "5日籌碼集中度"],
    "10日籌碼集中度(%)": ["10日籌碼集中度(%)", "10日籌碼集中度%", "10日籌碼集中度"],
    "20日籌碼集中度(%)": ["20日籌碼集中度(%)", "20日籌碼集中度%", "20日籌碼集中度"],
    "布林通道位階": ["布林通道位階"],
}


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def key(value: object) -> str:
    return str(value).strip().replace("（", "(").replace("）", ")").replace("％", "%").replace(" ", "")


def text_or_none(value: object) -> str | None:
    value = str(value).strip() if value is not None else ""
    return value or None


def number_or_none(value: object) -> float | None:
    text = text_or_none(value)
    if text is None:
        return None
    try:
        return float(text.replace(",", "").replace("%", ""))
    except ValueError:
        return None


def clean_code(value: object) -> str | None:
    text = text_or_none(value)
    if text is None:
        return None
    match = re.search(r"(\d{3,6})", text)
    return match.group(1).zfill(4) if match else text


def read_csv(path: Path) -> tuple[str, list[dict[str, str]]]:
    for encoding in ("cp950", "big5", "utf-8-sig", "utf-8"):
        try:
            content = path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise RuntimeError(f"無法讀取 CSV 編碼：{path.name}")

    lines = content.splitlines()
    if len(lines) < 4:
        return content, []
    reader = csv.DictReader(lines[3:])
    rows = []
    for row in reader:
        rows.append({str(column).strip().strip('"'): value for column, value in row.items() if column})
    return content, rows


def report_date(content: str, path: Path) -> str:
    match = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", content)
    if not match:
        match = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", content)
    if match:
        year, month, day = match.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")


def normalize(rows: list[dict[str, str]], source_file: str, date_value: str) -> list[dict[str, object]]:
    imported_at = datetime.now(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds")
    normalized = []
    for order, raw in enumerate(rows, start=1):
        lookup = {key(column): value for column, value in raw.items()}
        def first(names: list[str]) -> object:
            for name in names:
                value = lookup.get(key(name))
                if text_or_none(value) is not None:
                    return value
            return None

        code = clean_code(first(ALIASES["代碼"]))
        name = text_or_none(first(ALIASES["商品"]))
        if not code and not name:
            continue
        record: dict[str, object] = {}
        for column in CANONICAL_COLUMNS:
            value = first(ALIASES[column])
            record[column] = clean_code(value) if column == "代碼" else (number_or_none(value) if column in NUMERIC_COLUMNS else text_or_none(value))
        record.update({"資料日期": date_value, "來源檔案": source_file, "來源標題": Path(source_file).stem, "來源順位": order, "匯入時間": imported_at})
        known = {key(alias) for aliases in ALIASES.values() for alias in aliases}
        for column, value in raw.items():
            if key(column) not in known and column not in METADATA_COLUMNS:
                record[column] = text_or_none(value)
        normalized.append(record)
    return normalized


def ensure_columns(connection: sqlite3.Connection, rows: list[dict[str, object]]) -> list[str]:
    connection.execute(f"CREATE TABLE IF NOT EXISTS {TABLE_NAME} (\"資料日期\" TEXT, \"來源檔案\" TEXT)")
    existing = {item[1] for item in connection.execute(f"PRAGMA table_info({TABLE_NAME})")}
    columns = list(dict.fromkeys([column for row in rows for column in row]))
    for column in columns:
        if column not in existing:
            sql_type = "REAL" if column in NUMERIC_COLUMNS else "TEXT"
            connection.execute(f"ALTER TABLE {TABLE_NAME} ADD COLUMN {quote(column)} {sql_type}")
    return columns


def rebuild_strength_history(connection: sqlite3.Connection) -> None:
    rows = connection.execute(f"SELECT * FROM {TABLE_NAME} ORDER BY \"資料日期\"").fetchall()
    columns = [item[1] for item in connection.execute(f"PRAGMA table_info({TABLE_NAME})")]
    records = [dict(zip(columns, row)) for row in rows]
    dates = sorted({str(record.get("資料日期")) for record in records if record.get("資料日期")})
    output = []
    for date_value in dates:
        rs_records = [record for record in records if record.get("資料日期") == date_value and record.get("來源檔案") == "RS加權.csv"]
        main_records = [record for record in records if record.get("資料日期") == date_value and record.get("來源檔案") == "主力買向上.csv"]
        scores = [number_or_none(record.get("歐奈爾RS評分(1-99)")) for record in rs_records]
        scores = [score for score in scores if score is not None]
        output.append({"策略": "RS加權", "日期": date_value, "RS 80以上": sum(score >= 80 for score in scores), "RS 85以上": sum(score >= 85 for score in scores), "RS 90以上": sum(score >= 90 for score in scores), "RS 95以上": sum(score >= 95 for score in scores), "主力買向上家數": len(main_records) if main_records else ""})
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with STRENGTH_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["策略", "日期", "RS 80以上", "RS 85以上", "RS 90以上", "RS 95以上", "主力買向上家數"])
        writer.writeheader()
        writer.writerows(output)


def main() -> None:
    XQ_DIR.mkdir(exist_ok=True)
    files = sorted(XQ_DIR.glob("*.csv"), key=lambda item: item.name.lower())
    if not files:
        raise SystemExit(f"找不到 CSV。請將 XQ 選股檔放入：{XQ_DIR}")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    imported: list[tuple[str, str, int]] = []
    with sqlite3.connect(DB_PATH) as connection:
        for path in files:
            content, raw_rows = read_csv(path)
            date_value = report_date(content, path)
            rows = normalize(raw_rows, path.name, date_value)
            if not rows:
                print(f"略過 {path.name}：沒有可匯入的股票資料")
                continue
            columns = ensure_columns(connection, rows)
            connection.execute(f"DELETE FROM {TABLE_NAME} WHERE \"資料日期\" = ? AND \"來源檔案\" = ?", (date_value, path.name))
            placeholders = ", ".join("?" for _ in columns)
            sql = f"INSERT INTO {TABLE_NAME} ({', '.join(quote(column) for column in columns)}) VALUES ({placeholders})"
            connection.executemany(sql, [[row.get(column) for column in columns] for row in rows])
            imported.append((path.name, date_value, len(rows)))
        latest = connection.execute(f"SELECT MAX(\"資料日期\") FROM {TABLE_NAME}").fetchone()[0]
        if latest:
            cutoff = (datetime.fromisoformat(latest) - timedelta(days=365)).strftime("%Y-%m-%d")
            connection.execute(f"DELETE FROM {TABLE_NAME} WHERE \"資料日期\" < ?", (cutoff,))
        rebuild_strength_history(connection)
        connection.commit()
    if not imported:
        raise SystemExit("沒有匯入任何資料，請確認 CSV 格式與前三行 XQ 標頭。")
    print(f"已更新新專案資料庫：{DB_PATH}")
    for source_file, date_value, count in imported:
        print(f"  {source_file}｜{date_value}｜{count} 筆")


if __name__ == "__main__":
    main()
