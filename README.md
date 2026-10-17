# 310 選股靜態網站

這是與 `C:\stock_selector` 完全分離的新架構。原有 Streamlit 專案不會被修改。

## 每日更新資料

1. 將 XQ 匯出的 CSV 放入 `XQ` 資料夾。
2. 雙擊 `更新310選股資料.bat`；它會依 CSV 資料日期，自動建立或更新 `data\history\YYYY-MM.db`。
3. 需要查看網站時，雙擊 `開啟310選股靜態網站.bat`。它會先更新資料，再開啟或重用網站伺服器。

原始 CSV 不會被刪除。每月資料庫保留最近五個日曆年的紀錄，並輸出：

- `site/data/index.json`：可選日期、策略與檔案索引。
- `site/data/snapshots/YYYY-MM-DD/*.json`：每個日期、每個策略各一份欄位式 JSON。

歷史資料依月份保存在 `data/history/`，以最新資料日期回推五個日曆年（含閏年）。網頁只下載使用者選取的日期與策略 JSON。跨月及補傳舊日期時均自動選擇正確月份；重新上傳同日同策略會更新，不會重複累積。

## 本機預覽

靜態網站必須經由網站伺服器開啟，不能直接雙擊 `index.html`。在此資料夾執行：

```powershell
& "C:\stock_selector\.venv\Scripts\python.exe" -m http.server 8000 --directory site
```

接著開啟 `http://localhost:8000`。

部署時，將 `site` 資料夾內容上傳即可。

## GitHub 網頁自動更新

此專案包含 `.github/workflows/update-and-deploy.yml`。在 GitHub Pages 設定將來源選為 `GitHub Actions` 後，只要在 GitHub 網頁上覆蓋 `XQ` 資料夾內的四個 CSV 並提交，GitHub 就會自動：

1. 更新本專案的 SQLite 歷史資料庫。
2. 重建 `site/data` 的 JSON 與市場氣氛趨勢資料。
3. 部署 `site` 資料夾到 GitHub Pages。

首次建立 GitHub repository 時，請一併上傳 `data/history/`，保留現有歷史。既有倉庫升級時只上傳程式與 workflow，不要用本機資料覆蓋線上資料；第一次執行會備份並核對原有 `data/stock_selector.db`，轉成月份檔案後才移除單一資料庫。備份在 `data/backups/`，不提交到 GitHub。轉檔失敗時保留原始資料庫，可重試。

此外，GitHub Actions 每天台灣時間 08:15 會單獨核對期交所股票期貨標的，即使沒有上傳 XQ CSV 也會執行。定時執行只更新 `site/data/stock_futures.json` 並重新部署網站，不會匯入 CSV 或改寫選股歷史。網頁上的股票期貨名單核對時間與選股資料日期分開顯示；核對失敗時保留上次成功名單並顯示警示。GitHub 的排程可能延遲，不保證準點。
