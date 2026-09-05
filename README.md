# 台股籌碼與估值工作台

這個分支包含兩個功能：

1. 台股每日市場狀態：整合外資現貨、外資臺股期貨未平倉、融資餘額與加權指數確認。
2. 個股估值：以預估 EPS 與歷史本益比 20/50/80 分位數顯示估值區間。

## 資料來源與計算基礎

| 資料 | 來源 | 儲存單位 |
|---|---|---|
| 外資現貨買賣差額 | TWSE `BFI82U` | 新臺幣元 |
| 集中市場融資餘額 | TWSE `MI_MARGN` | 新臺幣元 |
| 外資臺股期貨未平倉 | TAIFEX OpenAPI | 口 |
| 加權指數價格確認 | Yahoo Finance `^TWII` | 指數點 |

市場狀態沿用既定雙軸規則：期貨絕對部位分界為 -80K、-65K、-50K、-40K、-30K，並加入近3日減空；現貨檢查單日 -300億元、3日與5日累計；融資檢查 5,300、5,200、5,000億元。`反轉形成` 與 `強多頭` 仍須通過現貨、均線與融資確認，不會只憑單一指標判定。

## 本機啟動

後端：

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

前端（另一個終端機）：

```bash
cd frontend
npm ci
npm start
```

前端預設呼叫 `http://127.0.0.1:5001/api`。部署時可設定 `REACT_APP_API_URL`。

第一次進入首頁請按「取得最新盤後資料」。OpenAPI 僅提供最新交易日，因此3日與5日條件會隨每日快照逐步累積；系統不會用虛構資料補齊歷史。

## API

- `POST /api/market/refresh`：從官方來源取得最新一致交易日並新增或更新快照。
- `GET /api/market/dashboard?days=60`：取得最新判定、計算依據、觀察條件與歷史資料。
- `GET /api/stock_history/<ticker>`：取得個股歷史價格。
- `GET /api/analyze/<ticker>`：執行個股估值。

## 測試

```bash
cd backend
python -m unittest test_market_data.py
```

判定是研究與觀察工具，不代表投資建議。若任一官方來源日期不同步，更新 API 會明確回報錯誤，不會混用不同交易日。
