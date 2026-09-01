# 310 選股靜態網站

這是與 `C:\stock_selector` 完全分離的新架構。原有 Streamlit 專案不會被修改。

## 每日更新資料

1. 將 XQ 匯出的 CSV 放入 `XQ` 資料夾。
2. 雙擊 `更新310選股資料.bat`；它會建立並更新本專案自己的 `data\stock_selector.db`。
3. 需要查看網站時，雙擊 `開啟310選股靜態網站.bat`。它會先更新資料，再開啟或重用網站伺服器。

原始 CSV 不會被刪除。資料庫會保留最近 365 天，並輸出：

- `site/data/index.json`：可選日期、策略與檔案索引。
- `site/data/snapshots/YYYY-MM-DD/*.json`：每個日期、每個策略各一份欄位式 JSON。

目前先保留最近 365 個日曆天內的資料。未來靜態網頁只需下載使用者選取的日期與策略 JSON。

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

首次建立 GitHub repository 時，請一併上傳 `data/stock_selector.db`，這樣網頁版會保留目前已補入的歷史資料。
